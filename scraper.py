# -*- coding: utf-8 -*-
import re
import urllib.parse
from datetime import datetime
from typing import List, Optional
import pandas as pd
from playwright.sync_api import sync_playwright
from config import ScraperConfig, ECOLES
from logger import logger
from email_notifier import EmailNotifier


class LinkedInScraper:
    def __init__(self, use_database: bool = True):
        self.config = ScraperConfig()
        self.errors = []
        self.use_database = use_database

        if use_database:
            try:
                from database import DatabaseManager
                # Legacy scraper (unused/not imported elsewhere in the app) — not multi-tenant-safe:
                # always writes to the global DatabaseManager() default, bypassing per-user isolation.
                self.db = DatabaseManager()
            except Exception as e:
                logger.warning(f"Base de données non disponible: {e}")
                self.use_database = False
                self.db = None
        else:
            self.db = None

    # ================================
    # URL de recherche LinkedIn
    # ================================
    def construire_url_recherche(self, keyword: str, entreprise: str, ecoles_ids: List[str]) -> str:
        """Construit l'URL de recherche LinkedIn.

        Note : LinkedIn utilise `currentCompany=["<URN_id_numérique>"]` pour
        filtrer par entreprise (pas `company=<nom>` qui est ignoré et renvoie
        0 résultat). On utilise donc deux stratégies :
          1) Si l'URN numérique est connu (cache `config/company_urns.json`),
             on utilise le vrai filtre `currentCompany`.
          2) Sinon, on injecte le nom d'entreprise dans la recherche
             booléenne (`(keywords) AND "Entreprise"`).
        """
        base_url = "https://www.linkedin.com/search/results/people/?"
        params = []

        company_urn = self._resoudre_company_urn(entreprise) if entreprise else None

        # Normaliser : retirer les parenthèses englobantes (LinkedIn renvoie
        # 0 résultat quand toute la requête est entourée d'une seule paire).
        keywords_combines = self._normalize_keyword(keyword)
        if entreprise and not company_urn:
            ent_safe = entreprise.replace('"', '\\"')
            if keywords_combines.strip():
                if " OR " in keywords_combines.upper():
                    keywords_combines = f'({keywords_combines}) AND "{ent_safe}"'
                else:
                    keywords_combines = f'{keywords_combines} AND "{ent_safe}"'
            else:
                keywords_combines = f'"{ent_safe}"'

        if keywords_combines:
            params.append(f"keywords={urllib.parse.quote(keywords_combines)}")

        params.append("origin=FACETED_SEARCH")

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
        """Retire les parens englobantes inutiles (LinkedIn renvoie 0 résultat
        quand toute la requête est entourée d'une seule paire de parens)."""
        if not keyword:
            return keyword or ""
        kw = keyword.strip()
        while len(kw) >= 2 and kw[0] == "(" and kw[-1] == ")":
            depth = 0
            envelops_all = True
            for i, ch in enumerate(kw):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i < len(kw) - 1:
                        envelops_all = False
                        break
            if envelops_all and depth == 0:
                kw = kw[1:-1].strip()
            else:
                break
        return kw

    @staticmethod
    def _resoudre_company_urn(entreprise: str):
        """Cherche l'URN numérique d'une entreprise dans le cache local.

        Cache : `config/company_urns.json`, ex :
            {"eurosport": "165158", "decathlon": "1815"}
        Clés insensibles à la casse. Retourne None si non trouvé.
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

    # ================================
    # EXTRACTION ENRICHIE DES DONNÉES
    # ================================
    def extraire_donnees_enrichies(self, link) -> dict:
        """Extrait des données enrichies du profil (localisation, connexions, etc.)"""
        try:
            donnees = link.evaluate("""
                el => {
                    const card = el.closest('li') || el.closest('div');
                    if (!card) return {};

                    let localisation = '';
                    let connexions = '';

                    // Extraire localisation
                    const locElements = card.querySelectorAll('.entity-result__secondary-subtitle');
                    for (const elem of locElements) {
                        const text = elem.textContent?.trim() || '';
                        if (text && !text.toLowerCase().includes('poste') &&
                            !text.toLowerCase().includes('chez') &&
                            text.length < 100) {
                            localisation = text;
                            break;
                        }
                    }

                    // Extraire nombre de connexions
                    const connElements = card.querySelectorAll('.entity-result__summary');
                    for (const elem of connElements) {
                        const text = elem.textContent?.trim() || '';
                        if (text.includes('connexion') || text.includes('connection')) {
                            connexions = text;
                            break;
                        }
                    }

                    return {
                        localisation: localisation,
                        connexions: connexions
                    };
                }
            """)
            return donnees
        except Exception as e:
            logger.debug(f"Erreur extraction enrichie: {e}")
            return {"localisation": "", "connexions": ""}

    # ================================
    # INVITATION
    # ================================
    def envoyer_invitation(self, page, lien_element, message_personnalise: str = "") -> bool:
        try:
            nom = lien_element.evaluate("""
                el => {
                    const figure = (el.closest('li') || el.closest('div'))?.querySelector('figure[aria-label]');
                    return figure?.getAttribute('aria-label') || 'Inconnu';
                }
            """)
            
            logger.info(f"💌 {nom}")
            
            # ÉTAPE 1 : Cliquer sur "Se connecter" (balise <A>)
            clicked_connect = lien_element.evaluate("""
                el => {
                    const card = el.closest('li') || el.closest('div');
                    if (!card) return 'no_card';

                    // MÉTHODE 1 : Chercher directement dans tous les boutons/liens
                    const allButtons = Array.from(card.querySelectorAll('button, a[role="button"]'));
                    for (const btn of allButtons) {
                        const text = btn.textContent?.trim() || '';
                        if (text === 'Se connecter' && btn.offsetParent !== null) {
                            btn.click();
                            return 'success';
                        }
                    }

                    // MÉTHODE 2 : Chercher "Se connecter" dans les spans (ancienne méthode)
                    const spans = Array.from(card.querySelectorAll('span'));
                    for (const span of spans) {
                        if (span.textContent?.trim() === 'Se connecter') {
                            let current = span;
                            for (let i = 0; i < 7; i++) {
                                current = current.parentElement;
                                if (!current) break;
                                if ((current.tagName === 'BUTTON' ||
                                     current.tagName === 'A' ||
                                     current.getAttribute('role') === 'button') &&
                                    current.offsetParent !== null) {
                                    current.click();
                                    return 'success';
                                }
                            }
                        }
                    }

                    // Si aucun bouton "Se connecter" trouvé, retourner les boutons disponibles
                    const buttonTexts = Array.from(card.querySelectorAll('button, a')).map(b => b.textContent?.trim()).filter(Boolean);
                    return 'no_button:' + buttonTexts.join(',');
                }
            """)

            if clicked_connect != 'success':
                if clicked_connect.startswith('no_button:'):
                    logger.info(f"  ⚠️ Pas de bouton 'Se connecter'. Boutons disponibles: {clicked_connect.replace('no_button:', '')}")
                else:
                    logger.info(f"  ⚠️ Impossible de trouver le bouton 'Se connecter'")
                return False
            
            logger.info(f"  ✓ Modal ouverte")

            # ÉTAPE 2 : Si message personnalisé, l'ajouter
            if message_personnalise:
                try:
                    # Cliquer sur "Ajouter une note"
                    add_note_btn = page.locator('button:has-text("Ajouter une note")').first
                    if add_note_btn.is_visible(timeout=2000):
                        add_note_btn.click()
                        page.wait_for_timeout(1000)

                        # Écrire le message
                        textarea = page.locator('textarea[name="message"]').first
                        if textarea.is_visible(timeout=2000):
                            textarea.fill(message_personnalise)
                            page.wait_for_timeout(500)
                            logger.info(f"  ✓ Message personnalisé ajouté")
                except Exception as e:
                    logger.warning(f"  ⚠ Impossible d'ajouter le message: {e}")

            # ÉTAPE 3 : Cliquer sur "Envoyer" avec Playwright
            try:
                # Attendre que la modal soit complètement visible
                delay = self.config.random_delay(
                    self.config.DELAY_AFTER_CONNECT_CLICK_MIN,
                    self.config.DELAY_AFTER_CONNECT_CLICK_MAX
                )
                page.wait_for_timeout(delay)
                
                # Stratégie 1 : Attendre le bouton par texte visible
                try:
                    # Chercher le bouton contenant "Envoyer sans note" ou "Envoyer"
                    send_button = page.locator('button:has-text("Envoyer sans note")').first
                    if send_button.is_visible(timeout=3000):
                        send_button.click()
                        logger.info(f"✅ Invitation envoyée à {nom} (méthode 1)")
                        page.wait_for_timeout(1500)
                        return True
                except:
                    logger.debug("Méthode 1 (has-text) échouée")
                
                # Stratégie 2 : Par aria-label
                try:
                    send_button = page.locator('button[aria-label*="sans note"]').first
                    if send_button.is_visible(timeout=2000):
                        send_button.click()
                        logger.info(f"✅ Invitation envoyée à {nom} (méthode 2)")
                        page.wait_for_timeout(1500)
                        return True
                except:
                    logger.debug("Méthode 2 (aria-label) échouée")
                
                # Stratégie 3 : Chercher tous les boutons primary et cliquer sur celui avec "envoyer"
                try:
                    primary_buttons = page.locator('button.artdeco-button--primary').all()
                    for btn in primary_buttons:
                        try:
                            text = btn.inner_text(timeout=500).lower().strip()
                            if 'envoyer' in text and btn.is_visible():
                                btn.click()
                                logger.info(f"✅ Invitation envoyée à {nom} (méthode 3)")
                                page.wait_for_timeout(1500)
                                return True
                        except:
                            continue
                except:
                    logger.debug("Méthode 3 (primary buttons) échouée")
                
                # Stratégie 4 : JavaScript evaluate en dernier recours
                page.wait_for_timeout(1000)
                clicked_send = page.evaluate("""
                    () => {
                        const normalize = (text) => {
                            return text?.replace(/\\s+/g, ' ').trim().toLowerCase() || '';
                        };
                        
                        // Chercher dans tous les boutons
                        const allButtons = document.querySelectorAll('button');
                        for (const btn of allButtons) {
                            const text = normalize(btn.textContent);
                            const ariaLabel = normalize(btn.getAttribute('aria-label') || '');
                            
                            if ((text.includes('envoyer sans note') || 
                                 text.includes('envoyer') ||
                                 ariaLabel.includes('envoyer sans note')) &&
                                btn.offsetParent !== null && 
                                !btn.disabled &&
                                !btn.getAttribute('aria-label')?.includes('Ajouter')) {
                                btn.click();
                                console.log('Cliqué sur:', text || ariaLabel);
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                
                if clicked_send:
                    logger.info(f"✅ Invitation envoyée à {nom} (méthode 4)")
                    delay = self.config.random_delay(
                        self.config.DELAY_AFTER_INVITATION_MIN,
                        self.config.DELAY_AFTER_INVITATION_MAX
                    )
                    page.wait_for_timeout(delay)
                    return True
                else:
                    logger.warning(f"❌ Bouton 'Envoyer sans note' introuvable pour {nom}")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Erreur lors de l'envoi: {e}")
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except:
                    pass
                return False
            
        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            try:
                page.keyboard.press("Escape")
            except:
                pass
            return False
    # ================================
    # EXTRACTION ENTREPRISE
    # ================================
    def extraire_entreprise(self, texte_entreprise: str) -> str:
        if not texte_entreprise:
            return ""

        temp = re.sub(
            r"(poste actuel|postes précédents|poste précédent|postes precedent|poste precedent)\s*:\s*",
            "",
            texte_entreprise,
            flags=re.IGNORECASE
        )
        temp = " ".join(temp.split())

        m = re.search(r"chez\s+([A-Za-zÀ-ÖØ-öø-ÿ0-9 .,'&\\-]+)", temp, flags=re.IGNORECASE)
        if m:
            entreprise_nom = m.group(1).strip()
            entreprise_nom = re.sub(r"[^\wÀ-ÖØ-öø-ÿ .,'&\\-]", "", entreprise_nom).strip()
            return entreprise_nom

        return ""

    # ================================
    # MAIN SCRAPER
    # ================================
    def run_scraper(self, cookie: str, keyword: str, entreprise: str, nb_profils: int,
                    ecoles_ids: List[str], inviter: bool = False,
                    email_notif: Optional[str] = None,
                    message_invitation: str = "",
                    reinviter_profils_scrapes: bool = False,
                    progress_callback=None, status_callback=None) -> pd.DataFrame:

        start_time = datetime.now()
        donnees = []
        self.errors = []

        # Log des paramètres importants
        logger.info(f"🔧 Paramètres: inviter={inviter}, reinviter_profils_scrapes={reinviter_profils_scrapes}")

        # Nom de l'école
        ecole_nom = ""
        if ecoles_ids:
            for nom, id_ in ECOLES.items():
                if id_ in ecoles_ids:
                    ecole_nom = nom
                    break

        try:
            with sync_playwright() as p:

                if status_callback:
                    status_callback("🚀 Lancement du navigateur...")

                logger.info("Démarrage Playwright…")

                # Ouvrir Chrome for Testing
                try:
                    browser = p.chromium.launch(channel="chrome", headless=self.config.HEADLESS)
                except Exception:
                    browser = p.chromium.launch(headless=self.config.HEADLESS)

                context = browser.new_context()

                # Appliquer cookie li_at
                context.add_cookies([{
                    "name": "li_at",
                    "value": cookie,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                }])

                page = context.new_page()

                # Charger la recherche
                url_recherche = self.construire_url_recherche(keyword, entreprise, ecoles_ids)

                if status_callback:
                    status_callback("🔗 Chargement recherche…")

                logger.info(f"Accès URL : {url_recherche}")

                page.goto(url_recherche + "&page=1", timeout=self.config.TIMEOUT_PAGE)
                delay = self.config.random_delay(
                    self.config.DELAY_PAGE_LOAD_MIN,
                    self.config.DELAY_PAGE_LOAD_MAX
                )
                page.wait_for_timeout(delay)

                if "login" in page.url:
                    logger.error("Cookie invalide")
                    self.errors.append("Cookie invalide ou expiré")
                    browser.close()
                    return pd.DataFrame()

                deja_scrapes_global = self._charger_urls_scrappees()
                logger.info(f"📚 {len(deja_scrapes_global)} profils déjà scrapés chargés (CSV + DB)")
                urls_session = set()

                profils_scrapes = 0
                invitations_envoyees = 0
                current_page = 1

                # ------------------------------
                # BOUCLE DE SCRAPING
                # ------------------------------
                while profils_scrapes < nb_profils:

                    if status_callback:
                        status_callback(f"📄 Page {current_page}…")

                    logger.info(f"Scraping page {current_page}")

                    page.wait_for_timeout(2000)

                    # DEBUG: Prendre un screenshot et afficher le HTML
                    if current_page == 1:
                        try:
                            page.screenshot(path="debug_linkedin.png")
                            logger.info("📸 Screenshot sauvegardé: debug_linkedin.png")

                            # Afficher les classes des <li> sur la page
                            li_classes = page.evaluate("""
                                () => {
                                    const lis = Array.from(document.querySelectorAll('li'));
                                    return lis.slice(0, 5).map(li => ({
                                        classes: li.className,
                                        hasLink: !!li.querySelector('a[href*="/in/"]')
                                    }));
                                }
                            """)
                            logger.info(f"🔍 Classes des 5 premiers <li>: {li_classes}")
                        except Exception as e:
                            logger.warning(f"Erreur screenshot: {e}")

                    try:
                        # Solution ultra-simple : Récupérer directement les URLs via JavaScript
                        # puis les utiliser pour obtenir les éléments Playwright
                        profile_data = page.evaluate("""
                            () => {
                                const profiles = [];
                                const debugInfo = [];

                                // STRATÉGIE FINALE : Filtrer par classes CSS du parent
                                // Les profils principaux ont parent.className contenant "_6f76c01e" ou "_90c98554"
                                // Les relations en commun ont "_57a34c9c _3f883ddb"

                                const allLinks = document.querySelectorAll('a[href*="/in/"]');

                                allLinks.forEach(link => {
                                    const href = link.href;

                                    // Filtrer : doit être /in/nom-prenom/ (pas /in/company/ ou /in/detail/)
                                    if (!href.match(/\\/in\\/[a-z0-9-]+\\/?$/i)) {
                                        return;
                                    }

                                    // FILTRE PRINCIPAL : Vérifier les classes du parent
                                    const parentClasses = link.parentElement?.className || '';
                                    const isMainProfile = parentClasses.includes('_6f76c01e') || parentClasses.includes('_90c98554');

                                    if (debugInfo.length < 10) {
                                        debugInfo.push({
                                            href: href.substring(href.lastIndexOf('/in/')).substring(0, 30),
                                            isMain: isMainProfile,
                                            text: link.textContent?.trim().substring(0, 40) || 'NO TEXT',
                                            parentClasses: parentClasses.substring(0, 50)
                                        });
                                    }

                                    // Ne garder QUE les profils principaux
                                    if (!isMainProfile) {
                                        return;
                                    }

                                    // Extraire le nom depuis le texte du lien
                                    let name = link.textContent?.trim() || '';

                                    // Nettoyer le nom
                                    // Format: "Nicolas DUMEZ  • 2ndData Product Manager..."
                                    if (name.includes('•')) {
                                        name = name.split('•')[0].trim();
                                    }

                                    // Enlever les retours à la ligne
                                    name = name.split('\\n')[0].trim();

                                    // Vérifier que c'est un vrai nom
                                    if (name.length < 3) return;
                                    if (name === 'Se connecter' || name === 'Message') return;

                                    profiles.push({
                                        href: href,
                                        name: name
                                    });
                                });

                                // Dédupliquer par href
                                const unique = [];
                                const seen = new Set();
                                profiles.forEach(p => {
                                    if (!seen.has(p.href)) {
                                        seen.add(p.href);
                                        unique.push(p);
                                    }
                                });

                                return { profiles: unique, debug: debugInfo };
                            }
                        """)

                        # Afficher les infos de debug
                        if 'debug' in profile_data and profile_data['debug']:
                            logger.info(f"🔍 DEBUG - Premiers liens /in/ trouvés:")
                            for d in profile_data['debug'][:8]:
                                logger.info(f"   • {d['href']} | isMain: {d['isMain']} | {d['text']}")

                        profiles_list = profile_data.get('profiles', [])
                        logger.info(f"🔍 {len(profiles_list)} profils trouvés via JavaScript")

                        # Maintenant récupérer les éléments Playwright correspondants
                        # ET stocker les noms pour les réutiliser
                        links_elements = []
                        profile_names = {}  # href -> name

                        for profile in profiles_list:
                            try:
                                # Nettoyer l'URL (enlever les paramètres)
                                clean_href = profile['href'].split('?')[0]
                                # Ignorer si c'est juste "Se connecter" ou trop court
                                if len(profile['name']) < 3 or profile['name'] in ['Se connecter', 'Message']:
                                    continue
                                # Chercher l'élément avec cet href
                                link = page.query_selector(f'a[href^="{clean_href}"]')
                                if link:
                                    links_elements.append(link)
                                    profile_names[clean_href] = profile['name']
                                    logger.info(f"✅ Profil trouvé: {profile['name']}")
                            except Exception as e:
                                logger.warning(f"⚠️ Impossible de récupérer l'élément pour {profile.get('name', 'inconnu')}: {e}")

                        links = links_elements
                        logger.info(f"🔗 {len(links)} profils à traiter")
                    except Exception as e:
                        self.errors.append(f"Erreur récupération liens: {e}")
                        logger.error(f"❌ Erreur: {e}")
                        break

                    if not links:
                        logger.warning("⚠️ Aucun lien trouvé sur la page")
                        break

                    profils_page = []

                    for link in links:

                        if profils_scrapes >= nb_profils:
                            logger.info(f"✋ Limite de {nb_profils} profils atteinte")
                            break

                        try:
                            # ===== URL =====
                            url_raw = link.get_attribute("href") or ""
                            url_profil = "https://www.linkedin.com" + url_raw if url_raw.startswith("/") else url_raw
                            url_profil = url_profil.split("?")[0]

                            # ===== NOM =====
                            # Utiliser le nom déjà trouvé par JavaScript
                            nom = profile_names.get(url_profil, "")

                            if not nom:
                                logger.info(f"⏭️ Profil sans nom, ignoré ({url_profil})")
                                continue

                            if "utilisateur linkedin" in nom.lower():
                                logger.info(f"⏭️ Utilisateur LinkedIn, ignoré")
                                continue

                            logger.info(f"👤 Profil trouvé: {nom}")

                            # Vérifier si déjà vu dans cette session
                            if url_profil in urls_session:
                                logger.info(f"⏭️ {nom} - Déjà vu dans cette session, ignoré")
                                continue

                            # Vérifier si déjà scrapé (sauf si réinvitation demandée)
                            if url_profil in deja_scrapes_global and not reinviter_profils_scrapes:
                                logger.info(f"⏭️ {nom} - Déjà scrapé, ignoré (réactivez 'Réinviter' pour l'inclure)")
                                continue

                            urls_session.add(url_profil)

                            # ===== POSTE / ENTREPRISE =====
                            poste_et_ent = link.evaluate("""
                                el => {
                                    const card = el.closest('li') || el.closest('div');
                                    if (!card) return {poste: '', entreprise: ''};
                                    
                                    let poste = '';
                                    let entreprise = '';
                                    
                                    // MÉTHODE 1: Chercher le titre principal (sous le nom, avant la localisation)
                                    // C'est la div avec classe entity-result__primary-subtitle
                                    const primarySubtitle = card.querySelector('.entity-result__primary-subtitle');
                                    if (primarySubtitle) {
                                        const text = primarySubtitle.textContent?.trim() || '';
                                        if (text && text.length > 0 && text.length < 200) {
                                            poste = text;
                                            
                                            // Extraire l'entreprise si présente avec @
                                            if (text.includes(' @ ')) {
                                                const parts = text.split(' @ ');
                                                poste = parts[0].trim();
                                                entreprise = parts[1].trim();
                                            }
                                            // Ou avec "chez"
                                            else if (text.toLowerCase().includes(' chez ')) {
                                                const parts = text.split(/ chez /i);
                                                poste = parts[0].trim();
                                                entreprise = parts[1].trim();
                                            }
                                            // Ou avec "at"
                                            else if (text.includes(' at ')) {
                                                const parts = text.split(' at ');
                                                poste = parts[0].trim();
                                                entreprise = parts[1].trim();
                                            }
                                        }
                                    }
                                    
                                    // MÉTHODE 2: Chercher dans "Poste actuel :" OU "Postes précédents :"
                                    const allText = Array.from(card.querySelectorAll('p, div, span'));
                                    for (const elem of allText) {
                                        const text = elem.textContent?.trim() || '';
                                        
                                        // Cas 1: "Poste actuel : [titre] chez [entreprise]"
                                        if (text.startsWith('Poste actuel :') || text.startsWith('Poste actuel:')) {
                                            let cleanText = text
                                                .replace(/^Poste actuel\\s*:\\s*/i, '')
                                                .trim();

                                            // Séparer poste et entreprise si "chez" est présent
                                            if (cleanText.toLowerCase().includes(' chez ')) {
                                                const match = cleanText.match(/^(.+?)\\s+chez\\s+(.+?)$/i);
                                                if (match) {
                                                    if (!poste) poste = match[1].trim();
                                                    entreprise = match[2].trim();
                                                    break;
                                                }
                                            }
                                        }
                                        
                                        // Cas 2: "Postes précédents : [titre] chez [entreprise]"
                                        if (!entreprise && (text.startsWith('Postes précédents :') || text.startsWith('Poste précédent :'))) {
                                            let cleanText = text
                                                .replace(/^Postes? précédents?\\s*:\\s*/i, '')
                                                .trim();

                                            // Séparer poste et entreprise si "chez" est présent
                                            if (cleanText.toLowerCase().includes(' chez ')) {
                                                const match = cleanText.match(/^(.+?)\\s+chez\\s+(.+?)(?:\\s*\\(|$)/i);
                                                if (match) {
                                                    // Seulement prendre le poste précédent si on n'a pas de poste actuel
                                                    if (!poste || poste.length < 5) {
                                                        poste = match[1].trim();
                                                    }
                                                    entreprise = match[2].trim();
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                    
                                    // MÉTHODE 3: Chercher "chez" ou "at" dans tous les éléments si entreprise pas encore trouvée
                                    if (!entreprise) {
                                        for (const elem of allText) {
                                            const text = elem.textContent || '';

                                            // Chercher "chez [entreprise]"
                                            const chezMatch = text.match(/\\bchez\\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\\s&.',-]+?)(?:\\s*\\(|\\s*$|\\s*·|\\s*\\d)/i);
                                            if (chezMatch) {
                                                entreprise = chezMatch[1].trim();
                                                break;
                                            }

                                            // Chercher "at [entreprise]" (pour les profils en anglais)
                                            if (!entreprise) {
                                                const atMatch = text.match(/\\bat\\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\\s&.',-]+?)(?:\\s*$|\\s*·|\\s*\\d)/i);
                                                if (atMatch) {
                                                    entreprise = atMatch[1].trim();
                                                    break;
                                                }
                                            }
                                            
                                            // Chercher "@ [entreprise]"
                                            if (!entreprise) {
                                                const arobaseMatch = text.match(/\\s@\\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9\\s&.',-]+?)(?:\\s*$|\\s*·|\\s*\\d)/i);
                                                if (arobaseMatch) {
                                                    entreprise = arobaseMatch[1].trim();
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                    
                                    return {poste: poste, entreprise: entreprise};
                                }
                            """)

                            poste = poste_et_ent.get("poste", "")
                            entreprise_nom = poste_et_ent.get("entreprise", "")

                            # Nettoyage entreprise
                            if entreprise_nom:
                                entreprise_nom = re.sub(
                                    r'^(Poste actuel|Postes précédents)\s*:\s*',
                                    '',
                                    entreprise_nom,
                                    flags=re.IGNORECASE
                                ).strip()

                            # ===== DONNÉES ENRICHIES =====
                            donnees_enrichies = self.extraire_donnees_enrichies(link)
                            localisation = donnees_enrichies.get("localisation", "")
                            connexions = donnees_enrichies.get("connexions", "")

                            # ===== ENVOI INVITATION IMMÉDIAT =====
                            deja_scrape = url_profil in deja_scrapes_global
                            invite_envoyee = False

                            # Logger le statut
                            if deja_scrape and reinviter_profils_scrapes:
                                logger.info(f"🔄 {nom} - Déjà scrapé mais réinvitation demandée")

                            # Décision d'inviter ou non
                            if inviter:
                                if status_callback:
                                    status_callback(f"📨 Tentative invitation pour {nom}")

                                logger.info(f"🔍 Tentative d'invitation pour {nom}")

                                try:
                                    invite_envoyee = self.envoyer_invitation(page, link, message_invitation)

                                    if invite_envoyee:
                                        invitations_envoyees += 1
                                        logger.info(f"✅ Invitation envoyée à {nom}")
                                    else:
                                        logger.warning(f"⚠️ Impossible d'envoyer invitation à {nom}")

                                    delay = self.config.random_delay(
                                        self.config.DELAY_BETWEEN_PROFILES_MIN,
                                        self.config.DELAY_BETWEEN_PROFILES_MAX
                                    )
                                    page.wait_for_timeout(delay)

                                except Exception as e:
                                    logger.error(f"❌ Erreur invitation {nom}: {e}")
                                    self.errors.append(f"Erreur invitation {nom}: {e}")

                            profils_page.append({
                                "nom": nom,
                                "poste": poste,
                                "entreprise": entreprise_nom,
                                "url": url_profil,
                                "localisation": localisation,
                                "connexions": connexions,
                                "deja_scrape": deja_scrape,
                                "invite_envoyee": invite_envoyee
                            })

                            profils_scrapes += 1

                            if progress_callback:
                                progress_callback(min(profils_scrapes / nb_profils, 1.0))

                        except Exception as e:
                            self.errors.append(f"Erreur profil: {e}")
                            continue

                    # -------------------------
                    # PHASE 3 : SAUVEGARDE (DB + CSV)
                    # -------------------------
                    for profil in profils_page:
                        # Sauvegarde CSV (rétrocompatibilité)
                        self._sauvegarder_profil(
                            profil["nom"],
                            profil["poste"],
                            profil["entreprise"],
                            ecole_nom,
                            profil["url"],
                            profil["invite_envoyee"]
                        )

                        # Sauvegarde base de données
                        if self.use_database and self.db:
                            try:
                                profile_id = self.db.ajouter_profil(
                                    nom=profil["nom"],
                                    poste=profil["poste"],
                                    entreprise=profil["entreprise"],
                                    ecole=ecole_nom,
                                    url=profil["url"],
                                    localisation=profil.get("localisation", ""),
                                    nb_connexions=profil.get("connexions", "")
                                )

                                if profil["invite_envoyee"] and profile_id:
                                    self.db.ajouter_invitation(profile_id, message_invitation)
                            except Exception as e:
                                logger.error(f"Erreur sauvegarde DB: {e}")

                        donnees.append({
                            "Nom": profil["nom"],
                            "Poste": profil["poste"],
                            "Entreprise": profil["entreprise"],
                            "École": ecole_nom,
                            "Localisation": profil.get("localisation", ""),
                            "Connexions": profil.get("connexions", ""),
                            "URL du profil": profil["url"],
                            "Déjà scrapé": profil["deja_scrape"],
                            "Invitation envoyée": "Oui" if profil["invite_envoyee"] else "Non"
                        })

                    # -------------------------
                    # PAGE SUIVANTE
                    # -------------------------
                    if profils_scrapes < nb_profils:
                        current_page += 1
                        try:
                            page.goto(url_recherche + f"&page={current_page}", timeout=self.config.TIMEOUT_PAGE)
                            page.wait_for_timeout(3000)
                        except:
                            break
                    else:
                        break

                browser.close()

                duration = (datetime.now() - start_time).total_seconds()

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

                if email_notif:
                    notifier = EmailNotifier(email_notif)
                    notifier.send_scraping_complete(
                        keyword=keyword,
                        nb_profils=profils_scrapes,
                        nb_invitations=invitations_envoyees,
                        ecoles=[ecole_nom] if ecole_nom else None,
                        duration=duration,
                        errors=self.errors
                    )

                return pd.DataFrame(donnees)

        except Exception as e:
            self.errors.append(str(e))
            logger.error(f"Erreur critique: {e}")

            if email_notif:
                notifier = EmailNotifier(email_notif)
                notifier.send_error_notification(str(e), context="Scraping LinkedIn")

            return pd.DataFrame()

    # ================================
    # CHARGEMENT CSV
    # ================================
    def _charger_urls_scrappees(self) -> set:
        """Charge les URLs depuis la base de données ET le CSV legacy"""
        urls = set()

        # 1. Charger depuis la base de données (prioritaire)
        if self.use_database and self.db:
            try:
                import sqlite3
                conn = sqlite3.connect(self.config.DATABASE_FILE)
                cursor = conn.cursor()
                cursor.execute("SELECT url FROM profiles WHERE url IS NOT NULL AND url != ''")
                urls.update(row[0] for row in cursor.fetchall())
                conn.close()
                logger.debug(f"📊 {len(urls)} URLs chargées depuis la base de données")
            except Exception as e:
                logger.warning(f"Erreur chargement URLs depuis DB: {e}")

        # 2. Charger aussi depuis le CSV (pour compatibilité)
        import os, csv
        if os.path.exists(self.config.PROFIL_FILE):
            try:
                with open(self.config.PROFIL_FILE, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    csv_urls = set(row.get("URL du profil", "") for row in reader if row.get("URL du profil"))
                    urls.update(csv_urls)
                    logger.debug(f"📊 Total {len(urls)} URLs uniques (DB + CSV)")
            except Exception as e:
                logger.warning(f"Erreur chargement URLs depuis CSV: {e}")

        return urls

    # ================================
    # SAUVEGARDE CSV
    # ================================
    def _sauvegarder_profil(self, nom: str, poste: str, entreprise: str,
                            ecole: str, url: str, invite: bool):
        import os, csv

        deja = self._charger_urls_scrappees()

        if url and url not in deja:
            champs = ["Nom", "Poste", "Entreprise", "École",
                      "URL du profil", "Date", "Invitation"]

            existe = os.path.exists(self.config.PROFIL_FILE)

            try:
                with open(self.config.PROFIL_FILE, "a", newline="", encoding="utf-8") as f:
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
                logger.error(f"Erreur sauvegarde: {e}")