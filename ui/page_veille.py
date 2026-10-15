# -*- coding: utf-8 -*-
"""Page 🏢 Veille : entreprises suivies, lancement, récap, fiche.

Écrite hors de `app_advanced.py`, déjà très long. N'ouvre jamais LinkedIn
elle-même : elle appelle le moteur (`veille.lancer_passage`), le même que le
réveil programmé de la livraison 3.
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import veille
from config import ScraperConfig
from ui.invitations import bloc_recuperer_inviter
from utils.veille_regles import (FAMILLES, PAGES_MAX, PAGES_MIN, ReglagesVeille, charger_reglages,
                                 nom_depuis_lien, resume_fiche, sauver_reglages)
from veille_store import VeilleStore, normaliser_degre

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
           "commune": "Commune du siège", "dirigeants": "Dirigeants", "effectif": "Effectif (INSEE)",
           # Site de l'entreprise
           "email": "Email", "lecture": "Lecture du site"}

# Coordonnées générales : à part du reste de la fiche, et nommées avec leur
# source — « Téléphone » seul ne dirait pas s'il vient de LinkedIn ou du site.
_COORDONNEES = {"linkedin.telephone": "Téléphone (LinkedIn)", "site.email": "Email (site)",
                "site.telephone": "Téléphone (site)", "site.lecture": "Lecture du site"}
_SOURCES = {"linkedin": "LinkedIn (page À propos)", "annuaire": "Annuaire officiel",
            "site": "Site de l'entreprise"}

# État des coordonnées d'un contact, quand il n'y a pas de valeur à montrer.
# Jamais de case vide : on dit pourquoi.
_HORS_RELATION = "après acceptation de l'invitation"
_RIEN_PARTAGE = "rien de partagé"
_ECHEC = "lecture impossible, nouvel essai prévu"
_A_LIRE = "à lire au prochain passage"
_NON_PARTAGE = "non partagé"
_PARTAGE = "partagé"

_COLONNES_EXPORT = ["Nom", "Intitulé", "Famille", "Degré", "Email", "Téléphone", "Statut coordonnées",
                    "Lien", "Trouvé le"]
_COLONNES_ECRAN = ["Famille", "Nom", "Intitulé", "Degré", "Email", "Téléphone", "Trouvé le", "Lien"]

# Débuts de cellule qu'Excel ou LibreOffice prendraient pour une formule.
_DEBUTS_FORMULE = ("=", "+", "-", "@", "\t", "\r")
# Un vrai numéro commence souvent par « + » : gardé tel quel, c'est du texte
# dans le classeur (xlsxwriter ne convertit pas les chaînes en nombres) et,
# dans le CSV, ses espaces l'empêchent d'être lu comme une formule valide.
_MOTIF_TELEPHONE = re.compile(r"^\+?[\d\s().\-/]+$")

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


def _lignes_coordonnees_entreprise(fiche: dict, lectures: dict) -> list:
    """Téléphone LinkedIn, email et téléphone du site, chacun avec sa source.

    Une source lue sans la donnée dit « non publié ». Un site non lisible
    est dit tel quel, et ses anciennes valeurs ne sont pas montrées : elles
    pourraient venir d'une autre adresse.
    """
    def ligne(cle, valeur, source, releve):
        return {"Information": _COORDONNEES[cle], "Valeur": valeur, "Source": _SOURCES[source],
                "Relevé le": (releve or "")[:10]}

    lignes = []
    tel = fiche.get("linkedin.telephone")
    if tel:
        lignes.append(ligne("linkedin.telephone", tel["valeur"], "linkedin",
                            _date_de_releve("linkedin.telephone", tel, lectures)))
    elif lectures.get("linkedin"):
        lignes.append(ligne("linkedin.telephone", "non publié", "linkedin", lectures["linkedin"]))
    lecture = fiche.get("site.lecture")
    if lecture and lecture["valeur"] != "site lu":
        lignes.append(ligne("site.lecture", lecture["valeur"], "site",
                            _date_de_releve("site.lecture", lecture, lectures)))
    elif lecture:
        for cle in ("site.email", "site.telephone"):
            v = fiche.get(cle)
            if v:
                lignes.append(ligne(cle, v["valeur"], "site", _date_de_releve(cle, v, lectures)))
            else:
                lignes.append(ligne(cle, "non publié", "site", lectures.get("site") or lecture["releve_le"]))
    return lignes


def _coordonnee_contact(c: dict, champ: str) -> tuple:
    """(valeur, statut) de l'email ou du téléphone d'un contact.

    La valeur n'est remplie que pour une coordonnée lue et partagée ; sinon
    le statut dit pourquoi. Hors relation, rien n'est montré, même lu un jour.
    """
    if not c.get("en_relation"):
        return "", _HORS_RELATION
    k = c.get("coordonnees")
    if k and k["partage"] == "oui":
        return k[champ] or "", _PARTAGE
    if k:
        return "", _RIEN_PARTAGE
    if c.get("echec_le"):
        return "", _ECHEC
    return "", _A_LIRE


def _cellule_ecran(valeur: str, statut: str) -> str:
    """À l'écran, jamais de case vide : la valeur, ou la raison de son absence."""
    if valeur:
        return valeur
    return _NON_PARTAGE if statut == _PARTAGE else statut


def _sans_formule(valeur, telephone: bool = False):
    if not isinstance(valeur, str) or not valeur.startswith(_DEBUTS_FORMULE):
        return valeur
    if telephone and _MOTIF_TELEPHONE.match(valeur):
        return valeur
    return "'" + valeur


def _degre_lisible(c: dict) -> str:
    degre = normaliser_degre(c.get("degre"))
    if c.get("en_relation") and degre != "1er":
        return "1er (invitation acceptée)"
    return degre or "inconnu"


def _lignes_contacts(contacts: list) -> list:
    """Une ligne par contact (`contacts_et_coordonnees`), base de l'écran et de l'export."""
    lignes = []
    for c in contacts:
        (email, statut), (tel, _) = _coordonnee_contact(c, "email"), _coordonnee_contact(c, "telephone")
        lignes.append({"Nom": c.get("nom") or "", "Intitulé": c.get("poste") or "",
                       "Famille": c.get("famille") or "", "Degré": _degre_lisible(c),
                       "Email": email, "Téléphone": tel, "Statut coordonnées": statut, "Lien": c["url"],
                       "Trouvé le": (c.get("decouvert_le") or "")[:10]})
    return lignes


def _contacts_a_afficher(contacts: list) -> pd.DataFrame:
    lignes = _lignes_contacts(contacts)
    for l in lignes:
        l["Email"] = _cellule_ecran(l["Email"], l["Statut coordonnées"])
        l["Téléphone"] = _cellule_ecran(l["Téléphone"], l["Statut coordonnées"])
    return pd.DataFrame(lignes, columns=_COLONNES_ECRAN)


def _contacts_a_exporter(contacts: list) -> pd.DataFrame:
    """L'export, exploitable par une machine : Email et Téléphone vides sauf
    coordonnée lue et partagée, la raison dans « Statut coordonnées ».

    Les textes venus de LinkedIn (nom, intitulé…) sont neutralisés : une
    cellule commençant par « = » serait exécutée comme formule à l'ouverture.
    """
    lignes = [{k: _sans_formule(v, telephone=(k == "Téléphone")) for k, v in l.items()}
              for l in _lignes_contacts(contacts)]
    return pd.DataFrame(lignes, columns=_COLONNES_EXPORT)


def _nom_export(entreprise: str, jour: str) -> str:
    """« Zéphyr & Fils SA », 2026-10-15 → contacts_zephyr-fils-sa_20261015."""
    ascii_ = unicodedata.normalize("NFKD", entreprise or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or "entreprise"
    return f"contacts_{slug}_{jour[:10].replace('-', '')}"


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
    visite = _visite_precedente(chemins.config_dir)
    nouveautes = store.nouveautes_depuis(visite)
    partages = store.coordonnees_nouvelles_depuis(visite)
    if not nouveautes["contacts"] and not nouveautes["changements"] and not partages:
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
    for p in partages:
        quoi = [f"son {n} : {p[k]}" for k, n in (("email", "email"), ("telephone", "téléphone")) if p[k]]
        st.markdown(f"- **{p['nom']}** ({p['entreprise']}) a partagé " + " et ".join(quoi)
                    + f" ({p['releve_le'][:10]})")

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
        generale = {cle: v for cle, v in fiche.items() if cle not in _COORDONNEES and not cle.startswith("site.")}
        if not generale:
            st.info("Pas encore de fiche : elle sera remplie au prochain passage de la veille.")
        else:
            st.dataframe(pd.DataFrame([{
                "Information": _CHAMPS.get(cle.split(".", 1)[1], cle.split(".", 1)[1]), "Valeur": v["valeur"],
                "Source": "LinkedIn" if v["source"] == "linkedin" else "Annuaire officiel",
                "Relevé le": _date_de_releve(cle, v, lectures)[:10]} for cle, v in generale.items()]),
                hide_index=True, width="stretch")
        st.markdown("**Coordonnées de l'entreprise**")
        coordonnees = _lignes_coordonnees_entreprise(fiche, lectures)
        if coordonnees:
            st.dataframe(pd.DataFrame(coordonnees), hide_index=True, width="stretch")
        else:
            st.caption("Pas encore relevées : le téléphone vient de sa page LinkedIn, l'email et le téléphone "
                       "de son site, lus au prochain passage de la veille.")
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
            st.markdown("**Contacts**")
            st.caption("Coordonnées : celles que la personne partage sur LinkedIn, lisibles seulement "
                       "une fois en relation (1er degré ou invitation acceptée).")
            avec_coordonnees = store.contacts_et_coordonnees(e["id"])
            st.dataframe(_contacts_a_afficher(avec_coordonnees), hide_index=True, width="stretch")
            tableau = _contacts_a_exporter(avec_coordonnees)
            fichier = _nom_export(e["nom"], datetime.now().strftime("%Y-%m-%d"))
            col_x, col_c = st.columns(2)
            with col_x:
                st.download_button(
                    "📥 Exporter en Excel",
                    data=st.session_state.export_manager.export_to_excel(tableau.to_dict("records")),
                    file_name=f"{fichier}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"veille_dl_xlsx_{e['id']}", width="stretch")
            with col_c:
                # Point-virgule et BOM : ouvert tel quel par Excel en français, accents compris.
                st.download_button(
                    "📥 Exporter en CSV", data=tableau.to_csv(index=False, sep=";").encode("utf-8-sig"),
                    file_name=f"{fichier}.csv", mime="text/csv",
                    key=f"veille_dl_csv_{e['id']}", width="stretch")
        elif e["derniere_veille"]:
            st.caption(f"Aucun contact trouvé au passage du {e['derniere_veille'][:10]} : rien à exporter.")
        else:
            st.caption("Aucun contact pour l'instant, rien à exporter : ils seront cherchés au prochain "
                       "passage de la veille.")

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
