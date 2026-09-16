# -*- coding: utf-8 -*-
"""Table des secteurs LinkedIn (facette `industry`).

Chaque code est épinglé à son libellé officiel de la taxonomie LinkedIn
Industry Codes V2. Un code juste mais mal étiqueté en français renvoie
silencieusement les mauvais profils : ce test empêche la dérive.
Source : https://learn.microsoft.com/en-us/linkedin/shared/references/reference-tables/industry-codes-v2
"""

from config import SECTEURS

# secteur (FR, tel qu'affiché dans l'UI) -> (code, libellé officiel LinkedIn)
REFERENCE = {
    "Services et conseil informatiques": ("96", "IT Services and IT Consulting"),
    "Édition de logiciels": ("4", "Software Development"),
    "Internet & technologies": ("6", "Technology, Information and Internet"),
    "Sécurité informatique": ("118", "Computer and Network Security"),
    "Jeux vidéo": ("109", "Computer Games"),
    "Matériel informatique (fabrication)": ("3", "Computer Hardware Manufacturing"),
    "Télécommunications": ("8", "Telecommunications"),
    "Médias audio & vidéo en ligne": ("113", "Online Audio and Video Media"),
    "Services et conseil aux entreprises": ("11", "Business Consulting and Services"),
    "Comptabilité & audit": ("47", "Accounting"),
    "Études de marché": ("97", "Market Research"),
    "Recrutement et intérim": ("104", "Staffing and Recruiting"),
    "Ressources humaines": ("137", "Human Resources Services"),
    "Formation professionnelle & coaching": ("105", "Professional Training and Coaching"),
    "Externalisation / offshoring": ("123", "Outsourcing and Offshoring Consulting"),
    "Ingénierie (bureaux d'études)": ("3242", "Engineering Services"),
    "Banque": ("41", "Banking"),
    "Assurance": ("42", "Insurance"),
    "Services financiers": ("43", "Financial Services"),
    "Marchés de capitaux": ("129", "Capital Markets"),
    "Capital-risque & private equity": ("106", "Venture Capital and Private Equity Principals"),
    "Publicité & marketing": ("80", "Advertising Services"),
    "Relations publiques & communication": ("98", "Public Relations and Communications Services"),
    "Design": ("99", "Design Services"),
    "Automobile (constructeurs)": ("53", "Motor Vehicle Manufacturing"),
    "Aéronautique & spatial (équipementiers)": ("52", "Aviation and Aerospace Component Manufacturing"),
    "Compagnies aériennes & aviation": ("94", "Airlines and Aviation"),
    "Machines industrielles": ("135", "Industrial Machinery Manufacturing"),
    "Industrie manufacturière": ("25", "Manufacturing"),
    "Pétrole & gaz": ("57", "Oil and Gas"),
    "Énergies renouvelables": ("3240", "Renewable Energy Power Generation"),
    "Services environnementaux": ("86", "Environmental Services"),
    "Construction": ("48", "Construction"),
    "Distribution / retail": ("27", "Retail"),
    "Luxe & joaillerie": ("143", "Retail Luxury Goods and Jewelry"),
    "Mode & habillement": ("19", "Retail Apparel and Fashion"),
    "Industrie pharmaceutique": ("15", "Pharmaceutical Manufacturing"),
    "Santé & hôpitaux": ("14", "Hospitals and Health Care"),
    "Dispositifs médicaux": ("17", "Medical Equipment Manufacturing"),
    "Transport & logistique": ("116", "Transportation, Logistics, Supply Chain and Storage"),
    "Immobilier": ("44", "Real Estate"),
    "Enseignement supérieur": ("68", "Higher Education"),
    "Administration publique": ("75", "Government Administration"),
}


def test_chaque_secteur_pointe_sur_le_bon_code_linkedin():
    attendu = {nom: code for nom, (code, _) in REFERENCE.items()}
    assert SECTEURS == attendu


def test_tous_les_secteurs_ont_un_id_numerique():
    # Un ID non numérique serait silencieusement ignoré par le scraper.
    assert {n: i for n, i in SECTEURS.items() if not str(i).isdigit()} == {}


def test_aucun_id_de_secteur_en_double():
    ids = list(SECTEURS.values())
    assert {i for i in ids if ids.count(i) > 1} == set()


def test_les_secteurs_cles_du_recrutement_tech_sont_presents():
    for attendu in ("Services et conseil aux entreprises", "Services et conseil informatiques",
                    "Édition de logiciels", "Recrutement et intérim"):
        assert attendu in SECTEURS
