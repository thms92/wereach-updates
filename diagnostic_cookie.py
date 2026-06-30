# -*- coding: utf-8 -*-
"""
Diagnostic du cookie LinkedIn.

Usage :
    python3 diagnostic_cookie.py

Le script :
  1. Charge le cookie sauvegardé dans config/cookie.txt
  2. Lance un navigateur Playwright (visible) avec le cookie
  3. Tente de charger le feed LinkedIn
  4. Trace toutes les redirections
  5. Sauvegarde un screenshot et te dit si le cookie est valide,
     expiré, en checkpoint, etc.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright


def load_cookie() -> str:
    """Charge le cookie li_at depuis config/cookie.txt (chiffré)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cookie_utils import CookieManager
    cookie = CookieManager().load_cookie()
    if not cookie:
        print("❌ Aucun cookie trouvé dans config/cookie.txt")
        sys.exit(1)
    return cookie


async def run_diagnostic(cookie: str, headless: bool = False) -> None:
    print("═" * 60)
    print("  DIAGNOSTIC COOKIE LINKEDIN")
    print("═" * 60)
    print(f"  Cookie chargé : {len(cookie)} caractères")
    print(f"  Préfixe : {cookie[:25]}...")
    print(f"  Suffixe : ...{cookie[-15:]}")
    print(f"  Date    : {datetime.now().isoformat(timespec='seconds')}")
    print()

    # Charger le profil stealth s'il existe
    profile_path = Path(__file__).resolve().parent / "config" / "browser_profile.json"
    profile = {}
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text())
        except Exception:
            profile = {}

    user_agent = profile.get("user_agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
    viewport = profile.get("viewport", {"width": 1280, "height": 800})
    locale = profile.get("locale", "fr-FR")
    timezone = profile.get("timezone", "Europe/Paris")

    redirects: list = []

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = await p.chromium.launch(headless=headless)

        context = await browser.new_context(
            viewport=viewport,
            user_agent=user_agent,
            locale=locale,
            timezone_id=timezone,
        )

        # Injecter le cookie
        await context.add_cookies([{
            "name": "li_at",
            "value": cookie,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        }])

        page = await context.new_page()

        # Tracer toutes les navigations / redirections
        page.on("response", lambda r: redirects.append(
            (r.status, r.url[:120])
        ) if r.status in (301, 302, 303, 307, 308) or "linkedin.com" in r.url
          else None)

        print("🌐 Tentative d'accès à https://www.linkedin.com/feed/ ...")
        final_url = ""
        error_msg = ""
        try:
            response = await page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            final_url = page.url
            status = response.status if response else "?"
            print(f"   → réponse HTTP {status}")
            print(f"   → URL finale : {final_url}")
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ ERREUR : {error_msg.splitlines()[0]}")
            try:
                final_url = page.url
                print(f"   → Dernière URL atteinte : {final_url}")
            except Exception:
                pass

        # Screenshot pour inspection visuelle
        screenshot_path = Path("diagnostic_cookie.png")
        try:
            await page.screenshot(path=str(screenshot_path))
            print(f"   📸 Screenshot : {screenshot_path}")
        except Exception:
            pass

        print()
        print("─" * 60)
        print("  Chaîne de redirections (max 12 dernières) :")
        for status, url in redirects[-12:]:
            print(f"   [{status}] {url}")
        print("─" * 60)
        print()

        # Verdict
        verdict = analyse(final_url, error_msg, redirects)
        print(verdict)

        if not headless:
            print()
            print("🔍 Le navigateur reste ouvert 15 secondes pour inspection...")
            await asyncio.sleep(15)

        await browser.close()


def analyse(final_url: str, error_msg: str, redirects: list) -> str:
    """Donne un verdict humainement compréhensible."""
    lines = ["═" * 60, "  VERDICT", "═" * 60]

    if "ERR_TOO_MANY_REDIRECTS" in error_msg:
        lines += [
            "❌ COOKIE INVALIDE : LinkedIn redirige en boucle.",
            "",
            "Causes les plus probables :",
            "  1. Le cookie li_at est expiré ou révoqué",
            "  2. Tu n'as pas refait un VRAI logout/login dans le navigateur",
            "  3. LinkedIn a flaggé l'account (checkpoint déclenché)",
            "",
            "À FAIRE :",
            "  1. Ouvre Chrome (pas le navigateur scraper)",
            "  2. Va sur linkedin.com → Déconnecte-toi complètement",
            "  3. Reconnecte-toi (valide tout checkpoint si LinkedIn t'en demande un)",
            "  4. F12 → onglet Application → Cookies → linkedin.com",
            "  5. Copie la NOUVELLE valeur de 'li_at' (vérifie qu'elle est différente)",
            "  6. Recolle-la dans l'app et relance le diagnostic",
        ]
    elif "login" in final_url or "uas" in final_url:
        lines += [
            "❌ COOKIE EXPIRÉ : LinkedIn t'a redirigé vers la page de login.",
            "",
            "À FAIRE : Reconnecte-toi à LinkedIn et copie un nouveau cookie li_at.",
        ]
    elif "checkpoint" in final_url or "challenge" in final_url:
        lines += [
            "⚠️ CHECKPOINT DE SÉCURITÉ : LinkedIn demande une vérification.",
            "",
            "À FAIRE : Connecte-toi sur linkedin.com dans ton navigateur normal,",
            "valide la vérification (email/SMS/captcha), puis copie un nouveau cookie.",
        ]
    elif "authwall" in final_url:
        lines += [
            "❌ AUTHWALL : LinkedIn ne reconnaît pas la session.",
            "",
            "À FAIRE : Reconnecte-toi à LinkedIn et copie un nouveau cookie li_at.",
        ]
    elif "feed" in final_url:
        lines += [
            "✅ COOKIE VALIDE : tu es bien connecté au feed LinkedIn !",
            "",
            "Si le scraping échoue malgré ça, le problème est ailleurs :",
            "  - Mauvaise URL de recherche (filtre entreprise, etc.)",
            "  - Rate limiting de LinkedIn (attends 1-2h)",
            "  - Sélecteurs DOM cassés (changement LinkedIn)",
        ]
    else:
        lines += [
            f"⚠️ Statut indéterminé. URL finale : {final_url or '(aucune)'}",
            f"   Erreur : {error_msg[:200] if error_msg else '(aucune)'}",
            "",
            "Regarde le screenshot diagnostic_cookie.png pour voir ce que LinkedIn a affiché.",
        ]

    lines.append("═" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    headless_mode = "--headless" in sys.argv
    cookie = load_cookie()
    asyncio.run(run_diagnostic(cookie, headless=headless_mode))
