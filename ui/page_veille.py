# -*- coding: utf-8 -*-
"""Page 🏢 Veille : entreprises suivies, lancement, récap, fiche.

Écrite hors de `app_advanced.py`, déjà très long. N'ouvre jamais LinkedIn
elle-même : elle appelle le moteur (`veille.lancer_passage`), le même que le
réveil programmé de la livraison 3.
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import veille
from config import ScraperConfig
from ui.invitations import bloc_recuperer_inviter
from utils.veille_regles import (FAMILLES, PAGES_MAX, PAGES_MIN, ReglagesVeille, charger_reglages,
                                 nom_depuis_lien, resume_fiche, sauver_reglages)
from veille_store import VeilleStore

_VISITE = "derniere_visite_veille.txt"
_MOTIF_LIEN = re.compile(r"^https?://([a-z]+\.)?linkedin\.com/company/[^/?#]+", re.I)

_CAUSES = {
    "termine": "Passage terminé.",
    "budget": "Budget de pages du jour atteint : les entreprises restantes passeront en tête la prochaine fois.",
    "occupe": "Une autre session LinkedIn était en cours.",
    "rien_a_faire": "Aucune entreprise à passer.",
    "erreur": "Le passage s'est interrompu sur une erreur.",
    # « interrompu » : phrase du moteur, via MESSAGES_ARRET.
    # Mêmes phrases que le moteur : voir `_afficher_passage`, qui retire la
    # ligne d'erreur identique.
    **veille.MESSAGES_ARRET,
}

# Libellés lisibles des champs de la fiche ; un champ inconnu garde son nom.
_CHAMPS = {"taille": "Taille", "secteur": "Secteur", "siege": "Siège", "site": "Site web",
           "telephone": "Téléphone", "fondee": "Fondée en", "specialisations": "Spécialisations",
           "membres": "Membres LinkedIn", "description": "Description", "recherche": "Recherche des employés",
           "rapprochement": "Rapprochement annuaire",
           # Annuaire officiel
           "siren": "SIREN", "activite": "Activité (NAF)", "creation": "Création", "categorie": "Catégorie",
           "commune": "Commune du siège", "dirigeants": "Dirigeants", "effectif": "Effectif (INSEE)"}

_ETATS = {"a_identifier": "à identifier", "identifiee": "identifiée",
          "non_identifiee": "non identifiée — collez son lien", "illisible": "page illisible"}


def _visite_precedente(config_dir) -> str | None:
    """Date de la visite précédente, lue une fois par session.

    Lue au premier affichage puis gardée en session : sinon chaque clic (qui
    relance la page) viderait le récap qu'on est en train de lire. Le fichier,
    lui, est réécrit à chaque affichage : la session suivante doit compter à
    partir de la dernière fois où la page a réellement été vue, pas de la
    première de la session précédente.
    """
    chemin = Path(config_dir) / _VISITE
    if "veille_visite_precedente" not in st.session_state:
        try:
            precedente = chemin.read_text(encoding="utf-8").strip() or None
        except Exception:
            precedente = None
        st.session_state["veille_visite_precedente"] = precedente
    try:
        chemin.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    except Exception:
        pass
    return st.session_state["veille_visite_precedente"]


def _lien_entreprise(saisie: str):
    """Lien de page entreprise ramené à sa racine, ou None s'il n'en est pas un."""
    m = _MOTIF_LIEN.match((saisie or "").strip())
    return m.group(0).rstrip("/") + "/" if m else None


def _date_de_releve(cle: str, valeur: dict, lectures: dict) -> str:
    """Date affichée pour une information : sa dernière lecture, pas son dernier changement.

    Une valeur inchangée n'est pas réécrite ; sans cela, une fiche relue la
    veille afficherait la date de sa première lecture. Le constat de
    recherche, lui, garde la sienne : il ne vient pas de la fiche.
    """
    if cle.endswith(".recherche"):
        return valeur["releve_le"]
    return max(valeur["releve_le"], lectures.get(valeur["source"]) or "")


def _motif_non_rapprochee(fiche: dict):
    """Motif si l'annuaire n'a pas été recoupé avec LinkedIn, sinon None."""
    r = fiche.get("annuaire.rapprochement")
    if r and r["valeur"] != "rapprochée":
        return r["valeur"]
    return None


def _fiche_affichable(fiche: dict) -> dict:
    """La fiche sans les valeurs d'annuaire d'un rapprochement abandonné.

    La fiche garde la dernière valeur de chaque champ : un ancien effectif
    d'annuaire survivrait à un rapprochement devenu impossible et serait lu
    comme vrai. On ne montre alors que le motif.
    """
    if not _motif_non_rapprochee(fiche):
        return fiche
    return {k: v for k, v in fiche.items() if not k.startswith("annuaire.") or k == "annuaire.rapprochement"}


def _etat_lisible(entreprise: dict, fiche: dict) -> str:
    etat = _ETATS.get(entreprise["etat"], entreprise["etat"])
    if _motif_non_rapprochee(fiche):
        etat += " · annuaire non rapproché"
    return etat


def _date_fr(horodatage: str) -> str:
    h = horodatage or ""
    if len(h) < 16:
        return h
    return f"{h[8:10]}/{h[5:7]}/{h[:4]} {h[11:16]}"


def _afficher_passage(fin, cause, entreprises, pages, erreurs,
                      nouveaux_contacts=None) -> None:
    """Résumé d'un passage, qu'il vienne de finir ou qu'il soit relu en base.

    Une seule fonction pour les deux : le résumé enregistré ne doit pas dire
    moins que celui affiché à chaud. Les compteurs de nouveautés ne sont pas
    stockés en base : ils n'apparaissent que juste après le passage.
    """
    couvertes = f"{len(entreprises)} entreprise(s)" + (f" : {', '.join(entreprises)}" if entreprises else "")
    morceaux = [couvertes, f"{pages} page(s) LinkedIn"]
    if nouveaux_contacts is not None:
        morceaux.append(f"{nouveaux_contacts} nouveau(x) contact(s)")
    resume = (f"**Passage du {_date_fr(fin)}** — {_CAUSES.get(cause, cause)} — " + ", ".join(morceaux) + ".")
    (st.success if cause in ("termine", "rien_a_faire") else st.warning)(resume)
    # Le moteur consigne aussi la cause d'arrêt parmi les erreurs : déjà dite
    # en tête, on ne la répète pas.
    for erreur in erreurs:
        if erreur != veille.MESSAGES_ARRET.get(cause):
            st.warning(f"⚠️ {erreur}")


def _afficher_rapport(rapport) -> None:
    _afficher_passage(rapport.fin, rapport.cause, rapport.entreprises, rapport.pages, rapport.erreurs,
                      rapport.nouveaux_contacts)


def afficher_page_veille() -> None:
    chemins = st.session_state.user_paths
    store = VeilleStore(str(chemins.db_file))
    st.header("🏢 Veille entreprises")

    # ── Nouveau aujourd'hui ────────────────────────────────────────────
    st.subheader("Nouveau depuis votre dernière visite")
    nouveautes = store.nouveautes_depuis(_visite_precedente(chemins.config_dir))
    if not nouveautes["contacts"] and not nouveautes["changements"]:
        st.info("Rien de nouveau depuis votre dernière visite.")
    colonnes = {"entreprise": "Entreprise", "famille": "Famille", "nom": "Nom", "poste": "Intitulé",
                 "degre": "Degré", "url": "Lien"}
    # « Autre » : trouvés par la recherche mais hors des familles visées. Ni
    # dans le tableau d'invitation, ni comptés dans le coup d'œil.
    vises = [c for c in nouveautes["contacts"] if c.get("famille") != "Autre"]
    autres = [c for c in nouveautes["contacts"] if c.get("famille") == "Autre"]
    if vises:
        df = pd.DataFrame(vises)[list(colonnes)]
        df.insert(0, "Inviter", False)
        choix = st.data_editor(
            df.rename(columns=colonnes),
            key="veille_recap", hide_index=True, width="stretch",
            disabled=list(colonnes.values()),
        )
        urls = list(choix.loc[choix["Inviter"], "Lien"])
        if urls:
            bloc_recuperer_inviter(urls, "veille", nom_export="veille")
    if autres:
        with st.expander(f"Autres postes trouvés ({len(autres)}) — hors des familles visées"):
            st.dataframe(pd.DataFrame(autres)[list(colonnes)].rename(columns=colonnes),
                         hide_index=True, width="stretch")
    for c in nouveautes["changements"]:
        source = "LinkedIn" if c["source"] == "linkedin" else "Annuaire officiel"
        st.markdown(f"- **{c['entreprise']}** — {_CHAMPS.get(c['champ'], c['champ'])} : {c['avant']} → "
                    f"**{c['apres']}** ({source}, {c['releve_le'][:10]})")

    # Le rapport d'un passage qui vient de finir est montré une fois, à la
    # place du résumé enregistré (même passage, avec ses compteurs en plus).
    rapport = st.session_state.pop("veille_rapport", None)
    dernier = store.dernier_passage()
    if rapport is not None and rapport.cause in ("occupe", "rien_a_faire"):
        # Un refus n'est pas un passage : il est dit une fois, et le résumé
        # du dernier vrai passage reste en dessous.
        st.warning(" ".join([_CAUSES[rapport.cause]] + list(rapport.erreurs)))
        rapport = None
    if rapport is not None:
        _afficher_rapport(rapport)
    elif dernier:
        _afficher_passage(dernier["fin"], dernier["cause"], dernier["entreprises"], dernier["pages"],
                          dernier["erreurs"])

    # ── Lancer ─────────────────────────────────────────────────────────
    st.markdown("---")
    # Même réglage que celui que lit le scraper au lancement de Chrome.
    # Quitter la page ou la recharger arrête la veille en cours (Streamlit
    # interrompt le script) : il faut le dire avant, dans les deux modes.
    if ScraperConfig.HEADLESS:
        st.caption("La veille travaille en arrière-plan quelques minutes : aucune fenêtre ne s'ouvre. "
                   "Gardez cette page ouverte jusqu'au rapport : la quitter arrête la veille.")
    else:
        st.caption("Une fenêtre Chrome va s'ouvrir et travailler quelques minutes : c'est normal, "
                   "LinkedIn l'exige. Laissez-la faire, et gardez cette page ouverte jusqu'au rapport : "
                   "la quitter arrête la veille.")
    if st.button("🏢 Lancer la veille", type="primary", key="veille_lancer"):
        if not st.session_state.get("global_cookie"):
            st.error("❌ Cookie manquant — renseignez votre cookie li_at dans la page Recherche.")
        else:
            with st.status("Veille en cours…", expanded=True) as statut:
                rapport = veille.lancer_passage(chemins, st.session_state.global_cookie,
                                                proxy=st.session_state.get("user_proxy"),
                                                status=lambda t: statut.update(label=t))
                statut.update(label="Veille terminée", state="complete")
            # Le récap, en haut, a été calculé avant le passage : on relance la
            # page pour qu'il montre ce que la veille vient de trouver.
            st.session_state["veille_rapport"] = rapport
            st.rerun()

    # ── Mes entreprises ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Mes entreprises")
    entreprises = store.entreprises()
    if entreprises:
        st.dataframe(pd.DataFrame([{
            "Entreprise": e["nom"], "État": _etat_lisible(e, store.fiche(e["id"])),
            "Dernier passage": (e["derniere_veille"] or "jamais")[:10], "Contacts": e["nb_contacts"],
        } for e in entreprises]), hide_index=True, width="stretch")
    else:
        st.info("Aucune entreprise suivie : ajoutez-en ci-dessous.")

    col1, col2 = st.columns(2)
    with col1:
        proposees = [s for s in store.societes_du_fichier()
                     if s.lower() not in {e["nom"].lower() for e in entreprises}]
        depuis_fichier = st.multiselect("Depuis mon fichier", proposees, key="veille_depuis_fichier")
        if st.button("Ajouter la sélection", key="veille_ajouter_fichier"):
            noms = [n for n in depuis_fichier if n.strip()]
            if not noms:
                st.error("❌ Choisissez au moins une société dans la liste.")
            else:
                for nom in noms:
                    store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"))
                st.rerun()
    with col2:
        lien = st.text_input("Ou le lien de sa page LinkedIn", key="veille_lien",
                             placeholder="https://www.linkedin.com/company/…")
        if st.button("Ajouter", key="veille_ajouter_lien"):
            url = _lien_entreprise(lien)
            if not url:
                st.error("❌ Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
            else:
                nom = nom_depuis_lien(url)
                if not nom:
                    st.error("❌ Impossible de lire le nom de l'entreprise dans ce lien : "
                             "copiez l'adresse complète de sa page LinkedIn.")
                else:
                    store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"), url_linkedin=url)
                    st.rerun()

    if entreprises:
        a_retirer = st.selectbox("Retirer une entreprise", ["—"] + [e["nom"] for e in entreprises],
                                 key="veille_retirer")
        if a_retirer != "—":
            st.caption("Retirer supprime sa fiche, ses contacts suivis ; "
                       "les profils restent dans l'Historique.")
        if a_retirer != "—" and st.button(f"Retirer {a_retirer}", key="veille_btn_retirer"):
            store.retirer_entreprise(next(e["id"] for e in entreprises if e["nom"] == a_retirer))
            st.rerun()

        # ── Fiche ──────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Fiche entreprise")
        nom = st.selectbox("Entreprise", [e["nom"] for e in entreprises], key="veille_fiche")
        e = next(x for x in entreprises if x["nom"] == nom)
        fiche_complete = store.fiche(e["id"])
        motif = _motif_non_rapprochee(fiche_complete)
        fiche = _fiche_affichable(fiche_complete)
        contacts = store.contacts(e["id"])
        lectures = store.lectures(e["id"])
        st.markdown(f"**En un coup d'œil** — {resume_fiche(fiche, contacts, st.session_state.get('veille_visite_precedente'))}")
        if not fiche:
            st.info("Pas encore de fiche : elle sera remplie au prochain passage de la veille.")
        else:
            st.dataframe(pd.DataFrame([{
                "Information": _CHAMPS.get(cle.split(".", 1)[1], cle.split(".", 1)[1]), "Valeur": v["valeur"],
                "Source": "LinkedIn" if v["source"] == "linkedin" else "Annuaire officiel",
                "Relevé le": _date_de_releve(cle, v, lectures)[:10]} for cle, v in fiche.items()]),
                hide_index=True, width="stretch")
        # Coller le lien sur la fiche, plutôt que par « Ajouter » : ce dernier
        # créerait une seconde entreprise, nommée d'après l'adresse.
        non_identifiee = e["etat"] in ("non_identifiee", "illisible")
        if non_identifiee:
            st.warning(f"{e['nom']} n'a pas pu être identifiée sur LinkedIn : collez ci-dessous le lien de "
                       "sa page entreprise, elle sera relue au prochain passage.")
        with st.expander("🔗 Lien de sa page LinkedIn", expanded=non_identifiee):
            if e.get("url_linkedin"):
                st.caption(f"Lien actuel : {e['url_linkedin']}")
            colle = st.text_input("Lien de sa page entreprise", key=f"veille_lien_fiche_{e['id']}",
                                  placeholder="https://www.linkedin.com/company/…")
            if st.button("Enregistrer ce lien", key="veille_attacher"):
                url = _lien_entreprise(colle)
                if not url:
                    st.error("❌ Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
                else:
                    store.attacher_lien(e["id"], url)
                    st.rerun()
        if motif:
            st.caption(f"Annuaire officiel : entreprise non rapprochée ({motif}). Faute de recoupement sûr "
                       "avec LinkedIn, aucune donnée de l'annuaire n'est affichée.")
        if contacts:
            st.dataframe(pd.DataFrame(contacts)[["famille", "nom", "poste", "degre", "decouvert_le", "url"]]
                         .rename(columns={"famille": "Famille", "nom": "Nom", "poste": "Intitulé",
                                          "degre": "Degré", "decouvert_le": "Trouvé le", "url": "Lien"}),
                         hide_index=True, width="stretch")
        elif e["derniere_veille"]:
            st.caption(f"Aucun contact trouvé au passage du {e['derniere_veille'][:10]}.")

    # ── Réglages ───────────────────────────────────────────────────────
    with st.expander("⚙️ Réglages de la veille"):
        r = charger_reglages(chemins.config_dir)
        familles = st.multiselect("Familles de postes", list(FAMILLES), default=r.familles, key="veille_familles")
        libres = st.text_input("Intitulés en plus (séparés par des virgules)",
                               value=", ".join(r.intitules_libres), key="veille_libres")
        pages = st.number_input("Pages LinkedIn par jour pour la veille", min_value=PAGES_MIN,
                                max_value=PAGES_MAX, value=r.pages_par_jour, key="veille_pages",
                                help="Chaque page « À propos » ou de résultats compte pour une. "
                                     "20 par défaut : environ six entreprises par matin.")
        if st.button("Enregistrer les réglages", key="veille_enregistrer"):
            if not familles and not libres.strip():
                st.error("❌ Cochez au moins une famille ou saisissez un intitulé.")
            else:
                sauver_reglages(chemins.config_dir, ReglagesVeille(
                    familles, [t.strip() for t in libres.split(",") if t.strip()], int(pages)))
                st.success("✅ Réglages enregistrés.")
