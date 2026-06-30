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
import re
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable
import pandas as pd
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config import ScraperConfig, ECOLES
from logger import logger
from utils.dom_selectors import DOMSelectors
from utils.profile_extractor import ProfileExtractor
from utils.network_manager import NetworkManager, RetryConfig, PermanentNetworkError
from utils.human_behavior import HumanBehavior
from utils.stealth_profile import StealthProfileManager


class LinkedInScraperV2:
    """
    Scraper LinkedIn V2 - Version améliorée avec async/await
    """

    def __init__(self, use_database: bool = True, proxy: dict = None,
                 db_file: str = None, profiles_csv: str = None):
        self._proxy = proxy
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

        # Initialiser le module de comportement humain
        self.human = HumanBehavior(fatigue_factor=0.0)

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
            "user_agent": profile.user_agent,
            "locale": profile.locale,
            "timezone_id": profile.timezone,
        }
        if self._proxy:
            kwargs["proxy"] = self._proxy
        return kwargs

    def construire_url_recherche(self, keyword: str, entreprise: str, ecoles_ids: List[str], ile_de_france: bool = False) -> str:
        """
        Construit l'URL de recherche LinkedIn

        Args:
            keyword: Mots-clés de recherche
            entreprise: Nom de l'entreprise (optionnel)
            ecoles_ids: IDs des écoles
            ile_de_france: Filtrer sur la région Île-de-France (optionnel)

        Returns:
            URL complète de recherche

        Note sur le filtre entreprise :
            LinkedIn utilise `currentCompany=["<URN_id_numérique>"]` pour le
            filtre entreprise, pas `company=<nom>` (qui est silencieusement
            ignoré et renvoie 0 résultat). On utilise donc deux stratégies :
              1) Si l'URN numérique est connu (cache `config/company_urns.json`,
                 ex: {"eurosport": "165158"}), on utilise le vrai filtre
                 `currentCompany`.
              2) Sinon, on injecte le nom d'entreprise dans la recherche
                 booléenne (`(keywords) AND "Entreprise"`), ce qui matche
                 les profils mentionnant l'entreprise.
        """
        base_url = "https://www.linkedin.com/search/results/people/?"
        params = []

        # Résoudre l'URN entreprise depuis le cache (si présent)
        company_urn = self._resoudre_company_urn(entreprise) if entreprise else None

        # Normaliser le keyword : retirer les parenthèses englobantes inutiles
        # car LinkedIn renvoie 0 résultat quand toute la requête est entourée
        # d'une seule paire de parens (ex: `(A OR B OR C)` → 0 résultat,
        # alors que `A OR B OR C` → résultats).
        keywords_combines = self._normalize_keyword(keyword)

        # Combiner entreprise dans les keywords si on n'a pas d'URN
        if entreprise and not company_urn:
            ent_safe = entreprise.replace('"', '\\"')
            if keywords_combines.strip():
                # On wrap les keywords entre parens AVANT le AND uniquement si
                # nécessaire (plusieurs termes OR), sinon on garde tel quel.
                if " OR " in keywords_combines.upper():
                    keywords_combines = f'({keywords_combines}) AND "{ent_safe}"'
                else:
                    keywords_combines = f'{keywords_combines} AND "{ent_safe}"'
            else:
                keywords_combines = f'"{ent_safe}"'

        if keywords_combines:
            params.append(f"keywords={urllib.parse.quote(keywords_combines)}")

        params.append("origin=FACETED_SEARCH")

        # Filtre géographique Île-de-France
        if ile_de_france:
            params.append('geoUrn=%5B%22104246759%22%5D')

        # Filtre entreprise via URN numérique (si disponible)
        if company_urn:
            params.append(f'currentCompany=%5B%22{company_urn}%22%5D')

        if ecoles_ids:
            ecole_id = ecoles_ids[0]
            params.append(f'schoolFilter=%5B%22{ecole_id}%22%5D')

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
        self, entreprise: str, page: Page
    ) -> Optional[str]:
        """Résout l'URN d'une entreprise via l'API typeahead authentifiée de LinkedIn.

        Cette méthode utilise la page Playwright déjà connectée pour appeler
        l'endpoint `/voyager/api/typeahead/hitsV2` (avec le bon CSRF token
        extrait du cookie JSESSIONID), puis cache le résultat dans
        `config/company_urns.json` pour les prochaines exécutions.

        Si la résolution échoue, l'appelant retombe automatiquement sur la
        stratégie "AND \"Nom\"" dans les keywords (via construire_url_recherche).
        """
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
                return None
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
                logger.warning(f"⚠️ Typeahead URN '{entreprise}' échoué: {result}")
                return None

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

            logger.info(f"  🔍 Recherche du lien 'Se connecter' pour vanityName: {vanity_name}")

            # STRATÉGIE: Chercher le lien <a href="/preload/search-custom-invite/?vanityName=X">
            # qui contient le texte "Se connecter"
            # Ce lien ouvre une modal SANS naviguer vers le profil

            try:
                # Pause naturelle avant d'agir (simule la lecture du profil)
                await self.human.reading_pause(text_length=80)

                # Chercher le lien d'invitation pour ce profil
                # Format: <a href="/preload/search-custom-invite/?vanityName=XXX">
                connect_link_selector = f'a[href*="/preload/search-custom-invite/?vanityName={vanity_name}"]'

                # Vérifier si le lien existe
                connect_links = await page.locator(connect_link_selector).count()

                if connect_links == 0:
                    logger.info(f"  ⏭️ Pas de bouton 'Se connecter' (déjà connecté, bouton 'Suivre' ou 'Message')")
                    logger.info(f"  → Profil ignoré, passage au suivant")
                    return False

                logger.info(f"  ✓ Lien 'Se connecter' trouvé ({connect_links} occurrences)")

                # Scroll naturel vers l'élément
                connect_locator = page.locator(connect_link_selector).first
                try:
                    await self.human.scroll_to_element_naturally(page, connect_locator)
                except Exception:
                    pass

                # Clic humain avec survol de souris
                await self.human.human_hover_and_click(page, connect_locator)

                logger.info(f"  ✓ Clic effectué sur le lien 'Se connecter'")

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

    async def run_scraper_async(
        self,
        cookie: str,
        keyword: str,
        entreprise: str,
        nb_profils: int,
        ecoles_ids: List[str],
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
            entreprise: Entreprise cible (optionnel)
            nb_profils: Nombre de profils à scraper
            ecoles_ids: IDs des écoles
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

        # Nom de l'école
        ecole_nom = ""
        if ecoles_ids:
            for nom, id_ in ECOLES.items():
                if id_ in ecoles_ids:
                    ecole_nom = nom
                    break

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

                # Appliquer les headers stealth (avec Sec-CH-UA)
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

                # Injecter les scripts stealth cohérents avec le profil
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
                if entreprise:
                    if status_callback:
                        status_callback(f"🏢 Résolution URN entreprise '{entreprise}'…")
                    await self._resoudre_company_urn_via_typeahead(entreprise, page)

                # Construire l'URL de recherche
                url_recherche = self.construire_url_recherche(keyword, entreprise, ecoles_ids, ile_de_france)

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
                            entreprise=entreprise,
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

    async def run_url_scraper_async(
        self,
        cookie: str,
        urls: List[str],
        inviter: bool = False,
        message_invitation: str = "",
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
                        headless=True,  # Mode headless pour serveur sans display
                        args=launch_args
                    )
                except Exception:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=launch_args
                    )

                context = await browser.new_context(
                    **self._context_kwargs(profile, viewport)
                )

                # Headers stealth avec Sec-CH-UA
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

                # Script stealth cohérent avec le profil
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

                        if profile_data['nom']:
                            logger.info(f"  ✅ {profile_data['nom']} | {profile_data['poste']} | {profile_data['entreprise']}")

                            # Sauvegarder en DB
                            if self.use_database and self.db:
                                try:
                                    self.db.ajouter_profil(
                                        nom=profile_data['nom'],
                                        poste=profile_data['poste'],
                                        entreprise=profile_data['entreprise'],
                                        ecole='',
                                        url=url,
                                        localisation='',
                                        nb_connexions=''
                                    )
                                except Exception as e:
                                    logger.error(f"  Erreur DB: {e}")

                            # Sauvegarder en CSV
                            self._sauvegarder_profil(
                                profile_data['nom'],
                                profile_data['poste'],
                                profile_data['entreprise'],
                                '',  # pas d'école
                                url,
                                False
                            )

                            donnees.append({
                                'Nom': profile_data['nom'],
                                'Poste': profile_data['poste'],
                                'Entreprise': profile_data['entreprise'],
                                'URL': url,
                                'Date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            })
                        else:
                            logger.warning(f"  ⚠️ Aucune donnée extraite")
                            self.errors.append(f"Pas de données: {url}")

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
