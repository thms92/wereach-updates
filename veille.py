# -*- coding: utf-8 -*-
"""Moteur de veille entreprises : un passage, du lot au rapport.

Sans Streamlit : l'application l'appelle par un bouton, et la livraison 3
l'appellera par un réveil programmé (`python -m veille --email …`). La
logique n'existe qu'ici.

Un passage relit d'abord l'actualité de toutes les entreprises suivies
(gratuite pour LinkedIn), puis prend les entreprises les plus en retard et,
tant que le budget de pages du jour le permet : identifie l'entreprise sur
LinkedIn, relit sa fiche si elle a plus de 30 jours (page « À propos » +
annuaire officiel recoupé), puis parcourt quelques pages de la recherche de
ses employés Product / Data / IA, en reprenant là où le passage précédent
s'était arrêté.
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
from utils.actualite import ActualiteIndisponible
from utils.actualite import interroger as interroger_actualite
from utils.annuaire import (
    AnnuaireIndisponible, choisir_candidat, fiche_depuis_annuaire, interroger, nom_interrogeable,
    normaliser_nom,
)
from utils.dom_selectors import DOMSelectors
from utils.veille_regles import (
    PAGES_MAX_PAR_ENTREPRISE, RELECTURE_FICHE_JOURS, charger_reglages, expression_mots_cles,
    famille_de_l_intitule, fiche_depuis_apropos, ordre_du_lot, signature_familles,
    url_recherche_personnes,
)
from utils.verrou_linkedin import VerrouOccupe, session_linkedin
from veille_store import VeilleStore


@dataclass
class RapportPassage:
    debut: str
    fin: str = ""
    entreprises: list = field(default_factory=list)
    pages: int = 0
    # termine, budget, cookie, deconnecte, securite, occupe, rien_a_faire, erreur
    cause: str = "termine"
    erreurs: list = field(default_factory=list)
    nouveaux_contacts: int = 0
    nouvelles_actualites: int = 0


# Une seule formulation par cause d'arrêt : la page Veille affiche la même
# phrase en tête du rapport et retire la ligne d'erreur identique, pour ne pas
# dire deux fois la même chose avec des mots différents.
MESSAGES_ARRET = {
    "cookie": "Cookie LinkedIn invalide ou expiré — renseignez un nouveau cookie li_at dans la page Recherche.",
    "deconnecte": "LinkedIn a demandé de se reconnecter : passage interrompu.",
    "securite": ("LinkedIn a signalé une activité inhabituelle (vérification ou limitation) : veille arrêtée "
                 "par sécurité. Réessayez plus tard."),
}


def _maintenant() -> str:
    # Horodatage complet : `nouveautes_depuis` compare des chaînes, une date
    # seule passerait à côté de ce qui a été trouvé le jour même.
    return datetime.now().isoformat(timespec="seconds")


class _Arret(Exception):
    """Fin anticipée du passage : budget, déconnexion."""

    def __init__(self, cause):
        super().__init__(cause)
        self.cause = cause


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


async def passage_async(scraper, store, db, reglages, cookie, maintenant, status=None, annuaire=interroger,
                        actualite=interroger_actualite):
    rapport = RapportPassage(debut=maintenant)
    limites = scraper.human.daily_limits

    def dire(texte):
        logger.info(f"🏢 {texte}")
        if status:
            status(texte)

    # 0. Actualité : gratuite pour LinkedIn, donc pour toutes les entreprises
    # suivies, une fois par jour — la rotation LinkedIn ne la retarde pas.
    pannes = 0
    for e in store.entreprises():
        if (e.get("derniere_actualite") or "")[:10] == maintenant[:10]:
            continue
        dire(f"Actualité de {e['nom']}…")
        try:
            rapport.nouvelles_actualites += store.enregistrer_actualites(e["id"], actualite(e["nom"]), maintenant)
        except ActualiteIndisponible:
            pannes += 1
    if pannes:
        rapport.erreurs.append(f"Google News injoignable : actualité non relue pour {pannes} entreprise(s).")

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

    async def traiter(page, entreprise, urls_au_fichier) -> bool:
        """Une entreprise ; False si elle n'a pas pu être passée."""
        eid, nom = entreprise["id"], entreprise["nom"]
        # Avant la recherche par nom : elle interroge LinkedIn elle aussi.
        if restant() <= 0:
            raise _Arret("budget")

        # 1. Identification
        devine = False
        if not entreprise.get("company_id") and not entreprise.get("url_linkedin"):
            devine = True
            company_id = await scraper._resoudre_company_urn_via_typeahead(nom, page)
            if not company_id:
                store.maj_identification(eid, "non_identifiee")
                rapport.erreurs.append(
                    f"{nom} : introuvable sur LinkedIn par son nom — collez le lien de sa page entreprise.")
                return False
            entreprise["company_id"] = company_id

        # 2. Fiche, si absente ou trop ancienne
        age = store.age_fiche_jours(eid, "linkedin", maintenant)
        if age is None or age >= RELECTURE_FICHE_JOURS or not entreprise.get("company_id"):
            await charger(page, _url_apropos(entreprise))
            lu = await page.evaluate(DOMSelectors.extract_page_apropos_js()) or {}
            fiche = fiche_depuis_apropos(lu.get("champs") or {})
            if not fiche or not lu.get("company_id"):
                scraper._dumper_panneau(lu.get("html") or "", nom_fichier="apropos_dump.html")
                store.maj_identification(eid, "illisible")
                # En fin de rotation : sinon elle mangerait une page à chaque passage.
                store.marquer_passage(eid, maintenant)
                rapport.erreurs.append(
                    f"{nom} : page « À propos » illisible — sa structure a peut-être changé "
                    "(page enregistrée dans logs/).")
                return False
            nom_page = lu.get("nom") or ""
            # La recherche par nom prend le premier résultat : il peut s'agir
            # d'un homonyme. Un lien collé, lui, est le choix de la personne.
            if devine and not _meme_entreprise(nom, nom_page):
                store.maj_identification(eid, "non_identifiee")
                rapport.erreurs.append(
                    f"{nom} : LinkedIn propose « {nom_page or 'une page sans nom'} » "
                    "— collez le lien de sa page pour confirmer.")
                return False
            if lu.get("description"):
                fiche["description"] = lu["description"][:500]
            store.maj_identification(eid, "identifiee", company_id=lu["company_id"])
            entreprise["company_id"] = lu["company_id"]
            store.enregistrer_fiche(eid, fiche, "linkedin", maintenant)

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
            if not trouves:
                if numero == 1:
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
                if store.relier_contact(eid, personne, famille, maintenant, urls_au_fichier):
                    rapport.nouveaux_contacts += 1
                if personne.get("url"):
                    db.ajouter_profil(personne.get("nom", ""), personne.get("poste", ""), nom, "",
                                      personne["url"], personne.get("localisation", ""))
            curseur = numero
            store.maj_curseur(eid, curseur, signature)
        store.maj_curseur(eid, curseur, signature)
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
            urls_au_fichier = db.urls_connues()
            for entreprise in lot:
                dire(f"{entreprise['nom']}…")
                try:
                    if await traiter(page, entreprise, urls_au_fichier):
                        rapport.entreprises.append(entreprise["nom"])
                except _Arret:
                    raise
                except _PageInjoignable as e:
                    # Pas de `marquer_passage` : elle reste en tête du prochain lot.
                    rapport.erreurs.append(f"{entreprise['nom']} : {e.motif} — reprise au prochain passage.")
                except Exception as e:
                    # Une page qui se recharge sous Playwright (« Execution context
                    # was destroyed ») ne doit pas fausser tout le passage.
                    logger.error(f"❌ Veille, {entreprise['nom']} : {type(e).__name__} : {e}", exc_info=True)
                    rapport.erreurs.append(f"{entreprise['nom']} : erreur inattendue ({type(e).__name__}).")
        except _Arret as arret:
            rapport.cause = arret.cause
            if arret.cause in ("deconnecte", "securite"):
                rapport.erreurs.append(MESSAGES_ARRET[arret.cause])
        finally:
            await navigateur.close()
    rapport.fin = _maintenant()
    return rapport


def lancer_passage(chemins, cookie, proxy=None, status=None) -> RapportPassage:
    """Un passage complet, verrou pris, rapport enregistré."""
    from scraper_v2 import LinkedInScraperV2

    maintenant = _maintenant()
    store = VeilleStore(str(chemins.db_file))
    try:
        with session_linkedin(chemins.config_dir, "veille"):
            scraper = LinkedInScraperV2(use_database=True, proxy=proxy, db_file=str(chemins.db_file),
                                        profiles_csv=str(chemins.profiles_csv), config_dir=str(chemins.config_dir))
            rapport = asyncio.run(passage_async(
                scraper, store, DatabaseManager(db_file=str(chemins.db_file)),
                charger_reglages(chemins.config_dir), cookie, maintenant, status))
    except VerrouOccupe as occupe:
        rapport = RapportPassage(debut=maintenant, fin=maintenant, cause="occupe", erreurs=[str(occupe)])
    except Exception as e:
        # L'interface ne doit pas tomber, mais une erreur de programmation ne
        # doit pas non plus passer pour un incident LinkedIn : on la nomme.
        logger.error(f"❌ Veille interrompue : {type(e).__name__} : {e}", exc_info=True)
        rapport = RapportPassage(debut=maintenant, fin=_maintenant(), cause="erreur",
                                 erreurs=[f"Erreur inattendue ({type(e).__name__}) : {e}"])
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
