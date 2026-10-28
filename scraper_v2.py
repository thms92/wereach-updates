# -*- coding: utf-8 -*-
"""
LinkedIn Scraper V2 - Version Refactorisée avec Async
Améliore la fiabilité, la performance et la maintenabilité

Améliorations principales :
- ✅ Sélecteurs DOM stables (plus de dépendance aux classes CSS)
- ✅ Extraction simplifiée avec stratégie unique
- ✅ Gestion d'erreurs réseau robuste avec retry intelligent
- ✅ Architecture async pour meilleure performance
- ✅ Code modulaire et testable
- ✅ Comportement humain simulé (délais gaussiens, souris, scroll, stealth)
"""

import asyncio
import json
import os
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable, Union
import pandas as pd
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config import ScraperConfig
from logger import logger
from utils.dom_selectors import DOMSelectors
from utils.browsemap import CHEMIN_PANNEAU, normaliser_url, vanity_depuis_url
from utils.profile_extractor import ProfileExtractor
from utils.network_manager import NetworkManager, RetryConfig, PermanentNetworkError
from utils.human_behavior import HumanBehavior
from utils.stealth_profile import StealthProfileManager
import utils.requete_linkedin as requete
import utils.listes_linkedin as listes
from utils.page_vide import diagnostiquer_page_vide
from utils.alerte_linkedin import ArretLinkedIn, CHEMINS_TRAVAIL, STATUTS_ALERTE, nature_page
from utils.budget import LIMITE_INVITATIONS_ATTEINTE, LIMITE_PAGES_ATTEINTE



# Message montré quand LinkedIn renvoie vers la connexion : la personne doit
# savoir quoi faire, pas quel cookie technique a expiré.
SESSION_EXPIREE = ("Session LinkedIn expirée : mettez-la à jour dans la page "
                   "Recherche.")
_DEGRES_EN = {"1st": "1er", "2nd": "2e", "3rd": "3e"}
_MARQUE_DEGRE = re.compile(r"·\s*(1er|2e|3e|1st|2nd|3rd)\b")
_LIGNE_DEGRE = re.compile(r"^(1er|2e|3e|1st|2nd|3rd)$")


def degre_depuis_entete(texte: str) -> str:
    """Degré de relation lu dans le texte de l'en-tête d'un profil.

    Rend « 1er », « 2e », « 3e » ou « » (illisible). Le marqueur « · 2e » prime ;
    à défaut une ligne qui ne contient que le degré. Jamais un « 2e » trouvé au
    milieu d'un intitulé (« Alternante 2e année »), comme dans dom_selectors.
    Seules les 4 premières lignes non vides comptent : le degré suit le nom,
    plus bas ce sont l'intitulé et le reste du profil (« · 1er cycle »).
    """
    lignes = [l.strip() for l in (texte or "").splitlines() if l.strip()][:4]
    marque = _MARQUE_DEGRE.search("\n".join(lignes))
    if marque:
        degre = marque.group(1)
    else:
        degre = next((l for l in lignes if _LIGNE_DEGRE.match(l)), "")
    return _DEGRES_EN.get(degre, degre)


def lecture_ratee(ou: str) -> str:
    """Message d'une première page de résultats affichée mais illisible."""
    return ("LinkedIn a affiché des résultats mais aucun profil n'a pu être lu — sa "
            f"structure a peut-être changé ({ou}). Signalez-le avec « Signaler un problème ».")



def _cle_url(url: str) -> Optional[str]:
    """Profil comparable : sans requête, sans ancre, sans « / » final.

    None hors d'un profil (/in/) : deux pages de résultats ne diffèrent que
    par leur requête (« &page=2 »), elles ne sont jamais « déjà ouvertes ».
    """
    if "/in/" not in urllib.parse.urlparse(url or "").path:
        return None
    return (url or "").split("#")[0].split("?")[0].rstrip("/")


def _page_de_travail(url: str) -> bool:
    """Profil, recherche, fil… : pages où le texte peut citer « activité
    inhabituelle » sans alerte. Leur texte n'est pas lu par le détecteur."""
    chemin = (urllib.parse.urlparse(url or "").path or "/").lower()
    if not chemin.endswith("/"):
        chemin += "/"
    return chemin.startswith(CHEMINS_TRAVAIL)


def deja_en_relation_ou_invite(profil: dict) -> bool:
    """Déjà dans le réseau (1er) ou invitation en attente : rien à proposer.

    Le bouton « Message » seul ne suffit pas : LinkedIn l'affiche aussi pour
    des 2e ou 3e degré au profil ouvert, qui restent invitables.
    """
    return profil.get("degre") == "1er" or bool(profil.get("en_attente"))


class LinkedInScraperV2:
    """
    Scraper LinkedIn V2 - Version améliorée avec async/await
    """

    def __init__(self, use_database: bool = True, proxy: dict = None,
                 db_file: str = None, profiles_csv: str = None,
                 config_dir: str = None):
        self._proxy = proxy
        self._config_dir = config_dir
        # Camouflage (spoof UA + navigator + en-têtes Sec-CH-UA). Sur du vrai
        # Chrome, ce spoofing rend la session incohérente → LinkedIn sert sa
        # version allégée sans JavaScript (pas de bouton "Se connecter").
        # SCRAPER_STEALTH=false pour l'utiliser tel quel (vrai Chrome).
        self._stealth = os.getenv("SCRAPER_STEALTH", "true").strip().lower() not in ("false", "0", "no")
        self.config = ScraperConfig()
        self.profil_file = profiles_csv or self.config.PROFIL_FILE
        self.errors = []
        self.ecartes_reseau = 0
        self.use_database = use_database
        # Rythme : plafond de pages de la séance (posé par l'enveloppe ;
        # None = pas de plafond), pages déjà chargées dans la séance, et
        # pages ouvertes dans le passage en cours (remis à zéro par chaque
        # point d'entrée) pour ne pas recharger un profil déjà ouvert.
        self.limite_pages_seance: Optional[int] = None
        self.pages_cette_seance = 0
        # Posé par l'enveloppe : la séance en cours est la dernière du jour.
        self.derniere_seance_du_jour = False
        self._deja_ouvertes: set = set()

        # Initialiser le gestionnaire réseau avec retry
        self.network_manager = NetworkManager(RetryConfig(
            max_attempts=self.config.MAX_RETRY_ATTEMPTS,
            base_delay=2.0,
            max_delay=30.0,
            timeout=self.config.TIMEOUT_PAGE
        ))

        # Initialiser le module de comportement humain (compteur quotidien
        # PAR UTILISATEUR quand config_dir est fourni → isolation multi-user)
        _limits_file = os.path.join(config_dir, "daily_limits.json") if config_dir else None
        self.human = HumanBehavior(fatigue_factor=0.0, limits_file=_limits_file)

        # Initialiser la base de données si nécessaire
        if use_database:
            try:
                from database import DatabaseManager
                self.db = DatabaseManager(db_file=db_file)
            except Exception as e:
                logger.warning(f"Base de données non disponible: {e}")
                self.use_database = False
                self.db = None
        else:
            self.db = None

    def _avant_page(self) -> None:
        """Refuse une nouvelle page si le budget du jour ou de la séance est
        épuisé (ArretLinkedIn « budget_jour » / « budget_seance »)."""
        if not self.human.daily_limits.can_navigate():
            raise ArretLinkedIn("budget_jour")
        if (self.limite_pages_seance is not None
                and self.pages_cette_seance >= self.limite_pages_seance):
            raise ArretLinkedIn("budget_seance")

    def _compter_page(self) -> None:
        """Une page de plus, pour le jour et pour la séance."""
        self.human.daily_limits.increment_pages()
        self.pages_cette_seance += 1

    async def _controler_arrivee(self, page, demande: str, statut: Optional[int] = None) -> None:
        """Lève ArretLinkedIn « alerte » ou « session » si la page affichée est
        un avertissement ou la connexion de LinkedIn (URL, statut, et texte
        hors des pages de travail)."""
        arrivee = page.url
        texte = None
        if not _page_de_travail(arrivee):
            try:
                texte = (await page.locator("body").inner_text(timeout=3000))[:3000]
            except Exception:
                texte = None
        nature = nature_page(arrivee, texte, statut)
        if nature == "alerte":
            logger.error(f"🚨 Page d'alerte LinkedIn ({arrivee}) en ouvrant {demande} — arrêt immédiat")
        elif nature == "session":
            logger.warning(f"🔐 LinkedIn renvoie vers sa connexion ({arrivee}) — arrêt")
        if nature:
            raise ArretLinkedIn(nature, arrivee)

    async def _naviguer(self, page, url: str) -> bool:
        """La seule porte vers une page LinkedIn : comptée, rythmée, surveillée.

        Refuse avant tout chargement si le budget du jour ou de la séance est
        épuisé (ArretLinkedIn « budget_jour » / « budget_seance »). Sinon
        attend une pause humaine, charge en une seule tentative (jamais
        retentée), compte 1 page (même si le chargement échoue : la requête
        est partie), puis lève ArretLinkedIn « alerte » ou
        « session » si LinkedIn a répondu par une page d'avertissement ou de
        connexion. Un profil déjà ouvert dans ce passage et toujours affiché
        n'est pas rechargé. Rend le booléen de safe_page_goto.
        Le panneau « profils similaires », ouvert par un clic, passe par les
        mêmes contrôles (_ouvrir_panneau).
        """
        cle = _cle_url(url)
        if cle is not None and cle in self._deja_ouvertes and _cle_url(page.url) == cle:
            return True

        self._avant_page()
        await self.human.pause_entre_pages()
        ok = False
        try:
            ok = await self.network_manager.safe_page_goto(page, url)
        finally:
            self._compter_page()
        if ok and cle is not None:
            self._deja_ouvertes.add(cle)

        await self._controler_arrivee(page, url, getattr(self.network_manager, "last_status", None))
        return ok

    def _noter_arret(self, arret: ArretLinkedIn) -> None:
        """Range dans self.errors la raison d'un arrêt, pour la personne."""
        if arret.motif == "budget_jour":
            msg = LIMITE_PAGES_ATTEINTE.format(n=self.human.daily_limits.pages_today)
        elif arret.motif == "budget_seance":
            # Total de la séance : pages déjà lues avant cette action, plus
            # celles de l'action.
            avant = (self.config.MAX_PAGES_PER_SEANCE - self.limite_pages_seance
                     if self.limite_pages_seance is not None else 0)
            msg = f"Séance terminée : {avant + self.pages_cette_seance} pages consultées. "
            if self.derniere_seance_du_jour:
                msg += "Vous pourrez reprendre demain."
            else:
                msg += (f"Prochaine séance possible dans "
                        f"{self.config.PAUSE_ENTRE_SEANCES_MIN} minutes.")
        else:
            # Alerte comme session : la personne voit la page de LinkedIn,
            # l'outil n'ajoute aucun texte (décision de Thomas, 2026-10-27).
            msg = SESSION_EXPIREE
        if arret.motif.startswith("budget"):
            logger.warning(f"🚫 {msg}")
        self.errors.append(msg)

    def _noter_limite_invitations(self) -> None:
        """Plafond d'invitations du jour atteint (bloquant) : dit une seule
        fois dans self.errors, avec le moment où reprendre."""
        msg = LIMITE_INVITATIONS_ATTEINTE.format(
            plafond=self.human.daily_limits.max_invitations)
        if msg not in self.errors:
            logger.warning(f"🚫 {msg}")
            self.errors.append(msg)

    def _context_kwargs(self, profile, viewport) -> dict:
        kwargs = {
            "viewport": viewport,
            # Forcé FR : les comptes ciblés sont français, le serveur est en DE.
            # Un mélange locale/geo peut déclencher une boucle de redirections
            # sur les pages /search/ de LinkedIn.
            "locale": "fr-FR",
            "timezone_id": "Europe/Paris",
        }
        if self._stealth:
            kwargs["user_agent"] = profile.user_agent
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return kwargs

    # Construction des recherches : logique pure, dans utils/requete_linkedin.py.
    # Ces noms restent pour les appelants et les tests existants.
    MAX_VALEURS_PAR_FACETTE = requete.MAX_VALEURS_PAR_FACETTE
    _as_list = staticmethod(requete.as_list)
    _encoder_facette = staticmethod(requete.encoder_facette)
    _expression_ou = staticmethod(requete.expression_ou)
    _combiner_et = staticmethod(requete.combiner_et)
    _nom_ecole = staticmethod(requete.nom_ecole)
    _normalize_keyword = staticmethod(requete.normalize_keyword)

    @classmethod
    def _plafonner(cls, valeurs: List[str], nom_facette: str) -> List[str]:
        return requete.plafonner(valeurs, nom_facette)

    @classmethod
    def _libelle_ecoles(cls, ecoles_ids: List[str]) -> str:
        """Libellé enregistré sur chaque profil : « Dauphine / ESCP »."""
        return requete.libelle_ecoles(ecoles_ids)

    def construire_url_recherche(
        self,
        keyword: str,
        entreprises: Union[str, List[str], None],
        ecoles_ids: List[str],
        ile_de_france: bool = False,
        secteurs_ids: Optional[List[str]] = None,
    ) -> str:
        """Adresse de recherche LinkedIn (voir utils/requete_linkedin.py)."""
        return requete.construire_url_recherche(
            keyword, entreprises, ecoles_ids, ile_de_france, secteurs_ids,
            resoudre_urn=self._resoudre_company_urn,
        )

    @staticmethod
    def _resoudre_company_urn(entreprise: str) -> Optional[str]:
        """Cherche l'URN numérique d'une entreprise dans le cache local.

        Le cache se trouve dans `config/company_urns.json` et a la forme :
            {
              "eurosport": "165158",
              "decathlon": "1815"
            }
        Les clés sont insensibles à la casse et aux espaces.

        Retourne l'ID numérique (str) ou None si l'entreprise n'est pas dans
        le cache. Dans ce dernier cas, l'appelant retombe sur la stratégie
        "AND \"Nom\"" dans les keywords.
        """
        if not entreprise:
            return None
        key0 = entreprise.strip().lower()
        # 1) Seed versionné (config.py COMPANY_URNS) — déployé avec l'app
        try:
            from config import COMPANY_URNS
            if COMPANY_URNS.get(key0):
                logger.info(f"🏢 URN entreprise '{entreprise}' (seed): {COMPANY_URNS[key0]}")
                return str(COMPANY_URNS[key0])
        except Exception:
            pass
        # 2) Cache local (config/company_urns.json, non versionné)
        try:
            import json
            from pathlib import Path
            cache_path = Path(__file__).resolve().parent / "config" / "company_urns.json"
            if not cache_path.exists():
                return None
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            key = entreprise.strip().lower()
            urn = cache.get(key) or cache.get(entreprise.strip())
            if urn:
                logger.info(f"🏢 URN entreprise '{entreprise}' (cache): {urn}")
                return str(urn)
        except Exception as e:
            logger.debug(f"Lecture cache URN entreprise échouée: {e}")
        return None

    @staticmethod
    def _save_company_urn(entreprise: str, urn_id: str) -> None:
        """Ajoute (ou met à jour) une entrée dans config/company_urns.json."""
        if not entreprise or not urn_id:
            return
        try:
            cache_path = Path(__file__).resolve().parent / "config" / "company_urns.json"
            cache_path.parent.mkdir(exist_ok=True)
            cache: dict = {}
            if cache_path.exists():
                try:
                    cache = json.loads(cache_path.read_text(encoding="utf-8"))
                    if not isinstance(cache, dict):
                        cache = {}
                except Exception:
                    cache = {}
            cache[entreprise.strip().lower()] = str(urn_id)
            cache_path.write_text(
                json.dumps(cache, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"Échec sauvegarde URN entreprise '{entreprise}': {e}")

    async def _resoudre_company_urn_via_typeahead(
        self, entreprise: str, page: Page, echecs: Optional[list] = None
    ) -> Optional[str]:
        """Résout l'URN d'une entreprise via l'API typeahead authentifiée de LinkedIn.

        Cette méthode utilise la page Playwright déjà connectée pour appeler
        l'endpoint `/voyager/api/typeahead/hitsV2` (avec le bon CSRF token
        extrait du cookie JSESSIONID), puis cache le résultat dans
        `config/company_urns.json` pour les prochaines exécutions.

        Si la résolution échoue, l'appelant retombe automatiquement sur la
        stratégie "AND \"Nom\"" dans les keywords (via construire_url_recherche).

        `echecs` (facultatif) reçoit le motif d'un échec *technique* (pas de
        JSESSIONID, réponse HTTP en erreur, fetch impossible, page fermée) :
        dans les deux cas la méthode rend None, mais la veille ne doit pas
        déclarer « introuvable » une entreprise que LinkedIn n'a pas pu
        chercher.
        """
        def _echec(motif):
            if echecs is not None:
                echecs.append(motif)
            return None

        if not entreprise:
            return None

        # 1) Cache local
        cached = self._resoudre_company_urn(entreprise)
        if cached:
            return cached

        # 2) Appel API typeahead via la page authentifiée
        try:
            cookies = await page.context.cookies("https://www.linkedin.com")
            jsess = next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), None)
            if not jsess:
                logger.debug(f"Pas de JSESSIONID — résolution URN '{entreprise}' impossible")
                return _echec("session LinkedIn incomplète (JSESSIONID absent)")
            csrf = jsess.strip('"')

            kw_q = urllib.parse.quote(entreprise)
            api_url = (
                "https://www.linkedin.com/voyager/api/typeahead/hitsV2"
                f"?keywords={kw_q}"
                "&origin=GLOBAL_SEARCH_HEADER"
                "&q=type"
                "&queryContext=List(spellCorrectionEnabled-%3Etrue,relatedSearchesEnabled-%3Etrue)"
                "&type=COMPANY"
            )

            result = await page.evaluate(
                """async ({url, csrf}) => {
                    try {
                        const r = await fetch(url, {
                            method: 'GET',
                            headers: {
                                'csrf-token': csrf,
                                'accept': 'application/vnd.linkedin.normalized+json+2.1',
                                'x-restli-protocol-version': '2.0.0',
                            },
                            credentials: 'include',
                        });
                        if (!r.ok) return {ok: false, status: r.status};
                        return {ok: true, data: await r.json()};
                    } catch (e) {
                        return {ok: false, error: String(e)};
                    }
                }""",
                {"url": api_url, "csrf": csrf}
            )

            if not result.get("ok"):
                logger.warning(f"⚠️ Typeahead URN '{entreprise}' échoué: {result} (page: {page.url})")
                # 429 ou 999 : LinkedIn freine ce compte, comme une page
                # d'alerte. Arrêt immédiat, pas de repli par navigation.
                if result.get("status") in STATUTS_ALERTE:
                    raise ArretLinkedIn("alerte", api_url)
                if result.get("status"):
                    return _echec(f"réponse HTTP {result['status']}")
                return _echec(f"appel impossible ({result.get('error') or 'raison inconnue'})")

            data = result.get("data", {}) or {}
            # Selon la version de la réponse, les éléments sont dans 'elements'
            # ou 'included'. On parcourt les deux.
            candidates = []
            for key in ("elements", "included"):
                v = data.get(key)
                if isinstance(v, list):
                    candidates.extend(v)

            urn_re = re.compile(r"urn:li:fs[d]?_company:(\d+)")
            for el in candidates:
                if not isinstance(el, dict):
                    continue
                for field in ("targetUrn", "entityUrn", "objectUrn"):
                    val = el.get(field) or ""
                    m = urn_re.search(str(val))
                    if m:
                        urn_id = m.group(1)
                        self._save_company_urn(entreprise, urn_id)
                        logger.info(f"🏢 URN entreprise '{entreprise}' résolu via API: {urn_id}")
                        return urn_id

            logger.warning(f"⚠️ Aucune correspondance URN trouvée pour '{entreprise}' (typeahead)")
            return None

        except ArretLinkedIn:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Erreur résolution URN '{entreprise}' via typeahead: {e}")
            return _echec(f"{type(e).__name__}")

    async def _resoudre_company_urn_via_navigation(
        self, entreprise: str, page: Page
    ) -> Optional[str]:
        """Résout l'URN d'une entreprise en NAVIGUANT vers la recherche
        d'entreprises LinkedIn puis en lisant l'URN numérique dans le HTML.

        Plus robuste que l'API typeahead (qui peut échouer avec "Failed to
        fetch" selon l'environnement) : on réutilise la navigation normale
        (la porte `_naviguer`), qui fonctionne déjà pour la recherche de
        personnes. Le résultat est mis en cache (config/company_urns.json).
        Un ArretLinkedIn (alerte, budget) remonte au point d'entrée appelant.
        """
        if not entreprise:
            return None
        cached = self._resoudre_company_urn(entreprise)
        if cached:
            return cached
        try:
            kw_q = urllib.parse.quote(entreprise)
            search_url = (
                "https://www.linkedin.com/search/results/companies/"
                f"?keywords={kw_q}&origin=SWITCH_SEARCH_VERTICAL"
            )
            ok = await self._naviguer(page, search_url)
            if not ok:
                logger.warning(f"⚠️ Navigation recherche entreprise '{entreprise}' échouée")
                return None
            await asyncio.sleep(3.5)
            info = await page.evaluate(
                r"""() => {
                    const html = document.documentElement.innerHTML;
                    const patterns = [
                        /urn:li:fsd_company:(\d+)/,
                        /urn:li:fs_company:(\d+)/,
                        /urn:li:company:(\d+)/,
                        /fsd_company:(\d+)/,
                        /\/company\/(\d+)/
                    ];
                    let urn = null;
                    for (const re of patterns) { const m = html.match(re); if (m) { urn = m[1]; break; } }
                    const idx = html.indexOf('/company/');
                    return {
                        urn: urn,
                        htmlLength: html.length,
                        snippet: idx >= 0 ? html.substring(idx, idx + 140) : '',
                        noResults: /Aucun r.sultat|No results found/i.test(html),
                    };
                }"""
            )
            urn_id = (info or {}).get("urn")
            if urn_id:
                self._save_company_urn(entreprise, str(urn_id))
                logger.info(f"🏢 URN entreprise '{entreprise}' résolu via navigation: {urn_id}")
                return str(urn_id)

            # Aucun URN → dumper le HTML réel pour analyse + tracer des indices
            logger.warning(
                f"⚠️ Aucun URN trouvé pour '{entreprise}' "
                f"(htmlLength={info.get('htmlLength')}, noResults={info.get('noResults')}, "
                f"snippet={info.get('snippet')!r})"
            )
            try:
                dbg = Path(__file__).parent / "logs"
                dbg.mkdir(exist_ok=True)
                (dbg / "company_search_dump.html").write_text(
                    await page.content(), encoding="utf-8"
                )
                await page.screenshot(path=str(dbg / "company_search.png"))
                logger.info(f"📄 HTML page entreprises dumpé dans {dbg}/company_search_dump.html")
            except Exception as dump_err:
                logger.warning(f"⚠️ Échec dump page entreprises: {dump_err}")
            return None
        except ArretLinkedIn:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Erreur résolution URN '{entreprise}' via navigation: {e}")
            return None

    async def extraire_profils_page(self, page: Page) -> List[Dict]:
        """
        Extrait tous les profils d'une page de résultats

        Args:
            page: Page Playwright

        Returns:
            Liste de dictionnaires de profils
        """
        try:
            # Utiliser le JavaScript robuste de DOMSelectors
            profile_data = await page.evaluate(DOMSelectors.extract_profiles_data_js())

            # Logger les informations de debug
            debug_info = profile_data.get('debug', [])
            if debug_info:
                logger.info(f"🔍 DEBUG - Premiers profils extraits:")
                for d in debug_info[:5]:
                    method = d.get('method', '?')
                    job = d.get('jobTitle', '') or '(vide)'
                    company = d.get('company', '') or '(vide)'
                    location = d.get('location', '') or '(vide)'
                    logger.info(
                        f"   • {d['name']} | {job} @ {company} | {location} "
                        f"[via {method}]"
                    )

            profiles_list = profile_data.get('profiles', [])
            logger.info(f"✅ {len(profiles_list)} profils extraits de la page")

            # Si aucun poste/entreprise extrait → dumper le HTML du premier card
            empty_count = sum(
                1 for p in profiles_list
                if not (p.get('jobTitle') or p.get('company'))
            )
            if profiles_list and empty_count == len(profiles_list):
                first_html = profile_data.get('firstContainerHTML', '')
                if first_html:
                    try:
                        from pathlib import Path
                        debug_dir = Path(__file__).parent / 'logs'
                        debug_dir.mkdir(exist_ok=True)
                        debug_file = debug_dir / 'first_container_dump.html'
                        debug_file.write_text(first_html, encoding='utf-8')
                        logger.warning(
                            f"⚠️ Tous les profils ont un poste vide. "
                            f"HTML du 1er card sauvegardé dans {debug_file} "
                            f"pour analyse des nouvelles classes LinkedIn."
                        )
                    except Exception as dump_err:
                        logger.warning(f"⚠️ Impossible de sauver le dump: {dump_err}")
                    # Afficher aussi un extrait dans les logs
                    excerpt = first_html[:800].replace('\n', ' ')
                    logger.info(f"📄 Extrait HTML 1er card: {excerpt}...")

            # Dumper le HTML des cartes avec poste mais SANS entreprise (diagnostic)
            empty_company_cards = profile_data.get('emptyCompanyHTML', [])
            if empty_company_cards:
                try:
                    from pathlib import Path
                    debug_dir = Path(__file__).parent / 'logs'
                    debug_dir.mkdir(exist_ok=True)
                    for i, card in enumerate(empty_company_cards):
                        debug_file = debug_dir / f'no_company_card_{i}.html'
                        debug_file.write_text(card.get('html', ''), encoding='utf-8')
                    names = ', '.join(c.get('name', '?') for c in empty_company_cards)
                    logger.warning(
                        f"⚠️ {len(empty_company_cards)} carte(s) sans entreprise "
                        f"sauvegardée(s) dans {debug_dir}/no_company_card_*.html "
                        f"(profils : {names})"
                    )
                except Exception as dump_err:
                    logger.warning(f"⚠️ Impossible de sauver les cartes sans entreprise: {dump_err}")

            # Convertir les données brutes en profils validés
            validated_profiles = []
            for raw_profile in profiles_list:
                profile = ProfileExtractor.extract_from_data(raw_profile)
                if profile and ProfileExtractor.validate_profile(profile):
                    validated_profiles.append(profile)

            logger.info(f"✅ {len(validated_profiles)} profils validés")
            return validated_profiles

        except Exception as e:
            logger.error(f"❌ Erreur extraction profils page: {e}")
            self.errors.append(f"Erreur extraction profils: {e}")
            return []

    async def envoyer_invitation(
        self,
        page: Page,
        profile_url: str,
        profile_name: str,
        message_personnalise: str = "",
        profile_index: int = 0
    ) -> bool:
        """
        Envoie une invitation à un profil LinkedIn

        IMPORTANT: L'invitation se fait DEPUIS LA PAGE DE RECHERCHE
        Il ne faut JAMAIS cliquer sur le profil de la personne.
        Le bouton "Se connecter" est un lien <a> qui ouvre une modal.

        Args:
            page: Page Playwright
            profile_url: URL du profil
            profile_name: Nom du profil
            message_personnalise: Message optionnel
            profile_index: Index du profil dans la liste (pour le retrouver)

        Returns:
            True si l'invitation a été envoyée
        """
        # Plafond du jour bloquant : aucun geste vers LinkedIn au-delà.
        if not self.human.daily_limits.can_invite():
            self._noter_limite_invitations()
            return False

        try:
            logger.info(f"💌 Tentative invitation: {profile_name}")

            # Extraire le vanityName du profil depuis l'URL
            # URL format: https://www.linkedin.com/in/vanityname/
            vanity_name = ""
            if "/in/" in profile_url:
                vanity_name = profile_url.split("/in/")[1].split("?")[0].split("/")[0]

            if not vanity_name:
                logger.warning(f"  ⚠️ Impossible d'extraire le vanityName de {profile_url}")
                return False

            logger.info(f"  🔍 Recherche du bouton 'Se connecter' pour: {vanity_name}")

            # STRATÉGIE 2026 : le bouton "Se connecter" est un <button> dans la
            # carte de résultat (aria-label "Inviter <Nom> à se connecter"), et
            # non plus le vieux lien /preload/search-custom-invite. S'il n'est
            # pas visible directement, il est souvent dans le menu "Plus".

            try:
                await self.human.reading_pause(text_length=80)

                connect = None
                on_search = '/search/results/' in page.url

                if on_search:
                    # ── Contexte RECHERCHE : bouton = <a> dans la carte de résultat
                    # (href /preload/search-custom-invite, aria-label "Inviter …").
                    card = page.locator(
                        f'div[role="listitem"]:has(a[href*="/in/{vanity_name}"])'
                    ).first
                    if await card.count() == 0:
                        card = page.locator(f'*:has(> a[href*="/in/{vanity_name}"])').first
                    try:
                        await card.scroll_into_view_if_needed(timeout=4000)
                    except Exception:
                        pass
                    await self.human.human_delay(1500, 400)

                    # SÉCURITÉ : ne jamais recliquer une invitation déjà envoyée
                    # ("En attente" → un clic ouvrirait "Retirer l'invitation").
                    pending = card.locator(
                        'button[aria-label*="En attente"], button:has-text("En attente"), '
                        'a[aria-label*="Retirer"], [componentkey*="withdraw"]'
                    ).first
                    if await pending.count() > 0:
                        logger.info("  ⏭️ Invitation déjà en attente — profil suivant")
                        return False

                    c = card.locator(
                        'a[href*="/preload/search-custom-invite"], '
                        'a[componentkey*="ConnectButton"], '
                        'a[aria-label^="Inviter"]'
                    ).first
                    try:
                        await c.wait_for(state="visible", timeout=5000)
                    except Exception:
                        pass
                    if await c.count() > 0:
                        connect = c
                else:
                    # ── Contexte PAGE PROFIL : aller sur le profil, puis trouver
                    # "Se connecter" (section principale, sinon menu "Plus").
                    clean_url = profile_url.split('?')[0].rstrip('/') + '/'
                    if vanity_name not in page.url:
                        await self._naviguer(page, clean_url)
                        await self.human.human_delay(2000, 500)
                    c = page.locator(
                        'main button[aria-label*="nviter"][aria-label*="onnecter"], '
                        'main button[aria-label^="Inviter"], '
                        'main button:has-text("Se connecter")'
                    ).first
                    if not (await c.count() > 0 and await c.is_visible()):
                        plus = page.locator(
                            'main button[aria-label*="Plus"], main button:has-text("Plus")'
                        ).first
                        if await plus.count() > 0 and await plus.is_visible():
                            logger.info("  ↳ Ouverture du menu 'Plus' du profil…")
                            await self.human.human_hover_and_click(page, plus)
                            await self.human.human_delay(800, 200)
                            c = page.locator(
                                'div[role="menu"] [aria-label*="nviter"][aria-label*="onnecter"], '
                                'div[role="menu"] div:has-text("Se connecter"), '
                                'div[aria-label*="nviter"][aria-label*="onnecter"]'
                            ).first
                    if await c.count() > 0 and await c.is_visible():
                        connect = c

                if connect is None:
                    logger.info("  ⏭️ 'Se connecter' introuvable (déjà en relation / en attente / non invitable)")
                    try:
                        from pathlib import Path
                        dbg = Path(__file__).parent / "logs"
                        dbg.mkdir(exist_ok=True)
                        if on_search:
                            scope = page.locator(f'div[role="listitem"]:has(a[href*="/in/{vanity_name}"])').first
                        else:
                            scope = page.locator("main").first
                        html = (await scope.evaluate("el => el.outerHTML")) if await scope.count() else (await page.content())
                        (dbg / "invite_card_dump.html").write_text(html[:10000], encoding="utf-8")
                        logger.info("  📄 Dump → logs/invite_card_dump.html")
                    except Exception:
                        pass
                    return False

                try:
                    await self.human.scroll_to_element_naturally(page, connect)
                except Exception:
                    pass

                await self.human.human_hover_and_click(page, connect)
                logger.info("  ✓ Clic sur 'Se connecter'")

            except ArretLinkedIn:
                raise
            except Exception as e:
                logger.warning(f"  ⚠️ Erreur lors du clic sur 'Se connecter': {e}")
                return False

            logger.info(f"  ✓ Modal d'invitation ouverte")

            # Attendre que la modal soit visible (délai gaussien réaliste)
            await self.human.human_delay(
                self.config.DELAY_AFTER_CONNECT_CLICK_MIN,
                (self.config.DELAY_AFTER_CONNECT_CLICK_MAX - self.config.DELAY_AFTER_CONNECT_CLICK_MIN) // 3
            )

            # ÉTAPE 2: Ajouter le message personnalisé si présent
            if message_personnalise:
                try:
                    # Chercher le bouton "Ajouter une note"
                    add_note_btn = page.locator('button:has-text("Ajouter une note")').first
                    if await add_note_btn.is_visible(timeout=2000):
                        await self.human.human_hover_and_click(page, add_note_btn)
                        await self.human.human_delay(800, 200)

                        # Écrire le message caractère par caractère
                        textarea = page.locator('textarea[name="message"]').first
                        if await textarea.is_visible(timeout=2000):
                            await self.human.human_type(page, textarea, message_personnalise)
                            logger.info(f"  ✓ Message personnalisé ajouté (frappe humaine)")
                except Exception as e:
                    logger.warning(f"  ⚠️ Impossible d'ajouter le message: {e}")

            # ÉTAPE 3: Cliquer sur "Envoyer sans note"
            logger.info(f"  🔍 Recherche du bouton 'Envoyer sans note'...")

            # DEBUG: Screenshot de la modal
            try:
                await page.screenshot(path="debug_modal_invitation.png")
                logger.info(f"  📸 Screenshot modal sauvegardé: debug_modal_invitation.png")
            except:
                pass

            # Stratégie 1: Chercher par texte avec Playwright
            try:
                send_button = page.locator('button:has-text("Envoyer sans note")').first
                if await send_button.is_visible(timeout=3000):
                    logger.info(f"  ✓ Bouton trouvé avec Playwright")
                    # Pause naturelle avant de cliquer (simule la réflexion)
                    await self.human.human_delay(400, 150)
                    await self.human.human_hover_and_click(page, send_button)
                    logger.info(f"✅ Invitation envoyée à {profile_name} (méthode Playwright)")
                    await self.human.human_delay(1200, 300)
                    return True
            except Exception as e:
                logger.debug(f"  Playwright échec: {e}")

            # Stratégie 2: Chercher avec un sélecteur plus spécifique
            try:
                send_button = page.locator('button span.artdeco-button__text:has-text("Envoyer sans note")').first
                parent_button = send_button.locator('..')
                if await parent_button.is_visible(timeout=2000):
                    logger.info(f"  ✓ Bouton trouvé avec sélecteur span")
                    await self.human.human_delay(350, 120)
                    await self.human.human_hover_and_click(page, parent_button)
                    logger.info(f"✅ Invitation envoyée à {profile_name} (méthode span)")
                    await self.human.human_delay(1200, 300)
                    return True
            except Exception as e:
                logger.debug(f"  Sélecteur span échec: {e}")

            # Stratégie 3: Via JavaScript avec debug
            try:
                logger.info(f"  🔍 Tentative avec JavaScript...")
                send_result = await page.evaluate("""
                    () => {
                        // DEBUG: Lister tous les boutons dans la modal
                        const modal = document.querySelector('[role="dialog"], .artdeco-modal');
                        const buttons = modal ? modal.querySelectorAll('button') : document.querySelectorAll('button');

                        const allButtonTexts = Array.from(buttons)
                            .map(b => b.textContent?.trim())
                            .filter(t => t && t.length < 100);

                        // Chercher "Envoyer sans note" ou "Envoyer"
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim() || '';

                            if (text === 'Envoyer sans note' || text === 'Envoyer') {
                                btn.click();
                                return { success: true, method: 'js_button', matched: text };
                            }
                        }

                        // Fallback: chercher les spans
                        const spans = modal ? modal.querySelectorAll('span') : document.querySelectorAll('span');
                        for (const span of spans) {
                            const text = span.textContent?.trim();
                            if (text === 'Envoyer sans note' || text === 'Envoyer') {
                                const btn = span.closest('button');
                                if (btn) {
                                    btn.click();
                                    return { success: true, method: 'js_span', matched: text };
                                }
                            }
                        }

                        return {
                            success: false,
                            reason: 'button_not_found',
                            availableButtons: allButtonTexts.slice(0, 5).join(', ')
                        };
                    }
                """)

                if send_result.get('success'):
                    logger.info(f"✅ Invitation envoyée à {profile_name} (méthode {send_result.get('method', 'JS')} - texte: {send_result.get('matched')})")
                    await self.human.human_delay(
                        self.config.DELAY_AFTER_INVITATION_MIN,
                        (self.config.DELAY_AFTER_INVITATION_MAX - self.config.DELAY_AFTER_INVITATION_MIN) // 3
                    )
                    return True
                else:
                    logger.warning(f"  ⚠️ JavaScript ne trouve pas le bouton")
                    logger.warning(f"  Boutons disponibles dans la modal: {send_result.get('availableButtons', 'N/A')}")

            except Exception as e:
                logger.error(f"❌ Erreur JavaScript: {e}")

            # Si on arrive ici, échec
            logger.warning(f"❌ Impossible d'envoyer l'invitation à {profile_name}")

            # Fermer la modal
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
            except:
                pass

            return False

        except ArretLinkedIn:
            raise
        except Exception as e:
            logger.error(f"❌ Erreur invitation {profile_name}: {e}")
            try:
                await page.keyboard.press("Escape")
            except:
                pass
            return False

    async def envoyer_message(
        self, page: Page, profile_url: str, profile_name: str, message: str
    ) -> bool:
        """Envoie un message direct à un profil (relation de 1er degré).

        Ouvre la page profil, clique "Message", saisit le texte et envoie.
        Ne fonctionne que si la personne est une relation (a accepté).
        """
        if not message.strip():
            return False
        try:
            logger.info(f"💬 Message à : {profile_name}")
            clean_url = profile_url.split('?')[0].rstrip('/') + '/'
            await self._naviguer(page, clean_url)
            await self.human.human_delay(2000, 500)

            btn = page.locator(
                'main button[aria-label^="Message"], main a[aria-label^="Message"], '
                'main button:has-text("Message"), main a:has-text("Message")'
            ).first
            if not (await btn.count() > 0 and await btn.is_visible()):
                logger.info("  ⏭️ Pas de bouton 'Message' (pas une relation de 1er degré ?)")
                try:
                    from pathlib import Path
                    dbg = Path(__file__).parent / "logs"; dbg.mkdir(exist_ok=True)
                    main_loc = page.locator("main").first
                    html = (await main_loc.evaluate("el => el.outerHTML")) if await main_loc.count() else (await page.content())
                    (dbg / "message_profile_dump.html").write_text(html[:12000], encoding="utf-8")
                    logger.info("  📄 Page profil dumpée → logs/message_profile_dump.html")
                except Exception:
                    pass
                return False

            await self.human.human_hover_and_click(page, btn)
            await self.human.human_delay(1500, 400)

            box = page.locator(
                'div[contenteditable="true"][role="textbox"], '
                'div.msg-form__contenteditable[contenteditable="true"], '
                'div[contenteditable="true"]'
            ).first
            try:
                await box.wait_for(state="visible", timeout=6000)
            except Exception:
                pass
            if await box.count() == 0:
                logger.info("  ⏭️ Zone de saisie du message introuvable")
                try:
                    from pathlib import Path
                    dbg = Path(__file__).parent / "logs"; dbg.mkdir(exist_ok=True)
                    (dbg / "message_compose_dump.html").write_text((await page.content())[:14000], encoding="utf-8")
                    logger.info("  📄 Compose dumpé → logs/message_compose_dump.html")
                except Exception:
                    pass
                return False

            await box.click()
            await self.human.human_type(page, box, message)
            await self.human.human_delay(900, 250)

            send = page.locator(
                'button.msg-form__send-button, '
                'button[type="submit"]:has-text("Envoyer"), '
                'button:has-text("Envoyer")'
            ).first
            if await send.count() > 0 and await send.is_visible():
                await self.human.human_hover_and_click(page, send)
                logger.info(f"  ✅ Message envoyé à {profile_name}")
                await self.human.human_delay(1200, 300)
                return True
            # Repli : touche Entrée
            await box.press("Enter")
            logger.info(f"  ✅ Message envoyé (Entrée) à {profile_name}")
            await self.human.human_delay(1000, 250)
            return True

        except ArretLinkedIn:
            raise
        except Exception as e:
            logger.warning(f"  ⚠️ Erreur message {profile_name}: {e}")
            return False

    async def _open_linkedin_page(self, p, cookie: str, status_callback=None):
        """Ouvre Chrome + session LinkedIn (cookie) + warm-up.
        Retourne (browser, page) ou (None, None) si le cookie est invalide/expiré.
        Lève ArretLinkedIn, Chrome déjà fermé, si le warm-up est refusé
        (budget) ou tombe sur une page d'alerte ou de connexion."""
        profile = StealthProfileManager.load_or_generate(prefer_mac=True)
        viewport = profile.viewport
        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            f"--window-size={profile.screen['width']},{profile.screen['height']}",
        ]
        try:
            browser = await p.chromium.launch(channel="chrome", headless=self.config.HEADLESS, args=launch_args)
        except Exception:
            browser = await p.chromium.launch(headless=self.config.HEADLESS, args=launch_args)
        context = await browser.new_context(**self._context_kwargs(profile, viewport))
        if self._stealth:
            await context.set_extra_http_headers(StealthProfileManager.get_stealth_headers(profile))
        await context.add_cookies([{
            "name": "li_at", "value": cookie, "domain": ".linkedin.com",
            "path": "/", "httpOnly": True, "secure": True,
        }])
        page = await context.new_page()
        if self._stealth:
            await page.add_init_script(StealthProfileManager.get_stealth_init_script(profile))
        self.human.attach_monitor(page)
        if status_callback:
            status_callback("Préparation de la session LinkedIn…")
        try:
            warmup_ok = await self.human.warmup_session(page, naviguer=self._naviguer)
        except ArretLinkedIn:
            await browser.close()
            raise
        if not warmup_ok:
            await browser.close()
            return None, None
        return browser, page

    async def _lire_une_liste(self, page, url: str, motif_total) -> Optional[listes.ListeLue]:
        """Charge une page de liste (1 page) et la fait défiler (0 page)
        jusqu'à lire tout le monde ou ne plus rien voir arriver.
        None si la page ne se charge pas ou ne se lit pas comme une liste."""
        if not await self._naviguer(page, url):
            return None
        try:
            await page.wait_for_selector('[data-component-type="LazyColumn"]', timeout=8000)
        except Exception:
            pass  # liste vide ou illisible : lire_liste le dira
        await self.human.human_delay(1500, 400)
        try:
            lue = listes.lire_liste(await page.content(), url, motif_total)
        except Exception as e:
            logger.warning(f"  ⚠️ Liste illisible ({url}): {e}")
            return None
        sans_nouveau = 0
        for _ in range(listes.MAX_DEFILEMENTS_LISTE):
            if lue is None or lue.complete or sans_nouveau >= listes.DEFILEMENTS_SANS_NOUVEAU:
                break
            try:
                # La souris au milieu de la fenêtre : la molette fait défiler la
                # liste, pas un bandeau fixe.
                taille = page.viewport_size or {}
                await page.mouse.move(taille.get("width", 1200) / 2, taille.get("height", 800) / 2)
                await self.human.human_scroll_down(page, total_px=1800, scroll_steps=6)
                await self.human.human_delay(1200, 300)
                suite = listes.lire_liste(await page.content(), url, motif_total)
            except Exception as e:
                logger.warning(f"  ⚠️ Défilement de la liste ({url}): {e}")
                break
            if suite is None:
                break
            avant = len(lue.slugs)
            lue = lue.fusionner(suite)
            sans_nouveau = 0 if len(lue.slugs) > avant else sans_nouveau + 1
        return lue

    async def _lire_listes(self, page, lues: dict, status_callback=None) -> None:
        """Remplit `lues` (« envoyees », « relations » : ListeLue, ou None si
        illisible), au plus MAX_PAGES_LISTES pages : les deux listes, puis
        la page suivante de la première qui n'a pas été lue en entier.
        Rempli au fil de l'eau : un arrêt en cours garde ce qui a été lu."""
        a_lire = (
            ("envoyees", listes.URL_INVITATIONS_ENVOYEES, listes.MOTIF_TOTAL_ENVOYEES,
             "Lecture de vos invitations envoyées…"),
            ("relations", listes.URL_RELATIONS, listes.MOTIF_TOTAL_RELATIONS,
             "Lecture de vos relations les plus récentes…"),
        )
        pages = 0
        for cle, url, motif, libelle in a_lire:
            if status_callback:
                status_callback(libelle)
            pages += 1
            lues[cle] = await self._lire_une_liste(page, url, motif)
        if pages >= listes.MAX_PAGES_LISTES:
            return
        for cle, _url, motif, libelle in a_lire:
            lue = lues.get(cle)
            if lue is not None and not lue.complete and lue.suivante:
                if status_callback:
                    status_callback(libelle)
                suite = await self._lire_une_liste(page, lue.suivante, motif)
                if suite is not None:
                    lues[cle] = lue.fusionner(suite)
                return

    def _appliquer_classement(self, classement, acceptees: list) -> None:
        """Reporte le classement des listes dans `acceptees` et `self.verifiees`."""
        for prof in classement.acceptees:
            acceptees.append({"url": prof.get("url"), "nom": prof.get("nom", "")})
            logger.info(f"  ✅ A accepté (liste des relations) : {prof.get('nom', '')}")
        for prof in classement.absentes:
            logger.info(f"  ↩️ Ni dans les invitations envoyées ni dans les relations : "
                        f"{prof.get('nom', '')} (invitation retirée ou refusée, statut inchangé)")
        self.verifiees.extend(classement.verifiees)

    async def _verifier_profils(self, page, profils, acceptees: list,
                                progress_callback=None, status_callback=None) -> int:
        """Repli : ouvre chaque profil et lit son degré dans l'en-tête.
        Rend le nombre de degrés illisibles."""
        illisibles = 0
        total = len(profils)
        for i, prof in enumerate(profils):
            url = prof.get("url"); nom = prof.get("nom", "")
            if status_callback:
                status_callback(f"Vérification {i+1} sur {total} : {nom}")
            try:
                clean_url = url.split('?')[0].rstrip('/') + '/'
                # La porte attend la pause entre pages et arrête tout
                # sur une page d'alerte ou de connexion.
                if not await self._naviguer(page, clean_url):
                    continue
                await self.human.human_delay(1500, 400)
                try:
                    entete = await page.locator("main section").first.inner_text(timeout=5000)
                except Exception as e:
                    logger.warning(f"  ⚠️ En-tête illisible pour {nom}: {e}")
                    entete = ""
                degre = degre_depuis_entete(entete)
                if not degre:
                    illisibles += 1
                    logger.info(f"  ⚠️ Degré illisible : {nom} reste en attente")
                else:
                    # Seul un degré lu fait de la page une page vérifiée.
                    self.verifiees.append(url)
                    if degre == "1er":
                        acceptees.append({"url": url, "nom": nom})
                        logger.info(f"  ✅ A accepté : {nom}")
                    else:
                        logger.info(f"  ⏳ Pas encore 1er degré : {nom} (degré lu : {degre})")
            except ArretLinkedIn:
                raise
            except Exception as e:
                logger.warning(f"  ⚠️ Vérif {nom}: {e}")
            if progress_callback:
                progress_callback(min(0.5 + 0.5 * (i + 1) / total, 1.0))
        return illisibles

    async def verifier_acceptations_async(self, cookie: str, profils,
                                          max_check: int = ScraperConfig.MAX_VERIFICATIONS_PAR_PASSAGE,
                                          progress_callback=None, status_callback=None):
        """Détecte les invitations acceptées en lisant deux listes LinkedIn.

        La liste des invitations envoyées et celle des relations (ajouts
        récents d'abord), au plus MAX_PAGES_LISTES pages pour tout le monde :
        dans les relations, la personne a accepté ; dans les envoyées, elle
        attend encore ; dans aucune des deux alors que les envoyées ont été
        lues en entier, l'invitation a été retirée ou refusée (statut
        inchangé). Les autres — liste illisible, liste pas lue en entier,
        adresse /in/ACoAA… — sont vérifiées sur leur profil (degré « 1er »
        dans l'en-tête), au plus MAX_VERIFICATIONS_PAR_PASSAGE.
        Retourne la liste [{'url','nom'}] des profils ayant accepté ;
        `self.verifiees` garde les URL dont le statut a bien été établi."""
        self.errors = []
        self.verifiees = []
        self._deja_ouvertes = set()
        max_check = min(max_check, self.config.MAX_VERIFICATIONS_PAR_PASSAGE)
        profils = list(profils)
        acceptees = []
        illisibles = 0
        if not profils:
            return acceptees
        lues = {}
        classement = None
        async with async_playwright() as p:
            if status_callback:
                status_callback("Ouverture du navigateur…")
            browser = None
            try:
                browser, page = await self._open_linkedin_page(p, cookie, status_callback)
                if page is None:
                    self.errors.append(SESSION_EXPIREE)
                    return acceptees
                await self._lire_listes(page, lues, status_callback)
                classement = listes.classer(profils, lues.get("envoyees"), lues.get("relations"))
                self._appliquer_classement(classement, acceptees)
                if progress_callback:
                    progress_callback(0.5)
                restants = classement.restants[:max_check]
                if restants and (lues.get("envoyees") is None or lues.get("relations") is None):
                    self.errors.append(listes.LIBELLE_LISTE_ILLISIBLE)
                if restants:
                    logger.info(f"🔎 {len(classement.restants)} invitation(s) sans statut "
                                f"établi par les listes : vérification de {len(restants)} profil(s)")
                    illisibles = await self._verifier_profils(
                        page, restants, acceptees, progress_callback, status_callback)
                if progress_callback:
                    progress_callback(1.0)
            except ArretLinkedIn as arret:
                self._noter_arret(arret)
                if classement is None and lues:
                    # Arrêt pendant les listes : ce qui a été lu reste acquis.
                    self._appliquer_classement(
                        listes.classer(profils, lues.get("envoyees"), lues.get("relations")),
                        acceptees)
            finally:
                if browser is not None:
                    await browser.close()
        if illisibles:
            self.errors.append(f"Degré de relation illisible pour {illisibles} "
                               f"profil{'s' if illisibles > 1 else ''} : ils restent en attente.")
        return acceptees

    async def envoyer_messages_async(self, cookie: str, cibles, message: str,
                                     max_msg: int = ScraperConfig.MAX_MESSAGES_PAR_SEANCE,
                                     progress_callback=None, status_callback=None):
        """Envoie `message` à chaque cible (relation 1er degré), au plus
        MAX_MESSAGES_PAR_SEANCE par séance.
        Retourne la liste [{'url','nom'}] des personnes effectivement messagées."""
        self.errors = []
        self._deja_ouvertes = set()
        max_msg = min(max_msg, self.config.MAX_MESSAGES_PAR_SEANCE)
        cibles = list(cibles)[:max_msg]
        envoyes = []
        if not cibles or not message.strip():
            return envoyes
        async with async_playwright() as p:
            if status_callback:
                status_callback("Ouverture du navigateur…")
            browser = None
            try:
                browser, page = await self._open_linkedin_page(p, cookie, status_callback)
                if page is None:
                    self.errors.append(SESSION_EXPIREE)
                    return envoyes
                total = len(cibles)
                for i, c in enumerate(cibles):
                    url = c.get("url"); nom = c.get("nom", "")
                    if status_callback:
                        status_callback(f"Message {i+1} sur {total} : {nom}")
                    try:
                        # envoyer_message passe par la porte : pause entre
                        # pages comprise, arrêt sur page d'alerte.
                        if await self.envoyer_message(page, url, nom, message):
                            envoyes.append({"url": url, "nom": nom})
                    except ArretLinkedIn:
                        raise
                    except Exception as e:
                        logger.warning(f"  ⚠️ Message {nom}: {e}")
                    if progress_callback:
                        progress_callback(min((i + 1) / total, 1.0))
            except ArretLinkedIn as arret:
                self._noter_arret(arret)
            finally:
                if browser is not None:
                    await browser.close()
        return envoyes

    def _nouvelle_session_humaine(self) -> HumanBehavior:
        """Comportement humain neuf (fatigue remise à zéro), même compteur.

        Recréer `HumanBehavior` sans `limits_file` repartait du fichier
        partagé `config/daily_limits.json` : les recherches Candidats et
        Clients comptaient alors les invitations ailleurs que dans le
        compteur de la personne, celui que lit la jauge du budget.
        """
        return HumanBehavior(fatigue_factor=0.0,
                             limits_file=self.human.daily_limits.limits_file)

    async def run_scraper_async(
        self,
        cookie: str,
        keyword: str,
        entreprises: Union[str, List[str], None],
        nb_profils: int,
        ecoles_ids: List[str],
        secteurs_ids: Optional[List[str]] = None,
        inviter: bool = False,
        email_notif: Optional[str] = None,
        message_invitation: str = "",
        reinviter_profils_scrapes: bool = False,
        ile_de_france: bool = False,
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> pd.DataFrame:
        """
        Exécute le scraping de manière asynchrone

        Args:
            cookie: Cookie li_at LinkedIn
            keyword: Mots-clés de recherche
            entreprises: Entreprise(s) cible(s) — chaîne ou liste (optionnel)
            nb_profils: Nombre de profils à scraper
            ecoles_ids: IDs des écoles
            secteurs_ids: IDs de secteurs LinkedIn (facette industry, optionnel)
            inviter: Si True, envoie des invitations
            email_notif: Email pour notifications (optionnel)
            message_invitation: Message personnalisé pour invitations
            reinviter_profils_scrapes: Si True, réinvite les profils déjà scrapés
            progress_callback: Callback pour mise à jour progression
            status_callback: Callback pour mise à jour statut

        Returns:
            DataFrame avec les profils scrapés
        """
        start_time = datetime.now()
        donnees = []
        self.errors = []
        self.ecartes_reseau = 0
        self._deja_ouvertes = set()
        # Au plus MAX_PROFILES_PER_RUN profils par recherche.
        nb_profils = min(nb_profils, self.config.MAX_PROFILES_PER_RUN)

        # Réinitialiser la fatigue pour chaque nouvelle session
        self.human = self._nouvelle_session_humaine()

        # Plafond d'invitations déjà atteint : refus sans ouvrir Chrome.
        if inviter and not self.human.daily_limits.can_invite():
            self._noter_limite_invitations()
            return pd.DataFrame()

        # Les profils consultés restent une statistique : c'est le budget de
        # pages (porte _naviguer) qui bloque désormais.
        self.human.daily_limits.increment_sessions()

        logger.info(f"🔧 Paramètres: inviter={inviter}, reinviter={reinviter_profils_scrapes}")
        logger.info(f"🤖 Module comportement humain activé (stealth mode)")
        logger.info(f"📊 Limites du jour: {self.human.daily_limits.profiles_today} profils, "
                     f"{self.human.daily_limits.invitations_today} invitations "
                     f"(session #{self.human.daily_limits.sessions_today})")

        # Normaliser les facettes : l'appelant peut passer une chaîne unique
        entreprises = self._as_list(entreprises)
        ecoles_ids = self._as_list(ecoles_ids)
        secteurs_ids = self._as_list(secteurs_ids)

        # Nom(s) de(s) école(s) ciblée(s) par la recherche
        ecole_nom = self._libelle_ecoles(ecoles_ids)

        try:
            async with async_playwright() as p:

                if status_callback:
                    status_callback("Ouverture du navigateur…")

                # Chrome, session, warm-up par la porte de navigation.
                browser, page = await self._open_linkedin_page(p, cookie, status_callback)
                if page is None:
                    logger.error("❌ Warm-up échoué — cookie invalide ?")
                    self.errors.append(SESSION_EXPIREE)
                    return pd.DataFrame()

                profils_scrapes = 0
                invitations_envoyees = 0
                try:
                    # Vérifier la sécurité après le warm-up
                    if not await self.human.check_safety(page):
                        logger.error("❌ Arrêt de sécurité post warm-up")
                        self.errors.append("LinkedIn demande une vérification de sécurité : ouvrez linkedin.com dans Chrome, puis relancez.")
                        return pd.DataFrame()

                    # Résoudre l'URN de l'entreprise via l'API typeahead LinkedIn
                    # (la page est maintenant authentifiée). Si succès, l'URN est
                    # ajouté au cache et utilisé par construire_url_recherche pour
                    # appliquer le vrai filtre `currentCompany` (beaucoup plus précis
                    # que la stratégie "AND keyword").
                    for entreprise in entreprises:
                        if status_callback:
                            status_callback(f"Identification de l'entreprise « {entreprise} »…")
                        urn = await self._resoudre_company_urn_via_typeahead(entreprise, page)
                        # Fallback navigation désactivé : /search/results/companies
                        # boucle en redirections depuis une IP datacenter et n'apporte
                        # rien de plus que le typeahead + le seed config.COMPANY_URNS.
                        if not urn:
                            logger.warning(
                                f"⚠️ URN entreprise '{entreprise}' non résolu (typeahead) — "
                                f"toute la facette entreprise bascule en recherche par mot-clé."
                            )

                    # Construire l'URL de recherche
                    url_recherche = self.construire_url_recherche(
                        keyword, entreprises, ecoles_ids, ile_de_france, secteurs_ids
                    )

                    if status_callback:
                        status_callback("Chargement des résultats LinkedIn…")

                    logger.info(f"Accès URL : {url_recherche}")

                    # Charger la première page (porte : pause, compte, détecteur)
                    success = await self._naviguer(page, url_recherche + "&page=1")

                    if not success:
                        # Distinguer le cas "cookie expiré" (boucle de redirections) d'une
                        # vraie erreur réseau pour donner un message d'erreur exploitable.
                        last_err = ""
                        try:
                            last_err = str(self.network_manager.last_error or "")
                        except Exception:
                            pass
                        if "ERR_TOO_MANY_REDIRECTS" in last_err or "login" in page.url:
                            msg = ("Session LinkedIn expirée (boucle de "
                                   "redirections). Reconnectez-vous à linkedin.com, "
                                   "puis mettez à jour votre session dans la page "
                                   "Recherche.")
                            logger.error(f"❌ {msg}")
                            self.errors.append(msg)
                        else:
                            logger.error("❌ Impossible de charger la page de recherche")
                            self.errors.append("Impossible de charger la page de recherche")
                        return pd.DataFrame()

                    # Comportement humain à l'arrivée sur la page (une redirection
                    # vers la connexion a déjà arrêté la porte de navigation)
                    await self.human.page_entry_behavior(page)

                    # Charger les profils déjà scrapés
                    deja_scrapes_global = self._charger_urls_scrappees()
                    logger.info(f"📚 {len(deja_scrapes_global)} profils déjà scrapés chargés")

                    urls_session = set()
                    profils_scrapes = 0
                    invitations_envoyees = 0
                    current_page = 1

                    # BOUCLE PRINCIPALE DE SCRAPING
                    # Si on envoie des invitations, on continue jusqu'à avoir le nombre d'invitations demandé
                    # Sinon, on continue jusqu'à avoir le nombre de profils scrapés demandé
                    while (inviter and invitations_envoyees < nb_profils) or (not inviter and profils_scrapes < nb_profils):

                        if status_callback:
                            status_callback(f"Lecture de la page {current_page} des résultats…")

                        logger.info(f"═══ Scraping page {current_page} ═══")

                        # ═══ CHECK SÉCURITÉ à chaque page ═══
                        if not await self.human.check_safety(page):
                            logger.error("🛑 Arrêt de sécurité en cours de scraping")
                            self.errors.append("Arrêt par précaution : LinkedIn a montré un signal de limitation. Réessayez plus tard.")
                            break

                        # Simuler la navigation naturelle sur la page (scroll, lecture)
                        await self.human.browse_page_naturally(page)

                        # Distraction aléatoire occasionnelle (5% de chance)
                        await self.human.simulate_distraction(probability=0.05)

                        # Screenshot de debug sur la première page
                        if current_page == 1:
                            try:
                                await page.screenshot(path="debug_linkedin_v2.png")
                                logger.info("📸 Screenshot sauvegardé: debug_linkedin_v2.png")
                            except Exception as e:
                                logger.warning(f"Erreur screenshot: {e}")

                        # Extraire les profils de la page
                        profiles_page = await self.extraire_profils_page(page)

                        if not profiles_page:
                            logger.warning("⚠️ Aucun profil trouvé sur cette page")
                            if current_page == 1:
                                ou = await diagnostiquer_page_vide(page, self._dumper_panneau,
                                                                   "recherche_resultats_dump.html")
                                if ou:
                                    self.errors.append(lecture_ratee(ou))
                            break

                        logger.info(f"📋 {len(profiles_page)} profils à traiter sur cette page")

                        # Pause avant chaque invitation sauf la première de la
                        # page : la porte attend déjà avant la page suivante.
                        deja_invite_sur_la_page = False

                        # Traiter chaque profil
                        for profile in profiles_page:

                            # Vérifier la limite selon le mode
                            if inviter:
                                if invitations_envoyees >= nb_profils:
                                    logger.info(f"✋ Limite de {nb_profils} invitations atteinte")
                                    break
                                # Plafond du jour bloquant : on s'arrête là. Les
                                # profils non invités ne sont pas enregistrés en
                                # mode invitation : ils resteront invitables.
                                if not self.human.daily_limits.can_invite():
                                    self._noter_limite_invitations()
                                    break
                            else:
                                if profils_scrapes >= nb_profils:
                                    logger.info(f"✋ Limite de {nb_profils} profils atteinte")
                                    break

                            url_profil = profile['url']
                            nom = profile['nom']

                            # Vérifier si déjà vu dans cette session
                            if url_profil in urls_session:
                                logger.info(f"⏭️ {nom} - Déjà vu dans cette session")
                                continue

                            if deja_en_relation_ou_invite(profile):
                                urls_session.add(url_profil)
                                self.ecartes_reseau += 1
                                logger.info(f"⏭️ {nom} - Déjà en relation ou invitation en attente")
                                continue

                            # Vérifier si déjà scrapé globalement
                            if url_profil in deja_scrapes_global and not reinviter_profils_scrapes:
                                logger.info(f"⏭️ {nom} - Déjà scrapé précédemment")
                                continue

                            urls_session.add(url_profil)

                            # Compteur pour affichage
                            num_affichage = invitations_envoyees + 1 if inviter else profils_scrapes + 1
                            logger.info(f"👤 Profil #{num_affichage}: {nom}")
                            logger.info(f"   📋 Poste: {profile['poste']}")
                            logger.info(f"   🏢 Entreprise: {profile['entreprise']}")

                            # Marquer comme déjà scrapé
                            deja_scrape = url_profil in deja_scrapes_global

                            # Envoi d'invitation si demandé
                            invite_envoyee = False
                            if inviter:
                                if status_callback:
                                    status_callback(f"Invitation de {nom}…")

                                try:
                                    if deja_invite_sur_la_page:
                                        await self.human.pause_entre_pages()
                                    deja_invite_sur_la_page = True
                                    invite_envoyee = await self.envoyer_invitation(
                                        page,
                                        url_profil,
                                        nom,
                                        message_invitation
                                    )

                                    if invite_envoyee:
                                        invitations_envoyees += 1
                                        self.human.daily_limits.increment_invitations()
                                        logger.info(f"   📊 Progression: {invitations_envoyees}/{nb_profils} invitations "
                                                    f"(jour: {self.human.daily_limits.invitations_today})")

                                    # Augmenter légèrement la fatigue au fil des invitations
                                    self.human.increase_fatigue(0.02)

                                except ArretLinkedIn:
                                    raise
                                except Exception as e:
                                    logger.error(f"❌ Erreur invitation {nom}: {e}")
                                    self.errors.append(f"Erreur invitation {nom}: {e}")

                            # Sauvegarder le profil seulement si invitation envoyée OU si mode scraping sans invitation
                            if invite_envoyee or not inviter:
                                # Sauvegarder le profil
                                self._sauvegarder_profil(
                                    profile['nom'],
                                    profile['poste'],
                                    profile['entreprise'],
                                    ecole_nom,
                                    url_profil,
                                    invite_envoyee
                                )

                                # Sauvegarder dans la DB
                                if self.use_database and self.db:
                                    try:
                                        profile_id = self.db.ajouter_profil(
                                            nom=profile['nom'],
                                            poste=profile['poste'],
                                            entreprise=profile['entreprise'],
                                            ecole=ecole_nom,
                                            url=url_profil,
                                            localisation=profile.get('localisation', ''),
                                            nb_connexions=profile.get('connexions', '')
                                        )

                                        if invite_envoyee and profile_id:
                                            self.db.ajouter_invitation(profile_id, message_invitation)

                                    except Exception as e:
                                        logger.error(f"Erreur sauvegarde DB: {e}")

                                # Ajouter aux données finales
                                donnees.append(ProfileExtractor.format_for_display(
                                    profile,
                                    ecole_nom,
                                    invite_envoyee
                                ))

                                profils_scrapes += 1
                                self.human.daily_limits.increment_profiles()

                            # Mettre à jour la progression
                            if progress_callback:
                                if inviter:
                                    progress_callback(min(invitations_envoyees / nb_profils, 1.0))
                                else:
                                    progress_callback(min(profils_scrapes / nb_profils, 1.0))

                        # Plafond du jour atteint avant le nombre demandé : pas de
                        # page de résultats de plus pour des invitations qui ne
                        # partiront pas.
                        if (inviter and invitations_envoyees < nb_profils
                                and not self.human.daily_limits.can_invite()):
                            self._noter_limite_invitations()
                            break

                        # PAGE SUIVANTE
                        # Vérifier si on a atteint la limite selon le mode
                        continuer = (inviter and invitations_envoyees < nb_profils) or (not inviter and profils_scrapes < nb_profils)

                        if continuer:
                            current_page += 1
                            logger.info(f"➡️ Passage à la page {current_page}")

                            next_url = url_recherche + f"&page={current_page}"
                            success = await self._naviguer(page, next_url)

                            if not success:
                                logger.warning("⚠️ Impossible de charger la page suivante")
                                break

                            # Comportement humain sur la nouvelle page
                            await self.human.page_entry_behavior(page)
                        else:
                            break

                except ArretLinkedIn as arret:
                    # Alerte, connexion ou budget : on garde ce qui est fait
                    # (déjà enregistré profil par profil), on s'arrête là.
                    self._noter_arret(arret)
                finally:
                    # Fermer le navigateur
                    await browser.close()

                # Statistiques finales
                duration = (datetime.now() - start_time).total_seconds()

                logger.info(f"\n{'═'*60}")
                logger.info(f"✅ SCRAPING TERMINÉ")
                logger.info(f"   Profils scrapés: {profils_scrapes}")
                logger.info(f"   Invitations envoyées: {invitations_envoyees}")
                logger.info(f"   Durée: {duration:.1f}s")
                logger.info(f"{'═'*60}\n")

                # Sauvegarder la recherche dans la DB
                if self.use_database and self.db:
                    try:
                        self.db.sauvegarder_recherche(
                            keyword=keyword,
                            entreprise=", ".join(entreprises),
                            ecole=ecole_nom,
                            nb_profils=profils_scrapes,
                            nb_invitations=invitations_envoyees,
                            duree=int(duration),
                            erreurs=self.errors
                        )
                    except Exception as e:
                        logger.error(f"Erreur sauvegarde recherche: {e}")

                # Envoyer notification email si configuré
                if email_notif:
                    try:
                        from email_notifier import EmailNotifier
                        notifier = EmailNotifier(email_notif)
                        notifier.send_scraping_complete(
                            keyword=keyword,
                            nb_profils=profils_scrapes,
                            nb_invitations=invitations_envoyees,
                            ecoles=[ecole_nom] if ecole_nom else None,
                            duration=duration,
                            errors=self.errors
                        )
                    except Exception as e:
                        logger.warning(f"Erreur notification email: {e}")

                return pd.DataFrame(donnees)

        except ArretLinkedIn as arret:
            # Refus ou alerte dès le warm-up : Chrome est déjà fermé.
            self._noter_arret(arret)
            return pd.DataFrame(donnees)

        except PermanentNetworkError as e:
            self.errors.append(f"Erreur permanente: {e}")
            logger.error(f"❌ Erreur permanente: {e}")

            if email_notif:
                try:
                    from email_notifier import EmailNotifier
                    notifier = EmailNotifier(email_notif)
                    notifier.send_error_notification(str(e), context="Scraping LinkedIn V2")
                except:
                    pass

            return pd.DataFrame()

        except Exception as e:
            self.errors.append(str(e))
            logger.error(f"❌ Erreur critique: {e}", exc_info=True)

            if email_notif:
                try:
                    from email_notifier import EmailNotifier
                    notifier = EmailNotifier(email_notif)
                    notifier.send_error_notification(str(e), context="Scraping LinkedIn V2")
                except:
                    pass

            return pd.DataFrame()

    def _charger_urls_scrappees(self) -> set:
        """Charge les URLs depuis la base de données ET le CSV legacy"""
        urls = set()

        # 1. Charger depuis la base de données
        if self.use_database and self.db:
            try:
                import sqlite3
                conn = sqlite3.connect(self.db.db_file)
                cursor = conn.cursor()
                cursor.execute("SELECT url FROM profiles WHERE url IS NOT NULL AND url != ''")
                urls.update(row[0] for row in cursor.fetchall())
                conn.close()
                logger.debug(f"📊 {len(urls)} URLs chargées depuis la DB")
            except Exception as e:
                logger.warning(f"Erreur chargement URLs depuis DB: {e}")

        # 2. Charger aussi depuis le CSV (compatibilité)
        import os, csv
        if os.path.exists(self.profil_file):
            try:
                with open(self.profil_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    csv_urls = set(row.get("URL du profil", "") for row in reader if row.get("URL du profil"))
                    urls.update(csv_urls)
                    logger.debug(f"📊 Total {len(urls)} URLs uniques (DB + CSV)")
            except Exception as e:
                logger.warning(f"Erreur chargement URLs depuis CSV: {e}")

        return urls

    def _enregistrer_invitation(self, url: str, nom: str, profile_data: dict, message: str) -> None:
        """Enregistre en base une invitation envoyée, même si le profil n'a pas pu être lu.
        Ne touche pas à une école déjà connue (ecole='') et n'échoue jamais.
        Sans extraction, `nom` est tiré du lien : il ne sert que pour un profil
        nouveau (la colonne est obligatoire) et n'écrase jamais un vrai nom."""
        if not (self.use_database and self.db):
            return
        try:
            if not profile_data.get('nom') and self.db.profil_existe(url):
                nom = ''
            profile_id = self.db.ajouter_profil(
                nom=nom, poste=profile_data.get('poste', ''),
                entreprise=profile_data.get('entreprise', ''), ecole='', url=url)
            self.db.ajouter_invitation(profile_id, message)
        except Exception as e:
            logger.error(f"  Erreur enregistrement invitation: {e}")

    def _sauvegarder_profil(self, nom: str, poste: str, entreprise: str,
                            ecole: str, url: str, invite: bool):
        """Sauvegarde un profil dans le CSV (rétrocompatibilité)"""
        import os, csv

        deja = self._charger_urls_scrappees()

        if url and url not in deja:
            champs = ["Nom", "Poste", "Entreprise", "École",
                      "URL du profil", "Date", "Invitation"]

            existe = os.path.exists(self.profil_file)

            try:
                with open(self.profil_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=champs)
                    if not existe:
                        writer.writeheader()

                    writer.writerow({
                        "Nom": nom,
                        "Poste": poste,
                        "Entreprise": entreprise,
                        "École": ecole,
                        "URL du profil": url,
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Invitation": "Oui" if invite else "Non",
                    })
            except Exception as e:
                logger.error(f"Erreur sauvegarde CSV: {e}")

    # ==================================================================
    # SCRAPING PAR URLs DIRECTES
    # ==================================================================

    async def extraire_profil_depuis_page(self, page: Page) -> dict:
        """
        Extrait nom, poste et société depuis une page de profil LinkedIn ouverte.
        Utilise JavaScript car LinkedIn obfusque les classes CSS.
        """
        data = await page.evaluate("""() => {
            let nom = '', fonction = '', societe = '';

            const main = document.querySelector('main') || document.querySelector('[role="main"]');
            const section = main ? main.querySelector('section') : document.querySelector('section');
            if (!section) return {nom, fonction, societe};

            // ── NOM ──
            const h1 = section.querySelector('h1');
            nom = h1 ? h1.textContent.trim() : '';

            // ── FONCTION (headline) ──
            const noise = ['abonné', 'relation', 'coordonnées', 'premium', 'réactivez',
                           'reactivate', 'suivre', '· 1er', '· 2e', '· 3e', 'upgrade',
                           'notification', 'message', 'accueil', 'emploi', 'commenter',
                           '50%', 'essai gratuit', 'en commun', 'profil', 'plus de'];
            const allP = section.querySelectorAll('p');
            for (const p of allP) {
                const txt = p.textContent.trim();
                if (txt.length < 10 || txt.length > 300) continue;
                if (txt === nom || nom.includes(txt)) continue;
                const lower = txt.toLowerCase();
                if (noise.some(n => lower.includes(n))) continue;
                fonction = txt;
                break;
            }

            // ── SOCIETE ──
            // Méthode 1 : image company-logo
            const companyImgs = document.querySelectorAll('img[src*="company-logo"]');
            for (const img of companyImgs) {
                let container = img.closest('[role="button"]') || img.closest('a');
                if (!container) container = img.parentElement?.parentElement?.parentElement;
                if (container) {
                    const ps = container.querySelectorAll('p');
                    for (const p of ps) {
                        const txt = p.textContent.trim();
                        if (txt.length > 1 && txt.length < 100
                            && !txt.toLowerCase().includes('premium')
                            && !txt.toLowerCase().includes('abonné')) {
                            societe = txt;
                            break;
                        }
                    }
                }
                if (societe) break;
            }

            // Méthode 2 : SVG company icon
            if (!societe) {
                const icons = document.querySelectorAll('svg[id*="company"]');
                for (const icon of icons) {
                    let fig = icon.closest('figure');
                    if (!fig) continue;
                    let wrapper = fig.parentElement?.closest('div') || fig.parentElement;
                    if (wrapper) {
                        const ps = wrapper.querySelectorAll('p');
                        for (const p of ps) {
                            const txt = p.textContent.trim();
                            if (txt.length > 1 && txt.length < 100
                                && !txt.toLowerCase().includes('premium')
                                && !txt.toLowerCase().includes('abonné')) {
                                societe = txt;
                                break;
                            }
                        }
                    }
                    if (societe) break;
                }
            }

            return {nom, fonction, societe};
        }""")

        return {
            'nom': (data.get('nom') or '').strip(),
            'poste': (data.get('fonction') or '').strip(),
            'entreprise': (data.get('societe') or '').strip(),
        }

    # ==================================================================
    # PROFILS VOISINS (panneau « Plus de profils pour vous »)
    # ==================================================================

    async def _derouler_panneau(self, page: Page, limite_tours: int = 12) -> int:
        """Déroule le panneau jusqu'à ce qu'il cesse de s'allonger.

        Au premier essai réel, 20 profils et pas un de plus au déroulement :
        on garde quand même la boucle, LinkedIn peut paginer demain. Le
        panneau choisi, compté et poussé est le même que celui qu'on lit —
        les trois scripts partagent `choisirPanneau`.

        `limite_tours` borne la boucle : un panneau qui s'alimenterait sans
        fin ne doit pas immobiliser l'outil.
        """
        compter = DOMSelectors.compter_panneau_browsemap_js()
        pousser = DOMSelectors.derouler_panneau_browsemap_js()
        precedent = -1
        stables = 0
        for _ in range(limite_tours):
            actuel = await page.evaluate(compter)
            # Deux lectures stables d'affilée : une seule peut tomber pendant
            # que LinkedIn charge la suite, et couperait la liste trop tôt.
            if actuel == precedent:
                stables += 1
                if stables >= 2:
                    break
            else:
                stables = 0
            precedent = actuel
            await page.evaluate(pousser)
            await self.human.human_delay(1200, 300)

        logger.info(f"📜 Panneau déroulé : {precedent} profils visibles")
        return max(precedent, 0)

    def _dumper_panneau(self, html: str, nom_fichier: str = 'browsemap_dump.html') -> bool:
        """Écrit le panneau sur disque quand on n'y a rien lu.

        Même geste que `extraire_profils_page` : le jour où LinkedIn change sa
        structure, la seule façon de la rattraper est d'avoir le HTML sous les
        yeux — faute de quoi on cherche à l'aveugle. `nom_fichier` : la veille
        a son propre dump, pour ne pas écraser celui des Profils similaires.
        """
        if not html:
            return False
        try:
            dossier = Path(__file__).parent / 'logs'
            dossier.mkdir(exist_ok=True)
            fichier = dossier / nom_fichier
            fichier.write_text(html, encoding='utf-8')
            logger.warning(f"⚠️ Panneau illisible — HTML enregistré dans {fichier}")
            return True
        except Exception as err:
            logger.warning(f"⚠️ Impossible d'enregistrer le panneau: {err}")
            return False

    async def _entreprise_reference(self, page: Page) -> Optional[str]:
        """Entreprise actuelle du profil de référence, ou None.

        `extraire_profil_depuis_page` cherche les logos d'entreprise dans
        tout le document : ici, il y piocherait celui d'une carte voisine du
        panneau et rendrait une entreprise fausse mais crédible. On borne donc
        la recherche à la carte de tête du profil, hors de tout dialogue.
        None vaut « non lue » : l'appelant la demande à la personne.
        """
        societe = await page.evaluate("""() => {
            const hors = el => !el.closest('dialog, [role="dialog"]');
            const main = document.querySelector('main');
            if (!main) return '';
            const section = main.querySelector('section') || main;
            const lire = conteneur => {
                for (const p of conteneur.querySelectorAll('p')) {
                    const txt = p.textContent.trim();
                    const bas = txt.toLowerCase();
                    if (txt.length > 1 && txt.length < 100
                        && !bas.includes('premium') && !bas.includes('abonné')) {
                        return txt;
                    }
                }
                return '';
            };
            for (const img of section.querySelectorAll('img[src*="company-logo"]')) {
                if (!hors(img)) continue;
                const c = img.closest('[role="button"]') || img.closest('a')
                       || img.parentElement?.parentElement?.parentElement;
                const t = c ? lire(c) : '';
                if (t) return t;
            }
            for (const icone of section.querySelectorAll('svg[id*="company"]')) {
                if (!hors(icone)) continue;
                const fig = icone.closest('figure');
                if (!fig) continue;
                const w = fig.parentElement?.closest('div') || fig.parentElement;
                const t = w ? lire(w) : '';
                if (t) return t;
            }
            return '';
        }""")
        return (societe or '').strip() or None

    @staticmethod
    def _est_page_de_connexion(url: str) -> bool:
        """Vrai si LinkedIn nous a renvoyés vers sa connexion.

        Segments de chemin, pas sous-chaînes : /in/jean-loginov/ est un
        profil, pas une page de connexion.
        """
        chemin = urllib.parse.urlparse(url or "").path
        return chemin.startswith(("/login", "/authwall", "/checkpoint", "/uas/login"))

    async def _ouvrir_panneau(self, page: Page) -> Optional[str]:
        """Clique sur « Tout afficher » ; rend None si le panneau est ouvert.

        Sinon, rend la raison de l'échec, en clair : elle finit dans
        l'avertissement affiché à la personne.

        Pourquoi un clic : chargée directement, l'URL de l'overlay redirige
        vers le profil nu (premier essai réel). Le panneau ne s'ouvre que par
        le lien de la section, en routage côté client — comme pour une
        personne, qui défile jusqu'au lien, marque un temps, puis clique.
        """
        selecteur = f'a[href*="/{CHEMIN_PANNEAU.rstrip("/")}"]'
        try:
            lien = await page.wait_for_selector(selecteur, state="attached", timeout=8000)
        except Exception as err:
            logger.info(f"Lien « Tout afficher » introuvable : {err}")
            lien = None
        if lien is None:
            return "le lien « Tout afficher » de la section est introuvable"

        # Le panneau est une page : mêmes budgets, même pause, même compte et
        # même détecteur que la porte _naviguer — le clic ne les contourne pas.
        self._avant_page()
        await self.human.pause_entre_pages()
        try:
            await lien.scroll_into_view_if_needed()
            await self.human.human_delay(900, 300)
            try:
                await self.human.human_hover_and_click(page, lien)
            finally:
                self._compter_page()
        except Exception as err:
            logger.warning(f"⚠️ Clic sur « Tout afficher » impossible : {err}")
            await self._controler_arrivee(page, "le panneau des profils similaires")
            return "le clic sur « Tout afficher » a échoué"

        # Borné : un panneau qui ne vient pas ne doit pas immobiliser l'outil,
        # on se rabat alors sur la section, avec un avertissement.
        attente = "() => (" + DOMSelectors.compter_panneau_browsemap_js() + ")() > 0"
        echec = None
        try:
            await page.wait_for_function(attente, timeout=10000)
        except Exception as err:
            logger.warning(f"⚠️ Panneau des profils voisins absent après le clic : {err}")
            echec = "le panneau ne s'est pas ouvert après le clic sur « Tout afficher »"
        # Pas de statut HTTP ici : routage côté client, aucun chargement.
        await self._controler_arrivee(page, "le panneau des profils similaires")
        return echec

    async def recolter_browsemap_async(
        self,
        cookie: str,
        url_reference: str,
        status_callback: Optional[Callable] = None
    ) -> tuple:
        """Profils voisins que LinkedIn propose pour `url_reference`.

        Rend `(suggestions, entreprise_reference)`. Ne scrape rien et n'invite
        personne : la liste d'URLs part ensuite dans `run_url_scraper`, qui
        fait déjà les deux.

        Parcours : la page du profil, puis un clic sur « Tout afficher » qui
        ouvre le panneau complet (≈20 profils). Si le lien manque ou que le
        panneau ne vient pas, on lit la section de la page du profil, qui
        n'en montre que les premiers (≈5) — et on le dit, sans bloquer.

        `entreprise_reference` vaut None si la page n'a pas permis de la lire.
        L'appelant la demande alors à la personne plutôt que d'abandonner
        l'exclusion « ailleurs » en silence.
        """
        self.errors = []
        self._deja_ouvertes = set()

        cible = normaliser_url(url_reference)
        if cible is None:
            # Refusé avant tout lancement : ouvrir Chrome pour apprendre ça
            # deux minutes plus tard n'aiderait personne.
            self.errors.append(
                "Ce lien n'est pas celui d'un profil LinkedIn "
                "(il doit contenir « /in/ »)."
            )
            return [], None

        reference = vanity_depuis_url(url_reference)

        async with async_playwright() as p:
            if status_callback:
                status_callback("Ouverture du navigateur…")

            browser = None
            try:
                browser, page = await self._open_linkedin_page(p, cookie, status_callback)
                if page is None:
                    self.errors.append(SESSION_EXPIREE)
                    return [], None

                if status_callback:
                    status_callback("Ouverture du profil de référence…")

                # Connexion ou alerte à l'arrivée : ArretLinkedIn, traité plus bas.
                if not await self._naviguer(page, cible):
                    self.errors.append(f"Impossible d'ouvrir le profil : {cible}")
                    return [], None

                await self.human.human_delay(2000, 500)

                # L'entreprise actuelle du profil de référence, lue avant
                # d'ouvrir le panneau, tant que rien ne recouvre le profil :
                # c'est tout ce dont le « ailleurs » a besoin.
                entreprise = await self._entreprise_reference(page)

                if status_callback:
                    status_callback("Ouverture des profils similaires…")
                echec_ouverture = await self._ouvrir_panneau(page)

                # Le clic change l'URL (routage côté client) : une session
                # expirée peut s'y révéler.
                if self._est_page_de_connexion(page.url):
                    self.errors.append(SESSION_EXPIREE)
                    return [], None

                if echec_ouverture is None:
                    if status_callback:
                        status_callback("Lecture de la liste…")
                    await self._derouler_panneau(page)
                    brut = await page.evaluate(DOMSelectors.extract_browsemap_js(), "panneau")
                else:
                    # Un panneau ouvert mais illisible n'arrive pas ici : ce
                    # serait un changement de structure, qu'on crie plus bas
                    # au lieu de le masquer derrière les 5 de la section.
                    if status_callback:
                        status_callback("Lecture de la section du profil…")
                    brut = await page.evaluate(DOMSelectors.extract_browsemap_js(), "section")

                entrees = brut.get("entrees", [])
                # Le JS rend toujours le HTML ; c'est ici qu'on décide de
                # l'enregistrer, chaque fois que la lecture est douteuse.
                html = brut.get("html", "") or ""

                # Le lien du profil de référence peut figurer dans la page :
                # ce n'est pas une suggestion. Le contrôle de vide porte sur
                # ce qui reste, sinon une lecture qui ne trouve que ce lien
                # rendrait une liste vide sans un mot.
                suggestions = [
                    e for e in entrees
                    if vanity_depuis_url(e.get("url")) not in (None, reference)
                ]

                # Des noms tous identiques trahissent des cartes fusionnées :
                # mieux vaut un échec bruyant que N copies d'une même personne.
                if len(suggestions) >= 2 and len({e.get("nom") for e in suggestions}) == 1:
                    self.errors.append(
                        "Le panneau a été lu de travers (toutes les entrées "
                        "portent le même nom) : sa structure a probablement "
                        "changé."
                    )
                    self._dumper_panneau(html)
                    return [], entreprise

                if not suggestions:
                    enregistre = self._dumper_panneau(html)
                    suite = (
                        "le contenu de la page est enregistré dans logs/ "
                        "pour analyse." if enregistre
                        else "le contenu de la page n'a pas pu être enregistré."
                    )
                    ou = (
                        "dans le panneau" if echec_ouverture is None
                        else f"({echec_ouverture}, et la section « Plus de "
                             f"profils pour vous » du profil est vide ou "
                             f"introuvable)"
                    )
                    self.errors.append(
                        f"Aucun profil voisin lu {ou}. Si ce profil en "
                        "affiche bien sur LinkedIn, sa structure a changé : "
                        + suite
                    )
                    return [], entreprise

                if echec_ouverture is not None:
                    # Non bloquant : la liste est juste, mais courte. La
                    # personne doit savoir qu'il en existe davantage.
                    self.errors.append(
                        f"Liste partielle ({echec_ouverture}) : seuls les "
                        f"{len(suggestions)} profils visibles sur la page du "
                        "profil ont été lus — le panneau complet en propose "
                        "habituellement une vingtaine."
                    )

                # Avertissements : la liste est peut-être juste, mais deux
                # lectures à vide d'un champ entier trahissent plutôt un
                # sélecteur périmé. On rend quand même les suggestions, avec
                # de quoi se méfier — et le HTML pour comprendre.
                if not any((e.get("degre") or "").strip() for e in suggestions):
                    self.errors.append(
                        "Degré de relation illisible : les relations de 1er "
                        "degré n'ont pas pu être écartées. Vérifiez la liste."
                    )
                    self._dumper_panneau(html)
                if not any(e.get("invitable") for e in suggestions):
                    self.errors.append(
                        "Aucun bouton « Se connecter » lu : la détection a "
                        "peut-être changé ; vérifiez avant de filtrer sur les "
                        "invitables."
                    )
                    self._dumper_panneau(html)

                logger.info(f"✅ {len(suggestions)} profils voisins retenus")
                return suggestions, entreprise

            except ArretLinkedIn as arret:
                self._noter_arret(arret)
                return [], None
            finally:
                if browser is not None:
                    await browser.close()

    async def run_url_scraper_async(
        self,
        cookie: str,
        urls: List[str],
        inviter: bool = False,
        message_invitation: str = "",
        message_direct: str = "",
        progress_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None
    ) -> pd.DataFrame:
        """
        Scrape des profils LinkedIn à partir d'une liste d'URLs directes.
        Ouvre un navigateur visible, visite chaque profil et extrait les infos.
        """
        self.errors = []
        self._deja_ouvertes = set()
        start_time = datetime.now()
        donnees = []

        # Nettoyer les URLs
        urls = [u.strip() for u in urls if u.strip() and '/in/' in u]
        total = len(urls)

        if total == 0:
            self.errors.append("Aucune URL LinkedIn valide fournie")
            return pd.DataFrame()

        # Plafond d'invitations déjà atteint : refus sans ouvrir Chrome.
        if inviter and not self.human.daily_limits.can_invite():
            self._noter_limite_invitations()
            return pd.DataFrame()

        logger.info(f"🔗 Scraping de {total} URLs de profils LinkedIn")

        try:
            async with async_playwright() as p:

                if status_callback:
                    status_callback("Ouverture du navigateur…")

                # Chrome, session, warm-up par la porte de navigation.
                browser, page = await self._open_linkedin_page(p, cookie, status_callback)
                if page is None:
                    logger.error("❌ Cookie invalide ou expiré (warm-up)")
                    self.errors.append(SESSION_EXPIREE)
                    return pd.DataFrame()

                logger.info("✅ Session LinkedIn active")

                try:
                    # ── Boucle sur les URLs ──
                    for i, url in enumerate(urls):
                        nom_affiche = url.split('/in/')[-1].strip('/').replace('-', ' ').title()
                        logger.info(f"[{i+1}/{total}] {nom_affiche}")

                        if status_callback:
                            status_callback(f"Profil {i+1} sur {total} : {nom_affiche}")

                        try:
                            # La porte attend la pause entre pages, compte la
                            # page et arrête tout sur une alerte ou la connexion.
                            success = await self._naviguer(page, url)
                            if not success:
                                logger.warning(f"  ⚠️ Impossible de charger {url}")
                                self.errors.append(f"Erreur chargement: {url}")
                                continue

                            # Comportement humain : scroll + lecture
                            await self.human.browse_page_naturally(page)

                            # Extraire les données du profil
                            profile_data = await self.extraire_profil_depuis_page(page)
                            profile_data['url'] = url
                            nom = profile_data.get('nom') or nom_affiche

                            if profile_data.get('nom'):
                                logger.info(f"  ✅ {profile_data['nom']} | {profile_data['poste']} | {profile_data['entreprise']}")
                                if self.use_database and self.db:
                                    try:
                                        self.db.ajouter_profil(
                                            nom=profile_data['nom'], poste=profile_data['poste'],
                                            entreprise=profile_data['entreprise'], ecole='',
                                            url=url, localisation='', nb_connexions=''
                                        )
                                    except Exception as e:
                                        logger.error(f"  Erreur DB: {e}")
                                self._sauvegarder_profil(
                                    profile_data['nom'], profile_data['poste'],
                                    profile_data['entreprise'], '', url, False
                                )
                            else:
                                logger.warning("  ⚠️ Données profil non extraites (invitation/message tentés quand même)")

                            ligne = {
                                'Nom': nom,
                                'Poste': profile_data.get('poste', ''),
                                'Entreprise': profile_data.get('entreprise', ''),
                                'URL': url,
                                'Date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            }

                            # Invitation — INDÉPENDANTE de l'extraction du profil.
                            # Plafond du jour atteint : plus d'invitation, mais
                            # l'extraction (déjà faite) et le message continuent.
                            if inviter and not self.human.daily_limits.can_invite():
                                self._noter_limite_invitations()
                                ligne['Invitation'] = 'Non'
                            elif inviter:
                                try:
                                    invited = await self.envoyer_invitation(page, url, nom, message_invitation)
                                    ligne['Invitation'] = 'Oui' if invited else 'Non'
                                    if invited:
                                        self.human.daily_limits.increment_invitations()
                                        self._enregistrer_invitation(url, nom, profile_data, message_invitation)
                                except ArretLinkedIn:
                                    raise
                                except Exception as _e:
                                    logger.warning(f"  ⚠️ Invitation échouée: {_e}")
                                    ligne['Invitation'] = 'Non'

                            # Message direct — INDÉPENDANT de l'extraction du profil
                            if message_direct.strip():
                                try:
                                    sent = await self.envoyer_message(page, url, nom, message_direct)
                                    ligne['Message'] = 'Oui' if sent else 'Non'
                                except ArretLinkedIn:
                                    raise
                                except Exception as _e:
                                    logger.warning(f"  ⚠️ Message échoué: {_e}")
                                    ligne['Message'] = 'Non'

                            donnees.append(ligne)

                        except ArretLinkedIn:
                            raise
                        except Exception as e:
                            logger.error(f"  ❌ Erreur: {e}")
                            self.errors.append(f"Erreur {url}: {e}")

                        # Progression
                        if progress_callback:
                            progress_callback(min((i + 1) / total, 1.0))

                        # Le délai entre deux profils est la pause de la porte
                        # de navigation, au chargement du suivant.
                        self.human.increase_fatigue(0.01)

                except ArretLinkedIn as arret:
                    # Alerte, connexion ou budget : on garde ce qui est fait,
                    # l'action en cours n'est pas ajoutée.
                    self._noter_arret(arret)
                finally:
                    await browser.close()

                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"\n{'═'*60}")
                logger.info(f"✅ SCRAPING URLs TERMINÉ")
                logger.info(f"   Profils extraits: {len(donnees)}/{total}")
                logger.info(f"   Durée: {duration:.1f}s")
                logger.info(f"{'═'*60}\n")

                return pd.DataFrame(donnees)

        except ArretLinkedIn as arret:
            # Refus ou alerte dès le warm-up : Chrome est déjà fermé.
            self._noter_arret(arret)
            return pd.DataFrame(donnees)

        except Exception as e:
            self.errors.append(str(e))
            logger.error(f"❌ Erreur critique: {e}", exc_info=True)
            return pd.DataFrame()
