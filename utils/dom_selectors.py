# -*- coding: utf-8 -*-
"""
Module de sélection DOM robuste pour LinkedIn
Utilise des sélecteurs stables qui ne dépendent pas des classes CSS générées
"""

from typing import List, Dict, Optional
from logger import logger


class DOMSelectors:
    """
    Classe qui fournit des sélecteurs DOM stables pour LinkedIn
    Stratégie : Utiliser la structure HTML et les attributs data-* plutôt que les classes CSS
    """

    # Sélecteurs principaux (par ordre de priorité)
    PROFILE_CONTAINERS = [
        "li.reusable-search__result-container",  # Container principal des résultats
        "div.entity-result",                      # Fallback 1
        "li[class*='search-result']",            # Fallback 2
    ]

    # Lien profil
    PROFILE_LINK_SELECTORS = [
        "a[href*='/in/'][data-control-name='search_srp_result']",  # Lien principal avec data attribute
        "a.app-aware-link[href*='/in/']",                          # Lien avec classe stable
        "a[href*='/in/']:not([href*='company']):not([href*='school'])",  # Fallback générique
    ]

    # Nom du profil
    NAME_SELECTORS = [
        "span[aria-hidden='true'] span[dir='ltr']",  # Nom dans span avec direction
        "span.entity-result__title-text a span[aria-hidden='true']",
        ".entity-result__title-line a span:first-child",
    ]

    # Poste actuel
    JOB_TITLE_SELECTORS = [
        ".entity-result__primary-subtitle",          # Titre principal
        "div[class*='primary-subtitle']",
        ".entity-result__summary .t-14",
    ]

    # Localisation
    LOCATION_SELECTORS = [
        ".entity-result__secondary-subtitle",
        "div[class*='secondary-subtitle']",
    ]

    # Bouton "Se connecter"
    CONNECT_BUTTON_SELECTORS = [
        "button[aria-label*='Inviter'][aria-label*='à se connecter']",
        "button:has-text('Se connecter')",
        "button[data-control-name='srp_profile_actions']",
    ]

    @staticmethod
    def extract_profiles_data_js() -> str:
        """
        Retourne le code JavaScript pour extraire les profils de manière robuste.

        STRATÉGIE :
        1. Trouver tous les liens /in/ uniques sur la page
        2. Pour chacun, remonter au container le plus proche qui ne contient qu'UN
           seul lien /in/ (isolation stricte)
        3. Dans ce container, extraire poste/entreprise via plusieurs heuristiques
           successives (sélecteurs modernes 2024/2025, anciens entity-result,
           puis walk DOM textuel)

        Le DOM LinkedIn change régulièrement (entity-result → mb1 → autre).
        On combine donc des sélecteurs spécifiques + un fallback générique
        qui scanne tous les éléments texte du card et choisit le meilleur
        candidat (ligne de 5-250 caractères qui ne contient ni le nom,
        ni un mot-clé d'action).
        """
        return """
        () => {
            const EXTRACT_VERSION = 'v3-2026-04-23';
            const profiles = [];
            const debugInfo = [];
            const seenHrefs = new Set();
            let firstContainerHTML = '';
            let firstLinkHTML = '';
            let firstLinkParentChainText = '';
            const emptyCompanyHTML = [];  // HTML des cartes avec poste mais SANS entreprise (debug)

            // ═══════════════════════════════════════════════════
            // HELPER : Parser "Poste chez/at/@ Entreprise"
            // ═══════════════════════════════════════════════════
            function parseJobAndCompany(text) {
                let jobTitle = '';
                let company = '';

                if (!text) return { jobTitle, company };

                text = text.replace(/\\s+/g, ' ').trim();

                const separators = [' chez ', ' at ', ' - ', ' — ', ' – '];
                for (const sep of separators) {
                    if (text.includes(sep)) {
                        const parts = text.split(sep);
                        jobTitle = parts[0].trim();
                        company = parts.slice(1).join(sep).trim();
                        if (company.includes(',')) {
                            company = company.split(',')[0].trim();
                        }
                        return { jobTitle, company };
                    }
                }

                if (text.includes('@')) {
                    const parts = text.split('@');
                    jobTitle = parts[0].trim();
                    company = parts.slice(1).join('@').trim();
                    if (company.includes(',')) {
                        company = company.split(',')[0].trim();
                    }
                    return { jobTitle, company };
                }

                if (text.includes('|')) {
                    const parts = text.split('|');
                    jobTitle = parts[0].trim();
                    company = parts[1]?.trim() || '';
                    return { jobTitle, company };
                }

                jobTitle = text;
                return { jobTitle, company };
            }

            // ═══════════════════════════════════════════════════
            // HELPER : Texte ressemble-t-il à une ligne poste/entreprise ?
            // ═══════════════════════════════════════════════════
            const ACTION_WORDS = [
                'se connecter', 'connect', 'message', 'suivre', 'follow',
                'voir le profil', 'view profile', 'plus', 'more',
                'envoyer', 'send', 'inviter', 'invite',
                'utilisateur linkedin', 'linkedin member',
                'mise en relation', 'mutual', 'relations en commun',
                'a publié', 'has posted', 'a partagé', 'has shared',
                'a aimé', 'likes this', 'a commenté', 'commented'
            ];
            const LOCATION_WORDS = [
                'région de', 'région ', 'ile-de-france', 'île-de-france',
                'paris', 'lyon', 'marseille', 'france', 'suisse', 'belgique',
                'area, ', ' area', 'metropolitan', 'région parisienne'
            ];

            function looksLikeJobLine(text, name) {
                if (!text) return false;
                const t = text.trim();
                if (t.length < 5 || t.length > 250) return false;
                const lower = t.toLowerCase();
                // Rejeter le degré de relation ("• 3e et +", "3e et +", "2e", "1er", "1re", "3rd+", etc.)
                // LinkedIn place ce badge avant le poste : sans ce filtre il est pris pour l'intitulé.
                if (/^[•·\\s]*\\d+(ère|ème|er|re|nd|rd|st|th|e)?(\\s*et\\s*\\+|\\s*\\+|\\s*(connection|niveau|degré))?\\s*$/i.test(t)) {
                    return false;
                }
                for (const w of ACTION_WORDS) {
                    if (lower.includes(w)) return false;
                }
                if (name && lower.includes(name.toLowerCase())) return false;
                // Pas une localisation pure (heuristique simple)
                let locHits = 0;
                for (const w of LOCATION_WORDS) {
                    if (lower.includes(w)) locHits++;
                }
                // Si la ligne ressemble plus à une localisation (mot loc + courte) → reject
                if (locHits > 0 && t.length < 60 && !t.includes(' chez ')
                    && !t.includes(' at ') && !t.includes('@')) {
                    return false;
                }
                // Au moins une lettre
                if (!/[a-zA-ZÀ-ÿ]/.test(t)) return false;
                // Pas que des chiffres ou statut
                if (/^(•|·|\\d+(st|nd|rd|th|er|ème|e)?\\s*(connection|niveau|degré)?)\\s*$/i.test(t)) return false;
                return true;
            }

            function looksLikeLocation(text, name) {
                if (!text) return false;
                const t = text.trim();
                if (t.length < 3 || t.length > 120) return false;
                const lower = t.toLowerCase();
                for (const w of ACTION_WORDS) {
                    if (lower.includes(w)) return false;
                }
                if (name && lower.includes(name.toLowerCase())) return false;
                for (const w of LOCATION_WORDS) {
                    if (lower.includes(w)) return true;
                }
                // Format "Ville, Pays"
                if (/^[A-ZÀ-Ÿ][a-zà-ÿ\\-\\s]+,\\s*[A-ZÀ-Ÿ][a-zà-ÿ\\-\\s]+$/.test(t)) return true;
                return false;
            }

            // ═══════════════════════════════════════════════════
            // HELPER : Extraire nom + poste + company depuis UN container isolé
            // ═══════════════════════════════════════════════════
            function extractFromContainer(container, profileLink) {
                const link = profileLink || container.querySelector('a[href*="/in/"]');
                if (!link) return null;

                const href = link.href;
                if (!href || !href.match(/\\/in\\/[a-zA-Z0-9%\\-_.]+/i)) return null;
                const cleanHref = href.split('?')[0].replace(/\\/+$/, '') + '/';
                if (seenHrefs.has(cleanHref)) return null;

                // 1. Nom
                let name = '';
                const nameSpan = link.querySelector('span[aria-hidden="true"]');
                if (nameSpan) {
                    name = nameSpan.textContent?.trim() || '';
                }
                if (!name) {
                    name = link.textContent?.trim()?.split('\\n')[0] || '';
                }
                if (name.includes('·')) name = name.split('·')[0].trim();
                if (name.includes('•')) name = name.split('•')[0].trim();
                name = name.split('\\n')[0].trim();
                if (name.length > 80) name = name.substring(0, 80).trim();

                if (!name || name.length < 2) return null;
                const invalidNames = ['Se connecter', 'Message', 'Suivre', 'Plus',
                                      'Utilisateur LinkedIn', 'LinkedIn Member',
                                      'Voir le profil', 'View profile'];
                if (invalidNames.includes(name)) return null;

                let jobTitle = '';
                let company = '';
                let location = '';
                let usedMethod = '';

                // ── Méthode A : ancien sélecteur entity-result ──
                const primarySubtitle = container.querySelector(
                    '.entity-result__primary-subtitle, ' +
                    'div[class*="entity-result__primary-subtitle"]'
                );
                if (primarySubtitle) {
                    const subtitleText = primarySubtitle.textContent?.trim() || '';
                    if (looksLikeJobLine(subtitleText, name)) {
                        const parsed = parseJobAndCompany(subtitleText);
                        jobTitle = parsed.jobTitle;
                        company = parsed.company;
                        usedMethod = 'A_entity-result';
                    }
                }

                const secondarySubtitle = container.querySelector(
                    '.entity-result__secondary-subtitle, ' +
                    'div[class*="entity-result__secondary-subtitle"]'
                );
                if (secondarySubtitle) {
                    location = secondarySubtitle.textContent?.trim() || '';
                }

                // ── Méthode B : sélecteurs modernes 2024/2025 ──
                // LinkedIn utilise maintenant des div avec classes utilitaires
                // t-14 t-black t-normal pour le poste, et t-14 t-normal pour la loc.
                if (!jobTitle) {
                    const modernSelectors = [
                        'div.t-14.t-black.t-normal',
                        'div.t-14.t-normal.t-black',
                        'div[class*="t-14"][class*="t-black"][class*="t-normal"]',
                        'p.entity-result__summary',
                        '.linked-area .t-14',
                        'div.mb1 div.t-14',
                        'div.linked-area div',
                    ];
                    for (const sel of modernSelectors) {
                        const els = container.querySelectorAll(sel);
                        for (const el of els) {
                            const text = el.textContent?.trim() || '';
                            if (looksLikeJobLine(text, name)) {
                                const parsed = parseJobAndCompany(text);
                                if (parsed.jobTitle) {
                                    jobTitle = parsed.jobTitle;
                                    company = parsed.company;
                                    usedMethod = 'B_modern:' + sel;
                                    break;
                                }
                            }
                        }
                        if (jobTitle) break;
                    }
                }

                // ── Méthode C : balises <p> (texte "Poste actuel : ...") ──
                if (!jobTitle) {
                    const paragraphs = container.querySelectorAll('p');
                    for (const p of paragraphs) {
                        const text = p.textContent?.trim() || '';
                        if (text.length < 5 || text.length > 250) continue;
                        if (text.match(/^Poste(s)? (actuel|précédent)/i)) {
                            const cleanText = text.replace(/^Poste(s)? (actuel|précédent)(s)?\\s*:\\s*/i, '').trim();
                            const parsed = parseJobAndCompany(cleanText);
                            if (parsed.jobTitle) {
                                jobTitle = parsed.jobTitle;
                                company = parsed.company;
                                usedMethod = 'C_p_poste';
                                break;
                            }
                        }
                        if (text.match(/^(Current|Previous) (role|position)/i)) {
                            const cleanText = text.replace(/^(Current|Previous) (role|position)\\s*:?\\s*/i, '').trim();
                            const parsed = parseJobAndCompany(cleanText);
                            if (parsed.jobTitle) {
                                jobTitle = parsed.jobTitle;
                                company = parsed.company;
                                usedMethod = 'C_p_current';
                                break;
                            }
                        }
                    }
                }

                // ── Méthode D : walk DOM générique (le plus robuste) ──
                // On scanne tous les div/p/span "feuilles" du container et on
                // sélectionne le premier texte qui ressemble à un poste.
                if (!jobTitle) {
                    const candidates = [];
                    const all = container.querySelectorAll('div, p, span');
                    for (const el of all) {
                        // Ignorer si contient d'autres éléments de bloc (on veut feuille)
                        const blockChildren = el.querySelectorAll('div, p, li, ul, button, a');
                        if (blockChildren.length > 0) continue;
                        // Ignorer si dans un bouton ou un lien
                        if (el.closest('button')) continue;
                        const linkAncestor = el.closest('a');
                        if (linkAncestor && linkAncestor.href && linkAncestor.href.includes('/in/')) {
                            // Si c'est dans le lien profil, on l'ignore (c'est le nom/badge)
                            continue;
                        }
                        const text = el.textContent?.trim() || '';
                        if (looksLikeJobLine(text, name)) {
                            candidates.push({ text, el });
                        }
                    }
                    // Premier candidat = poste, second éventuel = localisation
                    if (candidates.length > 0) {
                        const parsed = parseJobAndCompany(candidates[0].text);
                        jobTitle = parsed.jobTitle;
                        company = parsed.company;
                        usedMethod = 'D_walk';
                        if (!location) {
                            for (let i = 1; i < candidates.length; i++) {
                                if (looksLikeLocation(candidates[i].text, name)) {
                                    location = candidates[i].text;
                                    break;
                                }
                            }
                        }
                    }
                }

                // ── Méthode E : texte complet du lien ──
                if (!jobTitle) {
                    const fullText = link.textContent?.trim() || '';
                    let workText = fullText;
                    if (workText.startsWith(name)) {
                        workText = workText.substring(name.length).trim();
                    }
                    workText = workText.replace(/^[·•\\s]+\\d+(st|nd|rd|th|e|er|ème)\\+?\\s*/i, '').trim();
                    const cutPoints = ['Se connecter', 'Poste actuel', 'Postes précédents', 'Suivre', 'Message'];
                    for (const cp of cutPoints) {
                        const idx = workText.indexOf(cp);
                        if (idx !== -1) {
                            workText = workText.substring(0, idx).trim();
                            break;
                        }
                    }
                    if (workText.length > 3 && workText.length < 200) {
                        const parsed = parseJobAndCompany(workText);
                        jobTitle = parsed.jobTitle;
                        company = parsed.company || company;
                        usedMethod = usedMethod || 'E_link_text';
                    }
                }

                // Localisation fallback : chercher une feuille qui ressemble à loc
                if (!location) {
                    const all = container.querySelectorAll('div, p, span');
                    for (const el of all) {
                        const blockChildren = el.querySelectorAll('div, p, li, ul, button, a');
                        if (blockChildren.length > 0) continue;
                        if (el.closest('button')) continue;
                        const text = el.textContent?.trim() || '';
                        if (looksLikeLocation(text, name)) {
                            location = text;
                            break;
                        }
                    }
                }

                // ── Entreprise depuis la ligne "Poste actuel : … chez X" ──
                // Source la plus fiable : le headline ne contient pas toujours
                // l'entreprise (et peut contenir des séparateurs trompeurs).
                // On cherche l'élément dont le texte commence par
                // "Poste actuel/précédent" (ou "Current/Previous") et on prend
                // ce qui suit le dernier " chez " / " at ".
                {
                    const summaryEls = container.querySelectorAll('div, p, span');
                    for (const el of summaryEls) {
                        const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (!/^(Postes?\\s+(actuels?|pr[eé]c[eé]dents?)|Current|Previous)/i.test(text)) continue;
                        const lower = text.toLowerCase();
                        let idx = lower.lastIndexOf(' chez ');
                        let sep = 6;
                        if (idx === -1) { idx = lower.lastIndexOf(' at '); sep = 4; }
                        if (idx === -1) continue;
                        let comp = text.substring(idx + sep).trim();
                        if (comp.includes(',')) comp = comp.split(',')[0].trim();
                        comp = comp.split(/\\s+[|·•]\\s+/)[0].trim();
                        if (comp && comp.length <= 80) {
                            company = comp;
                            break;
                        }
                    }
                }

                seenHrefs.add(cleanHref);

                return {
                    href: cleanHref,
                    name: name,
                    jobTitle: jobTitle,
                    company: company,
                    location: location,
                    connections: '',
                    _method: usedMethod
                };
            }

            // ═══════════════════════════════════════════════════
            // HELPER : Trouver le card le plus PROCHE contenant
            // ce lien et un seul lien /in/
            // ═══════════════════════════════════════════════════
            function findIsolatedCard(profileLink) {
                const candidates = [
                    profileLink.closest('[data-chameleon-result-urn]'),
                    profileLink.closest('li.reusable-search__result-container'),
                    profileLink.closest('div.entity-result'),
                    profileLink.closest('li[class*="search-result"]'),
                    profileLink.closest('li.mb1'),
                    profileLink.closest('div.mb1'),
                    profileLink.closest('li'),
                    profileLink.closest('div[class*="entity-result"]'),
                ].filter(Boolean);

                // Garder le plus PETIT card qui contient au plus 1 lien /in/ unique
                let best = null;
                for (const card of candidates) {
                    const linksInCard = card.querySelectorAll('a[href*="/in/"]');
                    const uniqueHrefs = new Set(
                        Array.from(linksInCard)
                            .map(l => l.href.split('?')[0])
                            .filter(h => h.match(/\\/in\\/[a-zA-Z0-9%\\-_.]+/i))
                    );
                    if (uniqueHrefs.size <= 1) {
                        if (!best || card.contains(best) === false) {
                            best = card;
                        }
                    }
                }
                return best;
            }

            // ═══════════════════════════════════════════════════
            // STRATÉGIE PRINCIPALE : itérer sur les liens /in/
            // ═══════════════════════════════════════════════════
            const allLinks = document.querySelectorAll('a[href*="/in/"]');
            console.log(`[Extract] Found ${allLinks.length} /in/ links`);

            for (const profileLink of allLinks) {
                try {
                    const href = profileLink.href;
                    if (!href.match(/\\/in\\/[a-zA-Z0-9%\\-_.]+/i)) continue;
                    const cleanHref = href.split('?')[0].replace(/\\/+$/, '') + '/';
                    if (seenHrefs.has(cleanHref)) continue;

                    // Ne traiter que les liens qui ont un texte (= sont LE lien profil
                    // de la card, pas un lien image dupliqué)
                    const linkText = profileLink.textContent?.trim() || '';
                    if (linkText.length < 2) continue;

                    const card = findIsolatedCard(profileLink);
                    // ── FALLBACK ULTIME : si aucun closest() ne match,
                    // remonter manuellement jusqu'à trouver un ancêtre
                    // qui ne contient qu'un seul lien /in/
                    let usedCard = card;
                    if (!usedCard) {
                        let cur = profileLink.parentElement;
                        for (let depth = 0; depth < 12 && cur; depth++) {
                            const links = cur.querySelectorAll('a[href*="/in/"]');
                            const uniq = new Set(
                                Array.from(links)
                                    .map(l => l.href.split('?')[0])
                                    .filter(h => h.match(/\\/in\\/[a-zA-Z0-9%\\-_.]+/i))
                            );
                            if (uniq.size > 1) break;
                            // Si l'ancêtre a au moins 50 chars de texte, on le garde
                            const txtLen = (cur.textContent || '').trim().length;
                            if (txtLen >= 30) {
                                usedCard = cur;
                            }
                            cur = cur.parentElement;
                        }
                    }

                    // Capturer le HTML du premier lien + chaîne d'ancêtres pour debug
                    if (!firstLinkHTML) {
                        firstLinkHTML = (profileLink.outerHTML || '').substring(0, 1500);
                        // Chaîne d'ancêtres (tag.class) pour identifier la structure
                        const chain = [];
                        let p = profileLink.parentElement;
                        for (let i = 0; i < 8 && p; i++) {
                            const cls = (p.className || '').toString().substring(0, 80);
                            chain.push(`${p.tagName.toLowerCase()}.${cls}`);
                            p = p.parentElement;
                        }
                        firstLinkParentChainText = chain.join(' > ');
                    }

                    if (!usedCard) {
                        // Toujours pas de card → extraire juste le nom + populate debug
                        let name = '';
                        const nameSpan = profileLink.querySelector('span[aria-hidden="true"]');
                        if (nameSpan) name = nameSpan.textContent?.trim() || '';
                        if (!name) name = linkText.split('\\n')[0] || '';
                        if (name.includes('•')) name = name.split('•')[0].trim();
                        if (name.includes('·')) name = name.split('·')[0].trim();

                        if (name && name.length >= 2) {
                            seenHrefs.add(cleanHref);
                            profiles.push({
                                href: cleanHref, name, jobTitle: '', company: '',
                                location: '', connections: '', _method: 'no_card'
                            });
                            if (debugInfo.length < 5) {
                                debugInfo.push({
                                    name: name,
                                    jobTitle: '',
                                    company: '',
                                    location: '',
                                    method: 'no_card'
                                });
                            }
                        }
                        continue;
                    }

                    // Capturer le HTML du premier card pour debug
                    if (!firstContainerHTML) {
                        firstContainerHTML = (usedCard.outerHTML || '').substring(0, 4000);
                    }

                    const profile = extractFromContainer(usedCard, profileLink);
                    if (profile) {
                        profiles.push(profile);
                        // Capturer le HTML des cartes avec poste mais SANS entreprise
                        if (profile.jobTitle && !profile.company && emptyCompanyHTML.length < 3) {
                            emptyCompanyHTML.push({
                                name: profile.name,
                                jobTitle: profile.jobTitle,
                                html: (usedCard.outerHTML || '').substring(0, 6000)
                            });
                        }
                        if (debugInfo.length < 5) {
                            debugInfo.push({
                                name: profile.name,
                                jobTitle: (profile.jobTitle || '').substring(0, 60),
                                company: (profile.company || '').substring(0, 40),
                                location: (profile.location || '').substring(0, 40),
                                method: profile._method || '(none)'
                            });
                        }
                    }
                } catch (err) {
                    console.error('Error in link extraction:', err);
                }
            }

            console.log(`Total extracted: ${profiles.length} unique profiles`);
            if (debugInfo.length > 0) {
                console.log('Sample:', JSON.stringify(debugInfo, null, 2));
            }

            return {
                profiles: profiles,
                debug: debugInfo,
                totalLinks: profiles.length,
                firstContainerHTML: firstContainerHTML,
                emptyCompanyHTML: emptyCompanyHTML
            };
        }
        """

    @staticmethod
    def find_connect_button_js() -> str:
        """
        JavaScript pour trouver et cliquer sur le bouton "Se connecter"
        Utilise plusieurs stratégies pour maximiser la fiabilité
        """
        return """
        (containerElement) => {
            // Récupérer le container du profil
            const card = containerElement.closest('li') || containerElement.closest('div.entity-result');
            if (!card) {
                return { success: false, reason: 'no_card' };
            }

            // STRATÉGIE 1 : Chercher par aria-label (le plus stable)
            let connectButton = card.querySelector('button[aria-label*="Inviter"][aria-label*="à se connecter"]');

            // STRATÉGIE 2 : Chercher par texte "Se connecter"
            if (!connectButton) {
                const allButtons = card.querySelectorAll('button, a[role="button"]');
                for (const btn of allButtons) {
                    const text = btn.textContent?.trim() || '';
                    const ariaLabel = btn.getAttribute('aria-label') || '';

                    if (text === 'Se connecter' || ariaLabel.includes('Se connecter')) {
                        if (btn.offsetParent !== null && !btn.disabled) {
                            connectButton = btn;
                            break;
                        }
                    }
                }
            }

            // STRATÉGIE 3 : Chercher dans les spans (fallback)
            if (!connectButton) {
                const spans = card.querySelectorAll('span');
                for (const span of spans) {
                    if (span.textContent?.trim() === 'Se connecter') {
                        let current = span;
                        for (let i = 0; i < 7; i++) {
                            current = current.parentElement;
                            if (!current) break;

                            if ((current.tagName === 'BUTTON' || current.tagName === 'A' ||
                                 current.getAttribute('role') === 'button') &&
                                current.offsetParent !== null && !current.disabled) {
                                connectButton = current;
                                break;
                            }
                        }
                        if (connectButton) break;
                    }
                }
            }

            // Vérifier si on a trouvé le bouton
            if (!connectButton) {
                // Retourner les boutons disponibles pour debug
                const availableButtons = Array.from(card.querySelectorAll('button, a'))
                    .map(b => b.textContent?.trim())
                    .filter(Boolean)
                    .join(', ');

                return {
                    success: false,
                    reason: 'no_button',
                    availableButtons: availableButtons
                };
            }

            // Cliquer sur le bouton
            try {
                connectButton.click();
                return { success: true };
            } catch (err) {
                return {
                    success: false,
                    reason: 'click_failed',
                    error: err.message
                };
            }
        }
        """

    @staticmethod
    def find_send_invitation_button_js() -> str:
        """
        JavaScript pour trouver et cliquer sur "Envoyer sans note" ou "Envoyer"
        """
        return """
        () => {
            const normalize = (text) => {
                return text?.replace(/\\s+/g, ' ').trim().toLowerCase() || '';
            };

            // Chercher dans tous les boutons de la modal
            const allButtons = document.querySelectorAll('button');

            for (const btn of allButtons) {
                const text = normalize(btn.textContent);
                const ariaLabel = normalize(btn.getAttribute('aria-label') || '');

                // Chercher "Envoyer sans note" ou "Envoyer"
                if ((text.includes('envoyer sans note') ||
                     text === 'envoyer' ||
                     ariaLabel.includes('envoyer sans note') ||
                     ariaLabel.includes('envoyer l\\'invitation')) &&
                    btn.offsetParent !== null &&
                    !btn.disabled &&
                    !ariaLabel.includes('ajouter')) {

                    try {
                        btn.click();
                        console.log('Clicked send button:', text || ariaLabel);
                        return { success: true, method: 'js_click' };
                    } catch (err) {
                        return { success: false, error: err.message };
                    }
                }
            }

            return { success: false, reason: 'button_not_found' };
        }
        """
