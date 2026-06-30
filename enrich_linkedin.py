"""
enrich_linkedin.py
------------------
Script standalone pour enrichir les colonnes Fonction et Société - Nom
dans le CSV prospect à partir des URLs LinkedIn.

Usage:
    python3 enrich_linkedin.py --input "Base_de_donnée_Prospect.csv" --output "Base_enrichie.csv"

Prérequis:
    pip install playwright pandas
    playwright install chromium

Le script réutilise les cookies LinkedIn déjà présents dans votre profil
Chrome/Chromium ou via le fichier cookies.json si vous en avez un.

──────────────────────────────────────────────────────────────────────────────
NOUVEAUTÉS V2 (détection précoce ERR_TOO_MANY_REDIRECTS) :
  • Health-check au démarrage : visite linkedin.com/feed avant le batch
    → si le cookie est mort, on s'arrête IMMÉDIATEMENT (pas 190 tentatives)
  • Détection ERR_TOO_MANY_REDIRECTS dans chaque scrape_profile
  • Circuit-breaker : si 3 échecs consécutifs de type redirect/auth,
    on arrête le batch proprement et on sauvegarde ce qui a été fait
──────────────────────────────────────────────────────────────────────────────
"""

import argparse
import asyncio
import json
import os
import re
import time
import random
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


# ── Configuration ──────────────────────────────────────────────────────────────

COOKIES_FILE            = "linkedin_cookies.json"   # Fichier cookies exporté depuis votre outil
DELAY_MIN               = 3.0    # Délai minimum entre profils (secondes)
DELAY_MAX               = 7.0    # Délai maximum entre profils (secondes)
TIMEOUT_MS              = 15000  # Timeout par page (ms)
HEADLESS                = True   # False pour voir le navigateur
MAX_CONSECUTIVE_ERRORS  = 3      # Arrêt auto après N échecs session d'affilée
PAUSE_EVERY_N           = 20     # Pause longue tous les N profils
LONG_PAUSE_MIN          = 30.0   # Durée minimum de la pause longue (s)
LONG_PAUSE_MAX          = 90.0   # Durée maximum de la pause longue (s)


# ── Sélecteurs LinkedIn (multi-fallback) ───────────────────────────────────────

FONCTION_SELECTORS = [
    "div.text-body-medium.break-words",
    ".pv-text-details__left-panel .text-body-medium",
    "h2.mt1.t-18.t-black.t-normal",
    ".ph5 .mt2 .t-18",
    "div[data-generated-suggestion-target] .t-18",
]

SOCIETE_SELECTORS = [
    "div#experience ~ div .pvs-list__item--line-separated .t-bold span[aria-hidden='true']",
    "section#experience .pvs-entity .t-bold span[aria-hidden='true']",
    ".pv-profile-section__card-item-v2 .t-bold",
    "li.pv-entity__position-group-pager .pv-entity__secondary-title",
    "#experience .pvs-list__item--no-padding-in-columns .t-bold span",
]

# Sélecteur alternatif via l'URL du lien employeur
SOCIETE_LINK_SELECTOR = "a[href*='/company/'] span[aria-hidden='true']"


# ── Exception interne : session LinkedIn morte ─────────────────────────────────

class LinkedInSessionDead(Exception):
    """Levée quand on détecte que le cookie est expiré/bloqué."""
    pass


# ── Fonctions de scraping ──────────────────────────────────────────────────────

async def load_cookies(context):
    """Charge les cookies LinkedIn depuis le fichier JSON."""
    if not os.path.exists(COOKIES_FILE):
        print(f"⚠️  Fichier cookies '{COOKIES_FILE}' introuvable.")
        print("   Lance d'abord : python3 update_cookie.py")
        return False

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    # Normaliser le format (certains exports ont un wrapper)
    if isinstance(cookies, dict) and "cookies" in cookies:
        cookies = cookies["cookies"]

    await context.add_cookies(cookies)
    print(f"✅ {len(cookies)} cookies chargés")
    return True


def clean_text(text: str) -> str:
    """Nettoie le texte extrait (espaces, sauts de ligne)."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_session_dead_error(err_msg: str) -> bool:
    """
    Détecte les erreurs qui indiquent que le cookie LinkedIn ne fonctionne plus.
    """
    signals = [
        "ERR_TOO_MANY_REDIRECTS",
        "ERR_HTTP_RESPONSE_CODE_FAILURE",
        "net::ERR_ABORTED",  # parfois retourné sur redirect loops
    ]
    err_upper = err_msg.upper()
    return any(sig.upper() in err_upper for sig in signals)


async def health_check(page) -> bool:
    """
    Vérifie que le cookie LinkedIn fonctionne en visitant le feed.
    Retourne True si OK, False sinon.
    """
    print("\n🩺 Health-check de la session LinkedIn…")
    try:
        await page.goto(
            "https://www.linkedin.com/feed/",
            wait_until="domcontentloaded",
            timeout=TIMEOUT_MS,
        )
    except PlaywrightTimeout:
        print("   ⏱️  Timeout lors du chargement du feed.")
        return False
    except Exception as e:
        err = str(e)
        if is_session_dead_error(err):
            print(f"   ❌ Erreur de session (cookie mort) : {err[:150]}")
            return False
        print(f"   ⚠️  Erreur inattendue : {err[:150]}")
        return False

    # Vérifier qu'on n'est pas sur authwall/login/checkpoint
    current_url = page.url.lower()
    for bad_keyword in ("authwall", "login", "checkpoint", "uas/login"):
        if bad_keyword in current_url:
            print(f"   ❌ Redirigé vers '{bad_keyword}' → cookie invalide.")
            return False

    await page.wait_for_timeout(1500)
    print("   ✅ Session LinkedIn OK — feed accessible.\n")
    return True


async def scrape_profile(page, url: str) -> dict:
    """
    Scrape la Fonction et la Société depuis une URL de profil LinkedIn.
    Retourne un dict {"fonction": str, "societe": str, "_session_dead": bool}.
    """
    result = {"fonction": "", "societe": "", "_session_dead": False}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        await page.wait_for_timeout(2000)  # Laisser le JS se charger

        # ── Vérifier qu'on est connecté ────────────────────────────────────────
        if "authwall" in page.url or "login" in page.url or "checkpoint" in page.url:
            print("  ❌ Redirigé vers la page de connexion — cookie expiré.")
            result["_session_dead"] = True
            return result

        # ── Extraire la Fonction ───────────────────────────────────────────────
        for selector in FONCTION_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    text = clean_text(text)
                    if text and len(text) > 2:
                        result["fonction"] = text
                        break
            except Exception:
                continue

        # ── Extraire la Société (employeur actuel) ─────────────────────────────
        # Méthode 1 : lien vers une page company
        try:
            el = await page.query_selector(SOCIETE_LINK_SELECTOR)
            if el:
                text = await el.inner_text()
                text = clean_text(text)
                if text and len(text) > 1:
                    result["societe"] = text
        except Exception:
            pass

        # Méthode 2 : sélecteurs directs si méthode 1 a échoué
        if not result["societe"]:
            for selector in SOCIETE_SELECTORS:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        text = await el.inner_text()
                        text = clean_text(text)
                        # Filtrer les textes trop longs (souvent mauvais sélecteur)
                        if text and 1 < len(text) < 100:
                            result["societe"] = text
                            break
                except Exception:
                    continue

        # Méthode 3 : chercher dans la section experience via JS
        if not result["societe"]:
            try:
                societe = await page.evaluate("""() => {
                    const expSection = document.querySelector('#experience');
                    if (!expSection) return '';
                    const boldSpans = expSection.querySelectorAll('.t-bold span[aria-hidden="true"]');
                    for (const span of boldSpans) {
                        const txt = span.textContent.trim();
                        if (txt && txt.length > 1 && txt.length < 100) return txt;
                    }
                    return '';
                }""")
                if societe:
                    result["societe"] = clean_text(societe)
            except Exception:
                pass

    except PlaywrightTimeout:
        print(f"  ⏱️  Timeout sur {url}")
    except Exception as e:
        err = str(e)
        if is_session_dead_error(err):
            print(f"  ❌ ERR_TOO_MANY_REDIRECTS détecté → cookie mort.")
            result["_session_dead"] = True
        else:
            print(f"  ❌ Erreur sur {url}: {err[:150]}")

    return result


# ── Logique principale ─────────────────────────────────────────────────────────

async def enrich_csv(input_path: str, output_path: str):
    df = pd.read_csv(input_path, sep=';', encoding='utf-8-sig')

    # Normaliser les valeurs "vides" (\n, \r\n, espaces)
    def is_empty(val):
        if pd.isna(val):
            return True
        return str(val).strip() in ('', '\n', '\r\n', '\\n')

    # Identifier les lignes à enrichir
    mask = (
        (df['Fonction'].apply(is_empty)) |
        (df['Société - Nom'].apply(is_empty))
    ) & df['URL LK'].notna() & (~df['URL LK'].apply(is_empty))

    to_enrich = df[mask].copy()
    total = len(to_enrich)
    print(f"\n📋 {total} profils à enrichir\n")

    if total == 0:
        print("✅ Rien à faire, toutes les lignes sont déjà remplies.")
        df.to_csv(output_path, sep=';', encoding='utf-8-sig', index=False)
        return

    # Fichier de reprise (en cas d'interruption)
    progress_file = output_path + ".progress.json"
    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            progress = json.load(f)
        print(f"🔄 Reprise depuis progression sauvegardée ({len(progress)} profils déjà traités)\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        cookies_ok = await load_cookies(context)
        if not cookies_ok:
            await browser.close()
            return

        page = await context.new_page()

        # ── HEALTH-CHECK : sortie immédiate si cookie mort ─────────────────────
        if not await health_check(page):
            print("=" * 60)
            print("❌ IMPOSSIBLE DE DÉMARRER : la session LinkedIn est morte.")
            print("=" * 60)
            print()
            print("🔧 Que faire :")
            print("   1. Ouvre linkedin.com/feed/ dans Chrome")
            print("   2. Vérifie que tu es bien connecté (pas de checkpoint)")
            print("   3. Récupère un nouveau li_at depuis DevTools")
            print("   4. Lance : python3 update_cookie.py")
            print("   5. Attends 1-2h avant de relancer ce script")
            print()
            await browser.close()
            return

        enriched = 0
        errors   = 0
        consecutive_session_errors = 0
        processed_in_session = 0

        for i, (idx, row) in enumerate(to_enrich.iterrows()):
            url = str(row['URL LK']).strip()
            nom = str(row['Prénom / Nom']).strip()

            # Sauter si déjà traité dans une session précédente
            if url in progress:
                cached = progress[url]
                if cached.get("fonction") and is_empty(df.at[idx, 'Fonction']):
                    df.at[idx, 'Fonction'] = cached["fonction"]
                if cached.get("societe") and is_empty(df.at[idx, 'Société - Nom']):
                    df.at[idx, 'Société - Nom'] = cached["societe"]
                continue

            print(f"[{i+1}/{total}] {nom}")
            print(f"  🔗 {url}")

            result = await scrape_profile(page, url)

            # ── Circuit breaker : cookie mort en cours de route ────────────────
            if result.get("_session_dead"):
                consecutive_session_errors += 1
                print(f"  ⚠️  Erreur de session ({consecutive_session_errors}/{MAX_CONSECUTIVE_ERRORS})")

                if consecutive_session_errors >= MAX_CONSECUTIVE_ERRORS:
                    print()
                    print("=" * 60)
                    print("🛑 ARRÊT AUTOMATIQUE : trop d'erreurs de session d'affilée.")
                    print("=" * 60)
                    print(f"   {MAX_CONSECUTIVE_ERRORS} profils consécutifs ont échoué.")
                    print(f"   Ton cookie li_at est probablement révoqué.")
                    print()
                    print("🔧 Prochaines étapes :")
                    print("   1. python3 update_cookie.py  (récupère un cookie frais)")
                    print("   2. Attends au moins 2-4h")
                    print("   3. Relance ce script — la progression est sauvegardée,")
                    print("      tu ne reperds pas les profils déjà traités.")
                    print()
                    break
            else:
                # Reset du compteur dès qu'un profil réussit à charger
                consecutive_session_errors = 0

            # Mettre à jour le DataFrame uniquement si la valeur est vide
            if result["fonction"] and is_empty(df.at[idx, 'Fonction']):
                df.at[idx, 'Fonction'] = result["fonction"]
                print(f"  ✅ Fonction  : {result['fonction']}")
                enriched += 1
            else:
                if not result["fonction"]:
                    print(f"  ⚠️  Fonction  : non trouvée")
                    errors += 1

            if result["societe"] and is_empty(df.at[idx, 'Société - Nom']):
                df.at[idx, 'Société - Nom'] = result["societe"]
                print(f"  ✅ Société   : {result['societe']}")
            else:
                if not result["societe"]:
                    print(f"  ⚠️  Société   : non trouvée")

            # Sauvegarder la progression (hors flag interne)
            progress[url] = {
                "fonction": result["fonction"],
                "societe":  result["societe"],
            }
            with open(progress_file, "w") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)

            # Sauvegarder le CSV toutes les 10 lignes
            if (i + 1) % 10 == 0:
                df.to_csv(output_path, sep=';', encoding='utf-8-sig', index=False)
                print(f"\n  💾 Sauvegarde intermédiaire ({i+1}/{total})\n")

            processed_in_session += 1

            # Pause longue tous les PAUSE_EVERY_N profils (anti rate-limit)
            if processed_in_session > 0 and processed_in_session % PAUSE_EVERY_N == 0:
                long_pause = random.uniform(LONG_PAUSE_MIN, LONG_PAUSE_MAX)
                print(f"\n  ☕ Pause longue anti rate-limit : {long_pause:.0f}s\n")
                await asyncio.sleep(long_pause)
            else:
                # Délai aléatoire anti-détection
                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                await asyncio.sleep(delay)

        await browser.close()

    # Sauvegarde finale
    df.to_csv(output_path, sep=';', encoding='utf-8-sig', index=False)

    # Nettoyer le fichier de progression SEULEMENT si on est allé au bout
    # (si on a break pour session morte, on garde pour reprendre plus tard)
    all_done = all(url in progress for url in to_enrich['URL LK'].astype(str).str.strip())
    if all_done and os.path.exists(progress_file):
        os.remove(progress_file)
        print("\n🧹 Fichier de progression nettoyé (tout est terminé).")

    print(f"\n{'='*50}")
    print(f"✅ Session terminée")
    print(f"   Profils enrichis  : {enriched}")
    print(f"   Non trouvés       : {errors}")
    print(f"   Fichier sauvegardé: {output_path}")
    print(f"{'='*50}\n")


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrichit les colonnes Fonction et Société depuis LinkedIn"
    )
    parser.add_argument(
        "--input",  "-i",
        default="Base_de_donnée_Prospect_2026_-_Data___IA_BDD_Prospect_Data_IA_V2_.csv",
        help="Chemin du fichier CSV source"
    )
    parser.add_argument(
        "--output", "-o",
        default="Base_enrichie.csv",
        help="Chemin du fichier CSV de sortie"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Afficher le navigateur (mode non-headless, utile pour debug)"
    )
    args = parser.parse_args()

    global HEADLESS
    if args.visible:
        HEADLESS = False

    if not os.path.exists(args.input):
        print(f"❌ Fichier introuvable : {args.input}")
        return

    asyncio.run(enrich_csv(args.input, args.output))


if __name__ == "__main__":
    main()
