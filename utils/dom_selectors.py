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
                // Dédupliquer un nom répété ("Hugo Proust Hugo Proust" → "Hugo Proust")
                {
                    const toks = name.split(/\\s+/).filter(Boolean);
                    if (toks.length >= 2 && toks.length % 2 === 0) {
                        const half = toks.length / 2;
                        const a = toks.slice(0, half).join(' ');
                        const b = toks.slice(half).join(' ');
                        if (a && a.toLowerCase() === b.toLowerCase()) name = a;
                    }
                }
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
                        // Le vrai nom d'entreprise vient en premier : couper au
                        // premier séparateur (tiret espacé, deux-points, |, •, virgule).
                        comp = comp.split(/\\s+[-–—:|·•]\\s+|,/)[0].trim();
                        if (comp.length > 60) comp = comp.substring(0, 60).trim();
                        if (comp) {
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
                // Nouveau DOM : la carte de résultat est un div[role="listitem"].
                // On la renvoie telle quelle même si elle contient un 2e lien
                // /in/ (ex. "X est une relation que vous avez en commun").
                const lst = profileLink.closest('div[role="listitem"]');
                if (lst) return lst;
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

                    // Ignorer un lien SECONDAIRE d'une carte (ex. "X est une
                    // relation en commun") : on ne garde que le profil principal,
                    // càd le 1er lien /in/ de la carte listitem.
                    const _lst = profileLink.closest('div[role="listitem"]');
                    if (_lst) {
                        const _first = _lst.querySelector('a[href*="/in/"]');
                        if (_first) {
                            const _firstHref = _first.href.split('?')[0].replace(/\\/+$/, '') + '/';
                            if (_firstHref !== cleanHref) continue;
                        }
                    }

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

    # ------------------------------------------------------------------
    # Panneau « Plus de profils pour vous »
    # ------------------------------------------------------------------

    @staticmethod
    def extract_browsemap_js() -> str:
        """Lecture des profils voisins, dans le panneau ou dans la section.

        La fonction rendue prend un argument `mode` :

        - `'panneau'` (défaut) : le panneau ouvert par « Tout afficher ».
          On ne se rabat PAS sur `main` ou `body` quand il manque : on y
          lirait des liens `/in/` qui ne sont pas des suggestions, et des
          données plausibles mais fausses valent moins qu'un échec bruyant.
        - `'section'` : la section « Plus de profils pour vous » de la page
          du profil, repli quand le panneau ne s'ouvre pas. Elle n'en montre
          que les premiers (≈5) ; c'est à Python de le dire.

        Un seul extracteur à deux racines plutôt que deux extracteurs : les
        cartes sont les mêmes des deux côtés (constaté au premier essai
        réel), et deux copies de la lecture d'une carte finiraient par
        diverger sans que personne ne le voie.

        Écrit défensivement : on n'ancre sur aucune classe CSS — LinkedIn
        les regénère et les obfusque — mais sur les liens `/in/`, sur la
        structure et sur le texte. Quand rien n'est lu, le HTML de la racine
        (ou du document) est toujours renvoyé : c'est la seule façon de
        rattraper un changement de structure, y compris quand la lecture
        « réussit » mais de travers (c'est Python qui décide de
        l'enregistrer). Plafond d'un million de caractères.
        """
        return (
            "(mode) => {\n"
            + _JS_OUTILS_PANNEAU
            + _JS_LECTURE_CARTES
            + "\n}"
        )

    @staticmethod
    def compter_panneau_browsemap_js() -> str:
        """Nombre de profils distincts dans le panneau ouvert, 0 sans panneau.

        Sert à deux choses : attendre que le panneau soit là après le clic,
        et savoir quand le déroulement cesse d'en apporter. Il choisit le
        panneau exactement comme l'extracteur, sinon on attendrait ou on
        déroulerait un autre conteneur que celui qu'on lit.
        """
        return (
            "() => {\n"
            + _JS_OUTILS_PANNEAU
            + "\n    const racine = choisirPanneau();\n"
            "    return racine ? nbProfils(racine) : 0;\n}"
        )

    @staticmethod
    def derouler_panneau_browsemap_js() -> str:
        """Pousse vers le bas tout ce qui défile dans le panneau ouvert.

        Faire défiler la fenêtre ne suffit pas : le panneau est un overlay,
        c'est son propre conteneur qu'il faut pousser — et ce conteneur n'est
        pas forcément le dialogue lui-même, souvent un descendant.
        """
        return (
            "() => {\n"
            + _JS_OUTILS_PANNEAU
            + r"""
    const d = choisirPanneau();
    const cibles = d ? [d, ...d.querySelectorAll('*')] : [];
    let pousse = false;
    for (const el of cibles) {
        if (el.scrollHeight > el.clientHeight + 40) {
            el.scrollTop = el.scrollHeight;
            pousse = true;
        }
    }
    if (!pousse) window.scrollTo(0, document.body.scrollHeight);
}"""
        )


    @staticmethod
    def extract_page_apropos_js() -> str:
        """Lecture de la page « À propos » d'une entreprise.

        Ancrée sur la structure sémantique (<dl>/<dt>/<dd>, <main>, lien
        « voir les employés ») et jamais sur les classes CSS, que LinkedIn
        regénère. Quand aucune rubrique n'est lue, ou que l'identifiant est
        ambigu, le HTML de <main> est renvoyé pour être enregistré : c'est la seule façon de rattraper un
        changement de structure.
        """
        return r"""() => {
            const net = s => (s || '').replace(/\s+/g, ' ').trim();
            const racine = document.querySelector('main') || document.body;
            const champs = {};
            for (const dt of racine.querySelectorAll('dl dt')) {
                const cle = net(dt.innerText);
                const valeurs = [];
                let el = dt.nextElementSibling;
                while (el && el.tagName === 'DD') {
                    // LinkedIn double certaines valeurs d'un texte réservé aux
                    // lecteurs d'écran (« Le numéro est le … »), niché dans le
                    // même lien : on le retire avant de lire la valeur.
                    const copie = el.cloneNode(true);
                    copie.querySelectorAll('.visually-hidden').forEach(n => n.remove());
                    const v = net(copie.textContent);
                    if (v) valeurs.push(v);
                    el = el.nextElementSibling;
                }
                if (cle && valeurs.length) champs[cle] = valeurs;
            }
            // Plusieurs entreprises ont un lien « employés » dans <main> (la
            // page réelle y met aussi le bloc « Des personnes suivent
            // également »). Le premier lien peut donc être celui d'une autre :
            // on retient l'identifiant le plus fréquent, et en cas d'égalité on
            // renvoie vide plutôt que de ranger des inconnus sous cette entreprise.
            const compte = {};
            for (const lien of racine.querySelectorAll('a[href*="currentCompany"]')) {
                let href = lien.getAttribute('href') || '';
                try { href = decodeURIComponent(href); } catch (e) {}
                const m = href.match(/currentCompany=\["?(\d+)/);
                if (m) compte[m[1]] = (compte[m[1]] || 0) + 1;
            }
            let companyId = '';
            let meilleur = 0, egalite = false;
            for (const [id, n] of Object.entries(compte)) {
                if (n > meilleur) { meilleur = n; companyId = id; egalite = false; }
                else if (n === meilleur) egalite = true;
            }
            if (egalite) companyId = '';
            const h1 = racine.querySelector('h1');
            let description = '';
            for (const h of racine.querySelectorAll('h2')) {
                const t = net(h.innerText).replace('’', "'");
                if (t === "Vue d'ensemble") {
                    const p = h.parentElement && h.parentElement.querySelector('p');
                    if (p) description = net(p.innerText);
                    break;
                }
            }
            return {
                nom: h1 ? net(h1.innerText) : '',
                champs: champs,
                company_id: companyId,
                description: description,
                // Rubriques lues mais identifiant vide (égalité) : la page est
                // aussi rendue, pour voir dans logs/ d'où venait l'ambiguïté.
                html: (Object.keys(champs).length && companyId) ? '' : racine.innerHTML.slice(0, 1000000)
            };
        }"""

    @staticmethod
    def extract_recherche_entreprises_js() -> str:
        """Lecture de la recherche d'entreprises : `{resultats: [{nom, url}], html}`.

        Une carte `role="listitem"` = une entreprise, dans l'ordre de la page,
        dédoublonnées par slug ; `url` est le lien canonique
        `https://www.linkedin.com/company/<slug>/` (sans `?trk=`).

        Le nom vient du titre que la carte désigne par `aria-labelledby`, à
        défaut du premier lien non vide de la carte vers cette entreprise.
        Pas du texte le plus long : la capture réelle montre un lien
        « Jeanne et 3 autres relations suivent cette page » vers la même
        entreprise, plus long que « BNP Paribas » — il ferait manquer le nom
        exact. Les liens hors carte (en-tête, publicité, liens vides laissés
        par les <a> imbriqués que le navigateur défait) sont ignorés.
        Aucune carte lue : le HTML de <main> est renvoyé pour être enregistré.
        Sans <main>, aucune carte n'est lue (le reste de la page — en-tête,
        publicités — n'est pas un résultat) et le HTML du corps est renvoyé.
        """
        return r"""() => {
            const net = s => (s || '').replace(/\s+/g, ' ').trim();
            const racine = document.querySelector('main');
            if (!racine) return {resultats: [], html: document.body.innerHTML.slice(0, 1000000)};
            const slugDe = a => {
                const m = (a.getAttribute('href') || '').match(/\/company\/([^\/?#]+)/);
                return m ? m[1] : '';
            };
            const resultats = [];
            const vus = new Set();
            for (const carte of racine.querySelectorAll('[role="listitem"]')) {
                const liens = [...carte.querySelectorAll('a[href*="/company/"]')].filter(slugDe);
                let slug = '', nom = '';
                for (const id of (carte.getAttribute('aria-labelledby') || '').split(/\s+/)) {
                    const titre = id && document.getElementById(id);
                    const lien = titre && (titre.matches('a[href*="/company/"]') ? titre
                                           : titre.querySelector('a[href*="/company/"]'));
                    if (lien && slugDe(lien) && net(lien.innerText)) {
                        slug = slugDe(lien); nom = net(lien.innerText); break;
                    }
                }
                if (!slug && liens.length) slug = slugDe(liens[0]);
                if (!slug || vus.has(slug)) continue;
                if (!nom) {
                    const lien = liens.find(a => slugDe(a) === slug && net(a.innerText));
                    nom = lien ? net(lien.innerText) : '';
                }
                if (!nom) continue;
                vus.add(slug);
                resultats.push({nom: nom, url: 'https://www.linkedin.com/company/' + slug + '/'});
            }
            return {resultats: resultats, html: resultats.length ? '' : racine.innerHTML.slice(0, 1000000)};
        }"""

    @staticmethod
    def etat_resultats_personnes_js() -> str:
        """État d'une page de résultats de personnes : `{aucunResultat, html}`.

        Sert quand l'extracteur n'a rien lu : distinguer le « Aucun résultat »
        affiché par LinkedIn (vraie absence) d'une page pleine que l'on n'a
        pas su lire. Le HTML de la zone principale est rendu pour être
        enregistré dans logs/.
        """
        return r"""() => {
            const zone = document.querySelector('main') || document.body;
            const texte = (zone && zone.innerText) || '';
            return {
                aucunResultat: /Aucun r.sultat|No results found/i.test(texte),
                html: zone ? zone.outerHTML : '',
            };
        }"""

    @staticmethod
    def extract_degres_js() -> str:
        """Degré de relation par carte de résultats de personnes : `{vanity: "1er"|"2e"|"3e"}`.

        Le vanity est décodé et en minuscules (même clé que `vanity_depuis_url`).
        Le degré est lu dans le texte de la carte, sous la forme « · 1er » seul
        en fin de ligne (pas « · 1er cabinet » dans un titre) —
        vue sur d'autres listes LinkedIn, pas encore sur cette page : on
        accepte aussi « • » et l'anglais (« 1st »). Une carte sans degré
        lisible est absente du résultat ; rien de lu → `{}`, et la relation
        ne viendra alors que des invitations acceptées.
        """
        return r"""() => {
            const DEGRES = {'1er': '1er', '1st': '1er', '2e': '2e', '2nd': '2e', '3e': '3e', '3rd': '3e'};
            // Le badge est seul en fin de ligne (« Jeanne Exemple · 1er », « · 3e et + ») :
            // sans cette ancre, un titre « Consultante · 1er cabinet » ou « · 1st time
            // founder » ferait passer une inconnue pour une relation de 1er degré.
            // \u00a0 : innerText transforme un &nbsp; en espace insécable, que ni [ \t] ni
            // `$` n'acceptent ; sans lui un badge « · 1er&nbsp; » ne serait pas lu.
            const motif = /[·•]\s*(1er|2e|3e|1st|2nd|3rd)(?:\s*(?:et\s*)?\+)?[ \t ]*$/im;
            const vanityDe = href => {
                const m = (href || '').match(/\/in\/([^/?#]+)/);
                if (!m || /\/in\/[^/?#]+\/overlay\//.test(href)) return null;
                let v = m[1];
                try { v = decodeURIComponent(v); } catch (e) { /* encodage invalide : brut */ }
                return v.trim().toLowerCase() || null;
            };
            const degres = {};
            for (const carte of document.querySelectorAll('div[role="listitem"], li[role="listitem"]')) {
                const lien = [...carte.querySelectorAll('a[href*="/in/"]')]
                    .find(a => vanityDe(a.getAttribute('href')));
                if (!lien) continue;
                const vanity = vanityDe(lien.getAttribute('href'));
                // innerText seul : il garde les retours à la ligne entre blocs, dont
                // dépend l'ancre ; textContent collerait le badge au titre suivant.
                const m = (carte.innerText || '').match(motif);
                if (!m || vanity in degres) continue;
                degres[vanity] = DEGRES[m[1].toLowerCase()];
            }
            return degres;
        }"""

    @staticmethod
    def fenetre_coordonnees_ouverte_js() -> str:
        """Vrai dès que la fenêtre « Coordonnées » est ouverte.

        Sondé à chaque image pendant l'attente du clic : rien qu'un test, pas
        l'extracteur entier, qui copierait le HTML de la page à chaque fois.
        Même choix de fenêtre que `extract_coordonnees_js`.
        """
        return r"""() => [...document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]')]
            .some(el => (el.tagName === 'DIALOG' ? el.open
                         : !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
                        && /coordonn[ée]es|contact info/i.test(el.innerText || el.textContent || ''))"""

    @staticmethod
    def extract_coordonnees_js() -> str:
        """Fenêtre « Coordonnées » d'un profil : `{dialogue, email, telephone, html}`.

        La fenêtre est le `<dialog open>` (ou `[role=dialog]`/`[aria-modal]`
        visible) dont le texte porte « Coordonnées » / « Contact info » : le
        profil garde d'autres <dialog> fermés (menus), qu'on ignore.
        Email : premier lien `mailto:`. Téléphone : premier lien `tel:`, sinon
        le texte sous la rubrique « Téléphone » (sans « (Mobile) »).

        `dialogue` faux : aucune fenêtre ouverte, `html` = la page. Fenêtre
        ouverte mais aucune rubrique reconnue : `html` = la fenêtre — sa
        structure a changé, et « rien de partagé » serait un faux constat.
        Rubrique reconnue sans email ni téléphone : la personne ne partage
        rien, `html` vide.
        """
        return r"""() => {
            const net = s => (s || '').replace(/\s+/g, ' ').trim();
            const sansAccents = s => net(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
            const visible = el => el.tagName === 'DIALOG' ? el.open
                : !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const fenetre = [...document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]')]
                .filter(visible)
                .find(el => /coordonnees|contact info/.test(sansAccents(el.innerText || el.textContent)));
            if (!fenetre) {
                const racine = document.querySelector('main') || document.body;
                return {dialogue: false, email: '', telephone: '', html: racine.innerHTML.slice(0, 1000000)};
            }
            // Libellés de son propre profil (« Votre profil ») ET de celui d'autrui
            // (« Profil de Jeanne », « Jeanne’s Profile », « Relation depuis »,
            // « Connected since ») : la veille lit surtout les seconds.
            const RUBRIQUES = [
                /^(votre profil|your profile|profil|profile)\b/, /^profil de /, /['’]s profile$/,
                /^(e-mail|email|telephone|phone|site web|sites web|website|websites|adresse|address)$/,
                /^(anniversaire|birthday|messagerie instantanee|im)$/, /relation/, /^connected\b/,
            ];
            const TELEPHONE = /^(telephone|phone)$/;
            const libelles = [...fenetre.querySelectorAll('p, span, h3, dt, header')].filter(el => {
                const t = sansAccents(el.innerText || el.textContent);
                return t.length <= 60 && RUBRIQUES.some(r => r.test(t));
            });
            // Le lien du profil de la personne, présent dans toute fenêtre
            // « Coordonnées » : il suffit à dire la fenêtre lue, même si aucun
            // libellé n'est reconnu — sans email ni téléphone, c'est « rien de
            // partagé », pas une structure inconnue.
            const lienProfil = [...fenetre.querySelectorAll('a[href*="/in/"]')].some(a =>
                /\/in\/[^\/?#]+\/?(?:[?#]|$)/.test(a.getAttribute('href') || ''));
            const mail = fenetre.querySelector('a[href^="mailto:"]');
            let email = '';
            if (mail) {
                let v = (mail.getAttribute('href') || '').slice(7).split('?')[0];
                try { v = decodeURIComponent(v); } catch (e) { /* brut */ }
                email = net(v);
            }
            let telephone = '';
            const tel = fenetre.querySelector('a[href^="tel:"]');
            if (tel) {
                telephone = net((tel.getAttribute('href') || '').slice(4));
            } else {
                const libelle = libelles.find(el => TELEPHONE.test(sansAccents(el.innerText || el.textContent)));
                let suivant = libelle && libelle.nextElementSibling;
                while (suivant && !telephone) {
                    const texte = net((suivant.innerText || suivant.textContent).replace(/\([^)]*\)/g, ' '));
                    if ((texte.match(/\d/g) || []).length >= 6) telephone = texte;
                    suivant = suivant.nextElementSibling;
                }
            }
            const lisible = libelles.length || lienProfil || email || telephone;
            return {dialogue: true, email: email, telephone: telephone,
                    html: lisible ? '' : fenetre.outerHTML.slice(0, 1000000)};
        }"""


# Outils communs aux scripts du panneau, injectés en tête de chacun : le choix
# du conteneur doit être le même pour attendre, dérouler et lire.
_JS_OUTILS_PANNEAU = r"""
    const TITRE_SECTION = 'plus de profils pour vous';
    const normaliser = t => (t || '').replace(/\s+/g, ' ').trim();

    // Clé d'une personne : le vanity décodé, en minuscules — LinkedIn sert
    // « c%C3%A9line » là où un autre lien porte « céline ». Même règle que
    // vanity_depuis_url côté Python.
    const vanityDe = href => {
        const m = (href || '').match(/\/in\/([^/?#]+)/);
        if (!m) return null;
        let v = m[1];
        try { v = decodeURIComponent(v); } catch (e) { /* encodage invalide : brut */ }
        return v.trim().toLowerCase() || null;
    };

    // « Tout afficher » pointe vers /in/<référence>/overlay/… : un lien /in/
    // qui n'est pas une suggestion.
    const estLienProfil = a => {
        const href = a.getAttribute('href') || '';
        return /\/in\/[^/?#]+/.test(href) && !/\/in\/[^/?#]+\/overlay\//.test(href);
    };
    const liensProfil = el =>
        Array.from(el.querySelectorAll('a[href*="/in/"]')).filter(estLienProfil);
    const nbProfils = el =>
        new Set(liensProfil(el).map(a => vanityDe(a.getAttribute('href'))).filter(Boolean)).size;

    // Les fenêtres du lecteur vidéo (video.js) portent role="dialog" et
    // restent dans la page, cachées : au premier essai réel, c'est l'une
    // d'elles que l'ancien extracteur a lue. LinkedIn garde aussi des
    // <dialog> natifs fermés. On les écarte sur l'état visible, pas sur une
    // liste de classes à tenir à jour — sauf vjs-hidden, qui cache même
    // quand la feuille de style n'est pas encore chargée.
    const estCache = el => {
        if (el.hidden || el.closest('[hidden], .vjs-hidden')) return true;
        if (el.tagName === 'DIALOG' && !el.open) return true;
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return true;
        return el.getClientRects().length === 0;
    };

    // Plusieurs dialogues peuvent coexister (messagerie, cookies, vidéo) :
    // on prend le visible qui porte le plus de profils, pas le premier.
    const choisirPanneau = () => {
        let racine = null;
        let max = 0;
        for (const c of document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]')) {
            if (estCache(c)) continue;
            const n = nbProfils(c);
            if (n > max) { max = n; racine = c; }
        }
        return racine;
    };

    // La section de la page du profil, reconnue à son titre — le seul repère
    // stable, les classes étant obfusquées. Hors de tout dialogue : le
    // panneau ouvert porte le même titre.
    const choisirSection = () => {
        const titres = Array.from(
            document.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]')
        ).filter(h => normaliser(h.textContent).toLowerCase() === TITRE_SECTION
                   && !h.closest('dialog, [role="dialog"], [aria-modal="true"]'));
        for (const titre of titres) {
            let racine = titre.closest('section');
            if (!racine || nbProfils(racine) === 0) {
                racine = titre;
                while (racine && nbProfils(racine) === 0) racine = racine.parentElement;
            }
            if (racine && nbProfils(racine) > 0) return racine;
        }
        return null;
    };
"""

# Lecture des cartes, à partir de la racine choisie selon `mode`.
_JS_LECTURE_CARTES = r"""
    const racine = mode === 'section' ? choisirSection() : choisirPanneau();
    if (!racine) {
        return {entrees: [], html: document.body.innerHTML.slice(0, 1000000), conteneur: null};
    }

    const titresDans = el =>
        el.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]').length;

    // La carte d'un lien : son ancêtre le plus haut qui ne contient qu'UNE
    // personne. Les cartes actuelles sont de simples div imbriqués, sans li
    // ni role="listitem" ; un sélecteur de balise ne les trouve plus, une
    // règle de structure si — et elle couvre aussi les li d'avant. On
    // s'arrête aussi devant un ancêtre qui apporte un titre : dans une liste
    // d'une seule personne, la carte engloberait sinon le titre de la section.
    const carteDe = lien => {
        let carte = lien;
        while (carte.parentElement && carte.parentElement !== racine) {
            const parent = carte.parentElement;
            if (nbProfils(parent) > 1) break;
            if (titresDans(parent) > titresDans(carte)) break;
            carte = parent;
        }
        return carte;
    };

    // Libellés de boutons, de liens et marqueurs de degré : du bruit, jamais
    // un nom ni un intitulé.
    const bruit = /^(se connecter|suivre|s'abonner|message|inviter|tout afficher|afficher tout|· ?(1er|2e|3e)|(1er|2e|3e) ?·?)$/i;
    const motInvitation = /(se connecter|inviter|connect)/i;

    const vus = new Set();
    const entrees = [];

    for (const lien of liensProfil(racine)) {
        const href = lien.href || lien.getAttribute('href') || '';
        const vanity = vanityDe(href);
        if (!vanity || vus.has(vanity)) continue;

        const carte = carteDe(lien);
        const texte = (carte.innerText || '').trim();
        if (!texte) continue;
        const lignes = texte.split('\n').map(s => s.trim()).filter(Boolean);

        // Nom : la première ligne qui n'est pas du bruit.
        let nom = '';
        for (const ligne of lignes) {
            if (bruit.test(ligne)) continue;
            if (ligne.length < 2 || ligne.length > 120) continue;
            nom = ligne;
            break;
        }
        // « Marie Martin · 2e » : le marqueur de degré collé au nom n'en
        // fait pas partie.
        nom = nom.replace(/\s*·\s*(1er|2e|3e).*$/, '').trim();
        if (!nom) continue;

        // Degré : le marqueur « · 2e » d'abord ; à défaut une ligne qui ne
        // contient que le degré. Jamais un « 2e » trouvé au milieu d'un
        // intitulé (« 2e année d'alternance »).
        let degre = '';
        const marque = texte.match(/·\s*(1er|2e|3e)\b/);
        if (marque) {
            degre = marque[1];
        } else {
            degre = lignes.find(l => /^(1er|2e|3e)$/.test(l)) || '';
        }

        // Intitulé : la plus longue ligne restante. Gardé brut — il est écrit
        // à la main, dans tous les formats imaginables, et un champ structuré
        // faux vaut moins qu'un texte exact.
        let intitule = '';
        for (const ligne of lignes) {
            if (ligne === nom || bruit.test(ligne)) continue;
            if (/^(1er|2e|3e)$/.test(ligne)) continue;
            // Lignes d'interface, souvent plus longues que l'intitulé.
            if (/relations? en commun|Voir le profil/i.test(ligne)) continue;
            if (ligne.length > intitule.length) intitule = ligne;
        }

        // Invitable : décidé sur les boutons de la carte seulement — texte
        // ET aria-label (« Inviter X à rejoindre votre réseau »). Un intitulé
        // « Connecteur de talents » ne doit pas compter ; « Suivre » seul ne
        // permet pas d'inviter.
        const invitable = Array.from(
            carte.querySelectorAll('button, a[role="button"], a[href*="invite"]')
        ).some(b => motInvitation.test(
            (b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')
        ));

        vus.add(vanity);
        entrees.push({nom, url: href, degre, intitule, invitable});
    }

    return {
        entrees: entrees,
        html: racine.innerHTML.slice(0, 1000000),
        conteneur: racine.tagName.toLowerCase()
    };
"""
