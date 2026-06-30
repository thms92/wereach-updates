"""
enrich_excel.py
---------------
Script pour enrichir les colonnes Fonction et Société dans un fichier Excel (.xlsx)
à partir des URLs LinkedIn de chaque profil.

Usage:
    python3 enrich_excel.py --input "profil_scrap.xlsx" --output "profil_scrap_enrichi.xlsx"

    Si --input est omis, le script cherche automatiquement le premier .xlsx dans le dossier.

Prérequis:
    pip install playwright pandas openpyxl --break-system-packages
    playwright install chromium

Le script réutilise les cookies LinkedIn présents dans linkedin_cookies.json.
"""

import argparse
import asyncio
import json
import os
import re
import time
import random
import sys
import glob
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


# ── Configuration ──────────────────────────────────────────────────────────────

COOKIES_FILE = "linkedin_cookies.json"
DELAY_MIN    = 8.0    # Délai minimum entre profils (secondes)
DELAY_MAX    = 15.0   # Délai maximum entre profils (secondes)
PAUSE_EVERY  = 15     # Pause longue tous les N profils
PAUSE_MIN    = 45.0   # Pause longue minimum (secondes)
PAUSE_MAX    = 90.0   # Pause longue maximum (secondes)
TIMEOUT_MS   = 15000  # Timeout par page (ms)
HEADLESS     = False  # Navigateur visible — évite la déconnexion LinkedIn


# ── Détection automatique des colonnes ────────────────────────────────────────

# Variantes possibles pour chaque colonne (insensible à la casse)
COL_VARIANTS = {
    "url": [
        "url linkedin", "url lk", "linkedin url", "url", "lien linkedin",
        "linkedin", "profil linkedin", "lien profil", "url du profil",
        "url profil", "profile url"
    ],
    "fonction": [
        "fonction", "poste", "titre", "job title", "title", "intitulé de poste",
        "intitule", "position", "rôle", "role"
    ],
    "societe": [
        "société - nom", "société", "societe", "entreprise", "company",
        "société nom", "nom société", "nom de l'entreprise", "employeur",
        "société - nom"
    ],
    "prenom_nom": [
        "prénom / nom", "prénom/nom", "prenom / nom", "prenom/nom",
        "nom prénom", "nom/prénom", "prénom nom", "prénom + nom",
        "full name", "nom complet"
    ],
    "prenom": [
        "prénom", "prenom", "first name", "firstname"
    ],
    "nom": [
        "nom", "last name", "lastname", "surname"
    ],
}

def find_column(df_columns: list, col_type: str) -> str | None:
    """Cherche parmi les colonnes du DataFrame celle qui correspond au type donné."""
    variants = COL_VARIANTS.get(col_type, [])
    cols_lower = {c.lower().strip(): c for c in df_columns}
    for variant in variants:
        if variant.lower() in cols_lower:
            return cols_lower[variant.lower()]
    return None

def detect_columns(df: pd.DataFrame) -> dict:
    """
    Détecte automatiquement les colonnes clés dans le DataFrame.
    Retourne un dict: {'url': 'col_url', 'fonction': 'col_fonction', ...}
    """
    result = {}
    cols = list(df.columns)

    for key in ["url", "fonction", "societe", "prenom_nom", "prenom", "nom"]:
        found = find_column(cols, key)
        if found:
            result[key] = found

    return result


# ── Filtre anti-bannière promo ─────────────────────────────────────────────────

JUNK_PATTERNS = [
    "premium", "reactivate", "réactivez", "réactiver", "upgrade",
    "try premium", "essayez premium", "50%", "% off", "% de réduction",
    "subscribe", "abonnez", "free trial", "essai gratuit",
    "get hired", "linkedin learning",
]

def is_junk(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in JUNK_PATTERNS)


# ── Nettoyage de texte ──────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_empty(val) -> bool:
    if pd.isna(val):
        return True
    return str(val).strip() in ('', '\n', '\r\n', '\\n', 'nan', 'NaN')


# ── Cookies LinkedIn ───────────────────────────────────────────────────────────

async def load_cookies(context):
    if not os.path.exists(COOKIES_FILE):
        print(f"⚠️  Fichier cookies '{COOKIES_FILE}' introuvable.")
        print("   Lancez d'abord l'application principale pour vous connecter à LinkedIn.")
        return False

    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    if isinstance(cookies, dict) and "cookies" in cookies:
        cookies = cookies["cookies"]

    normalized = []
    for cookie in cookies:
        c = dict(cookie)
        c.setdefault("secure", True)
        c.setdefault("httpOnly", True)
        c.setdefault("sameSite", "None")
        if c.get("domain") and not c["domain"].startswith("."):
            c["domain"] = "." + c["domain"]
        normalized.append(c)

    await context.add_cookies(normalized)
    await context.add_cookies([{
        "name": "lang",
        "value": "v=2&lang=fr_FR",
        "domain": ".linkedin.com",
        "path": "/",
        "secure": False,
        "httpOnly": False,
        "sameSite": "Lax",
    }])

    print(f"✅ {len(normalized)} cookies chargés")
    return True


# ── Scroll humain ──────────────────────────────────────────────────────────────

async def human_scroll(page):
    for scroll_y in [300, 600, 900, 600, 300]:
        await page.evaluate(f"window.scrollTo({{top: {scroll_y}, behavior: 'smooth'}})")
        await page.wait_for_timeout(random.randint(600, 1400))
    await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    await page.wait_for_timeout(random.randint(400, 800))


# ── Scraping d'un profil ───────────────────────────────────────────────────────

async def scrape_profile(page, url: str) -> dict:
    """Scrape Fonction et Société depuis une URL de profil LinkedIn."""
    result = {"fonction": "", "societe": ""}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)

        if any(x in page.url for x in ["authwall", "login", "checkpoint", "signup"]):
            print("  ❌ Redirigé vers la page de connexion — cookie expiré !")
            return result

        await human_scroll(page)

        data = await page.evaluate("""() => {
            let fonction = '';
            let societe = '';

            const main = document.querySelector('main') || document.querySelector('[role="main"]');
            const firstSection = main ? main.querySelector('section') : document.querySelector('section');
            if (!firstSection) return {fonction, societe};

            const h2 = firstSection.querySelector('h2');
            const personName = h2 ? h2.textContent.trim() : '';

            const allP = firstSection.querySelectorAll('p');
            const noise = ['abonné', 'relation', 'coordonnées', 'premium', 'réactivez',
                           'reactivate', 'suivre', '· 1er', '· 2e', '· 3e', 'upgrade',
                           'notification', 'message', 'accueil', 'emploi', 'commenter',
                           '50%', 'essai gratuit', 'en commun'];

            for (const p of allP) {
                const txt = p.textContent.trim();
                if (txt.length < 15 || txt.length > 300) continue;
                if (txt === personName) continue;
                if (personName.includes(txt) || txt === personName) continue;
                const lower = txt.toLowerCase();
                if (noise.some(n => lower.includes(n))) continue;
                fonction = txt;
                break;
            }

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
                            && !txt.toLowerCase().includes('réactivez')
                            && !txt.toLowerCase().includes('abonné')) {
                            societe = txt;
                            break;
                        }
                    }
                }
                if (societe) break;
            }

            if (!societe) {
                const companyIcons = document.querySelectorAll('svg[id*="company"]');
                for (const icon of companyIcons) {
                    let fig = icon.closest('figure');
                    if (!fig) continue;
                    let wrapper = fig.parentElement?.closest('div');
                    if (!wrapper) wrapper = fig.parentElement;
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

            return {fonction, societe};
        }""")

        if data:
            fn = clean_text(data.get("fonction", ""))
            sc = clean_text(data.get("societe", ""))
            if fn and not is_junk(fn):
                result["fonction"] = fn
            if sc and not is_junk(sc):
                result["societe"] = sc

    except PlaywrightTimeout:
        print(f"  ⏱️  Timeout sur {url}")
    except Exception as e:
        print(f"  ❌ Erreur sur {url}: {e}")

    return result


# ── Logique principale ─────────────────────────────────────────────────────────

async def enrich_excel(input_path: str, output_path: str):
    # ── Lecture du fichier Excel ───────────────────────────────────────────────
    print(f"\n📂 Lecture de : {input_path}")
    try:
        df = pd.read_excel(input_path, engine='openpyxl')
    except Exception as e:
        print(f"❌ Impossible de lire le fichier Excel : {e}")
        return

    print(f"   {len(df)} lignes trouvées, {len(df.columns)} colonnes : {list(df.columns)}")

    # ── Détection automatique des colonnes ────────────────────────────────────
    cols = detect_columns(df)
    print(f"\n🔍 Colonnes détectées :")

    col_url = cols.get("url")
    col_fonction = cols.get("fonction")
    col_societe = cols.get("societe")
    col_nom = cols.get("prenom_nom") or cols.get("nom") or cols.get("prenom")

    print(f"   URL LinkedIn  : {col_url or '❌ NON TROUVÉE'}")
    print(f"   Fonction      : {col_fonction or '⚠️  absente (sera créée)'}")
    print(f"   Société       : {col_societe or '⚠️  absente (sera créée)'}")
    print(f"   Nom           : {col_nom or '(non détecté)'}")

    if not col_url:
        print("\n❌ ERREUR : Impossible de trouver la colonne URL LinkedIn dans ce fichier.")
        print(f"   Colonnes disponibles : {list(df.columns)}")
        print("   Renommez la colonne URL LinkedIn en 'URL LinkedIn' ou 'URL LK' et réessayez.")
        return

    # Créer les colonnes manquantes
    if not col_fonction:
        col_fonction = "Fonction"
        df[col_fonction] = ""
        print(f"   ➕ Colonne 'Fonction' créée")

    if not col_societe:
        col_societe = "Société"
        df[col_societe] = ""
        print(f"   ➕ Colonne 'Société' créée")

    # ── Identifier les lignes à enrichir ──────────────────────────────────────
    mask = (
        (df[col_fonction].apply(is_empty)) |
        (df[col_societe].apply(is_empty))
    ) & df[col_url].notna() & (~df[col_url].apply(is_empty))

    to_enrich = df[mask].copy()
    total = len(to_enrich)
    print(f"\n📋 {total} profils à enrichir\n")

    if total == 0:
        print("✅ Rien à faire, toutes les lignes sont déjà remplies.")
        df.to_excel(output_path, index=False, engine='openpyxl')
        print(f"💾 Fichier sauvegardé : {output_path}")
        return

    # ── Fichier de reprise ─────────────────────────────────────────────────────
    progress_file = output_path + ".progress.json"
    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            progress = json.load(f)
        print(f"🔄 Reprise depuis progression sauvegardée ({len(progress)} profils déjà traités)\n")

    # ── Lancement du navigateur ────────────────────────────────────────────────
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--ignore-certificate-errors",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )

        cookies_ok = await load_cookies(context)
        if not cookies_ok:
            await browser.close()
            return

        page = await context.new_page()

        # ── Vérification de la session LinkedIn ───────────────────────────────
        print("🔍 Vérification de la session LinkedIn...")
        try:
            await page.goto("https://www.linkedin.com/feed/",
                            wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            await page.wait_for_timeout(2000)
            current = page.url
            if any(x in current for x in ["authwall", "login", "checkpoint", "signup"]):
                print("❌ Session LinkedIn invalide — cookies expirés.")
                print("   Mettez à jour linkedin_cookies.json depuis l'application principale.")
                await browser.close()
                return
            print(f"✅ Session LinkedIn active\n")
        except Exception as e:
            print(f"⚠️  Impossible de vérifier la session : {e}")

        enriched = 0
        errors = 0
        consecutive_errors = 0

        for i, (idx, row) in enumerate(to_enrich.iterrows()):
            url = str(row[col_url]).strip()
            nom = str(row[col_nom]).strip() if col_nom else f"Ligne {idx+1}"

            # Sauter si déjà dans le cache de progression
            if url in progress:
                cached = progress[url]
                if cached.get("fonction") and not is_junk(cached["fonction"]) and is_empty(df.at[idx, col_fonction]):
                    df.at[idx, col_fonction] = cached["fonction"]
                if cached.get("societe") and not is_junk(cached["societe"]) and is_empty(df.at[idx, col_societe]):
                    df.at[idx, col_societe] = cached["societe"]
                if (cached.get("fonction") and is_junk(cached["fonction"])) or \
                   (cached.get("societe") and is_junk(cached["societe"])):
                    del progress[url]
                else:
                    continue

            print(f"[{i+1}/{total}] {nom}")
            print(f"  🔗 {url}")

            result = await scrape_profile(page, url)

            # Détection rate-limit
            if not result["fonction"] and not result["societe"]:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    pause = random.uniform(120, 180)
                    print(f"\n  🚨 {consecutive_errors} échecs consécutifs — pause de {pause:.0f}s...\n")
                    df.to_excel(output_path, index=False, engine='openpyxl')
                    await asyncio.sleep(pause)
                    consecutive_errors = 0
            else:
                consecutive_errors = 0

            # Mettre à jour le DataFrame
            if result["fonction"] and is_empty(df.at[idx, col_fonction]):
                df.at[idx, col_fonction] = result["fonction"]
                print(f"  ✅ Fonction  : {result['fonction']}")
                enriched += 1
            else:
                if not result["fonction"]:
                    print(f"  ⚠️  Fonction  : non trouvée")
                    errors += 1

            if result["societe"] and is_empty(df.at[idx, col_societe]):
                df.at[idx, col_societe] = result["societe"]
                print(f"  ✅ Société   : {result['societe']}")
            else:
                if not result["societe"]:
                    print(f"  ⚠️  Société   : non trouvée")

            # Sauvegarder la progression JSON
            progress[url] = result
            with open(progress_file, "w") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)

            # Sauvegarde Excel toutes les 10 lignes
            if (i + 1) % 10 == 0:
                df.to_excel(output_path, index=False, engine='openpyxl')
                print(f"\n  💾 Sauvegarde intermédiaire ({i+1}/{total})\n")

            # Délai aléatoire
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            if (i + 1) % PAUSE_EVERY == 0:
                pause = random.uniform(PAUSE_MIN, PAUSE_MAX)
                print(f"\n  ☕ Pause de {pause:.0f}s ({i+1}/{total})...\n")
                await asyncio.sleep(pause)
            else:
                await asyncio.sleep(delay)

        await browser.close()

    # ── Sauvegarde finale ──────────────────────────────────────────────────────
    df.to_excel(output_path, index=False, engine='openpyxl')

    if os.path.exists(progress_file):
        os.remove(progress_file)

    print(f"\n{'='*50}")
    print(f"✅ Terminé !")
    print(f"   Profils enrichis  : {enriched}")
    print(f"   Non trouvés       : {errors}")
    print(f"   Fichier sauvegardé: {output_path}")
    print(f"{'='*50}\n")


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def find_excel_file(directory: str) -> str | None:
    """Cherche automatiquement un fichier .xlsx dans le dossier."""
    xlsx_files = glob.glob(os.path.join(directory, "*.xlsx"))
    # Exclure les fichiers de sortie enrichis
    xlsx_files = [f for f in xlsx_files if "_enrichi" not in os.path.basename(f).lower()]
    if xlsx_files:
        return xlsx_files[0]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Enrichit les colonnes Fonction et Société dans un fichier Excel depuis LinkedIn"
    )
    parser.add_argument(
        "--input",  "-i",
        default=None,
        help="Chemin du fichier Excel source (.xlsx). Si omis, cherche automatiquement dans le dossier."
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Chemin du fichier Excel de sortie. Par défaut : [nom_fichier]_enrichi.xlsx"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Afficher le navigateur (utile pour debug)"
    )

    args = parser.parse_args()

    if args.visible:
        global HEADLESS
        HEADLESS = False

    # Trouver le fichier Excel automatiquement si non spécifié
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = args.input

    if not input_path:
        input_path = find_excel_file(script_dir)
        if not input_path:
            print("❌ Aucun fichier .xlsx trouvé dans le dossier.")
            print("   Placez votre fichier Excel dans le dossier et relancez.")
            print(f"   Dossier : {script_dir}")
            sys.exit(1)
        print(f"📁 Fichier Excel détecté automatiquement : {os.path.basename(input_path)}")

    if not os.path.exists(input_path):
        print(f"❌ Fichier introuvable : {input_path}")
        sys.exit(1)

    # Nom du fichier de sortie
    if args.output:
        output_path = args.output
    else:
        stem = Path(input_path).stem
        output_path = os.path.join(script_dir, f"{stem}_enrichi.xlsx")

    print(f"   Entrée  : {input_path}")
    print(f"   Sortie  : {output_path}")

    asyncio.run(enrich_excel(input_path, output_path))


if __name__ == "__main__":
    main()
