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

from config import ScraperConfig, ECOLES
from logger import logger
from utils.dom_selectors import DOMSelectors
from utils.browsemap import CHEMIN_PANNEAU, normaliser_url, vanity_depuis_url
from utils.profile_extractor import ProfileExtractor
from utils.search_filters import equilibrer_parentheses
from utils.network_manager import NetworkManager, RetryConfig, PermanentNetworkError
from utils.human_behavior import HumanBehavior
from utils.stealth_profile import StealthProfileManager
from utils.ecoles import composer_libelle


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
        self.use_database = use_database

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

    # Nombre maximum de valeurs par facette LinkedIn. Au-delà, l'URL devient
    # anormalement longue — c'est un signal de détection côté LinkedIn.
    MAX_VALEURS_PAR_FACETTE = 10

    @staticmethod
    def _as_list(valeur) -> List[str]:
        """Normalise None / str / liste en liste de chaînes non vides."""
        if valeur is None:
            return []
        if isinstance(valeur, str):
            valeur = [valeur]
        return [str(v).strip() for v in valeur if str(v).strip()]

    @classmethod
    def _plafonner(cls, valeurs: List[str], nom_facette: str) -> List[str]:
        """Limite une facette à MAX_VALEURS_PAR_FACETTE valeurs."""
        if len(valeurs) <= cls.MAX_VALEURS_PAR_FACETTE:
            return valeurs
        logger.warning(
            f"⚠️ {len(valeurs)} {nom_facette} sélectionnées — "
            f"seules les {cls.MAX_VALEURS_PAR_FACETTE} premières sont utilisées."
        )
        return valeurs[: cls.MAX_VALEURS_PAR_FACETTE]

    @staticmethod
    def _encoder_facette(valeurs: List[str]) -> str:
        """Encode une facette LinkedIn : ["a","b"] → %5B%22a%22%2C%22b%22%5D."""
        return "%5B" + "%2C".join(f"%22{v}%22" for v in valeurs) + "%5D"

    @staticmethod
    def _expression_ou(noms: List[str]) -> str:
        """Construit `"A"` (une valeur) ou `("A" OR "B")` (plusieurs)."""
        cites = ['"{}"'.format(n.replace('"', '\\"')) for n in noms]
        if len(cites) == 1:
            return cites[0]
        return "(" + " OR ".join(cites) + ")"

    @staticmethod
    def _combiner_et(base: str, expression: str) -> str:
        """Ajoute `AND <expression>` à une requête booléenne existante.

        La base est parenthésée si elle contient déjà un OU, sinon le AND
        n'aurait pas la bonne priorité.
        """
        base = (base or "").strip()
        if not base:
            return expression
        if " OR " in base.upper():
            base = f"({base})"
        return f"{base} AND {expression}"

    @staticmethod
    def _nom_ecole(ecole_id: str) -> str:
        """Retrouve le nom d'une école à partir de sa valeur dans ECOLES."""
        for nom, id_ in ECOLES.items():
            if str(id_) == str(ecole_id):
                return nom
        return str(ecole_id)

    @classmethod
    def _libelle_ecoles(cls, ecoles_ids: List[str]) -> str:
        """Libellé enregistré sur chaque profil : « Dauphine / ESCP »."""
        return composer_libelle(cls._nom_ecole(e) for e in ecoles_ids)

    def construire_url_recherche(
        self,
        keyword: str,
        entreprises: Union[str, List[str], None],
        ecoles_ids: List[str],
        ile_de_france: bool = False,
        secteurs_ids: Optional[List[str]] = None,
    ) -> str:
        """
        Construit l'URL de recherche LinkedIn

        Args:
            keyword: Mots-clés de recherche
            entreprises: Entreprise(s) ciblée(s) — une chaîne ou une liste
            ecoles_ids: IDs (ou noms) des écoles, tels que stockés dans ECOLES
            ile_de_france: Filtrer sur la région Île-de-France (optionnel)
            secteurs_ids: IDs numériques de secteurs LinkedIn (facette industry)

        Returns:
            URL complète de recherche

        Sémantique LinkedIn :
            Les valeurs d'une MÊME facette sont combinées en OU
            (`currentCompany=["A","B"]` = chez A ou chez B), et les facettes
            entre elles en ET (école ET entreprise ET secteur).

        Note sur les replis :
            LinkedIn attend des identifiants numériques pour `currentCompany`
            (URN entreprise) et `schoolFilter` (ID école). Quand un seul
            identifiant d'une facette manque, TOUTE la facette bascule dans la
            recherche booléenne : `(kw) AND ("A" OR "B")`. Mélanger les deux
            (`currentCompany=[urnA]` + `"B"` en mot-clé) produirait un ET et
            ne renverrait rien.
        """
        base_url = "https://www.linkedin.com/search/results/people/?"
        params = []

        # Seules les entreprises sont plafonnées, et non pour la longueur de
        # l'URL — elle fait 742 caractères avec les 38 écoles, pour une limite
        # pratique de 8 000. La vraie raison est le nombre d'appels à l'API de
        # LinkedIn : chaque entreprise non connue en déclenche un pour résoudre
        # son identifiant. Écoles et secteurs ont leurs identifiants dans
        # config.py, donc aucun appel : rien ne justifie de les tronquer.
        entreprises = self._plafonner(self._as_list(entreprises), "entreprises")
        ecoles_ids = self._as_list(ecoles_ids)
        # Les secteurs n'ont pas de repli booléen : un ID non numérique est
        # forcément une erreur de configuration, on l'ignore.
        secteurs_ids = [s for s in self._as_list(secteurs_ids) if s.isdigit()]

        # Normaliser le keyword : retirer les parenthèses englobantes inutiles
        # car LinkedIn renvoie 0 résultat quand toute la requête est entourée
        # d'une seule paire de parens (ex: `(A OR B OR C)` → 0 résultat,
        # alors que `A OR B OR C` → résultats).
        # Une parenthèse oubliée rend l'expression invalide et LinkedIn
        # répond « Aucun résultat » sans erreur — indiagnostiquable. On répare
        # avant d'envelopper quoi que ce soit, sinon on aggrave le défaut.
        keywords_combines = self._normalize_keyword(equilibrer_parentheses(keyword))

        # Facette entreprise : tout-ou-rien (cf. note sur les replis)
        urns = [self._resoudre_company_urn(e) for e in entreprises]
        if entreprises and all(urns):
            company_urns = urns
        else:
            company_urns = []
            if entreprises:
                keywords_combines = self._combiner_et(
                    keywords_combines, self._expression_ou(entreprises)
                )

        # Facette école : même règle. Les entrées non numériques de ECOLES sont
        # des noms (ID LinkedIn pas encore connu) → repli pour toute la facette.
        # Une seule école sans identifiant faisait auparavant basculer la
        # TOTALITÉ du filtre en recherche textuelle : trois écoles obscures
        # suffisaient à ruiner une sélection de quarante. On écarte celles qui
        # n'ont pas d'identifiant et on garde le filtre précis pour les autres
        # — l'interface nomme les écartées. Le repli textuel ne subsiste que
        # si AUCUNE n'a d'identifiant, sinon il ne resterait aucun critère.
        ecoles_avec_id = [e for e in ecoles_ids if e.isdigit()]
        if ecoles_avec_id:
            ecoles_filter = ecoles_avec_id
        else:
            ecoles_filter = []
            if ecoles_ids:
                keywords_combines = self._combiner_et(
                    keywords_combines,
                    self._expression_ou([self._nom_ecole(e) for e in ecoles_ids]),
                )

        # Les replis peuvent avoir produit une requête entièrement parenthésée
        # (ex. `("A" OR "B")` quand il n'y a aucun mot-clé) → 0 résultat chez
        # LinkedIn. On repasse la normalisation après combinaison.
        keywords_combines = self._normalize_keyword(keywords_combines)

        if keywords_combines:
            params.append(f"keywords={urllib.parse.quote(keywords_combines)}")

        params.append("origin=FACETED_SEARCH")

        # Filtre géographique Île-de-France
        if ile_de_france:
            params.append('geoUrn=%5B%22104246759%22%5D')

        if company_urns:
            params.append(f"currentCompany={self._encoder_facette(company_urns)}")

        if ecoles_filter:
            params.append(f"schoolFilter={self._encoder_facette(ecoles_filter)}")

        if secteurs_ids:
            params.append(f"industry={self._encoder_facette(secteurs_ids)}")

        url = base_url + "&".join(params)
        logger.debug(f"URL construite: {url}")
        return url

    @staticmethod
    def _normalize_keyword(keyword: str) -> str:
        """Retire les parenthèses englobantes inutiles d'une requête keyword.

        LinkedIn n'aime pas qu'une requête entière soit entourée d'une seule
        paire de parens (`(A OR B OR C)` → 0 résultat) alors que la même
        requête sans parens englobantes (`A OR B OR C`) retourne bien des
        résultats. Cette fonction retire UNIQUEMENT les parens externes qui
        englobent toute l'expression (sans casser des sous-groupes type
        `(A OR B) AND (C OR D)`).
        """
        if not keyword:
            return keyword or ""
        kw = keyword.strip()
        while len(kw) >= 2 and kw[0] == "(" and kw[-1] == ")":
            # Vérifier que ces parens forment un seul groupe englobant
            depth = 0
            envelops_all = True
            for i, ch in enumerate(kw):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    # Si on retombe à 0 avant la fin, ce ne sont pas des
                    # parens englobantes (ex: `(A) OR (B)` retombe à 0 après `(A)`)
                    if depth == 0 and i < len(kw) - 1:
                        envelops_all = False
                        break
            if envelops_all and depth == 0:
                kw = kw[1:-1].strip()
            else:
                break
        return kw

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
        (page.goto), qui fonctionne déjà pour la recherche de personnes.
        Le résultat est mis en cache (config/company_urns.json).
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
            ok = await self.network_manager.safe_page_goto(page, search_url)
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
                        await self.network_manager.safe_page_goto(page, clean_url)
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
            await self.network_manager.safe_page_goto(page, clean_url)
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

        except Exception as e:
            logger.warning(f"  ⚠️ Erreur message {profile_name}: {e}")
            return False

    async def _open_linkedin_page(self, p, cookie: str, status_callback=None):
        """Ouvre Chrome + session LinkedIn (cookie) + warm-up.
        Retourne (browser, page) ou (None, None) si le cookie est invalide/expiré."""
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
            status_callback("🌡️ Warm-up session...")
        if not await self.human.warmup_session(page):
            await browser.close()
            return None, None
        return browser, page

    async def verifier_acceptations_async(self, cookie: str, profils, max_check: int = 30,
                                          progress_callback=None, status_callback=None):
        """Revisite les profils invités et détecte ceux devenus relation 1er degré.
        Retourne la liste [{'url','nom'}] des profils ayant accepté."""
        self.errors = []
        profils = list(profils)[:max_check]
        acceptees = []
        if not profils:
            return acceptees
        async with async_playwright() as p:
            if status_callback:
                status_callback("🚀 Lancement du navigateur...")
            browser, page = await self._open_linkedin_page(p, cookie, status_callback)
            if page is None:
                self.errors.append("Cookie invalide ou expiré — reconnectez-vous.")
                return acceptees
            try:
                total = len(profils)
                for i, prof in enumerate(profils):
                    url = prof.get("url"); nom = prof.get("nom", "")
                    if status_callback:
                        status_callback(f"🔎 [{i+1}/{total}] {nom}")
                    try:
                        clean_url = url.split('?')[0].rstrip('/') + '/'
                        if not await self.network_manager.safe_page_goto(page, clean_url):
                            continue
                        if any(x in page.url for x in ["login", "authwall"]):
                            self.errors.append("Redirigé vers login — cookie invalide.")
                            break
                        await self.human.human_delay(1500, 400)
                        btn = page.locator(
                            'main button[aria-label^="Message"], main a[aria-label^="Message"], '
                            'main button:has-text("Message"), main a:has-text("Message")'
                        ).first
                        if await btn.count() > 0 and await btn.is_visible():
                            acceptees.append({"url": url, "nom": nom})
                            logger.info(f"  ✅ A accepté : {nom}")
                    except Exception as e:
                        logger.warning(f"  ⚠️ Vérif {nom}: {e}")
                    if progress_callback:
                        progress_callback(min((i + 1) / total, 1.0))
                    await self.human.human_delay(
                        self.config.DELAY_BETWEEN_PROFILES_MIN,
                        (self.config.DELAY_BETWEEN_PROFILES_MAX - self.config.DELAY_BETWEEN_PROFILES_MIN) // 3,
                    )
            finally:
                await browser.close()
        return acceptees

    async def envoyer_messages_async(self, cookie: str, cibles, message: str, max_msg: int = 20,
                                     progress_callback=None, status_callback=None):
        """Envoie `message` à chaque cible (relation 1er degré).
        Retourne la liste [{'url','nom'}] des personnes effectivement messagées."""
        self.errors = []
        cibles = list(cibles)[:max_msg]
        envoyes = []
        if not cibles or not message.strip():
            return envoyes
        async with async_playwright() as p:
            if status_callback:
                status_callback("🚀 Lancement du navigateur...")
            browser, page = await self._open_linkedin_page(p, cookie, status_callback)
            if page is None:
                self.errors.append("Cookie invalide ou expiré — reconnectez-vous.")
                return envoyes
            try:
                total = len(cibles)
                for i, c in enumerate(cibles):
                    url = c.get("url"); nom = c.get("nom", "")
                    if status_callback:
                        status_callback(f"✉️ [{i+1}/{total}] {nom}")
                    try:
                        if await self.envoyer_message(page, url, nom, message):
                            envoyes.append({"url": url, "nom": nom})
                    except Exception as e:
                        logger.warning(f"  ⚠️ Message {nom}: {e}")
                    if progress_callback:
                        progress_callback(min((i + 1) / total, 1.0))
                    await self.human.human_delay(
                        self.config.DELAY_BETWEEN_PROFILES_MIN,
                        (self.config.DELAY_BETWEEN_PROFILES_MAX - self.config.DELAY_BETWEEN_PROFILES_MIN) // 3,
                    )
                    await self.human.random_long_pause(probability=0.10)
            finally:
                await browser.close()
        return envoyes

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

        # Réinitialiser la fatigue pour chaque nouvelle session
        self.human = HumanBehavior(fatigue_factor=0.0)

        # Vérifier les limites quotidiennes AVANT de lancer
        if not self.human.daily_limits.can_scrape():
            msg = (f"🚫 Limite quotidienne atteinte ({self.human.daily_limits.profiles_today} profils). "
                   f"Réessayez demain.")
            logger.error(msg)
            self.errors.append(msg)
            return pd.DataFrame()

        if inviter and not self.human.daily_limits.can_invite():
            msg = (f"🚫 Limite d'invitations quotidienne atteinte ({self.human.daily_limits.invitations_today}). "
                   f"Réessayez demain.")
            logger.error(msg)
            self.errors.append(msg)
            return pd.DataFrame()

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
                    status_callback("🚀 Lancement du navigateur...")

                logger.info("Démarrage Playwright (async)…")

                # ═══ STEALTH PROFILE ═══
                # Générer un profil navigateur complet et cohérent
                # (UA + viewport + screen + headers — tout matche)
                profile = StealthProfileManager.load_or_generate(prefer_mac=True)
                viewport = profile.viewport

                logger.info(f"🎭 Profil: {profile.platform} / Chrome {profile.chrome_major} / "
                             f"{viewport['width']}x{viewport['height']}")

                # Lancer le navigateur avec configuration naturelle
                launch_args = [
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    f"--window-size={profile.screen['width']},{profile.screen['height']}",
                ]
                try:
                    browser = await p.chromium.launch(
                        channel="chrome",
                        headless=self.config.HEADLESS,
                        args=launch_args
                    )
                except Exception:
                    browser = await p.chromium.launch(
                        headless=self.config.HEADLESS,
                        args=launch_args
                    )

                # Créer le contexte avec le profil stealth complet
                context = await browser.new_context(
                    **self._context_kwargs(profile, viewport)
                )

                # Appliquer les headers stealth (avec Sec-CH-UA) — sauf si désactivé
                if self._stealth:
                    stealth_headers = StealthProfileManager.get_stealth_headers(profile)
                    await context.set_extra_http_headers(stealth_headers)

                # Appliquer le cookie
                await context.add_cookies([{
                    "name": "li_at",
                    "value": cookie,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }])

                page = await context.new_page()

                # Injecter les scripts stealth cohérents avec le profil — sauf si désactivé
                if self._stealth:
                    stealth_script = StealthProfileManager.get_stealth_init_script(profile)
                    await page.add_init_script(stealth_script)

                # ═══ MONITORING HTTP ═══
                self.human.attach_monitor(page)

                # ═══ WARM-UP SESSION ═══
                if status_callback:
                    status_callback("🌡️ Warm-up session...")

                warmup_ok = await self.human.warmup_session(page)
                if not warmup_ok:
                    logger.error("❌ Warm-up échoué — cookie invalide ?")
                    self.errors.append("Cookie invalide ou expiré (échec warm-up)")
                    await browser.close()
                    return pd.DataFrame()

                # Vérifier la sécurité après le warm-up
                if not await self.human.check_safety(page):
                    logger.error("❌ Arrêt de sécurité post warm-up")
                    self.errors.append("Détection d'un problème de sécurité LinkedIn")
                    await browser.close()
                    return pd.DataFrame()

                # Résoudre l'URN de l'entreprise via l'API typeahead LinkedIn
                # (la page est maintenant authentifiée). Si succès, l'URN est
                # ajouté au cache et utilisé par construire_url_recherche pour
                # appliquer le vrai filtre `currentCompany` (beaucoup plus précis
                # que la stratégie "AND keyword").
                for entreprise in entreprises:
                    if status_callback:
                        status_callback(f"🏢 Résolution URN entreprise '{entreprise}'…")
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
                    status_callback("🔗 Chargement recherche…")

                logger.info(f"Accès URL : {url_recherche}")

                # Charger la première page avec gestion d'erreurs
                success = await self.network_manager.safe_page_goto(
                    page,
                    url_recherche + "&page=1"
                )

                if not success:
                    # Distinguer le cas "cookie expiré" (boucle de redirections) d'une
                    # vraie erreur réseau pour donner un message d'erreur exploitable.
                    last_err = ""
                    try:
                        last_err = str(self.network_manager.last_error or "")
                    except Exception:
                        pass
                    if "ERR_TOO_MANY_REDIRECTS" in last_err or "login" in page.url:
                        msg = ("Cookie LinkedIn expiré ou invalidé (boucle de "
                               "redirections). Reconnectez-vous à linkedin.com, "
                               "copiez le nouveau cookie 'li_at' et mettez-le à jour "
                               "dans l'application.")
                        logger.error(f"❌ {msg}")
                        self.errors.append(msg)
                    else:
                        logger.error("❌ Impossible de charger la page de recherche")
                        self.errors.append("Impossible de charger la page de recherche")
                    await browser.close()
                    return pd.DataFrame()

                # Comportement humain à l'arrivée sur la page
                await self.human.page_entry_behavior(page)

                # Vérifier qu'on n'est pas redirigé vers login
                if "login" in page.url:
                    logger.error("❌ Cookie invalide ou expiré")
                    self.errors.append("Cookie invalide ou expiré")
                    await browser.close()
                    return pd.DataFrame()

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
                        status_callback(f"📄 Page {current_page}…")

                    logger.info(f"═══ Scraping page {current_page} ═══")

                    # ═══ CHECK SÉCURITÉ à chaque page ═══
                    if not await self.human.check_safety(page):
                        logger.error("🛑 Arrêt de sécurité en cours de scraping")
                        self.errors.append("Arrêt de sécurité — signal LinkedIn détecté")
                        break

                    # Vérifier la limite quotidienne en cours de route
                    if not self.human.daily_limits.can_scrape():
                        logger.warning("🚫 Limite quotidienne de profils atteinte en cours de session")
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
                        break

                    logger.info(f"📋 {len(profiles_page)} profils à traiter sur cette page")

                    # Traiter chaque profil
                    for profile in profiles_page:

                        # Vérifier la limite selon le mode
                        if inviter:
                            if invitations_envoyees >= nb_profils:
                                logger.info(f"✋ Limite de {nb_profils} invitations atteinte")
                                break
                            # Sécurité max : plafond quotidien PAR UTILISATEUR
                            if not self.human.daily_limits.can_invite():
                                logger.warning(
                                    f"🛑 Plafond quotidien d'invitations atteint "
                                    f"({self.human.daily_limits.invitations_today}/"
                                    f"{self.human.daily_limits.max_invitations}) — arrêt sécurité."
                                )
                                if status_callback:
                                    status_callback("🛑 Plafond quotidien d'invitations atteint")
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
                                status_callback(f"📨 Invitation pour {nom}")

                            try:
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

                                # Délai humain entre profils (gaussien + fatigue progressive)
                                await self.human.human_delay(
                                    self.config.DELAY_BETWEEN_PROFILES_MIN,
                                    (self.config.DELAY_BETWEEN_PROFILES_MAX - self.config.DELAY_BETWEEN_PROFILES_MIN) // 3
                                )
                                # Augmenter légèrement la fatigue au fil des invitations
                                self.human.increase_fatigue(0.02)
                                # Pause longue aléatoire (10% de chance)
                                await self.human.random_long_pause(probability=0.10)

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

                    # PAGE SUIVANTE
                    # Vérifier si on a atteint la limite selon le mode
                    continuer = (inviter and invitations_envoyees < nb_profils) or (not inviter and profils_scrapes < nb_profils)

                    if continuer:
                        current_page += 1
                        logger.info(f"➡️ Passage à la page {current_page}")

                        next_url = url_recherche + f"&page={current_page}"
                        success = await self.network_manager.safe_page_goto(page, next_url)

                        if not success:
                            logger.warning("⚠️ Impossible de charger la page suivante")
                            break

                        # Comportement humain sur la nouvelle page
                        await self.human.page_entry_behavior(page)
                    else:
                        break

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

        try:
            await lien.scroll_into_view_if_needed()
            await self.human.human_delay(900, 300)
            await self.human.human_hover_and_click(page, lien)
        except Exception as err:
            logger.warning(f"⚠️ Clic sur « Tout afficher » impossible : {err}")
            return "le clic sur « Tout afficher » a échoué"

        # Borné : un panneau qui ne vient pas ne doit pas immobiliser l'outil,
        # on se rabat alors sur la section, avec un avertissement.
        attente = "() => (" + DOMSelectors.compter_panneau_browsemap_js() + ")() > 0"
        try:
            await page.wait_for_function(attente, timeout=10000)
        except Exception as err:
            logger.warning(f"⚠️ Panneau des profils voisins absent après le clic : {err}")
            return "le panneau ne s'est pas ouvert après le clic sur « Tout afficher »"
        return None

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
                status_callback("🚀 Lancement du navigateur...")

            browser, page = await self._open_linkedin_page(p, cookie, status_callback)
            if page is None:
                self.errors.append("Cookie invalide ou expiré — reconnectez-vous.")
                return [], None

            try:
                if status_callback:
                    status_callback("👤 Ouverture du profil de référence...")

                if not await self.network_manager.safe_page_goto(page, cible):
                    self.errors.append(f"Impossible d'ouvrir le profil : {cible}")
                    return [], None

                if self._est_page_de_connexion(page.url):
                    self.errors.append("Redirigé vers login — cookie invalide.")
                    return [], None

                await self.human.human_delay(2000, 500)

                # L'entreprise actuelle du profil de référence, lue avant
                # d'ouvrir le panneau, tant que rien ne recouvre le profil :
                # c'est tout ce dont le « ailleurs » a besoin.
                entreprise = await self._entreprise_reference(page)

                if status_callback:
                    status_callback("👥 Ouverture des profils voisins...")
                echec_ouverture = await self._ouvrir_panneau(page)

                # Le clic change l'URL (routage côté client) : une session
                # expirée peut s'y révéler.
                if self._est_page_de_connexion(page.url):
                    self.errors.append("Redirigé vers login — cookie invalide.")
                    return [], None

                if echec_ouverture is None:
                    if status_callback:
                        status_callback("📜 Déroulement de la liste...")
                    await self._derouler_panneau(page)
                    brut = await page.evaluate(DOMSelectors.extract_browsemap_js(), "panneau")
                else:
                    # Un panneau ouvert mais illisible n'arrive pas ici : ce
                    # serait un changement de structure, qu'on crie plus bas
                    # au lieu de le masquer derrière les 5 de la section.
                    if status_callback:
                        status_callback("📋 Lecture de la section du profil...")
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

            finally:
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
        start_time = datetime.now()
        donnees = []

        # Nettoyer les URLs
        urls = [u.strip() for u in urls if u.strip() and '/in/' in u]
        total = len(urls)

        if total == 0:
            self.errors.append("Aucune URL LinkedIn valide fournie")
            return pd.DataFrame()

        logger.info(f"🔗 Scraping de {total} URLs de profils LinkedIn")

        try:
            async with async_playwright() as p:

                if status_callback:
                    status_callback("🚀 Lancement du navigateur...")

                # ═══ STEALTH PROFILE ═══
                profile = StealthProfileManager.load_or_generate(prefer_mac=True)
                viewport = profile.viewport

                logger.info(f"🎭 Profil: {profile.platform} / Chrome {profile.chrome_major}")

                launch_args = [
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    f"--window-size={profile.screen['width']},{profile.screen['height']}",
                ]
                try:
                    browser = await p.chromium.launch(
                        channel="chrome",
                        headless=self.config.HEADLESS,
                        args=launch_args
                    )
                except Exception:
                    browser = await p.chromium.launch(
                        headless=self.config.HEADLESS,
                        args=launch_args
                    )

                context = await browser.new_context(
                    **self._context_kwargs(profile, viewport)
                )

                # Headers stealth (Sec-CH-UA) — sauf si désactivé
                if self._stealth:
                    stealth_headers = StealthProfileManager.get_stealth_headers(profile)
                    await context.set_extra_http_headers(stealth_headers)

                await context.add_cookies([{
                    "name": "li_at",
                    "value": cookie,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }])

                page = await context.new_page()

                # Script stealth cohérent avec le profil — sauf si désactivé
                if self._stealth:
                    stealth_script = StealthProfileManager.get_stealth_init_script(profile)
                    await page.add_init_script(stealth_script)

                # ═══ MONITORING HTTP ═══
                self.human.attach_monitor(page)

                # ═══ WARM-UP SESSION ═══
                if status_callback:
                    status_callback("🌡️ Warm-up session...")

                warmup_ok = await self.human.warmup_session(page)
                if not warmup_ok:
                    logger.error("❌ Cookie invalide ou expiré (warm-up)")
                    self.errors.append("Cookie invalide ou expiré — reconnectez-vous.")
                    await browser.close()
                    return pd.DataFrame()

                logger.info("✅ Session LinkedIn active")

                # ── Boucle sur les URLs ──
                for i, url in enumerate(urls):
                    nom_affiche = url.split('/in/')[-1].strip('/').replace('-', ' ').title()
                    logger.info(f"[{i+1}/{total}] {nom_affiche}")

                    if status_callback:
                        status_callback(f"👤 [{i+1}/{total}] {nom_affiche}")

                    try:
                        success = await self.network_manager.safe_page_goto(page, url)
                        if not success:
                            logger.warning(f"  ⚠️ Impossible de charger {url}")
                            self.errors.append(f"Erreur chargement: {url}")
                            continue

                        # Vérifier la redirection login
                        if any(x in page.url for x in ["login", "authwall"]):
                            logger.error("  ❌ Redirigé vers login — arrêt")
                            self.errors.append("Déconnecté de LinkedIn pendant le scraping")
                            break

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

                        # Invitation — INDÉPENDANTE de l'extraction du profil
                        if inviter:
                            try:
                                invited = await self.envoyer_invitation(page, url, nom, message_invitation)
                                ligne['Invitation'] = 'Oui' if invited else 'Non'
                                if invited:
                                    self.human.daily_limits.increment_invitations()
                            except Exception as _e:
                                logger.warning(f"  ⚠️ Invitation échouée: {_e}")
                                ligne['Invitation'] = 'Non'

                        # Message direct — INDÉPENDANT de l'extraction du profil
                        if message_direct.strip():
                            try:
                                sent = await self.envoyer_message(page, url, nom, message_direct)
                                ligne['Message'] = 'Oui' if sent else 'Non'
                            except Exception as _e:
                                logger.warning(f"  ⚠️ Message échoué: {_e}")
                                ligne['Message'] = 'Non'

                        donnees.append(ligne)

                    except Exception as e:
                        logger.error(f"  ❌ Erreur: {e}")
                        self.errors.append(f"Erreur {url}: {e}")

                    # Progression
                    if progress_callback:
                        progress_callback(min((i + 1) / total, 1.0))

                    # Délai humain entre chaque profil
                    if i < total - 1:
                        await self.human.human_delay(
                            self.config.DELAY_BETWEEN_PROFILES_MIN,
                            (self.config.DELAY_BETWEEN_PROFILES_MAX - self.config.DELAY_BETWEEN_PROFILES_MIN) // 3
                        )
                        self.human.increase_fatigue(0.01)
                        await self.human.random_long_pause(probability=0.08)

                # Fermer le navigateur
                await browser.close()

                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"\n{'═'*60}")
                logger.info(f"✅ SCRAPING URLs TERMINÉ")
                logger.info(f"   Profils extraits: {len(donnees)}/{total}")
                logger.info(f"   Durée: {duration:.1f}s")
                logger.info(f"{'═'*60}\n")

                return pd.DataFrame(donnees)

        except Exception as e:
            self.errors.append(str(e))
            logger.error(f"❌ Erreur critique: {e}", exc_info=True)
            return pd.DataFrame()
