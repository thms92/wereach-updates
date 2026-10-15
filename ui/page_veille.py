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
from ui.invitations import bloc_recuperer_inviter
from utils.veille_regles import (FAMILLES, PAGES_MAX, PAGES_MIN, ReglagesVeille, charger_reglages,
                                 resume_fiche, sauver_reglages)
from veille_store import VeilleStore

_VISITE = "derniere_visite_veille.txt"
_MOTIF_LIEN = re.compile(r"^https?://([a-z]+\.)?linkedin\.com/company/[^/?#]+", re.I)

_CAUSES = {
    "termine": "Passage terminé.",
    "budget": "Budget de pages du jour atteint : les entreprises restantes passeront en tête la prochaine fois.",
    "cookie": "Cookie LinkedIn invalide ou expiré.",
    "deconnecte": "LinkedIn a demandé de se reconnecter : passage interrompu.",
    "securite": ("LinkedIn a signalé une activité inhabituelle : veille arrêtée par prudence. "
                 "Réessayez plus tard."),
    "occupe": "Une autre session LinkedIn était en cours.",
    "rien_a_faire": "Aucune entreprise à passer.",
    "erreur": "Le passage s'est interrompu sur une erreur.",
}

# Libellés lisibles des champs de la fiche ; un champ inconnu garde son nom.
_CHAMPS = {"taille": "Taille", "secteur": "Secteur", "siege": "Siège", "site": "Site web",
           "telephone": "Téléphone", "fondee": "Fondée en", "specialisations": "Spécialisations",
           "membres": "Membres LinkedIn", "description": "Description", "recherche": "Recherche des employés",
           "rapprochement": "Rapprochement annuaire", "effectif": "Effectif"}

_ETATS = {"a_identifier": "à identifier", "identifiee": "identifiée",
          "non_identifiee": "non identifiée — collez son lien", "illisible": "page illisible"}


def _visite_precedente(config_dir) -> str | None:
    """Date de la visite précédente, lue une fois par session.

    Lue au premier affichage puis remplacée par maintenant : sinon chaque
    clic (qui relance la page) viderait le récap qu'on est en train de lire.
    """
    if "veille_visite_precedente" not in st.session_state:
        chemin = Path(config_dir) / _VISITE
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


def _nom_depuis_lien(url: str) -> str:
    return " ".join(url.rstrip("/").split("/")[-1].replace("-", " ").split()).title()


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


def _afficher_rapport(rapport) -> None:
    resume = (f"**{_CAUSES.get(rapport.cause, rapport.cause)}** — "
              f"{len(rapport.entreprises)} entreprise(s), {rapport.pages} page(s) LinkedIn, "
              f"{rapport.nouveaux_contacts} nouveau(x) contact(s).")
    (st.success if rapport.cause in ("termine", "rien_a_faire") else st.warning)(resume)
    for erreur in rapport.erreurs:
        st.warning(f"⚠️ {erreur}")


def afficher_page_veille() -> None:
    chemins = st.session_state.user_paths
    store = VeilleStore(str(chemins.db_file))
    st.header("🏢 Veille entreprises")

    # ── Nouveau aujourd'hui ────────────────────────────────────────────
    st.subheader("Nouveau depuis votre dernière visite")
    nouveautes = store.nouveautes_depuis(_visite_precedente(chemins.config_dir))
    if not nouveautes["contacts"] and not nouveautes["changements"] and not nouveautes["actualites"]:
        st.info("Rien de nouveau depuis votre dernière visite.")
    if nouveautes["contacts"]:
        df = pd.DataFrame(nouveautes["contacts"])[["entreprise", "famille", "nom", "poste", "degre", "url"]]
        df.insert(0, "Inviter", False)
        choix = st.data_editor(
            df.rename(columns={"entreprise": "Entreprise", "famille": "Famille", "nom": "Nom",
                               "poste": "Intitulé", "degre": "Degré", "url": "Lien"}),
            key="veille_recap", hide_index=True, use_container_width=True,
            disabled=["Entreprise", "Famille", "Nom", "Intitulé", "Degré", "Lien"],
        )
        urls = list(choix.loc[choix["Inviter"], "Lien"])
        if urls:
            bloc_recuperer_inviter(urls, "veille", nom_export="veille")
    for a in nouveautes["actualites"]:
        st.markdown(f"- 📰 **{a['entreprise']}** — {a['categorie']} : [{a['titre']}]({a['lien']}) "
                    f"· {a.get('source') or ''} · {(a.get('publie_le') or '')[:10]}")
    for c in nouveautes["changements"]:
        source = "LinkedIn" if c["source"] == "linkedin" else "Annuaire officiel"
        st.markdown(f"- **{c['entreprise']}** — {_CHAMPS.get(c['champ'], c['champ'])} : {c['avant']} → "
                    f"**{c['apres']}** ({source}, {c['releve_le'][:10]})")

    dernier = store.dernier_passage()
    if dernier:
        st.caption(f"Dernier passage : {dernier['fin'][:16].replace('T', ' ')} — "
                   f"{_CAUSES.get(dernier['cause'], dernier['cause'])}")

    # ── Lancer ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption("Une fenêtre Chrome va s'ouvrir et travailler quelques minutes : c'est normal, "
               "LinkedIn l'exige. Laissez-la faire.")
    if st.button("🏢 Lancer la veille", type="primary", key="veille_lancer"):
        if not st.session_state.get("global_cookie"):
            st.error("❌ Cookie manquant — renseignez votre cookie li_at dans la page Recherche.")
        else:
            with st.status("Veille en cours…", expanded=True) as statut:
                rapport = veille.lancer_passage(chemins, st.session_state.global_cookie,
                                                proxy=st.session_state.get("user_proxy"),
                                                status=lambda t: statut.update(label=t))
                statut.update(label="Veille terminée", state="complete")
            _afficher_rapport(rapport)

    # ── Mes entreprises ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Mes entreprises")
    entreprises = store.entreprises()
    if entreprises:
        st.dataframe(pd.DataFrame([{
            "Entreprise": e["nom"], "État": _etat_lisible(e, store.fiche(e["id"])),
            "Dernier passage": (e["derniere_veille"] or "jamais")[:10], "Contacts": e["nb_contacts"],
        } for e in entreprises]), hide_index=True, use_container_width=True)
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
            m = _MOTIF_LIEN.match((lien or "").strip())
            if not m:
                st.error("❌ Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
            else:
                url = m.group(0).rstrip("/") + "/"
                nom = _nom_depuis_lien(url)
                if not nom:
                    st.error("❌ Impossible de lire le nom de l'entreprise dans ce lien : "
                             "copiez l'adresse complète de sa page LinkedIn.")
                else:
                    store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"), url_linkedin=url)
                    st.rerun()

    if entreprises:
        a_retirer = st.selectbox("Retirer une entreprise", ["—"] + [e["nom"] for e in entreprises],
                                 key="veille_retirer")
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
        actualites = store.actualites(e["id"])
        st.markdown(f"**En un coup d'œil** — {resume_fiche(fiche, contacts, actualites, st.session_state.get('veille_visite_precedente'))}")
        if not fiche:
            st.info("Pas encore de fiche : elle sera remplie au prochain passage de la veille.")
        else:
            st.dataframe(pd.DataFrame([{
                "Information": _CHAMPS.get(cle.split(".", 1)[1], cle.split(".", 1)[1]), "Valeur": v["valeur"],
                "Source": "LinkedIn" if v["source"] == "linkedin" else "Annuaire officiel",
                "Relevé le": v["releve_le"][:10]} for cle, v in fiche.items()]),
                hide_index=True, use_container_width=True)
        if motif:
            st.caption(f"Annuaire officiel : entreprise non rapprochée ({motif}). Faute de recoupement sûr "
                       "avec LinkedIn, aucune donnée de l'annuaire n'est affichée.")
        st.markdown("**Actualité (12 derniers mois)**")
        if actualites:
            for a in actualites:
                st.markdown(f"- {a['categorie']} — [{a['titre']}]({a['lien']}) · {a.get('source') or ''} "
                            f"· {(a.get('publie_le') or '')[:10]}")
            st.caption("Classement par mots-clés, approximatif : ouvrez l'article pour juger.")
        elif e.get("derniere_actualite"):
            st.caption(f"Aucune actualité marquante trouvée (relevé du {e['derniere_actualite'][:10]}).")
        if contacts:
            st.dataframe(pd.DataFrame(contacts)[["famille", "nom", "poste", "degre", "decouvert_le", "url"]]
                         .rename(columns={"famille": "Famille", "nom": "Nom", "poste": "Intitulé",
                                          "degre": "Degré", "decouvert_le": "Trouvé le", "url": "Lien"}),
                         hide_index=True, use_container_width=True)
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
