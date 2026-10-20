# -*- coding: utf-8 -*-
"""Moteur de veille entreprises : un passage, du lot au rapport.

Sans Streamlit : l'application l'appelle par un bouton, et la livraison 3
l'appellera par un réveil programmé (`python -m veille --email …`). La
logique n'existe qu'ici.

Un passage prend les entreprises les plus en retard et, tant que le budget
de pages du jour le permet : identifie l'entreprise sur LinkedIn, relit sa
fiche si elle a plus de 30 jours (page « À propos » + annuaire officiel
recoupé), puis parcourt quelques pages de la recherche de
ses employés Product / Data / IA, en reprenant là où le passage précédent
s'était arrêté. Il relève aussi les coordonnées : générales, sur le site de
l'entreprise (sans coût LinkedIn), et celles que partagent les personnes en
relation, dans leur fenêtre « Coordonnées » (une page du budget chacune).
"""

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime

from playwright.async_api import async_playwright

from database import DatabaseManager
from logger import logger
from utils.annuaire import (
    AnnuaireIndisponible, choisir_candidat, fiche_depuis_annuaire, interroger, nom_interrogeable,
    normaliser_nom,
)
from utils.browsemap import normaliser_url
from utils.coordonnees_site import SiteInjoignable, _normaliser_fr, lire_site, motif_inutilisable
from utils.dom_selectors import DOMSelectors
from utils.identification import choisir_entreprise, url_recherche_entreprises
from utils.veille_regles import (
    PAGES_MAX_PAR_ENTREPRISE, RELECTURE_FICHE_JOURS, charger_reglages, expression_mots_cles,
    famille_de_l_intitule, fiche_depuis_apropos, nom_depuis_lien, ordre_du_lot, signature_familles,
    url_recherche_personnes,
)
from utils.verrou_linkedin import VerrouOccupe, session_linkedin
from veille_store import NOUVEL_ESSAI_COORDONNEES_JOURS, VeilleStore


# Profils dont on lit les coordonnées, par entreprise et par passage : chacun
# coûte une page du budget, la recherche d'employés ne doit pas en manquer.
COORDONNEES_PAR_ENTREPRISE = 3
# Attente de la fenêtre « Coordonnées » après le clic.
ATTENTE_FENETRE_MS = 8000
_SELECTEUR_LIEN_COORDONNEES = 'a[href*="overlay/contact-info"]'
_REPRISE_COORDONNEES = f"nouvel essai dans {NOUVEL_ESSAI_COORDONNEES_JOURS} jours."


@dataclass
class RapportPassage:
    debut: str
    fin: str = ""
    entreprises: list = field(default_factory=list)
    pages: int = 0
    # termine, budget, cookie, deconnecte, securite, occupe, rien_a_faire, erreur, interrompu
    cause: str = "termine"
    erreurs: list = field(default_factory=list)
    nouveaux_contacts: int = 0


# Une seule formulation par cause d'arrêt : la page Veille affiche la même
# phrase en tête du rapport et retire la ligne d'erreur identique, pour ne pas
# dire deux fois la même chose avec des mots différents.
MESSAGES_ARRET = {
    "cookie": "Session LinkedIn invalide ou expirée : mettez-la à jour dans la page Recherche.",
    "deconnecte": "LinkedIn a demandé de se reconnecter : passage interrompu.",
    "securite": ("LinkedIn a signalé une activité inhabituelle (vérification ou limitation) : veille arrêtée "
                 "par sécurité. Réessayez plus tard."),
    "interrompu": ("Veille interrompue : la page a été quittée ou rechargée pendant le passage. "
                   "Ce qui avait été lu est gardé ; la prochaine fois, gardez la page Veille ouverte "
                   "jusqu'au rapport."),
}


def _maintenant() -> str:
    # Horodatage complet : `nouveautes_depuis` compare des chaînes, une date
    # seule passerait à côté de ce qui a été trouvé le jour même.
    return datetime.now().isoformat(timespec="seconds")


class _Arret(Exception):
    """Fin anticipée du passage : budget, déconnexion."""

    def __init__(self, cause, message=None):
        super().__init__(cause)
        self.cause = cause
        self.message = message or MESSAGES_ARRET.get(cause)


class _PageInjoignable(Exception):
    """Une page n'a pas pu être lue : on passe à l'entreprise suivante.

    Lire quand même la page affichée reviendrait à lire la précédente —
    la recherche d'une autre entreprise, rangée sous ce nom-ci. Et une
    extraction en échec n'est pas une fin de liste : on garderait le
    silence en remettant le curseur à zéro.
    """

    def __init__(self, motif="page LinkedIn injoignable"):
        super().__init__(motif)
        self.motif = motif


def _fenetre_fermee(page) -> None:
    """Arrête le passage si la fenêtre LinkedIn a été fermée.

    Sans cela, chaque entreprise suivante dépenserait une page du budget
    pour échouer à son tour, toute l'entreprise étant dite « injoignable ».
    """
    if page.is_closed():
        raise _Arret("erreur", "La fenêtre LinkedIn s'est fermée pendant le passage : veille arrêtée. Relancez-la.")


def _meme_entreprise(nom_suivi: str, nom_page: str) -> bool:
    """Vrai si la page LinkedIn porte bien le nom suivi.

    Égalité, ou tous les mots du nom suivi présents dans celui de la page
    (« Decathlon » / « Decathlon France ») ; le reste est un homonyme
    possible, et la veille ne devine pas.
    """
    suivi, page = normaliser_nom(nom_suivi), normaliser_nom(nom_page)
    if not suivi or not page:
        return False
    return suivi == page or set(suivi.split()) <= set(page.split())


_RACINE_PAGE_ENTREPRISE = re.compile(r"^(https?://[^/]+/company/[^/?#]+)")


def _url_apropos(entreprise) -> str:
    lien = entreprise.get("url_linkedin")
    if lien:
        # Lien collé tel quel : « …/company/x/about/?trk=… », « …/company/x/people/ ».
        m = _RACINE_PAGE_ENTREPRISE.match(lien.strip())
        racine = m.group(1) if m else lien.split("?")[0].rstrip("/")
        return racine + "/about/"
    return f"https://www.linkedin.com/company/{entreprise['company_id']}/about/"


async def passage_async(scraper, store, db, reglages, cookie, maintenant, status=None, annuaire=interroger, rapport=None,
                        site_web=lire_site):
    # `rapport` fourni par l'appelant : si le passage est interrompu, ce qui a
    # été fait jusque-là reste lisible et s'enregistre (voir `lancer_passage`).
    rapport = rapport if rapport is not None else RapportPassage(debut=maintenant)
    limites = scraper.human.daily_limits

    def dire(texte):
        logger.info(f"🏢 {texte}")
        if status:
            status(texte)

    def restant():
        return reglages.pages_par_jour - limites.pages_veille_today

    lot = ordre_du_lot(store.entreprises())
    if not lot:
        rapport.cause, rapport.fin = "rien_a_faire", _maintenant()
        return rapport
    try:
        expression = expression_mots_cles(reglages.familles, reglages.intitules_libres)
    except ValueError:
        rapport.cause, rapport.fin = "erreur", _maintenant()
        rapport.erreurs.append("Aucun intitulé à chercher : cochez au moins une famille dans les réglages de la veille.")
        return rapport
    signature = signature_familles(reglages.familles, reglages.intitules_libres)
    cibles = " / ".join(list(reglages.familles) + list(reglages.intitules_libres or []))
    if restant() <= 0:
        rapport.cause, rapport.fin = "budget", _maintenant()
        rapport.erreurs.append(f"Budget de veille du jour déjà consommé ({reglages.pages_par_jour} pages).")
        return rapport

    async def charger(page, url):
        # Le budget se vérifie avant chaque chargement : une page chargée est
        # une page dépensée, même si elle n'apporte rien.
        if restant() <= 0:
            raise _Arret("budget")
        limites.increment_pages_veille(1)
        rapport.pages += 1
        ok = await scraper.network_manager.safe_page_goto(page, url)
        if scraper._est_page_de_connexion(page.url):
            raise _Arret("deconnecte")
        # Même moniteur HTTP que la recherche : vérification, limitation de
        # débit — on s'arrête plutôt que d'insister sur un compte surveillé.
        if not await scraper.human.check_safety(page):
            raise _Arret("securite")
        if not ok:
            raise _PageInjoignable()
        await scraper.human.human_delay(1500, 400)
        # Défilement comme la recherche existante : déclenche l'affichage
        # paresseux des résultats et garde une allure humaine.
        await scraper.human.browse_page_naturally(page)

    # Page de recherche d'entreprises illisible (aucune carte lue) : sans doute
    # une mise en page changée. On n'y dépense plus de page pour les noms
    # suivants de ce passage, et on ne déclare personne « introuvable ».
    suspension = {"ligne": None, "reportees": []}

    async def relire_site(entreprise):
        """Coordonnées générales, sur le site de l'entreprise : aucune page LinkedIn."""
        eid, nom = entreprise["id"], entreprise["nom"]
        site = (store.fiche(eid).get("linkedin.site") or {}).get("valeur")
        age = store.age_fiche_jours(eid, "site", maintenant)
        if not site or (age is not None and age < RELECTURE_FICHE_JOURS):
            return
        # Panne récente (réseau, HTTP, certificat) : on ne réessaie ni ne redit
        # rien avant 7 jours. Source « site_echec » à part de « site » : un
        # échec n'est pas une lecture (l'âge de la fiche reste celui de la
        # dernière lecture réussie) et un succès l'efface.
        echec = store.age_fiche_jours(eid, "site_echec", maintenant)
        if echec is not None and echec < NOUVEL_ESSAI_COORDONNEES_JOURS:
            return
        motif = motif_inutilisable(site)
        if motif:
            # Refus durable (réseau social, adresse locale…) : dit une fois dans
            # la fiche et daté, revu dans 30 jours, plutôt qu'une ligne d'erreur
            # à chaque passage pour une adresse qui ne changera pas d'elle-même.
            store.enregistrer_fiche(eid, {"lecture": f"site non lisible ({motif})"}, "site", maintenant)
            store.marquer_lecture(eid, "site", maintenant)
            return
        dire(f"{nom} : lecture de son site…")
        try:
            # Hors de la boucle d'événements : un site lent (plusieurs pages à
            # quelques secondes chacune) ne doit pas figer le navigateur ouvert.
            lu = await asyncio.to_thread(site_web, site)
        except SiteInjoignable as e:
            # Pas de date de lecture, mais un échec daté : nouvel essai dans 7 jours.
            # Seul un échec neuf arrive ici (le délai est tenu plus haut), donc
            # la ligne n'est dite qu'une fois par essai.
            store.marquer_lecture(eid, "site_echec", maintenant)
            rapport.erreurs.append(f"{nom} : site {site} injoignable ({e}) — coordonnées générales non relues.")
            return
        emails, telephones = (lu.get("emails") or [])[:3], (lu.get("telephones") or [])[:3]
        # Rien trouvé est un constat daté, pas un champ vide muet — pour le
        # téléphone comme pour l'email : `enregistrer_fiche` ignore une valeur
        # vide, un numéro retiré du site resterait affiché comme actuel.
        # « lecture » remplace un ancien « site non lisible » si l'adresse a changé.
        store.enregistrer_fiche(eid, {"lecture": "site lu", "email": ", ".join(emails) or "non publié",
                                      "telephone": ", ".join(telephones) or "non publié"}, "site", maintenant)
        store.marquer_lecture(eid, "site", maintenant)
        store.effacer_lecture(eid, "site_echec")

    async def lire_coordonnees(page, entreprise, contact):
        """La fenêtre « Coordonnées » d'une personne en relation.

        L'adresse directe `…/overlay/contact-info/` est redirigée vers le
        profil : on charge le profil et on clique le lien, comme à la main.
        Seule une fenêtre lue est enregistrée (« rien » compris) : un lien
        absent ou une fenêtre fermée ne disent rien de ce que la personne
        partage, et un faux « rien » empêcherait de relire pendant 90 jours.
        Ces échecs sont datés à part (nouvel essai dans 7 jours), pour qu'une
        même personne ne reprenne pas la tête de la file à chaque passage.
        """
        nom = entreprise["nom"]
        qui = contact.get("nom") or contact["url"]
        reprise = _REPRISE_COORDONNEES
        await charger(page, contact["url"])
        lien = page.locator(_SELECTEUR_LIEN_COORDONNEES).first
        if not await lien.count():
            rapport.erreurs.append(f"{nom} : {qui} — lien « Coordonnées » absent du profil ; {reprise}")
            store.noter_echec_coordonnees(contact["url"], maintenant)
            return
        await scraper.human.human_hover_and_click(page, lien)
        try:
            # Un petit test sondé à chaque image, qui ne reconnaît que LA fenêtre
            # « Coordonnées » : le profil garde d'autres fenêtres (menus fermés,
            # messagerie) qu'un sélecteur `[role=dialog]` prendrait pour elle.
            await page.wait_for_function(DOMSelectors.fenetre_coordonnees_ouverte_js(), timeout=ATTENTE_FENETRE_MS)
        except Exception:
            rapport.erreurs.append(f"{nom} : {qui} — la fenêtre « Coordonnées » ne s'est pas ouverte ; {reprise}")
            store.noter_echec_coordonnees(contact["url"], maintenant)
            return
        await scraper.human.human_delay(1200, 300)  # le temps de lire la fenêtre
        lu = await page.evaluate(DOMSelectors.extract_coordonnees_js()) or {}
        if not lu.get("dialogue") or lu.get("html"):
            enregistree = scraper._dumper_panneau(lu.get("html") or "", nom_fichier="coordonnees_dump.html")
            ou = "page enregistrée dans logs/" if enregistree else "page non enregistrée"
            rapport.erreurs.append(f"{nom} : {qui} — fenêtre « Coordonnées » illisible, sa structure a peut-être "
                                   f"changé ({ou}) ; rien n'est enregistré.")
            store.noter_echec_coordonnees(contact["url"], maintenant)
            return
        # Même forme « +33 6 12 34 56 78 » que les téléphones de site : un numéro
        # collé sans espaces deviendrait un nombre dans Excel. Un numéro non
        # français (ou illisible) reste tel que lu.
        brut = (lu.get("telephone") or "").strip()
        store.enregistrer_coordonnees(contact["url"], lu.get("email"), _normaliser_fr(brut) or brut, maintenant)

    async def traiter(page, entreprise, connus) -> bool:
        """Une entreprise ; False si elle n'a pas pu être passée.

        `connus` : URL canoniques déjà au fichier, complété au fil du passage.
        """
        eid, nom = entreprise["id"], entreprise["nom"]

        # 1. Identification, par la page de recherche d'entreprises (une page
        # du budget, vérifiée par `charger`). Le service « typeahead » qui le
        # faisait répond 404 depuis le 2026-10-15.
        devine = trouvee = False
        if not entreprise.get("company_id") and not entreprise.get("url_linkedin"):
            devine = True
            if suspension["ligne"] is not None:
                suspension["reportees"].append(nom)
                return False
            await charger(page, url_recherche_entreprises(nom))
            lu = await page.evaluate(DOMSelectors.extract_recherche_entreprises_js()) or {}
            resultats = lu.get("resultats") or []
            url, motif = choisir_entreprise(resultats, nom)
            html = lu.get("html") or ""
            if not resultats and html.strip():
                # Page affichée mais aucune carte lue : panne de lecture, pas
                # absence. Elle reste « à identifier », passe en fin de rotation
                # (sinon elle rouvrirait la même page en tête de chaque passage).
                enregistree = scraper._dumper_panneau(html, nom_fichier="recherche_entreprises_dump.html")
                ou = "page enregistrée dans logs/" if enregistree else "page non enregistrée"
                store.marquer_passage(eid, maintenant)
                suspension["ligne"] = len(rapport.erreurs)
                rapport.erreurs.append(
                    f"{nom} : aucune entreprise lue sur la page de recherche LinkedIn — sa structure a peut-être "
                    f"changé ({ou}) ; nouvel essai au prochain passage.")
                return False
            if not url:
                # Cartes lues, mais aucun nom exact, ou plusieurs : on ne devine pas.
                store.maj_identification(eid, "non_identifiee")
                rapport.erreurs.append(f"{nom} : {motif}.")
                return False
            # Le lien sert à lire « À propos » ; il n'est enregistré qu'une fois
            # le nom de la page confirmé (plus bas) : enregistré avant, un
            # refus laisserait une entreprise « non identifiée » avec un lien,
            # que le passage suivant reprendrait comme un lien collé — sans
            # plus comparer les noms.
            entreprise["url_linkedin"] = url
            trouvee = True

        # 2. Fiche, si absente ou trop ancienne
        age = store.age_fiche_jours(eid, "linkedin", maintenant)
        if age is None or age >= RELECTURE_FICHE_JOURS or not entreprise.get("company_id"):
            await charger(page, _url_apropos(entreprise))
            lu = await page.evaluate(DOMSelectors.extract_page_apropos_js()) or {}
            fiche = fiche_depuis_apropos(lu.get("champs") or {})
            if not fiche or not lu.get("company_id"):
                enregistree = scraper._dumper_panneau(lu.get("html") or "", nom_fichier="apropos_dump.html")
                store.maj_identification(eid, "illisible")
                # En fin de rotation : sinon elle mangerait une page à chaque passage.
                store.marquer_passage(eid, maintenant)
                if fiche:
                    # Rubriques lues, mais aucun identifiant majoritaire : les
                    # employés d'une autre société seraient rangés sous celle-ci.
                    motif = "identifiant de l'entreprise ambigu sur la page"
                else:
                    motif = "page « À propos » illisible — sa structure a peut-être changé"
                ou = "page enregistrée dans logs/" if enregistree else "page non enregistrée"
                rapport.erreurs.append(f"{nom} : {motif} ({ou}).")
                return False
            nom_page = lu.get("nom") or ""
            # Seconde sûreté après le nom exact de la carte : la page elle-même
            # doit porter ce nom. Un lien collé, lui, est le choix de la personne.
            if devine and not _meme_entreprise(nom, nom_page):
                store.maj_identification(eid, "non_identifiee")
                rapport.erreurs.append(
                    f"{nom} : LinkedIn propose « {nom_page or 'une page sans nom'} » "
                    "— collez le lien de sa page pour confirmer.")
                return False
            if lu.get("description"):
                fiche["description"] = lu["description"][:500]
            store.maj_identification(eid, "identifiee", company_id=lu["company_id"],
                                     url_linkedin=entreprise["url_linkedin"] if trouvee else None)
            entreprise["company_id"] = lu["company_id"]
            store.enregistrer_fiche(eid, fiche, "linkedin", maintenant)
            store.marquer_lecture(eid, "linkedin", maintenant)

            # Ajoutée par son lien : son nom n'était qu'un morceau d'adresse
            # (« Orbique Conseil Sas 2 »). Un nom choisi par la personne, lui,
            # est gardé : c'est sous ce nom qu'elle la cherche dans son fichier.
            # Un lien trouvé par la recherche ne vaut pas un lien collé : le nom
            # est alors celui que la personne a saisi, même s'il ressemble à
            # l'adresse (« orbique-conseil » / « Orbique Conseil »).
            lien = None if devine else entreprise.get("url_linkedin")
            if lien and nom_page and nom == nom_depuis_lien(lien) and nom_page != nom:
                if store.renommer(eid, nom_page):
                    entreprise["nom"] = nom = nom_page
                else:
                    rapport.erreurs.append(
                        f"{nom} : sa page LinkedIn s'appelle « {nom_page} », nom déjà suivi dans la veille "
                        f"— gardée sous « {nom} » ; retirez l'une des deux.")

            # 3. Annuaire officiel, recoupé — sans coût LinkedIn. Avec le nom
            # de la page : c'est LinkedIn qu'on recoupe, pas le libellé saisi.
            nom_page = nom_page or nom
            if not nom_interrogeable(nom_page):
                store.enregistrer_fiche(eid, {"rapprochement": "nom trop court pour l'annuaire"},
                                        "annuaire", maintenant)
            else:
                try:
                    candidat, motif = choisir_candidat(annuaire(nom_page), nom_page, fiche.get("siege", ""))
                except AnnuaireIndisponible as e:
                    rapport.erreurs.append(f"{nom} : annuaire officiel injoignable ({e}) — fiche annuaire inchangée.")
                else:
                    if candidat:
                        store.enregistrer_fiche(eid, dict(fiche_depuis_annuaire(candidat), rapprochement="rapprochée"),
                                                "annuaire", maintenant)
                    else:
                        store.enregistrer_fiche(eid, {"rapprochement": motif}, "annuaire", maintenant)
                    store.marquer_lecture(eid, "annuaire", maintenant)

        # 3 bis. Coordonnées générales sur son site : après la fiche, qui donne
        # l'adresse du site, et avant toute page du budget — un budget épuisé
        # plus loin ne les fait pas perdre.
        await relire_site(entreprise)

        # 4. Employés, à partir du curseur (dernière page réellement lue)
        curseur = entreprise.get("curseur_page") or 0
        if entreprise.get("signature_familles") != signature:
            curseur = 0
        for numero in range(curseur + 1, curseur + 1 + PAGES_MAX_PAR_ENTREPRISE):
            await charger(page, url_recherche_personnes(entreprise["company_id"], expression, numero))
            erreurs_avant = len(scraper.errors)
            trouves = await scraper.extraire_profils_page(page)
            if not trouves and len(scraper.errors) > erreurs_avant:
                # `extraire_profils_page` avale ses erreurs et rend [] : ce
                # n'est pas une fin de liste, le curseur ne bouge pas.
                raise _PageInjoignable("résultats de recherche illisibles")
            # Le degré n'est pas lu par l'extracteur des résultats (partagé avec
            # la recherche) : un second passage sur la même page, sans coût.
            # Rien de lu n'est pas une erreur : la relation viendra alors des
            # seules invitations acceptées.
            try:
                degres = await page.evaluate(DOMSelectors.extract_degres_js())
            except Exception as e:
                logger.warning(f"⚠️ Veille, degrés illisibles sur {page.url} : {type(e).__name__} : {e}")
                degres = {}
            degres = {normaliser_url(f"https://www.linkedin.com/in/{v}/"): d
                      for v, d in (degres.items() if isinstance(degres, dict) else ())}
            if not trouves:
                if numero == 1:
                    # Une absence ne se déclare que si LinkedIn l'affiche. Sinon
                    # la page était peut-être pleine et mal lue (cas Amazon du
                    # 15/10, resté indiagnostiquable) : on la garde pour
                    # comprendre, sans conclure que l'entreprise est vide.
                    try:
                        etat = await page.evaluate(DOMSelectors.etat_resultats_personnes_js()) or {}
                    except Exception as e:
                        logger.warning(f"⚠️ Veille, état des résultats illisible sur {page.url} : "
                                       f"{type(e).__name__} : {e}")
                        etat = {}
                    if not etat.get("aucunResultat"):
                        enregistree = scraper._dumper_panneau(
                            etat.get("html") or "", nom_fichier="recherche_personnes_dump.html")
                        ou = "page enregistrée dans logs/" if enregistree else "page non enregistrée"
                        rapport.erreurs.append(
                            f"{nom} : la page de résultats LinkedIn s'est affichée mais aucun profil n'a pu "
                            f"être lu — sa structure a peut-être changé ({ou}) ; nouvel essai au prochain passage.")
                        break
                    rapport.erreurs.append(f"{nom} : aucun profil {cibles} trouvé.")
                    store.enregistrer_fiche(eid, {"recherche": "aucun profil trouvé"}, "linkedin", maintenant)
                curseur = 0  # fin de liste : le prochain cycle repart du début
                break
            if numero == 1 and (store.fiche(eid).get("linkedin.recherche") or {}).get("valeur") == "aucun profil trouvé":
                # Le constat d'absence daté ne doit pas survivre aux premiers résultats.
                store.enregistrer_fiche(eid, {"recherche": "profils trouvés"}, "linkedin", maintenant)
            for personne in trouves:
                famille = famille_de_l_intitule(personne.get("poste", ""), reglages.familles,
                                                reglages.intitules_libres)
                canonique = normaliser_url(personne.get("url"))
                if store.relier_contact(eid, personne, famille, maintenant, connus):
                    rapport.nouveaux_contacts += 1
                if degres.get(canonique):
                    store.maj_degre(eid, canonique, degres[canonique])
                # Seulement les inconnus : pour un profil déjà au fichier,
                # `ajouter_profil` réécrirait sa fiche (école, connexions
                # effacées) ou, sous une autre écriture du lien, la doublerait.
                if canonique and canonique not in connus:
                    db.ajouter_profil(personne.get("nom", ""), personne.get("poste", ""), nom, "",
                                      personne["url"], personne.get("localisation", ""))
                    connus.add(canonique)
            curseur = numero
            store.maj_curseur(eid, curseur, signature)
        store.maj_curseur(eid, curseur, signature)

        # 5. Coordonnées des personnes en relation, après la recherche (qui
        # vient de lire les degrés) et avant de marquer le passage : un budget
        # épuisé ici arrête le passage (ce qui est lu reste), et l'entreprise
        # reste en tête du lot pour finir au passage suivant. Jamais personne
        # hors relation : la fenêtre ne montrerait rien, pour une page dépensée.
        for contact in store.contacts_en_relation(eid, maintenant)[:COORDONNEES_PAR_ENTREPRISE]:
            dire(f"{nom} : coordonnées de {contact.get('nom') or contact['url']}…")
            try:
                await lire_coordonnees(page, entreprise, contact)
            except _Arret:
                raise
            except _PageInjoignable as e:
                _fenetre_fermee(page)
                rapport.erreurs.append(f"{nom} : {contact.get('nom') or contact['url']} — {e.motif} ; "
                                       f"{_REPRISE_COORDONNEES}")
                store.noter_echec_coordonnees(contact["url"], maintenant)
            except Exception as e:
                # Une personne en échec ne prive pas l'entreprise de son passage :
                # ses employés sont déjà lus, elle sortirait sinon de la rotation.
                _fenetre_fermee(page)
                logger.error(f"❌ Veille, coordonnées de {contact['url']} : {type(e).__name__} : {e}", exc_info=True)
                rapport.erreurs.append(f"{nom} : {contact.get('nom') or contact['url']} — erreur inattendue "
                                       f"({type(e).__name__}) en lisant ses coordonnées ; {_REPRISE_COORDONNEES}")
                store.noter_echec_coordonnees(contact["url"], maintenant)
        store.marquer_passage(eid, maintenant)
        return True

    async with async_playwright() as p:
        dire("Ouverture de LinkedIn…")
        navigateur, page = await scraper._open_linkedin_page(p, cookie, status)
        if page is None:
            rapport.cause, rapport.fin = "cookie", _maintenant()
            rapport.erreurs.append(MESSAGES_ARRET["cookie"])
            return rapport
        try:
            connus = {u for u in map(normaliser_url, db.urls_connues()) if u}
            for entreprise in lot:
                dire(f"{entreprise['nom']}…")
                try:
                    if await traiter(page, entreprise, connus):
                        rapport.entreprises.append(entreprise["nom"])
                except _Arret:
                    raise
                except _PageInjoignable as e:
                    _fenetre_fermee(page)
                    # Pas de `marquer_passage` : elle reste en tête du prochain lot.
                    rapport.erreurs.append(f"{entreprise['nom']} : {e.motif} — reprise au prochain passage.")
                except Exception as e:
                    _fenetre_fermee(page)
                    # Une page qui se recharge sous Playwright (« Execution context
                    # was destroyed ») ne doit pas fausser tout le passage.
                    logger.error(f"❌ Veille, {entreprise['nom']} : {type(e).__name__} : {e}", exc_info=True)
                    rapport.erreurs.append(f"{entreprise['nom']} : erreur inattendue ({type(e).__name__}).")
        except _Arret as arret:
            rapport.cause = arret.cause
            if arret.message:
                rapport.erreurs.append(arret.message)
        finally:
            await navigateur.close()
    if suspension["reportees"]:
        rapport.erreurs[suspension["ligne"]] += (
            f" Recherche par nom suspendue pour ce passage : {', '.join(suspension['reportees'])} "
            "attend(ent) le prochain.")
    rapport.fin = _maintenant()
    return rapport


def lancer_passage(chemins, cookie, proxy=None, status=None) -> RapportPassage:
    """Un passage complet, verrou pris, rapport enregistré."""
    from scraper_v2 import LinkedInScraperV2

    maintenant = _maintenant()
    store = VeilleStore(str(chemins.db_file))
    en_cours = RapportPassage(debut=maintenant)
    try:
        with session_linkedin(chemins.config_dir, "veille"):
            scraper = LinkedInScraperV2(use_database=True, proxy=proxy, db_file=str(chemins.db_file),
                                        profiles_csv=str(chemins.profiles_csv), config_dir=str(chemins.config_dir))
            rapport = asyncio.run(passage_async(
                scraper, store, DatabaseManager(db_file=str(chemins.db_file)),
                charger_reglages(chemins.config_dir), cookie, maintenant, status, rapport=en_cours))
    except VerrouOccupe as occupe:
        rapport = RapportPassage(debut=maintenant, fin=maintenant, cause="occupe", erreurs=[str(occupe)])
    except Exception as e:
        # L'interface ne doit pas tomber, mais une erreur de programmation ne
        # doit pas non plus passer pour un incident LinkedIn : on la nomme.
        logger.error(f"❌ Veille interrompue : {type(e).__name__} : {e}", exc_info=True)
        rapport = RapportPassage(debut=maintenant, fin=_maintenant(), cause="erreur",
                                 erreurs=[f"Erreur inattendue ({type(e).__name__}) : {e}"])
    except BaseException:
        # Streamlit arrête le script (page quittée, rechargée) en levant une
        # exception hors de la hiérarchie `Exception`. Chrome est fermé et le
        # verrou rendu par les `finally` ; reste à garder trace du passage.
        en_cours.cause, en_cours.fin = "interrompu", _maintenant()
        en_cours.erreurs.append(MESSAGES_ARRET["interrompu"])
        store.enregistrer_passage(en_cours.debut, en_cours.fin, en_cours.entreprises, en_cours.pages,
                                  en_cours.cause, en_cours.erreurs)
        raise
    store.enregistrer_passage(rapport.debut, rapport.fin, rapport.entreprises, rapport.pages,
                              rapport.cause, rapport.erreurs)
    return rapport


def main(argv=None) -> int:
    from cookie_utils import CookieManager
    from utils.user_context import user_paths_for

    args = argparse.ArgumentParser(description="Un passage de veille We.Reach.")
    args.add_argument("--email", required=True)
    email = args.parse_args(argv).email
    chemins = user_paths_for(email)
    cookie = CookieManager(config_dir=str(chemins.config_dir)).load_cookie()
    if not cookie:
        print("Aucun cookie LinkedIn enregistré pour cet utilisateur.", file=sys.stderr)
        return 2
    rapport = lancer_passage(chemins, cookie)
    print(f"{rapport.cause} — {len(rapport.entreprises)} entreprise(s), {rapport.pages} page(s), "
          f"{rapport.nouveaux_contacts} nouveau(x) contact(s)")
    for erreur in rapport.erreurs:
        print(f"  · {erreur}", file=sys.stderr)
    return 0 if rapport.cause in ("termine", "budget", "rien_a_faire") else 1


if __name__ == "__main__":
    sys.exit(main())
