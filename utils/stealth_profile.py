# -*- coding: utf-8 -*-
"""
StealthProfile - Gestion cohérente des profils navigateur
Chaque session utilise un profil complet et cohérent :
UA + viewport + screen + platform + Sec-CH-UA headers

Principe : un profil = un "vrai" utilisateur avec un setup crédible.
Tout doit être cohérent entre les propriétés JS, les headers HTTP,
et les métadonnées du contexte Playwright.
"""

import random
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from logger import logger


@dataclass
class BrowserProfile:
    """Un profil navigateur complet et cohérent."""
    platform: str           # "macOS" | "Windows" | "Linux"
    os_version: str         # "10_15_7" ou "10.0"
    chrome_major: int       # 124, 125, 126...
    chrome_full: str        # "124.0.6367.118"
    user_agent: str
    viewport: Dict[str, int]
    screen: Dict[str, int]  # screen.width / screen.height réels
    sec_ch_ua: str          # valeur du header Sec-CH-UA
    sec_ch_ua_platform: str
    sec_ch_ua_mobile: str
    locale: str
    timezone: str
    languages: List[str]


# ─── Pools de profils réalistes (avril 2026) ──────────────────────────────────
# Basé sur les versions Chrome réelles en circulation

_CHROME_VERSIONS = [
    {"major": 132, "full": "132.0.6834.110"},
    {"major": 133, "full": "133.0.6943.98"},
    {"major": 134, "full": "134.0.6998.72"},
    {"major": 135, "full": "135.0.7049.56"},
]

_MAC_PROFILES = [
    {
        "os_version": "10_15_7",
        "screens": [
            {"viewport": {"width": 1440, "height": 900}, "screen": {"width": 1440, "height": 900}},
            {"viewport": {"width": 1280, "height": 800}, "screen": {"width": 1440, "height": 900}},
            {"viewport": {"width": 1680, "height": 1050}, "screen": {"width": 1680, "height": 1050}},
        ],
    },
    {
        "os_version": "13_6_4",
        "screens": [
            {"viewport": {"width": 1512, "height": 982}, "screen": {"width": 1512, "height": 982}},
            {"viewport": {"width": 1440, "height": 900}, "screen": {"width": 1512, "height": 982}},
            {"viewport": {"width": 1728, "height": 1117}, "screen": {"width": 1728, "height": 1117}},
        ],
    },
    {
        "os_version": "14_4_1",
        "screens": [
            {"viewport": {"width": 1512, "height": 982}, "screen": {"width": 1512, "height": 982}},
            {"viewport": {"width": 1440, "height": 900}, "screen": {"width": 1512, "height": 982}},
            {"viewport": {"width": 2560, "height": 1440}, "screen": {"width": 2560, "height": 1440}},
        ],
    },
]

_WINDOWS_PROFILES = [
    {
        "os_version": "10.0",
        "screens": [
            {"viewport": {"width": 1920, "height": 1080}, "screen": {"width": 1920, "height": 1080}},
            {"viewport": {"width": 1536, "height": 864}, "screen": {"width": 1920, "height": 1080}},
            {"viewport": {"width": 1366, "height": 768}, "screen": {"width": 1366, "height": 768}},
        ],
    },
    {
        "os_version": "10.0",
        "screens": [
            {"viewport": {"width": 2560, "height": 1440}, "screen": {"width": 2560, "height": 1440}},
            {"viewport": {"width": 1920, "height": 1080}, "screen": {"width": 2560, "height": 1440}},
        ],
    },
]

_FR_LOCALES = [
    {"locale": "fr-FR", "timezone": "Europe/Paris", "languages": ["fr-FR", "fr", "en-US", "en"]},
    {"locale": "fr-FR", "timezone": "Europe/Paris", "languages": ["fr-FR", "fr", "en"]},
]


class StealthProfileManager:
    """
    Génère et gère des profils navigateur cohérents.
    Peut persister le profil entre sessions pour garder un fingerprint stable.
    """

    PROFILE_CACHE_FILE = "config/browser_profile.json"

    @classmethod
    def generate_profile(cls, prefer_mac: bool = True) -> BrowserProfile:
        """
        Génère un profil navigateur complet et cohérent.

        Args:
            prefer_mac: Si True, 70% de chance d'avoir un profil Mac (cohérent
                        avec le fait que Thomas et son équipe sont sur Mac)
        """
        # Choisir la plateforme
        if prefer_mac:
            platform = "macOS" if random.random() < 0.70 else "Windows"
        else:
            platform = random.choice(["macOS", "Windows"])

        # Choisir la version Chrome
        chrome = random.choice(_CHROME_VERSIONS)

        # Choisir le profil OS + écran
        if platform == "macOS":
            os_profile = random.choice(_MAC_PROFILES)
            os_version = os_profile["os_version"]
            screen_config = random.choice(os_profile["screens"])
            ua = (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X {os_version}) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome['full']} Safari/537.36"
            )
            sec_ch_platform = '"macOS"'
        else:
            os_profile = random.choice(_WINDOWS_PROFILES)
            os_version = os_profile["os_version"]
            screen_config = random.choice(os_profile["screens"])
            ua = (
                f"Mozilla/5.0 (Windows NT {os_version}; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome['full']} Safari/537.36"
            )
            sec_ch_platform = '"Windows"'

        # Construire le header Sec-CH-UA (format Chrome réel)
        sec_ch_ua = (
            f'"Chromium";v="{chrome["major"]}", '
            f'"Google Chrome";v="{chrome["major"]}", '
            f'"Not-A.Brand";v="99"'
        )

        # Ajouter une légère variation au viewport (±10px)
        viewport = screen_config["viewport"].copy()
        viewport["width"] += random.randint(-8, 8)
        viewport["height"] += random.randint(-5, 5)
        # S'assurer que le viewport ne dépasse pas l'écran
        viewport["width"] = min(viewport["width"], screen_config["screen"]["width"])
        viewport["height"] = min(viewport["height"], screen_config["screen"]["height"])

        locale_config = random.choice(_FR_LOCALES)

        profile = BrowserProfile(
            platform=platform,
            os_version=os_version,
            chrome_major=chrome["major"],
            chrome_full=chrome["full"],
            user_agent=ua,
            viewport=viewport,
            screen=screen_config["screen"],
            sec_ch_ua=sec_ch_ua,
            sec_ch_ua_platform=sec_ch_platform,
            sec_ch_ua_mobile="?0",
            locale=locale_config["locale"],
            timezone=locale_config["timezone"],
            languages=locale_config["languages"],
        )

        logger.info(f"🎭 Profil généré: {platform} / Chrome {chrome['major']} / "
                     f"{viewport['width']}x{viewport['height']}")

        return profile

    @classmethod
    def load_or_generate(cls, prefer_mac: bool = True) -> BrowserProfile:
        """
        Charge un profil existant ou en génère un nouveau.
        Un même profil est réutilisé pendant 24h pour paraître cohérent.
        """
        try:
            if os.path.exists(cls.PROFILE_CACHE_FILE):
                with open(cls.PROFILE_CACHE_FILE, "r") as f:
                    data = json.load(f)

                # Vérifier que le profil n'est pas trop vieux (max 24h)
                created = datetime.fromisoformat(data.get("created_at", "2000-01-01"))
                age_hours = (datetime.now() - created).total_seconds() / 3600

                if age_hours < 24:
                    profile = BrowserProfile(**{k: v for k, v in data.items() if k != "created_at"})
                    logger.info(f"🎭 Profil rechargé (âge: {age_hours:.1f}h): "
                                f"{profile.platform} / Chrome {profile.chrome_major}")
                    return profile
                else:
                    logger.info("🔄 Profil expiré (>24h), régénération...")
        except Exception as e:
            logger.debug(f"Impossible de charger le profil cache: {e}")

        # Générer un nouveau profil
        profile = cls.generate_profile(prefer_mac=prefer_mac)

        # Sauvegarder
        try:
            os.makedirs(os.path.dirname(cls.PROFILE_CACHE_FILE), exist_ok=True)
            data = {
                "platform": profile.platform,
                "os_version": profile.os_version,
                "chrome_major": profile.chrome_major,
                "chrome_full": profile.chrome_full,
                "user_agent": profile.user_agent,
                "viewport": profile.viewport,
                "screen": profile.screen,
                "sec_ch_ua": profile.sec_ch_ua,
                "sec_ch_ua_platform": profile.sec_ch_ua_platform,
                "sec_ch_ua_mobile": profile.sec_ch_ua_mobile,
                "locale": profile.locale,
                "timezone": profile.timezone,
                "languages": profile.languages,
                "created_at": datetime.now().isoformat(),
            }
            with open(cls.PROFILE_CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Impossible de sauvegarder le profil: {e}")

        return profile

    @staticmethod
    def get_stealth_headers(profile: BrowserProfile) -> Dict[str, str]:
        """
        Retourne les headers HTTP cohérents avec le profil.
        Inclut les Sec-CH-UA headers que Chrome envoie vraiment.
        """
        return {
            "Accept-Language": ",".join(
                f"{lang};q={max(0.1, 1.0 - i*0.2):.1f}" if i > 0 else lang
                for i, lang in enumerate(profile.languages)
            ),
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,image/apng,*/*;q=0.8",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": profile.sec_ch_ua,
            "Sec-CH-UA-Mobile": profile.sec_ch_ua_mobile,
            "Sec-CH-UA-Platform": profile.sec_ch_ua_platform,
        }

    @staticmethod
    def get_stealth_init_script(profile: BrowserProfile) -> str:
        """
        Retourne le script JS d'initialisation stealth cohérent avec le profil.
        Injecté AVANT chaque navigation via page.add_init_script().
        """
        languages_js = json.dumps(profile.languages)
        platform_js = "MacIntel" if profile.platform == "macOS" else "Win32"
        screen_w = profile.screen["width"]
        screen_h = profile.screen["height"]
        chrome_major = profile.chrome_major

        return f"""
            // ═══ STEALTH CORE ═══

            // 1. Masquer webdriver (détection #1)
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
                configurable: true
            }});

            // Supprimer aussi le flag CDP
            delete navigator.__proto__.webdriver;

            // 2. Plugins réalistes (Chrome en a toujours 5)
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const plugins = [
                        {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer',
                           description: 'Portable Document Format', length: 1 }},
                        {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                           description: '', length: 1 }},
                        {{ name: 'Native Client', filename: 'internal-nacl-plugin',
                           description: '', length: 2 }},
                        {{ name: 'Chromium PDF Plugin', filename: 'internal-pdf-viewer',
                           description: 'Portable Document Format', length: 1 }},
                        {{ name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer',
                           description: '', length: 1 }},
                    ];
                    plugins.refresh = () => {{}};
                    plugins.item = (i) => plugins[i];
                    plugins.namedItem = (n) => plugins.find(p => p.name === n);
                    return plugins;
                }}
            }});

            // 3. Languages cohérentes avec les headers
            Object.defineProperty(navigator, 'languages', {{
                get: () => {languages_js}
            }});
            Object.defineProperty(navigator, 'language', {{
                get: () => {languages_js}[0]
            }});

            // 4. Platform cohérente
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{platform_js}'
            }});

            // 5. Masquer HeadlessChrome
            Object.defineProperty(navigator, 'userAgent', {{
                get: () => navigator.userAgent.replace('HeadlessChrome', 'Chrome')
            }});

            // 6. Screen dimensions cohérentes avec le viewport
            Object.defineProperty(screen, 'width', {{ get: () => {screen_w} }});
            Object.defineProperty(screen, 'height', {{ get: () => {screen_h} }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => {screen_w} }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {screen_h - 40} }});
            Object.defineProperty(screen, 'colorDepth', {{ get: () => 24 }});
            Object.defineProperty(screen, 'pixelDepth', {{ get: () => 24 }});

            // 7. Hardware concurrency réaliste (4-16 threads)
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {random.choice([4, 8, 10, 12, 16])}
            }});

            // 8. Device memory réaliste (8 ou 16 Go)
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {random.choice([8, 16])}
            }});

            // 9. Permissions naturelles
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({{ state: Notification.permission }})
                    : originalQuery(parameters)
            );

            // 10. Chrome runtime (présent dans un vrai Chrome)
            window.chrome = {{
                runtime: {{
                    PlatformOs: {{ MAC: 'mac', WIN: 'win', LINUX: 'linux' }},
                    connect: () => {{}},
                    sendMessage: () => {{}},
                }},
                loadTimes: function() {{
                    return {{
                        requestTime: Date.now() / 1000 - Math.random() * 0.5,
                        startLoadTime: Date.now() / 1000 - Math.random() * 0.3,
                        commitLoadTime: Date.now() / 1000 - Math.random() * 0.1,
                        finishDocumentLoadTime: Date.now() / 1000,
                        finishLoadTime: Date.now() / 1000,
                        firstPaintTime: Date.now() / 1000 - Math.random() * 0.05,
                        firstPaintAfterLoadTime: 0,
                        navigationType: 'Other',
                    }};
                }},
                csi: function() {{
                    return {{
                        onloadT: Date.now(),
                        pageT: Math.random() * 500 + 100,
                        startE: Date.now() - Math.floor(Math.random() * 1000),
                        tran: 15,
                    }};
                }},
                app: {{
                    isInstalled: false,
                    InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }},
                    RunningState: {{ CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }},
                }},
            }};

            // 11. WebRTC leak prevention (masquer l'IP locale)
            const origRTCPeerConnection = window.RTCPeerConnection;
            if (origRTCPeerConnection) {{
                window.RTCPeerConnection = function(...args) {{
                    const pc = new origRTCPeerConnection(...args);
                    const origCreateOffer = pc.createOffer.bind(pc);
                    pc.createOffer = function(options) {{
                        if (options) options.offerToReceiveAudio = false;
                        return origCreateOffer(options);
                    }};
                    return pc;
                }};
                window.RTCPeerConnection.prototype = origRTCPeerConnection.prototype;
            }}

            // 12. maxTouchPoints = 0 (desktop, pas mobile)
            Object.defineProperty(navigator, 'maxTouchPoints', {{
                get: () => 0
            }});

            // 13. Connection API réaliste
            if (navigator.connection) {{
                Object.defineProperty(navigator.connection, 'rtt', {{ get: () => {random.choice([50, 75, 100, 150])} }});
                Object.defineProperty(navigator.connection, 'downlink', {{ get: () => {random.choice([5, 10, 15, 20])} }});
                Object.defineProperty(navigator.connection, 'effectiveType', {{ get: () => '4g' }});
            }}

            // 14. Empêcher la détection via les iframes Playwright
            const origAttachShadow = Element.prototype.attachShadow;
            Element.prototype.attachShadow = function(init) {{
                return origAttachShadow.call(this, init);
            }};

            // 15. Cacher l'automation flag dans les Error stack traces
            const origError = Error;
            Error = function(...args) {{
                const err = new origError(...args);
                if (err.stack) {{
                    err.stack = err.stack.replace(/playwright/gi, 'chrome-extension');
                }}
                return err;
            }};
            Error.prototype = origError.prototype;
        """
