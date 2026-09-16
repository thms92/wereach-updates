# -*- coding: utf-8 -*-
from dataclasses import dataclass
import os
import random

@dataclass
class ScraperConfig:
    PROFIL_FILE: str = "profils_scrapes.csv"
    DATABASE_FILE: str = "profiles.db"
    LOG_FILE: str = "scraper.log"
    CONFIG_DIR: str = "config"
    SCHEDULE_FILE: str = "config/schedules.json"
    COOKIE_FILE: str = "config/cookie.txt"
    TEMPLATES_FILE: str = "config/search_templates.json"

    TIMEOUT_PAGE: int = 60000
    TIMEOUT_ELEMENT: int = 3000

    # -----------------------------------------------------------------------
    # Délais (en ms) — utilisés comme moyenne pour distribution gaussienne
    # Les valeurs MIN/MAX définissent la plage naturelle du comportement humain
    # -----------------------------------------------------------------------

    # Entre chaque profil traité (scroll, lecture, décision)
    # Valeurs volontairement longues (mode "sécurité max", sans proxy)
    DELAY_BETWEEN_PROFILES_MIN: int = 4000
    DELAY_BETWEEN_PROFILES_MAX: int = 9000

    # Après envoi d'invitation (attendre que la modal se ferme)
    DELAY_AFTER_INVITATION_MIN: int = 3000
    DELAY_AFTER_INVITATION_MAX: int = 6000

    # Après le clic sur "Se connecter" (attendre l'ouverture de la modal)
    DELAY_AFTER_CONNECT_CLICK_MIN: int = 1800
    DELAY_AFTER_CONNECT_CLICK_MAX: int = 4000

    # Après le chargement d'une page (temps de "lecture" initiale)
    DELAY_PAGE_LOAD_MIN: int = 2500
    DELAY_PAGE_LOAD_MAX: int = 6000

    # Plafonds PAR UTILISATEUR et PAR JOUR (source de vérité — appliqués dans
    # le scraper via DailyLimitsTracker). Conservateurs pour limiter le risque
    # LinkedIn quand plusieurs comptes partagent l'IP du serveur (sans proxy).
    MAX_PROFILES_PER_RUN: int = 80
    MAX_INVITATIONS_PER_DAY: int = 20
    MAX_RETRY_ATTEMPTS: int = 3
    # Headless pilotable par variable d'env : SCRAPER_HEADLESS=false lance un
    # navigateur VISIBLE (headed). LinkedIn masque certains boutons d'action
    # (ex. "Se connecter") aux sessions headless détectées.
    HEADLESS: bool = os.getenv("SCRAPER_HEADLESS", "true").strip().lower() not in ("false", "0", "no")

    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")

    SCHEDULER_CHECK_INTERVAL: int = 60

    @staticmethod
    def random_delay(min_ms: int, max_ms: int) -> int:
        """Génère un délai aléatoire entre min et max millisecondes"""
        return random.randint(min_ms, max_ms)

# Écoles / Formations.
# Valeur = ID interne LinkedIn (schoolFilter précis) quand on le connaît,
# sinon le NOM de l'école → repli : injecté dans la recherche booléenne
# (moins précis, mais fonctionnel). Pour rendre une école "précise", il
# suffit de remplacer son nom par son ID LinkedIn numérique.
ECOLES = {
    "Dauphine": "15092700",
    "Arts et Métiers": "1280025",
    "GEM": "18927",
    "Bootcamp Noé": "Bootcamp Noé",      # ID à fournir (repli par nom)
    "ESCP": "308907",
    "Université Cergy": "86580",
    "Audencia": "15104766",
    "INSA": "28135",
    "Sorbonne": "15094912",
    "PPA": "15097420",
    "EDHEC": "16001",
    "ESIEE": "15106279",
    "ESG": "1883450",
    "Inseec": "12635396",
    "SKEMA": "2413397",
    "Rennes BS": "15092681",
    "Kedge": "2757210",
    "ECE": "280138",
    "TBS": "47992",
    "Mines": "15092675",
    "IESEG": "319911",
    "ESGI": "ESGI",                      # ID en doublon reçu → à revérifier
    "EPF": "15094113",
    "Miage": "64556889",
    "EM Lyon": "18361",
    "PSTB": "77002277",
    "Neoma": "3330082",
    "ESSEC": "11415",
    "EPFL": "3883",
    "ESITV": "ESITV",                    # ID à fournir (repli par nom)
    "EFREI": "15094099",
    "ISCOM": "15248540",
    "Ingé Epita": "15106487",
    "HEC": "235785",
    "EM Normandie": "101603",
    "ESSCA": "238453",
    "Paris DIDEROT": "19143575",
    "IMM": "15098374",
    "Sup de Pub": "15100368",
    "Nanterre": "352250",
    "Université d'Angers": "315727",
}

# Secteurs d'activité LinkedIn (facette `industry` de la recherche people).
# Valeur = code de la taxonomie officielle "Industry Codes V2" :
# https://learn.microsoft.com/en-us/linkedin/shared/references/reference-tables/industry-codes-v2
# Sélection curée pour le recrutement tech / conseil. Le libellé français doit
# rester fidèle au libellé LinkedIn (rappelé en commentaire) : un code juste
# mais mal étiqueté renvoie silencieusement les mauvais profils.
# tests/test_secteurs_config.py épingle chaque code à son libellé officiel.
SECTEURS = {
    # Tech & numérique
    "Services et conseil informatiques": "96",      # IT Services and IT Consulting
    "Édition de logiciels": "4",                    # Software Development
    "Internet & technologies": "6",                 # Technology, Information and Internet
    "Sécurité informatique": "118",                 # Computer and Network Security
    "Jeux vidéo": "109",                            # Computer Games
    "Matériel informatique (fabrication)": "3",     # Computer Hardware Manufacturing
    "Télécommunications": "8",                      # Telecommunications
    "Médias audio & vidéo en ligne": "113",         # Online Audio and Video Media
    # Conseil & services aux entreprises
    "Services et conseil aux entreprises": "11",    # Business Consulting and Services
    "Comptabilité & audit": "47",                   # Accounting
    "Études de marché": "97",                       # Market Research
    "Recrutement et intérim": "104",                # Staffing and Recruiting
    "Ressources humaines": "137",                   # Human Resources Services
    "Formation professionnelle & coaching": "105",  # Professional Training and Coaching
    "Externalisation / offshoring": "123",          # Outsourcing and Offshoring Consulting
    "Ingénierie (bureaux d'études)": "3242",        # Engineering Services
    # Finance
    "Banque": "41",                                 # Banking
    "Assurance": "42",                              # Insurance
    "Services financiers": "43",                    # Financial Services
    "Marchés de capitaux": "129",                   # Capital Markets
    "Capital-risque & private equity": "106",       # Venture Capital and Private Equity Principals
    # Marketing, communication & design
    "Publicité & marketing": "80",                  # Advertising Services
    "Relations publiques & communication": "98",    # Public Relations and Communications Services
    "Design": "99",                                 # Design Services
    # Industrie, transport & énergie
    "Automobile (constructeurs)": "53",             # Motor Vehicle Manufacturing
    "Aéronautique & spatial (équipementiers)": "52",  # Aviation and Aerospace Component Manufacturing
    "Compagnies aériennes & aviation": "94",        # Airlines and Aviation
    "Machines industrielles": "135",                # Industrial Machinery Manufacturing
    "Industrie manufacturière": "25",               # Manufacturing
    "Pétrole & gaz": "57",                          # Oil and Gas
    "Énergies renouvelables": "3240",               # Renewable Energy Power Generation
    "Services environnementaux": "86",              # Environmental Services
    "Construction": "48",                           # Construction
    "Transport & logistique": "116",                # Transportation, Logistics, Supply Chain and Storage
    # Consommation & santé
    "Distribution / retail": "27",                  # Retail
    "Luxe & joaillerie": "143",                     # Retail Luxury Goods and Jewelry
    "Mode & habillement": "19",                     # Retail Apparel and Fashion
    "Industrie pharmaceutique": "15",               # Pharmaceutical Manufacturing
    "Santé & hôpitaux": "14",                       # Hospitals and Health Care
    "Dispositifs médicaux": "17",                   # Medical Equipment Manufacturing
    # Immobilier, éducation & public
    "Immobilier": "44",                             # Real Estate
    "Enseignement supérieur": "68",                 # Higher Education
    "Administration publique": "75",                # Government Administration
}

# Cabinets / entreprises concurrents (chasse). Sert la liste déroulante de la
# page Recherche. Le filtrage précis (currentCompany) dépend de l'URN LinkedIn
# dans config/company_urns.json ; sinon repli par nom (mot-clé).
CONCURRENTS = [
    "5 degrés", "ACCENTURE", "AFDTECH", "Ailancy", "AKKODIS (ex- AKKA & Modis)",
    "Aldemia", "Aliancy", "Aliznet", "ALPHONSE", "ALTEN", "ALTRAN", "Amaris",
    "AMETIX", "ANEO", "Apsia", "APSIDE", "Ares & co", "Arneo", "ASM Consulting",
    "ASTEK", "ATECNA", "Athoria", "ATOS", "AUBAY", "AUSY", "Avanade (Microsoft)",
    "B/ACCEPTANCE", "BAM", "Bearing Point", "Beelix", "Berexia", "BERTEK",
    "BETC UX", "Byron Group", "Capgemini", "Capteo", "CGI", "Cognizant",
    "Concentrix", "Consort NT", "Daveo", "DAVIDSON", "DEGETEL", "Deloitte",
    "Devoteam", "Digilityx", "DXC", "Dynemia", "Ebiznext (Umanis)", "Eleven Labs",
    "Emakina", "Europgroup Consulting", "Exomind", "Extia", "EY", "Fabernovel",
    "FERPECTION", "Grant Thorton", "Havas", "Headmind (ex-Beijaflore)", "Hitpart",
    "Hubvisory", "IBM", "IKXO", "Ineat", "INETUM (ex-GFI)", "INFOTEL", "Insign",
    "Inspearit", "Ippon Technologies", "Itecor", "Julhiet Sterwen", "Kaibee",
    "KANBIOS", "Karré", "Kea Partners", "Keley", "Klanik", "Klee", "KPMG",
    "Listen Too", "LMW Digital Expert", "Mantu", "Margo", "Mazars", "MC2i",
    "Meritis", "Mind7 Consulting", "Monsieur Guiz", "NEXTON", "NIJI", "Novencia",
    "NSI Group", "OAIO", "Océane Consulting Testing Services", "Octo", "OnePoint",
    "OPEN", "Orange Business Services", "Orphoz (McKinsey)", "PaloIT",
    "Polyconseil", "Publicis Sapient", "PwC", "Razorfish (Publicis)", "SAEGUS",
    "Scalian", "SFEIR", "Sia Partners", "SII", "Silamir", "Singulier", "Smile",
    "SOAT", "Softeam", "SoGETI", "Solutec", "SOPRA STERIA", "SOPRA STERIA NEXT",
    "Square Management", "Stanwell", "STEAM", "SURICATS CONSULTING",
    "Swood Partners", "TAK", "Talan", "TEAMINSIDE", "Themis Conseil", "THEODO",
    "Thiga", "Thinkmarket", "Tnp Consultant", "UMANIS", "UNIWARE", "UX Republic",
    "Valtech", "Velvet Consulting", "Vertone", "VISEO", "Wavestone",
    "Wed'R (Stanwell)", "Wemanity", "WERIN", "WOLD", "XEBIA", "Yeita", "Zenika",
]

# URN LinkedIn d'entreprises (filtre currentCompany précis). Versionné → déployé
# avec l'app. Clés en minuscules. Complété au fil de l'eau (ex. concurrents).
COMPANY_URNS = {
    "thiga": "4998677",
    "leroy merlin": "164715",
    "kering": "165528",
    "winamax": "862188",
    "kiloutou": "102956",
    "leclerc": "55152",
}

os.makedirs(ScraperConfig.CONFIG_DIR, exist_ok=True)
