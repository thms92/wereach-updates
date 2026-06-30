# -*- coding: utf-8 -*-
"""
Module d'extraction de données de profils LinkedIn
Stratégie unique et robuste pour extraire nom, poste, entreprise, etc.
"""

from typing import Dict, Optional
from logger import logger


class ProfileExtractor:
    """
    Classe pour extraire les données d'un profil LinkedIn
    Utilise une stratégie cascade élégante plutôt que plusieurs méthodes
    """

    @staticmethod
    def extract_from_data(profile_data: Dict) -> Dict:
        """
        Extrait et valide les données d'un profil à partir du dict retourné par JavaScript

        Args:
            profile_data: Dictionnaire avec les données brutes du profil

        Returns:
            Dictionnaire avec les données nettoyées et validées
        """
        try:
            # Extraction de base
            url = profile_data.get('href', '').split('?')[0]  # Nettoyer l'URL
            name = ProfileExtractor._clean_name(profile_data.get('name', ''))
            job_title = ProfileExtractor._clean_job_title(profile_data.get('jobTitle', ''))
            company = ProfileExtractor._clean_company(profile_data.get('company', ''))
            location = ProfileExtractor._clean_location(profile_data.get('location', ''))
            connections = profile_data.get('connections', '')

            # Validation
            if not name or not url:
                logger.warning(f"Profil invalide : nom ou URL manquant")
                return {}

            # Construire le profil final
            profile = {
                'nom': name,
                'poste': job_title,
                'entreprise': company,
                'url': url,
                'localisation': location,
                'connexions': connections,
            }

            logger.debug(f"✅ Profil extrait : {name} - {job_title} @ {company}")
            return profile

        except Exception as e:
            logger.error(f"Erreur extraction profil : {e}")
            return {}

    @staticmethod
    def _clean_name(name: str) -> str:
        """Nettoie et valide le nom"""
        if not name:
            return ""

        # Nettoyer les espaces multiples
        name = ' '.join(name.split())

        # Enlever les suffixes LinkedIn
        name = name.replace('Utilisateur LinkedIn', '').strip()

        # Validation basique
        if len(name) < 2:
            return ""

        # Filtrer les noms non valides
        invalid_names = ['Se connecter', 'Message', 'Suivre', 'Plus']
        if name in invalid_names:
            return ""

        return name

    @staticmethod
    def _clean_job_title(job_title: str) -> str:
        """Nettoie le titre du poste"""
        if not job_title:
            return ""

        # Nettoyer les espaces
        job_title = ' '.join(job_title.split())

        # Enlever les préfixes LinkedIn
        prefixes = [
            'Poste actuel :', 'Poste actuel:',
            'Postes précédents :', 'Postes précédents:',
            'Poste précédent :', 'Poste précédent:'
        ]

        for prefix in prefixes:
            if job_title.startswith(prefix):
                job_title = job_title[len(prefix):].strip()

        # Limiter la longueur
        if len(job_title) > 200:
            job_title = job_title[:200] + '...'

        return job_title

    @staticmethod
    def _clean_company(company: str) -> str:
        """Nettoie le nom de l'entreprise"""
        if not company:
            return ""

        # Nettoyer les espaces
        company = ' '.join(company.split())

        # Couper au | (souvent suivi de "Ex-PM", "HEC Paris", etc.)
        if '|' in company:
            company = company.split('|')[0].strip()

        # Enlever "Ex-PM", "Hiring", et autres suffixes communs
        suffixes_to_remove = [
            'Ex-PM', 'Hiring', '🙌🏻', 'We are hiring', 'We\'re hiring',
            'Join us', 'HEC Paris', 'HEC', 'ESSEC', 'EM Lyon'
        ]
        for suffix in suffixes_to_remove:
            if company.endswith(suffix):
                company = company[:-len(suffix)].strip()

        # Enlever les emojis et caractères spéciaux à la fin
        import re
        company = re.sub(r'[\U0001F000-\U0001F9FF\s]+$', '', company)

        # Couper les villes/pays collés à la fin (ex: "SkillupParis" -> "Skillup")
        # Liste des villes/pays communs
        location_suffixes = [
            'Paris', 'Lyon', 'Marseille', 'Lille', 'Toulouse', 'Bordeaux', 'Nantes',
            'Strasbourg', 'Montpellier', 'Nice', 'Rennes', 'Grenoble',
            'France', 'London', 'Berlin', 'Madrid', 'Barcelona', 'Rome', 'Milan',
            'Amsterdam', 'Brussels', 'Geneva', 'Zurich', 'Munich', 'Vienna',
            'Nanterre', 'Puteaux', 'Courbevoie', 'Levallois', 'Boulogne'
        ]

        for loc in location_suffixes:
            if company.endswith(loc):
                company = company[:-len(loc)].strip()
                break

        # Enlever les caractères parasites
        company = company.replace('(', '').replace(')', '').strip()

        # Enlever les suffixes de durée "Entreprise (2 ans)"
        company = re.sub(r'\s*\(\d+\s*(an|mois|année|year|month)s?\)', '', company, flags=re.IGNORECASE)

        # Limiter la longueur
        if len(company) > 100:
            company = company[:100] + '...'

        return company.strip()

    @staticmethod
    def _clean_location(location: str) -> str:
        """Nettoie la localisation"""
        if not location:
            return ""

        # Nettoyer les espaces
        location = ' '.join(location.split())

        # Vérifier que ce n'est pas un poste déguisé
        if any(keyword in location.lower() for keyword in ['poste', 'chez', 'manager', 'engineer']):
            return ""

        # Limiter la longueur
        if len(location) > 100:
            location = location[:100] + '...'

        return location

    @staticmethod
    def extract_name_from_element(element, page) -> Optional[str]:
        """
        Extrait le nom depuis un élément Playwright (fallback method)
        Utilisé si l'extraction JavaScript échoue
        """
        try:
            # Méthode 1 : Via aria-label
            aria_label = element.evaluate("""
                el => {
                    const figure = (el.closest('li') || el.closest('div'))?.querySelector('figure[aria-label]');
                    return figure?.getAttribute('aria-label') || '';
                }
            """)

            if aria_label and len(aria_label) > 2:
                return ProfileExtractor._clean_name(aria_label)

            # Méthode 2 : Via inner text
            text = element.inner_text()
            if text:
                # Prendre la première ligne (souvent le nom)
                first_line = text.split('\n')[0].strip()
                if first_line and len(first_line) > 2:
                    return ProfileExtractor._clean_name(first_line)

            return None

        except Exception as e:
            logger.debug(f"Erreur extraction nom fallback : {e}")
            return None

    @staticmethod
    def validate_profile(profile: Dict) -> bool:
        """
        Valide qu'un profil contient les informations minimales requises

        Args:
            profile: Dictionnaire du profil

        Returns:
            True si le profil est valide
        """
        # Vérifications obligatoires
        if not profile.get('nom'):
            logger.debug("Profil invalide : nom manquant")
            return False

        if not profile.get('url'):
            logger.debug("Profil invalide : URL manquante")
            return False

        # Vérifier que l'URL est valide
        url = profile.get('url', '')
        if '/in/' not in url:
            logger.debug(f"Profil invalide : URL incorrecte {url}")
            return False

        # Vérifier que ce n'est pas un profil "Utilisateur LinkedIn"
        if 'utilisateur linkedin' in profile.get('nom', '').lower():
            logger.debug("Profil invalide : Utilisateur LinkedIn générique")
            return False

        return True

    @staticmethod
    def format_for_display(profile: Dict, ecole: str = "", invited: bool = False) -> Dict:
        """
        Formate un profil pour l'affichage dans le DataFrame final

        Args:
            profile: Profil brut
            ecole: Nom de l'école
            invited: Si une invitation a été envoyée

        Returns:
            Profil formaté pour export
        """
        return {
            "Nom": profile.get('nom', ''),
            "Poste": profile.get('poste', ''),
            "Entreprise": profile.get('entreprise', ''),
            "École": ecole,
            "URL du profil": profile.get('url', ''),
            "Invitation envoyée": "Oui" if invited else "Non"
        }
