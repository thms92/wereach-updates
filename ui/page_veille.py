# -*- coding: utf-8 -*-
"""Page Veille : nouveautés, entreprises suivies, fiche, réglages.

Une vue par métier, en onglets : ce qui est nouveau (et le lancement),
la liste suivie, la fiche d'une entreprise, les réglages. Les onglets
Streamlit exécutent tout leur contenu à chaque passage : les widgets
gardent leur état quand on change d'onglet.

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
from ui.composants import afficher_bandeau_contexte, afficher_etat_vide, pluriel, ton_budget
from ui.invitations import bloc_recuperer_inviter
from utils.budget import budget_du_jour
from utils.veille_regles import (FAMILLES, PAGES_MAX, PAGES_MIN, ReglagesVeille, charger_reglages,
                                 nom_depuis_lien, resume_fiche, sauver_reglages)
from veille_store import VeilleStore, normaliser_degre

# Lu aussi par le tableau de bord (nouveautés de la veille).
FICHIER_VISITE_VEILLE = "derniere_visite_veille.txt"
_MOTIF_LIEN = re.compile(r"^https?://([a-z]+\.)?linkedin\.com/company/[^/?#]+", re.I)

ONGLETS = ["Nouveautés", "Mes entreprises", "Fiche entreprise", "Réglages"]
_CLE_ONGLET = "veille_onglet"
_CLE_TABLEAU = "veille_tableau_entreprises"
# Génération du tableau « Mes entreprises » : changer sa clé efface la ligne
# choisie. Sans cela, la ligne restait cochée et un nouveau clic dessus (ou sur
# une autre après un retrait) n'ouvrait pas la fiche du premier coup.
_CLE_GENERATION = "_veille_tableau_generation"
_CLE_RETRAIT = "_veille_retrait_message"

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
# Phrases d'arrêt enregistrées en base par une version précédente du moteur :
# relues avec la formulation actuelle, et donc reconnues comme déjà dites.
_ANCIENS_MESSAGES = {
    "Cookie LinkedIn invalide ou expiré — renseignez un nouveau cookie li_at dans la page Recherche.":
        veille.MESSAGES_ARRET["cookie"],
}
# Caractères qui changeraient le rendu Markdown d'un texte venu de LinkedIn.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!$~|>])")
# Causes qui arrêtent la veille avant son terme : seules elles valent un avertissement.
_ARRETS = ("erreur", "cookie", "deconnecte", "securite", "interrompu")
# « Orbique : aucun profil Product / Data / IA trouvé. » (moteur, une ligne par entreprise)
_MOTIF_SANS_RESULTAT = re.compile(r"^(?P<nom>.+?) : aucun profil (?P<cibles>.+) trouvé\.$")

# Libellés lisibles des champs de la fiche ; un champ inconnu garde son nom.
_CHAMPS = {"taille": "Taille", "secteur": "Secteur", "siege": "Siège", "site": "Site web",
           "telephone": "Téléphone", "fondee": "Fondée en", "specialisations": "Spécialisations",
           "membres": "Membres LinkedIn", "description": "Description", "recherche": "Recherche des employés",
           "rapprochement": "Données légales (annuaire des entreprises)",
           # Annuaire officiel
           "siren": "SIREN", "activite": "Activité (NAF)", "creation": "Création", "categorie": "Catégorie",
           "commune": "Commune du siège", "dirigeants": "Dirigeants", "effectif": "Effectif (INSEE)",
           # Site de l'entreprise
           "email": "Email", "lecture": "Lecture du site"}

# Coordonnées générales : nommées avec leur source — « Téléphone » seul ne
# dirait pas s'il vient de LinkedIn ou du site.
_COORDONNEES = {"linkedin.telephone": "Téléphone (LinkedIn)", "site.email": "Email (site)",
                "site.telephone": "Téléphone (site)", "site.lecture": "Lecture du site"}
_SOURCES = {"linkedin": "LinkedIn (page À propos)", "annuaire": "Annuaire officiel",
            "site": "Site de l'entreprise"}

# Texte de recrutement que LinkedIn met à la place d'une vraie description.
_DESCRIPTION_GENERIQUE = re.compile(r"^\s*partagez votre profil", re.I)
_SANS_DESCRIPTION = "Description non disponible"

# État des coordonnées d'un contact, quand il n'y a pas de valeur à montrer.
# Jamais de case vide : on dit pourquoi.
_HORS_RELATION = "après acceptation de l'invitation"
_RIEN_PARTAGE = "rien de partagé"
_ECHEC = "lecture impossible, nouvel essai prévu"
_A_LIRE = "à lire au prochain passage"
_NON_PARTAGE = "non partagé"
_PARTAGE = "partagé"

# L'export garde « Degré » et ses valeurs brutes (1er, 2e…) : c'est un format
# machine. L'écran dit « Relation ».
_COLONNES_EXPORT = ["Nom", "Intitulé", "Famille", "Degré", "Email", "Téléphone", "Statut coordonnées",
                    "Lien", "Trouvé le"]
_COLONNES_ECRAN = ["Famille", "Nom", "Intitulé", "Relation", "Email", "Téléphone", "Trouvé le", "Lien"]

# Débuts de cellule qu'Excel ou LibreOffice prendraient pour une formule.
_DEBUTS_FORMULE = ("=", "+", "-", "@", "\t", "\r")
# Un vrai numéro commence souvent par « + » : gardé tel quel, c'est du texte
# dans le classeur (xlsxwriter ne convertit pas les chaînes en nombres) et,
# dans le CSV, ses espaces l'empêchent d'être lu comme une formule valide.
_MOTIF_TELEPHONE = re.compile(r"^\+?[\d\s().\-/]+$")

_ETATS = {"a_identifier": "à identifier", "identifiee": "identifiée",
          "non_identifiee": "non identifiée — collez son lien", "illisible": "page illisible"}

_LIEN_PROFIL = st.column_config.LinkColumn("Lien", display_text="Voir le profil")


def _visite_precedente(config_dir) -> str | None:
    """Date de la visite précédente, lue une fois par session.

    Lue au premier affichage puis gardée en session : sinon chaque clic (qui
    relance la page) viderait le récap qu'on est en train de lire. Le fichier,
    lui, est réécrit à chaque affichage : la session suivante doit compter à
    partir de la dernière fois où la page a réellement été vue, pas de la
    première de la session précédente.
    """
    chemin = Path(config_dir) / FICHIER_VISITE_VEILLE
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


def _jour_fr(horodatage: str) -> str:
    """« 2026-10-14T08:00:00 » → « 14/10/2026 » ; autre chose rendu tel quel."""
    h = horodatage or ""
    if len(h) < 10 or h[4] != "-" or h[7] != "-":
        return h
    return f"{h[8:10]}/{h[5:7]}/{h[:4]}"


def _date_fr(horodatage: str) -> str:
    h = horodatage or ""
    if len(h) < 16:
        return _jour_fr(h)
    return f"{h[8:10]}/{h[5:7]}/{h[:4]} {h[11:16]}"


def _valeur_lisible(cle: str, valeur: str) -> str:
    """Valeur d'un champ de fiche telle qu'on la lit à l'écran (jamais en base)."""
    if cle == "annuaire.rapprochement":
        # Le motif d'un échec est dit en légende sous le tableau, en entier.
        return "vérifiées" if valeur == "rapprochée" else "non vérifiées"
    return valeur


def _description_lisible(valeur: str) -> str:
    if not (valeur or "").strip() or _DESCRIPTION_GENERIQUE.match(valeur):
        return _SANS_DESCRIPTION
    return valeur


def _lignes_coordonnees_entreprise(fiche: dict, lectures: dict) -> list:
    """Téléphone LinkedIn, email et téléphone du site, chacun avec sa source.

    Une source lue sans la donnée dit « non publié ». Un site non lisible
    est dit tel quel, et ses anciennes valeurs ne sont pas montrées : elles
    pourraient venir d'une autre adresse.
    """
    def ligne(cle, valeur, source, releve):
        return {"Information": _COORDONNEES[cle], "Valeur": valeur, "Source": _SOURCES[source],
                "Relevé le": _jour_fr(releve)}

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


def _lignes_fiche(fiche: dict, lectures: dict) -> list:
    """La fiche et les coordonnées générales, en un seul tableau.

    La description n'y figure pas : trop longue pour une cellule, elle est
    affichée à part.
    """
    lignes = []
    for cle, v in fiche.items():
        if cle in _COORDONNEES or cle.startswith("site.") or cle == "linkedin.description":
            continue
        champ = cle.split(".", 1)[1]
        lignes.append({"Information": _CHAMPS.get(champ, champ), "Valeur": _valeur_lisible(cle, v["valeur"]),
                       "Source": "LinkedIn" if v["source"] == "linkedin" else "Annuaire officiel",
                       "Relevé le": _jour_fr(_date_de_releve(cle, v, lectures))})
    return lignes + _lignes_coordonnees_entreprise(fiche, lectures)


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
    """Degré brut, pour l'export : « 1er », « 2e », « 1er (invitation acceptée) », « inconnu »."""
    degre = normaliser_degre(c.get("degre"))
    if c.get("en_relation") and degre != "1er":
        return "1er (invitation acceptée)"
    return degre or "inconnu"


def _relation_lisible(c: dict) -> str:
    """Le degré dit à l'écran : « 1er niveau », « 2e niveau »… ou « inconnue »."""
    degre = normaliser_degre(c.get("degre"))
    if c.get("en_relation") and degre != "1er":
        return "1er niveau (invitation acceptée)"
    return f"{degre} niveau" if degre else "inconnue"


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
    for c, l in zip(contacts, lignes):
        l["Email"] = _cellule_ecran(l["Email"], l["Statut coordonnées"])
        l["Téléphone"] = _cellule_ecran(l["Téléphone"], l["Statut coordonnées"])
        l["Relation"] = _relation_lisible(c)
        l["Trouvé le"] = _jour_fr(l["Trouvé le"])
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
        etat += " · données légales non vérifiées"
    return etat


def _cibles_lisibles(cibles: str) -> str:
    """« Product / Data / IA » → « Product, Data ou IA »."""
    morceaux = [m.strip() for m in cibles.split(" / ") if m.strip()]
    if len(morceaux) < 2:
        return cibles
    return ", ".join(morceaux[:-1]) + " ou " + morceaux[-1]


def _md(texte) -> str:
    """Texte venu de LinkedIn ou de l'annuaire, rendu tel quel dans du Markdown."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", str(texte if texte is not None else ""))


def _erreurs_actuelles(erreurs) -> list:
    """Les erreurs d'un passage, les anciennes phrases du moteur remises à jour."""
    return [_ANCIENS_MESSAGES.get(e, e) for e in erreurs or []]


def _texte_passage(fin, cause, entreprises, pages, erreurs, nouveaux_contacts=None) -> tuple:
    """(ton, texte) du résumé d'un passage : un seul message, qui dit tout.

    Les entreprises sans résultat tiennent sur une ligne d'information ; les
    autres points sont listés dessous. Un avertissement est réservé à un
    arrêt avant terme.
    """
    couvertes = pluriel(len(entreprises), "entreprise") + (f" : {', '.join(entreprises)}" if entreprises else "")
    morceaux = [couvertes, pluriel(pages, "page LinkedIn", "pages LinkedIn")]
    if nouveaux_contacts is not None:
        morceaux.append(pluriel(nouveaux_contacts, "nouveau contact", "nouveaux contacts"))
    lignes = [f"**Passage du {_date_fr(fin)}** — {_CAUSES.get(cause, cause)} — " + ", ".join(morceaux) + "."]
    # Le moteur consigne aussi la cause d'arrêt parmi les erreurs : déjà dite
    # en tête, on ne la répète pas.
    restantes = [e for e in _erreurs_actuelles(erreurs) if e != veille.MESSAGES_ARRET.get(cause)]
    sans_resultat, cibles, autres = [], "", []
    for e in restantes:
        m = _MOTIF_SANS_RESULTAT.match(e)
        if m:
            sans_resultat.append(m.group("nom"))
            cibles = cibles or m.group("cibles")
        else:
            autres.append(e)
    if sans_resultat:
        lignes.append(f"Aucun profil {_cibles_lisibles(cibles)} trouvé chez : {', '.join(sans_resultat)}.")
    if autres:
        lignes.append("À vérifier :\n" + "\n".join(f"- {e}" for e in autres))
    if cause in _ARRETS:
        ton = "attention"
    elif restantes or cause == "budget":
        ton = "neutre"
    else:
        ton = "ok"
    return ton, "\n\n".join(lignes)


def _afficher_passage(fin, cause, entreprises, pages, erreurs,
                      nouveaux_contacts=None) -> None:
    """Résumé d'un passage, qu'il vienne de finir ou qu'il soit relu en base.

    Une seule fonction pour les deux : le résumé enregistré ne doit pas dire
    moins que celui affiché à chaud. Les compteurs de nouveautés ne sont pas
    stockés en base : ils n'apparaissent que juste après le passage.
    """
    ton, texte = _texte_passage(fin, cause, entreprises, pages, erreurs, nouveaux_contacts)
    {"attention": st.warning, "neutre": st.info, "ok": st.success}[ton](texte)


def _afficher_rapport(rapport) -> None:
    _afficher_passage(rapport.fin, rapport.cause, rapport.entreprises, rapport.pages, rapport.erreurs,
                      rapport.nouveaux_contacts)


# ── Rappels (callbacks) : exécutés avant le script, ils peuvent écrire l'état des widgets ──

def _cle_tableau() -> str:
    """Clé actuelle du tableau « Mes entreprises » (voir `_CLE_GENERATION`)."""
    generation = st.session_state.get(_CLE_GENERATION, 0)
    return _CLE_TABLEAU if not generation else f"{_CLE_TABLEAU}_{generation}"


def _vider_selection_tableau() -> None:
    """Nouvelle clé pour le tableau : il revient sans ligne choisie."""
    st.session_state[_CLE_GENERATION] = st.session_state.get(_CLE_GENERATION, 0) + 1


def _ouvrir_fiche_selectionnee() -> None:
    """Une ligne choisie dans « Mes entreprises » ouvre sa fiche.

    La sélection est aussitôt effacée : au retour sur l'onglet, un clic sur
    n'importe quelle ligne, la même comprise, ouvre de nouveau sa fiche.
    """
    etat = st.session_state.get(_cle_tableau()) or {}
    lignes = (etat.get("selection") or {}).get("rows") or []
    noms = st.session_state.get("_veille_noms_tableau") or []
    if lignes and lignes[0] < len(noms):
        st.session_state["veille_fiche"] = noms[lignes[0]]
        st.session_state[_CLE_ONGLET] = "Fiche entreprise"
    _vider_selection_tableau()


def _retirer(db_file: str, entreprise_id: int, nom: str) -> None:
    # Le bouton est désactivé sans la case ; vérifié encore ici, au cas où.
    if not st.session_state.get(f"veille_retirer_confirme_{entreprise_id}"):
        return
    VeilleStore(db_file).retirer_entreprise(entreprise_id)
    st.session_state["veille_retirer"] = "—"
    st.session_state.pop(f"veille_retirer_confirme_{entreprise_id}", None)
    if st.session_state.get("veille_fiche") == nom:
        st.session_state.pop("veille_fiche", None)
    # Les lignes ont bougé : une sélection gardée viserait une autre entreprise.
    _vider_selection_tableau()
    st.session_state[_CLE_RETRAIT] = f"{nom} retirée de la veille."


# ── Bandeau ──────────────────────────────────────────────────────────────

def _afficher_bandeau(chemins, entreprises: list, dernier) -> None:
    puces = [(pluriel(len(entreprises), "entreprise suivie", "entreprises suivies"), "neutre"),
             (f"Dernier passage : {_date_fr(dernier['fin'])}" if dernier else "Veille jamais lancée", "neutre")]
    try:
        b = budget_du_jour(chemins.config_dir)
        puces.append((f"Invitations du jour : {b.utilisees}/{b.plafond}", ton_budget(b.utilisees, b.plafond)))
    except Exception:
        pass
    afficher_bandeau_contexte("Chaque jour, We.Reach repère les personnes Product, Data et IA de vos "
                              "entreprises cibles.", puces=puces)


# ── Onglet Nouveautés ────────────────────────────────────────────────────

def _onglet_nouveautes(store, chemins, entreprises, dernier) -> None:
    st.header("Nouveau depuis votre dernière visite", anchor=False)
    visite = _visite_precedente(chemins.config_dir)
    nouveautes = store.nouveautes_depuis(visite)
    partages = store.coordonnees_nouvelles_depuis(visite)
    rien = not nouveautes["contacts"] and not nouveautes["changements"] and not partages
    if rien and not entreprises:
        afficher_etat_vide("Aucune entreprise suivie",
                           "Ajoutez des entreprises dans l'onglet Mes entreprises, puis lancez la veille.")
    elif rien:
        st.info("Rien de nouveau depuis votre dernière visite.")
    colonnes = {"entreprise": "Entreprise", "famille": "Famille", "nom": "Nom", "poste": "Intitulé",
                "relation": "Relation", "url": "Lien"}
    # « Autre » : trouvés par la recherche mais hors des familles visées. Ni
    # dans le tableau d'invitation, ni comptés dans le coup d'œil.
    vises = [dict(c, relation=_relation_lisible(c)) for c in nouveautes["contacts"] if c.get("famille") != "Autre"]
    autres = [dict(c, relation=_relation_lisible(c)) for c in nouveautes["contacts"] if c.get("famille") == "Autre"]
    if vises:
        st.caption("Cochez les personnes à inviter : le bloc d'invitation apparaît sous le tableau.")
        df = pd.DataFrame(vises)[list(colonnes)]
        df.insert(0, "Inviter", False)
        choix = st.data_editor(
            df.rename(columns=colonnes),
            key="veille_recap", hide_index=True, width="stretch",
            disabled=list(colonnes.values()), column_config={"Lien": _LIEN_PROFIL},
        )
        urls = list(choix.loc[choix["Inviter"], "Lien"])
        if urls:
            bloc_recuperer_inviter(urls, "veille", nom_export="veille")
    if autres:
        with st.expander(f"Autres postes trouvés ({len(autres)}) — hors des familles visées"):
            st.dataframe(pd.DataFrame(autres)[list(colonnes)].rename(columns=colonnes),
                         hide_index=True, width="stretch", column_config={"Lien": _LIEN_PROFIL})
    for c in nouveautes["changements"]:
        source = "LinkedIn" if c["source"] == "linkedin" else "Annuaire officiel"
        st.markdown(f"- **{_md(c['entreprise'])}** — {_md(_CHAMPS.get(c['champ'], c['champ']))} : "
                    f"{_md(c['avant'])} → **{_md(c['apres'])}** ({source}, {_jour_fr(c['releve_le'])})")
    for p in partages:
        quoi = [f"son {n} : {_md(p[k])}" for k, n in (("email", "email"), ("telephone", "téléphone")) if p[k]]
        # Sans nom, le lien du profil (adresse LinkedIn normalisée) est montré tel quel.
        st.markdown(f"- **{_md(p['nom']) if p['nom'] else p['url']}** ({_md(p['entreprise'])}) a partagé " + " et ".join(quoi)
                    + f" ({_jour_fr(p['releve_le'])})")

    # ── Lancer ─────────────────────────────────────────────────────────
    st.header("Lancer la veille", anchor=False)
    # Le rapport d'un passage qui vient de finir est montré une fois, à la
    # place du résumé enregistré (même passage, avec ses compteurs en plus).
    rapport = st.session_state.pop("veille_rapport", None)
    if rapport is not None and rapport.cause in ("occupe", "rien_a_faire"):
        # Un refus n'est pas un passage : il est dit une fois, et le résumé
        # du dernier vrai passage reste en dessous.
        st.warning(" ".join([_CAUSES[rapport.cause]] + _erreurs_actuelles(rapport.erreurs)))
        rapport = None
    if rapport is not None:
        _afficher_rapport(rapport)
    elif dernier:
        _afficher_passage(dernier["fin"], dernier["cause"], dernier["entreprises"], dernier["pages"],
                          dernier["erreurs"])

    # Même réglage que celui que lit le moteur au lancement de Chrome.
    # Quitter la page ou la recharger arrête la veille en cours (Streamlit
    # interrompt le script) : il faut le dire avant, dans les deux modes.
    if ScraperConfig.HEADLESS:
        st.caption("La veille travaille en arrière-plan quelques minutes : aucune fenêtre ne s'ouvre. "
                   "Gardez cette page ouverte jusqu'au rapport : la quitter arrête la veille.")
    else:
        st.caption("Une fenêtre Chrome va s'ouvrir et travailler quelques minutes : c'est normal, "
                   "LinkedIn l'exige. Laissez-la faire, et gardez cette page ouverte jusqu'au rapport : "
                   "la quitter arrête la veille.")
    if st.button("Lancer la veille", type="primary", key="veille_lancer", disabled=not entreprises,
                 help=None if entreprises else "Ajoutez d'abord une entreprise dans l'onglet Mes entreprises."):
        if not st.session_state.get("global_cookie"):
            st.error("Session LinkedIn manquante : connectez votre session LinkedIn dans la page Recherche.")
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


# ── Onglet Mes entreprises ───────────────────────────────────────────────

def _nb_contacts_cibles(contacts: list) -> int:
    """Même règle que la fiche (`resume_fiche`) : « Autre » n'est pas un poste visé."""
    return sum(1 for c in contacts if c.get("famille") != "Autre")


def _onglet_entreprises(store, entreprises) -> None:
    retrait = st.session_state.pop(_CLE_RETRAIT, None)
    if retrait:
        st.success(retrait)
    if entreprises:
        noms = [e["nom"] for e in entreprises]
        st.session_state["_veille_noms_tableau"] = noms
        st.dataframe(pd.DataFrame([{
            "Entreprise": e["nom"], "État": _etat_lisible(e, store.fiche(e["id"])),
            "Dernier passage": _jour_fr(e["derniere_veille"]) if e["derniere_veille"] else "jamais",
            "Contacts ciblés": _nb_contacts_cibles(store.contacts(e["id"])),
        } for e in entreprises]), hide_index=True, width="stretch", key=_cle_tableau(),
            on_select=_ouvrir_fiche_selectionnee, selection_mode="single-row")
        st.caption("Cliquez sur une ligne pour ouvrir la fiche de l'entreprise.")
    else:
        afficher_etat_vide("Aucune entreprise suivie",
                           "Ajoutez-en depuis votre fichier ou par le lien de leur page LinkedIn, ci-dessous.")

    st.markdown("**Ajouter des entreprises**")
    col1, col2 = st.columns([4, 1], vertical_alignment="bottom")
    with col1:
        suivies = {e["nom"].lower() for e in entreprises}
        proposees = [s for s in store.societes_du_fichier() if s.lower() not in suivies]
        depuis_fichier = st.multiselect("Depuis mon fichier", proposees, key="veille_depuis_fichier",
                                        placeholder="Choisir des entreprises…")
    with col2:
        ajouter_fichier = st.button("Ajouter la sélection", key="veille_ajouter_fichier", width="stretch")
    if ajouter_fichier:
        noms_choisis = [n for n in depuis_fichier if n.strip()]
        if not noms_choisis:
            st.error("Choisissez au moins une entreprise dans la liste.")
        else:
            for nom in noms_choisis:
                store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"))
            st.rerun()
    col3, col4 = st.columns([4, 1], vertical_alignment="bottom")
    with col3:
        lien = st.text_input("Ou le lien de sa page LinkedIn", key="veille_lien",
                             placeholder="https://www.linkedin.com/company/…")
    with col4:
        ajouter_lien = st.button("Ajouter", key="veille_ajouter_lien", width="stretch")
    if ajouter_lien:
        url = _lien_entreprise(lien)
        if not url:
            st.error("Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
        else:
            nom = nom_depuis_lien(url)
            if not nom:
                st.error("Impossible de lire le nom de l'entreprise dans ce lien : "
                         "copiez l'adresse complète de sa page LinkedIn.")
            else:
                store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"), url_linkedin=url)
                st.rerun()

    if entreprises:
        st.markdown("**Retirer une entreprise**")
        options = ["—"] + [e["nom"] for e in entreprises]
        if st.session_state.get("veille_retirer") not in options:
            st.session_state.pop("veille_retirer", None)
        a_retirer = st.selectbox("Entreprise à retirer", options, key="veille_retirer")
        if a_retirer != "—":
            e = next(x for x in entreprises if x["nom"] == a_retirer)
            n = e["nb_contacts"]
            quoi = ("sa fiche" if n == 0 else "sa fiche et son contact" if n == 1
                    else f"sa fiche et ses {n} contacts")
            st.warning(f"Retirer {a_retirer} supprimera {quoi} de la veille ; "
                       "les profils restent dans l'Historique.")
            confirme = st.checkbox("Je confirme", key=f"veille_retirer_confirme_{e['id']}")
            st.button(f"Retirer {a_retirer}", key="veille_btn_retirer", disabled=not confirme,
                      icon=":material/delete:", on_click=_retirer,
                      args=(store.db_file, e["id"], a_retirer))


# ── Onglet Fiche entreprise ──────────────────────────────────────────────

def _onglet_fiche(store, entreprises) -> None:
    if not entreprises:
        afficher_etat_vide("Aucune fiche à montrer",
                           "Ajoutez des entreprises dans l'onglet Mes entreprises : leur fiche se remplit "
                           "au premier passage de la veille.")
        return
    noms = [e["nom"] for e in entreprises]
    if st.session_state.get("veille_fiche") not in noms:
        st.session_state.pop("veille_fiche", None)
    nom = st.selectbox("Entreprise", noms, key="veille_fiche")
    e = next(x for x in entreprises if x["nom"] == nom)
    fiche_complete = store.fiche(e["id"])
    motif = _motif_non_rapprochee(fiche_complete)
    fiche = _fiche_affichable(fiche_complete)
    contacts = store.contacts(e["id"])
    lectures = store.lectures(e["id"])
    st.markdown(f"**En un coup d'œil** — {resume_fiche(fiche, contacts, st.session_state.get('veille_visite_precedente'))}")

    lignes = _lignes_fiche(fiche, lectures)
    if not lignes:
        st.info("Pas encore de fiche : elle sera remplie au prochain passage de la veille (page LinkedIn, "
                "annuaire des entreprises et site de l'entreprise).")
    else:
        st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch", column_config={
            "Information": st.column_config.TextColumn(width=310),
            "Source": st.column_config.TextColumn(width=180),
            "Relevé le": st.column_config.TextColumn(width=110)})
        if not _lignes_coordonnees_entreprise(fiche, lectures):
            st.caption("Coordonnées pas encore relevées : le téléphone vient de sa page LinkedIn, l'email et "
                       "le téléphone de son site, lus au prochain passage de la veille.")
    if "linkedin.description" in fiche:
        st.markdown("**Description**")
        st.caption(_description_lisible(fiche["linkedin.description"]["valeur"]))
    if motif:
        st.caption(f"Données légales non vérifiées ({motif}) : faute de recoupement sûr avec LinkedIn, "
                   "aucune donnée de l'annuaire des entreprises n'est affichée.")

    # Coller le lien sur la fiche, plutôt que par « Ajouter » : ce dernier
    # créerait une seconde entreprise, nommée d'après l'adresse.
    non_identifiee = e["etat"] in ("non_identifiee", "illisible")
    if non_identifiee:
        st.warning(f"{e['nom']} n'a pas pu être identifiée sur LinkedIn : collez ci-dessous le lien de "
                   "sa page entreprise, elle sera relue au prochain passage.")
    with st.expander("Lien de sa page LinkedIn", expanded=non_identifiee, icon=":material/link:"):
        if e.get("url_linkedin"):
            st.caption(f"Lien actuel : {e['url_linkedin']}")
        colle = st.text_input("Lien de sa page entreprise", key=f"veille_lien_fiche_{e['id']}",
                              placeholder="https://www.linkedin.com/company/…")
        if st.button("Enregistrer ce lien", key="veille_attacher"):
            url = _lien_entreprise(colle)
            if not url:
                st.error("Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
            else:
                store.attacher_lien(e["id"], url)
                st.rerun()

    st.markdown("**Contacts**")
    if contacts:
        st.caption("Coordonnées : celles que la personne partage sur LinkedIn, lisibles seulement "
                   "une fois en relation (1er niveau ou invitation acceptée).")
        avec_coordonnees = store.contacts_et_coordonnees(e["id"])
        st.dataframe(_contacts_a_afficher(avec_coordonnees), hide_index=True, width="stretch",
                     column_config={"Lien": _LIEN_PROFIL})
        tableau = _contacts_a_exporter(avec_coordonnees)
        fichier = _nom_export(e["nom"], datetime.now().strftime("%Y-%m-%d"))
        col_x, col_c = st.columns(2)
        with col_x:
            st.download_button(
                "Exporter en Excel", icon=":material/download:",
                data=st.session_state.export_manager.export_to_excel(tableau.to_dict("records")),
                file_name=f"{fichier}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"veille_dl_xlsx_{e['id']}", width="stretch", on_click="ignore")
        with col_c:
            # Point-virgule et BOM : ouvert tel quel par Excel en français, accents compris.
            st.download_button(
                "Exporter en CSV", icon=":material/download:",
                data=tableau.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"{fichier}.csv", mime="text/csv",
                key=f"veille_dl_csv_{e['id']}", width="stretch", on_click="ignore")
    elif e["derniere_veille"]:
        st.caption(f"Aucun contact trouvé au passage du {_jour_fr(e['derniere_veille'])} : rien à exporter.")
    else:
        st.caption("Aucun contact pour l'instant, rien à exporter : ils seront cherchés au prochain "
                   "passage de la veille.")


# ── Onglet Réglages ──────────────────────────────────────────────────────

def _onglet_reglages(chemins) -> None:
    r = charger_reglages(chemins.config_dir)
    familles = st.multiselect("Familles de postes", list(FAMILLES), default=r.familles, key="veille_familles",
                              placeholder="Choisir des familles…")
    libres = st.text_input("Intitulés en plus (séparés par des virgules)",
                           value=", ".join(r.intitules_libres), key="veille_libres")
    pages = st.number_input("Pages LinkedIn par jour pour la veille", min_value=PAGES_MIN,
                            max_value=PAGES_MAX, value=r.pages_par_jour, key="veille_pages",
                            help="Chaque page « À propos » ou de résultats compte pour une. "
                                 "20 par défaut : environ six entreprises par matin.")
    if st.button("Enregistrer les réglages", key="veille_enregistrer"):
        if not familles and not libres.strip():
            st.error("Cochez au moins une famille ou saisissez un intitulé.")
        else:
            sauver_reglages(chemins.config_dir, ReglagesVeille(
                familles, [t.strip() for t in libres.split(",") if t.strip()], int(pages)))
            st.success("Réglages enregistrés.")


def afficher_page_veille() -> None:
    chemins = st.session_state.user_paths
    store = VeilleStore(str(chemins.db_file))
    entreprises = store.entreprises()
    dernier = store.dernier_passage()
    st.title("Veille entreprises", anchor=False)
    _afficher_bandeau(chemins, entreprises, dernier)

    # Onglets suivis (clé + rerun) pour qu'une ligne du tableau puisse ouvrir
    # la fiche ; tout leur contenu reste exécuté à chaque passage, si bien que
    # les widgets des onglets cachés gardent leur état.
    nouveautes, mes_entreprises, fiche, reglages = st.tabs(ONGLETS, key=_CLE_ONGLET, on_change="rerun")
    with nouveautes:
        _onglet_nouveautes(store, chemins, entreprises, dernier)
    with mes_entreprises:
        _onglet_entreprises(store, entreprises)
    with fiche:
        _onglet_fiche(store, entreprises)
    with reglages:
        _onglet_reglages(chemins)
