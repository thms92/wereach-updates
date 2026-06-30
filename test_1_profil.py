"""
test_1_profil.py
----------------
Test rapide sur UN SEUL profil LinkedIn pour vérifier que :
  - le cookie fonctionne
  - les sélecteurs de scraping sont OK
  - pas de rate-limit en cours

Usage:
    python3 test_1_profil.py https://www.linkedin.com/in/nom-du-profil/

Lance en mode VISIBLE pour que tu puisses voir ce qui se passe.
"""

import asyncio
import sys

# On importe les fonctions depuis enrich_linkedin.py (même dossier)
from enrich_linkedin import (
    load_cookies,
    health_check,
    scrape_profile,
)
from playwright.async_api import async_playwright


async def run_test(profile_url: str):
    print("=" * 60)
    print("  🧪 Test sur 1 profil LinkedIn (mode visible)")
    print("=" * 60)
    print(f"  URL : {profile_url}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # TOUJOURS visible
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        if not await load_cookies(context):
            await browser.close()
            return

        page = await context.new_page()

        # 1. Health-check
        if not await health_check(page):
            print("\n❌ Health-check échoué.")
            print("   → Lance `python3 update_cookie.py` pour rafraîchir le cookie.")
            await browser.close()
            return

        # 2. Scrape du profil de test
        print(f"🔍 Scraping du profil…")
        result = await scrape_profile(page, profile_url)

        print()
        print("=" * 60)
        print("  📊 Résultat")
        print("=" * 60)
        print(f"  Fonction : {result['fonction'] or '(non trouvée)'}")
        print(f"  Société  : {result['societe'] or '(non trouvée)'}")
        print()

        if result.get("_session_dead"):
            print("❌ Session morte détectée pendant le scraping.")
        elif result["fonction"] or result["societe"]:
            print("✅ Tout fonctionne — tu peux lancer le batch complet.")
        else:
            print("⚠️  Aucune donnée extraite. Deux possibilités :")
            print("   - LinkedIn a encore changé sa structure HTML (selectors KO)")
            print("   - Le profil testé est vraiment vide")
            print("   Le navigateur reste ouvert 10s pour que tu puisses vérifier…")
            await page.wait_for_timeout(10000)

        await browser.close()


def main():
    if len(sys.argv) < 2:
        print("Usage : python3 test_1_profil.py <url_linkedin>")
        print("Exemple : python3 test_1_profil.py https://www.linkedin.com/in/john-doe/")
        sys.exit(1)

    url = sys.argv[1].strip()
    if not url.startswith("http"):
        print(f"❌ URL invalide : {url}")
        sys.exit(1)

    asyncio.run(run_test(url))


if __name__ == "__main__":
    main()
