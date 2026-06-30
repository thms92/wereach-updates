# -*- coding: utf-8 -*-
"""
Module d'intégration avec l'API FullEnrich
Permet d'enrichir les profils LinkedIn avec des emails professionnels et personnels
API Documentation: https://docs.fullenrich.com
"""

import requests
import pandas as pd
import time
from typing import Optional, List, Dict
from logger import logger


class FullEnrichAPI:
    """Client pour l'API FullEnrich (bulk enrichment)"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://app.fullenrich.com/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        logger.info(f"FullEnrich API initialisée avec Bearer authentication")
    
    def start_bulk_enrichment(self, linkedin_urls: List[str], name: str = "LinkedIn Scraper Enrichment") -> Optional[str]:
        """
        Démarre un enrichissement en bulk et retourne l'ID
        
        Args:
            linkedin_urls: Liste des URLs LinkedIn à enrichir
            name: Nom de l'enrichissement (visible dans le dashboard)
            
        Returns:
            ID de l'enrichissement ou None en cas d'erreur
        """
        try:
            # Préparer les données selon le format FullEnrich
            datas = []
            for url in linkedin_urls:
                clean_url = url.split('?')[0].strip()
                datas.append({
                    "linkedin_url": clean_url,
                    "enrich_fields": [
                        "contact.emails",
                        "contact.personal_emails", 
                        "contact.phones"
                    ]
                })
            
            payload = {
                "name": name,
                "datas": datas
            }
            
            logger.info(f"Démarrage enrichissement bulk de {len(datas)} profils")
            logger.debug(f"Payload: {payload}")
            
            response = requests.post(
                f"{self.base_url}/contact/enrich/bulk",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            logger.info(f"Status: {response.status_code}")
            logger.info(f"Response: {response.text[:300]}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                enrichment_id = data.get('enrichment_id')
                logger.info(f"✅ Enrichissement bulk démarré - ID: {enrichment_id}")
                return enrichment_id
            elif response.status_code == 401 or response.status_code == 403:
                logger.error(f"❌ Authentification échouée: {response.text}")
                return None
            else:
                logger.error(f"❌ Erreur: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Erreur start_bulk_enrichment: {e}", exc_info=True)
            return None
    
    def get_enrichment_result(self, enrichment_id: str, max_attempts: int = 60) -> Dict:
        """
        Récupère le résultat d'un enrichissement bulk (polling)
        
        Args:
            enrichment_id: ID de l'enrichissement
            max_attempts: Nombre maximum de tentatives (60 = 120 secondes max)
            
        Returns:
            Résultat de l'enrichissement
        """
        try:
            # Tester plusieurs endpoints possibles
            endpoints = [
                f"/contact/enrich/bulk/{enrichment_id}",
                f"/bulk/{enrichment_id}",
                f"/enrichment/{enrichment_id}",
                f"/contact/enrichment/{enrichment_id}"
            ]
            
            working_endpoint = None
            
            # Trouver le bon endpoint
            for endpoint in endpoints:
                test_url = f"{self.base_url}{endpoint}"
                logger.info(f"Test polling endpoint: {endpoint}")
                
                response = requests.get(
                    test_url,
                    headers=self.headers,
                    timeout=30
                )
                
                logger.info(f"  → Status: {response.status_code}")
                
                # Si 404 avec "Unknown api path", passer au suivant
                if response.status_code == 404:
                    try:
                        error_data = response.json()
                        if error_data.get('code') == 'error.api.not_found':
                            continue
                    except:
                        pass
                
                # Si on a une réponse valide (200, ou même autre que 404)
                if response.status_code in [200, 202]:
                    working_endpoint = endpoint
                    logger.info(f"✅ Endpoint polling trouvé: {endpoint}")
                    break
            
            if not working_endpoint:
                logger.error("❌ Aucun endpoint de polling valide trouvé")
                return {'status': 'error', 'results': []}
            
            # Polling avec le bon endpoint
            for attempt in range(max_attempts):
                response = requests.get(
                    f"{self.base_url}{working_endpoint}",
                    headers=self.headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '')
                    
                    logger.info(f"Polling {attempt + 1}/{max_attempts} - Status: {status}")
                    
                    if status == 'completed' or status == 'done' or status == 'finished' or status == 'COMPLETED' or status == 'DONE':
                        logger.info("✅ Enrichissement terminé")
                        logger.info(f"📋 Données complètes reçues: {str(data)[:500]}...")
                        return data
                    elif status == 'failed' or status == 'error' or status == 'FAILED':
                        logger.warning("❌ Enrichissement échoué")
                        logger.warning(f"Données d'erreur: {str(data)[:500]}")
                        return data
                    elif status == 'pending' or status == 'processing' or status == 'in_progress' or status == 'IN_PROGRESS' or status == 'PENDING':
                        # Attendre 2 secondes avant la prochaine tentative
                        logger.debug(f"  → En cours, nouvelle tentative dans 2s...")
                        time.sleep(2)
                        continue
                    else:
                        # Statut inconnu, peut-être que c'est terminé
                        logger.warning(f"⚠️ Statut inconnu: {status}")
                        logger.info(f"📋 Données reçues: {str(data)[:500]}...")
                        # Vérifier si on a des résultats
                        if 'results' in data or 'data' in data or 'contacts' in data:
                            logger.info("  → Des résultats sont présents, on les retourne")
                            return data
                        else:
                            logger.warning("  → Pas de résultats visibles, on continue le polling")
                            time.sleep(2)
                            continue
                else:
                    logger.error(f"Erreur polling: {response.status_code} - {response.text}")
                    return {'status': 'error', 'results': []}
            
            # Timeout après max_attempts
            logger.warning("⏱️ Timeout lors du polling")
            return {'status': 'timeout', 'results': []}
            
        except Exception as e:
            logger.error(f"Erreur get_enrichment_result: {e}", exc_info=True)
            return {'status': 'error', 'results': []}
    
    def enrich_profile(self, linkedin_url: str) -> Dict:
        """
        Enrichit un seul profil LinkedIn (wrapper pour compatibilité)
        Utilise l'API bulk avec 1 seul profil
        
        Args:
            linkedin_url: URL du profil LinkedIn
            
        Returns:
            Résultat de l'enrichissement
        """
        try:
            results = self.enrich_profiles_bulk([linkedin_url])
            
            if results and len(results) > 0:
                return parse_fullenrich_result(results[0], linkedin_url)
            else:
                return {
                    'success': False,
                    'email_pro': '',
                    'email_perso': '',
                    'telephone': '',
                    'entreprise_verifiee': '',
                    'poste_verifie': '',
                    'statut': 'aucun_resultat',
                    'nom_complet': '',
                    'linkedin_url': linkedin_url
                }
                
        except Exception as e:
            logger.error(f"Erreur enrich_profile: {e}", exc_info=True)
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': f'erreur: {str(e)[:50]}',
                'nom_complet': '',
                'linkedin_url': linkedin_url
            }
    
    def enrich_profiles_bulk(self, linkedin_urls: List[str]) -> List[Dict]:
        """
        Enrichit plusieurs profils LinkedIn en une seule requête bulk
        
        Args:
            linkedin_urls: Liste des URLs LinkedIn
            
        Returns:
            Liste des résultats d'enrichissement
        """
        try:
            # Étape 1: Démarrer l'enrichissement bulk
            enrichment_id = self.start_bulk_enrichment(linkedin_urls)
            
            if not enrichment_id:
                logger.error("Impossible de démarrer l'enrichissement bulk")
                return []
            
            # Étape 2: Polling pour récupérer les résultats
            result = self.get_enrichment_result(enrichment_id)
            
            # Étape 3: Extraire les résultats
            # Tester plusieurs clés possibles
            results = []
            
            if 'results' in result:
                results = result['results']
            elif 'data' in result:
                results = result['data']
            elif 'contacts' in result:
                results = result['contacts']
            elif 'datas' in result:
                results = result['datas']
            else:
                # Peut-être que le résultat entier est une liste
                if isinstance(result, list):
                    results = result
                else:
                    logger.warning(f"⚠️ Clés de résultats non trouvées. Clés disponibles: {list(result.keys())}")
                    logger.info(f"Structure complète: {str(result)[:1000]}")
            
            logger.info(f"📊 {len(results)} résultats extraits")
            
            return results
            
        except Exception as e:
            logger.error(f"Erreur enrich_profiles_bulk: {e}", exc_info=True)
            return []


def parse_fullenrich_result(result: Dict, linkedin_url: str) -> Dict:
    """
    Parse un résultat individuel de FullEnrich
    
    Args:
        result: Résultat brut de l'API
        linkedin_url: URL LinkedIn du profil
        
    Returns:
        Dictionnaire formaté
    """
    try:
        # Structure FullEnrich : result contient 'contact' et 'company'
        contact = result.get('contact', {})
        company = result.get('company', {})
        
        # Emails
        emails = contact.get('emails', [])
        personal_emails = contact.get('personal_emails', [])
        
        email_pro = emails[0] if emails else ''
        email_perso = personal_emails[0] if personal_emails else ''
        
        # Téléphones
        phones = contact.get('phones', [])
        telephone = phones[0] if phones else ''
        
        # Informations de profil
        full_name = contact.get('full_name', contact.get('name', ''))
        job_title = contact.get('title', contact.get('job_title', ''))
        company_name = company.get('name', '')
        
        # Vérifier si enrichissement réussi
        success = bool(email_pro or email_perso or telephone)
        statut = 'enrichi' if success else 'non_trouve'
        
        return {
            'success': success,
            'email_pro': email_pro,
            'email_perso': email_perso,
            'telephone': telephone,
            'entreprise_verifiee': company_name,
            'poste_verifie': job_title,
            'statut': statut,
            'nom_complet': full_name,
            'linkedin_url': linkedin_url
        }
        
    except Exception as e:
        logger.error(f"Erreur parse_fullenrich_result: {e}")
        return {
            'success': False,
            'email_pro': '',
            'email_perso': '',
            'telephone': '',
            'entreprise_verifiee': '',
            'poste_verifie': '',
            'statut': 'erreur_parsing',
            'nom_complet': '',
            'linkedin_url': linkedin_url
        }


def enrich_profiles(df: pd.DataFrame, api_key: str, 
                   progress_callback=None, status_callback=None) -> pd.DataFrame:
    """
    Enrichit un DataFrame de profils LinkedIn avec FullEnrich
    
    Args:
        df: DataFrame contenant une colonne 'URL du profil'
        api_key: Clé API FullEnrich
        progress_callback: Fonction de callback pour la progression
        status_callback: Fonction de callback pour le statut
        
    Returns:
        DataFrame enrichi avec les nouvelles colonnes
    """
    
    if 'URL du profil' not in df.columns:
        raise ValueError("Le DataFrame doit contenir une colonne 'URL du profil'")
    
    logger.info(f"Démarrage enrichissement de {len(df)} profils")
    
    client = FullEnrichAPI(api_key)
    
    # Créer les nouvelles colonnes
    df['Email Pro'] = ''
    df['Email Perso'] = ''
    df['Téléphone'] = ''
    df['Entreprise (vérifiée)'] = ''
    df['Poste (vérifié)'] = ''
    df['Statut Enrichissement'] = ''
    
    # Collecter les URLs valides
    linkedin_urls = []
    url_to_index = {}
    
    for idx, row in df.iterrows():
        linkedin_url = row['URL du profil']
        
        if pd.isna(linkedin_url) or linkedin_url == '':
            df.at[idx, 'Statut Enrichissement'] = 'url_manquante'
            continue
        
        linkedin_urls.append(linkedin_url)
        url_to_index[linkedin_url] = idx
    
    if not linkedin_urls:
        logger.warning("Aucune URL valide à enrichir")
        return df
    
    logger.info(f"📋 {len(linkedin_urls)} URLs valides à enrichir")
    
    if status_callback:
        status_callback(f"🚀 Enrichissement bulk de {len(linkedin_urls)} profils...")
    
    # Enrichissement bulk
    results = client.enrich_profiles_bulk(linkedin_urls)
    
    logger.info(f"📊 {len(results)} résultats reçus de FullEnrich")
    
    # Mapper les résultats aux lignes du DataFrame
    enrichis = 0
    erreurs = 0
    
    for i, (url, result) in enumerate(zip(linkedin_urls, results)):
        if status_callback:
            status_callback(f"📧 Traitement {i + 1}/{len(results)}")
        
        idx = url_to_index.get(url)
        if idx is None:
            continue
        
        # Parser le résultat
        parsed = parse_fullenrich_result(result, url)
        
        # Remplir les colonnes
        df.at[idx, 'Email Pro'] = parsed['email_pro']
        df.at[idx, 'Email Perso'] = parsed['email_perso']
        df.at[idx, 'Téléphone'] = parsed['telephone']
        df.at[idx, 'Entreprise (vérifiée)'] = parsed['entreprise_verifiee']
        df.at[idx, 'Poste (vérifié)'] = parsed['poste_verifie']
        df.at[idx, 'Statut Enrichissement'] = parsed['statut']
        
        if parsed['success']:
            enrichis += 1
            logger.info(f"✅ {parsed.get('nom_complet', 'Inconnu')}: {parsed['email_pro']}")
        else:
            erreurs += 1
            logger.warning(f"❌ {url}: {parsed['statut']}")
        
        if progress_callback:
            progress_callback((i + 1) / len(results))
    
    logger.info(f"\n{'='*60}")
    logger.info(f"RÉSUMÉ: {enrichis}/{len(results)} profils enrichis, {erreurs} erreurs")
    logger.info('='*60)
    
    return df

    """Client pour l'API FullEnrich (asynchrone)"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://app.fullenrich.com/api/v1"
        self.headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        logger.info(f"FullEnrich API initialisée")
    
    def start_enrichment(self, linkedin_url: str) -> Optional[str]:
        """
        Démarre un enrichissement et retourne l'ID de l'enrichissement
        Teste plusieurs endpoints jusqu'à trouver le bon
        
        Args:
            linkedin_url: URL du profil LinkedIn
            
        Returns:
            ID de l'enrichissement ou None en cas d'erreur
        """
        try:
            clean_url = linkedin_url.split('?')[0].strip()
            
            # Liste des endpoints possibles à tester
            endpoints_to_try = [
                "/waterfall/enrich",
                "/enrich",
                "/enrichment/start",
                "/enrichment",
                "/person/enrich",
                "/enrich/person",
                "/v1/enrich",
                "/enrichments"
            ]
            
            # Payload standard
            payload = {
                "linkedin_url": clean_url
            }
            
            # Essayer aussi avec d'autres formats de payload
            payloads_to_try = [
                {"linkedin_url": clean_url},
                {"url": clean_url},
                {"linkedin": clean_url},
                {"profile_url": clean_url}
            ]
            
            for endpoint in endpoints_to_try:
                for payload in payloads_to_try:
                    full_url = f"{self.base_url}{endpoint}"
                    
                    logger.info(f"Test: {endpoint} avec payload {list(payload.keys())}")
                    
                    response = requests.post(
                        full_url,
                        headers=self.headers,
                        json=payload,
                        timeout=30
                    )
                    
                    logger.info(f"  → Status: {response.status_code}")
                    
                    # Si on a un 404 "Unknown api path", passer au suivant
                    if response.status_code == 404:
                        try:
                            error_data = response.json()
                            if error_data.get('code') == 'error.api.not_found':
                                logger.debug(f"  → Endpoint inconnu, suivant...")
                                continue
                        except:
                            pass
                    
                    # Si le status n'est pas 404 "unknown", c'est probablement le bon endpoint
                    if response.status_code in [200, 201]:
                        data = response.json()
                        enrichment_id = data.get('id', data.get('enrichment_id', data.get('_id', data.get('enrichmentId'))))
                        
                        logger.info(f"✅ ENDPOINT TROUVÉ: {endpoint}")
                        logger.info(f"✅ PAYLOAD VALIDE: {list(payload.keys())}")
                        logger.info(f"✅ Enrichissement démarré - ID: {enrichment_id}")
                        logger.info(f"✅ Réponse complète: {response.text[:300]}")
                        
                        # Sauvegarder l'endpoint qui fonctionne
                        self.working_endpoint = endpoint
                        self.working_payload_format = list(payload.keys())[0]
                        
                        return enrichment_id
                    
                    elif response.status_code == 401 or response.status_code == 403:
                        logger.error(f"❌ Authentification échouée: {response.text}")
                        return None
                    
                    elif response.status_code == 400:
                        logger.warning(f"  → Mauvais format de payload: {response.text[:200]}")
                        # Continuer pour essayer un autre format de payload
                        continue
            
            logger.error("❌ Aucun endpoint valide trouvé après tous les tests")
            logger.error(f"Endpoints testés: {endpoints_to_try}")
            logger.error(f"Formats de payload testés: {[list(p.keys()) for p in payloads_to_try]}")
            return None
                
        except Exception as e:
            logger.error(f"Erreur start_enrichment: {e}", exc_info=True)
            return None
    
    def get_enrichment_result(self, enrichment_id: str, max_attempts: int = 30) -> dict:
        """
        Récupère le résultat d'un enrichissement (polling)
        
        Args:
            enrichment_id: ID de l'enrichissement
            max_attempts: Nombre maximum de tentatives (30 = 60 secondes max)
            
        Returns:
            Résultat de l'enrichissement
        """
        try:
            for attempt in range(max_attempts):
                response = requests.get(
                    f"{self.base_url}/enrich/{enrichment_id}",
                    headers=self.headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '')
                    
                    logger.info(f"Polling {attempt + 1}/{max_attempts} - Status: {status}")
                    
                    if status == 'completed' or status == 'done':
                        logger.info("✅ Enrichissement terminé")
                        return self._parse_result(data, True)
                    elif status == 'failed' or status == 'error':
                        logger.warning("❌ Enrichissement échoué")
                        return self._parse_result(data, False)
                    elif status == 'pending' or status == 'processing' or status == 'in_progress':
                        # Attendre 2 secondes avant la prochaine tentative
                        time.sleep(2)
                        continue
                    else:
                        # Statut inconnu, peut-être que les données sont déjà disponibles
                        return self._parse_result(data, True)
                else:
                    logger.error(f"Erreur polling: {response.status_code}")
                    return self._empty_result('erreur_polling')
            
            # Timeout après max_attempts
            logger.warning("Timeout lors du polling")
            return self._empty_result('timeout')
            
        except Exception as e:
            logger.error(f"Erreur get_enrichment_result: {e}")
            return self._empty_result('erreur')
    
    def _parse_result(self, data: dict, success: bool) -> dict:
        """Parse le résultat de l'API FullEnrich"""
        
        if not success:
            return self._empty_result('enrichissement_echoue')
        
        # Extraire les données de la réponse
        person = data.get('person', data.get('data', data.get('result', data)))
        
        # Emails
        emails = person.get('emails', person.get('email', []))
        if isinstance(emails, str):
            emails = [{'email': emails}]
        elif not isinstance(emails, list):
            emails = []
        
        email_pro = ''
        email_perso = ''
        
        for email_obj in emails:
            if isinstance(email_obj, dict):
                email_addr = email_obj.get('email', email_obj.get('value', ''))
                email_type = email_obj.get('type', '').lower()
                
                if 'work' in email_type or 'professional' in email_type or 'business' in email_type:
                    if not email_pro:
                        email_pro = email_addr
                elif 'personal' in email_type or 'private' in email_type:
                    if not email_perso:
                        email_perso = email_addr
                elif '@' in email_addr:
                    # Si pas de type, le premier devient pro
                    if not email_pro:
                        email_pro = email_addr
                    elif not email_perso:
                        email_perso = email_addr
        
        # Téléphones
        phones = person.get('phones', person.get('phoneNumbers', person.get('phone', [])))
        if isinstance(phones, str):
            phones = [phones]
        elif not isinstance(phones, list):
            phones = []
        
        telephone = ''
        if phones:
            phone_obj = phones[0]
            if isinstance(phone_obj, dict):
                telephone = phone_obj.get('number', phone_obj.get('value', ''))
            elif isinstance(phone_obj, str):
                telephone = phone_obj
        
        # Entreprise
        company = person.get('company', person.get('organization', person.get('currentCompany', {})))
        if isinstance(company, dict):
            company_name = company.get('name', '')
        else:
            company_name = str(company) if company else ''
        
        # Poste
        job_title = person.get('title', person.get('jobTitle', person.get('position', '')))
        
        # Nom complet
        full_name = person.get('fullName', person.get('name', ''))
        
        return {
            'success': True,
            'email_pro': email_pro,
            'email_perso': email_perso,
            'telephone': telephone,
            'entreprise_verifiee': company_name,
            'poste_verifie': job_title,
            'statut': 'enrichi',
            'nom_complet': full_name
        }
    
    def _empty_result(self, statut: str) -> dict:
        """Retourne un résultat vide avec un statut"""
        return {
            'success': False,
            'email_pro': '',
            'email_perso': '',
            'telephone': '',
            'entreprise_verifiee': '',
            'poste_verifie': '',
            'statut': statut,
            'nom_complet': ''
        }
    
    def enrich_profile(self, linkedin_url: str) -> dict:
        """
        Enrichit un profil LinkedIn (méthode complète: start + polling)
        
        Args:
            linkedin_url: URL du profil LinkedIn
            
        Returns:
            Résultat de l'enrichissement
        """
        try:
            clean_url = linkedin_url.split('?')[0].strip()
            logger.info(f"Enrichissement de: {clean_url}")
            
            # Étape 1: Démarrer l'enrichissement
            enrichment_id = self.start_enrichment(clean_url)
            
            if not enrichment_id:
                logger.error("Impossible de démarrer l'enrichissement")
                return self._empty_result('erreur_demarrage')
            
            # Étape 2: Polling pour récupérer le résultat
            result = self.get_enrichment_result(enrichment_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur enrich_profile: {e}", exc_info=True)
            return self._empty_result(f'erreur: {str(e)[:50]}')


def enrich_profiles(df: pd.DataFrame, api_key: str, 
                   progress_callback=None, status_callback=None) -> pd.DataFrame:
    """
    Enrichit un DataFrame de profils LinkedIn avec FullEnrich
    
    Args:
        df: DataFrame contenant une colonne 'URL du profil'
        api_key: Clé API FullEnrich
        progress_callback: Fonction de callback pour la progression
        status_callback: Fonction de callback pour le statut
        
    Returns:
        DataFrame enrichi avec les nouvelles colonnes
    """
    
    if 'URL du profil' not in df.columns:
        raise ValueError("Le DataFrame doit contenir une colonne 'URL du profil'")
    
    logger.info(f"Démarrage enrichissement de {len(df)} profils")
    
    client = FullEnrichAPI(api_key)
    
    # Créer les nouvelles colonnes
    df['Email Pro'] = ''
    df['Email Perso'] = ''
    df['Téléphone'] = ''
    df['Entreprise (vérifiée)'] = ''
    df['Poste (vérifié)'] = ''
    df['Statut Enrichissement'] = ''
    
    total = len(df)
    enrichis = 0
    erreurs = 0
    
    for idx, row in df.iterrows():
        if status_callback:
            status_callback(f"📧 Enrichissement {idx + 1}/{total}")
        
        linkedin_url = row['URL du profil']
        
        if pd.isna(linkedin_url) or linkedin_url == '':
            df.at[idx, 'Statut Enrichissement'] = 'url_manquante'
            erreurs += 1
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Profil {idx + 1}/{total}: {linkedin_url}")
        logger.info('='*60)
        
        # Enrichir le profil
        result = client.enrich_profile(linkedin_url)
        
        # Remplir les colonnes
        df.at[idx, 'Email Pro'] = result['email_pro']
        df.at[idx, 'Email Perso'] = result['email_perso']
        df.at[idx, 'Téléphone'] = result['telephone']
        df.at[idx, 'Entreprise (vérifiée)'] = result['entreprise_verifiee']
        df.at[idx, 'Poste (vérifié)'] = result['poste_verifie']
        df.at[idx, 'Statut Enrichissement'] = result['statut']
        
        if result['success']:
            enrichis += 1
            logger.info(f"✅ Profil enrichi: {result.get('nom_complet', 'Inconnu')}")
        else:
            erreurs += 1
            logger.warning(f"❌ Échec enrichissement: {result['statut']}")
        
        if progress_callback:
            progress_callback((idx + 1) / total)
        
        # Petite pause entre chaque profil
        if idx < total - 1:  # Pas de pause après le dernier
            time.sleep(1)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"RÉSUMÉ: {enrichis}/{total} profils enrichis, {erreurs} erreurs")
    logger.info('='*60)
    
    return df

    """Client pour l'API FullEnrich"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # URL corrigée - FullEnrich utilise app.fullenrich.com
        self.base_url = "https://app.fullenrich.com/api/v1"
        self.headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        logger.info(f"FullEnrich API initialisée avec base_url: {self.base_url}")
    
    def enrich_profile(self, linkedin_url: str) -> dict:
        """
        Enrichit un profil LinkedIn avec FullEnrich
        
        Args:
            linkedin_url: URL du profil LinkedIn
            
        Returns:
            dict avec les informations enrichies (emails, téléphone, etc.)
        """
        try:
            # Nettoyer l'URL LinkedIn
            clean_url = linkedin_url.split('?')[0].strip()
            
            logger.info(f"Appel FullEnrich pour: {clean_url}")
            
            # Essayer plusieurs endpoints possibles
            endpoints = [
                "/enrich/person",
                "/waterfall/enrich", 
                "/enrichment",
                "/v1/enrich"
            ]
            
            # Essayer chaque endpoint jusqu'à trouver le bon
            for endpoint in endpoints:
                # Payload FullEnrich
                payload = {
                    "linkedin_url": clean_url
                }
                
                full_url = f"{self.base_url}{endpoint}"
                logger.info(f"Test endpoint: {full_url}")
                
                response = requests.post(
                    full_url,
                    headers=self.headers,
                    json=payload,
                    timeout=60
                )
                
                logger.info(f"Réponse: Status {response.status_code}")
                logger.info(f"Body: {response.text[:300]}")
                
                # Si on a une erreur 404 "Unknown api path", essayer le prochain endpoint
                if response.status_code == 404:
                    try:
                        error_data = response.json()
                        if error_data.get('code') == 'error.api.not_found':
                            continue  # Essayer le prochain endpoint
                    except:
                        pass
                
                # Si on a un autre code (200, 401, 429, etc.), c'est le bon endpoint
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Endpoint trouvé: {endpoint}")
                    logger.info(f"Données reçues: {str(data)[:200]}...")
                    
                    # Extraire les données selon la structure de réponse
                    # Essayer plusieurs structures possibles
                    person = data.get('person', data.get('data', data))
                    
                    # Extraire les emails
                    emails = person.get('emails', person.get('email', []))
                    if isinstance(emails, str):
                        emails = [emails]
                    
                    email_pro = ''
                    email_perso = ''
                    
                    for email_obj in emails:
                        if isinstance(email_obj, dict):
                            email_addr = email_obj.get('email', email_obj.get('value', ''))
                            email_type = email_obj.get('type', '')
                            
                            if 'work' in email_type.lower() or 'professional' in email_type.lower():
                                email_pro = email_addr
                            elif 'personal' in email_type.lower():
                                email_perso = email_addr
                            elif not email_pro:
                                email_pro = email_addr
                        elif isinstance(email_obj, str) and '@' in email_obj:
                            if not email_pro:
                                email_pro = email_obj
                            elif not email_perso:
                                email_perso = email_obj
                    
                    # Extraire les téléphones
                    phones = person.get('phones', person.get('phoneNumbers', person.get('phone', [])))
                    if isinstance(phones, str):
                        phones = [phones]
                    
                    telephone = ''
                    if phones:
                        if isinstance(phones[0], dict):
                            telephone = phones[0].get('number', phones[0].get('value', ''))
                        elif isinstance(phones[0], str):
                            telephone = phones[0]
                    
                    # Extraire entreprise et poste
                    company = person.get('company', person.get('organization', person.get('currentCompany', {})))
                    if isinstance(company, dict):
                        company_name = company.get('name', '')
                    else:
                        company_name = str(company) if company else ''
                    
                    job_title = person.get('title', person.get('jobTitle', person.get('position', '')))
                    
                    return {
                        'success': True,
                        'email_pro': email_pro,
                        'email_perso': email_perso,
                        'telephone': telephone,
                        'entreprise_verifiee': company_name,
                        'poste_verifie': job_title,
                        'statut': 'enrichi',
                        'linkedin_url': clean_url,
                        'nom_complet': person.get('fullName', person.get('name', ''))
                    }
                    
                elif response.status_code == 401 or response.status_code == 403:
                    logger.error(f"Authentification échouée: {response.status_code} - {response.text}")
                    return {
                        'success': False,
                        'email_pro': '',
                        'email_perso': '',
                        'telephone': '',
                        'entreprise_verifiee': '',
                        'poste_verifie': '',
                        'statut': 'api_key_invalide',
                        'linkedin_url': clean_url,
                        'nom_complet': ''
                    }
                    
                elif response.status_code == 429:
                    logger.warning("Rate limit atteint, pause de 60 secondes")
                    time.sleep(60)
                    return self.enrich_profile(linkedin_url)
                    
                elif response.status_code == 404:
                    # Si 404 mais pas "Unknown api path", c'est probablement "profil non trouvé"
                    logger.warning(f"Profil non trouvé (404): {clean_url}")
                    return {
                        'success': False,
                        'email_pro': '',
                        'email_perso': '',
                        'telephone': '',
                        'entreprise_verifiee': '',
                        'poste_verifie': '',
                        'statut': 'non_trouve',
                        'linkedin_url': clean_url,
                        'nom_complet': ''
                    }
            
            # Si aucun endpoint n'a fonctionné
            logger.error(f"Aucun endpoint valide trouvé. Essayé: {endpoints}")
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': 'endpoint_inconnu',
                'linkedin_url': clean_url,
                'nom_complet': ''
            }
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Erreur de connexion: {e}")
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': 'erreur_connexion',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }
        except requests.exceptions.Timeout:
            logger.error("Timeout lors de l'appel à FullEnrich")
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': 'timeout',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement: {e}", exc_info=True)
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': f'erreur: {str(e)[:50]}',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }
        """
        Enrichit un profil LinkedIn avec FullEnrich
        
        Args:
            linkedin_url: URL du profil LinkedIn
            
        Returns:
            dict avec les informations enrichies (emails, téléphone, etc.)
        """
        try:
            # Nettoyer l'URL LinkedIn
            clean_url = linkedin_url.split('?')[0].strip()
            
            logger.info(f"Appel FullEnrich pour: {clean_url}")
            
            # Appel à l'API FullEnrich - endpoint /person/enrich
            payload = {
                "linkedin_url": clean_url
            }
            
            logger.info(f"URL complète: {self.base_url}/person/enrich")
            logger.info(f"Headers: {self.headers}")
            
            response = requests.post(
                f"{self.base_url}/person/enrich",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            logger.info(f"Réponse FullEnrich: Status {response.status_code}")
            logger.info(f"Réponse body: {response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Données reçues: {str(data)[:200]}...")
                
                # Structure de réponse FullEnrich
                person = data.get('person', {})
                
                # Extraire les emails
                emails = person.get('emails', [])
                email_pro = ''
                email_perso = ''
                
                for email_obj in emails:
                    if isinstance(email_obj, dict):
                        email_addr = email_obj.get('email', email_obj.get('value', ''))
                        email_type = email_obj.get('type', '')
                        
                        if email_type == 'professional' or email_type == 'work':
                            email_pro = email_addr
                        elif email_type == 'personal':
                            email_perso = email_addr
                    elif isinstance(email_obj, str):
                        # Si c'est juste une liste de strings
                        if not email_pro:
                            email_pro = email_obj
                        elif not email_perso:
                            email_perso = email_obj
                
                # Extraire les téléphones
                phones = person.get('phones', person.get('phoneNumbers', []))
                telephone = ''
                if phones:
                    if isinstance(phones[0], dict):
                        telephone = phones[0].get('number', phones[0].get('value', ''))
                    elif isinstance(phones[0], str):
                        telephone = phones[0]
                
                # Extraire entreprise et poste
                company = person.get('company', person.get('organization', {}))
                if isinstance(company, dict):
                    company_name = company.get('name', '')
                else:
                    company_name = str(company) if company else ''
                
                job_title = person.get('title', person.get('jobTitle', ''))
                
                return {
                    'success': True,
                    'email_pro': email_pro,
                    'email_perso': email_perso,
                    'telephone': telephone,
                    'entreprise_verifiee': company_name,
                    'poste_verifie': job_title,
                    'statut': 'enrichi',
                    'linkedin_url': clean_url,
                    'nom_complet': person.get('fullName', person.get('name', ''))
                }
            elif response.status_code == 404:
                logger.warning(f"Profil non trouvé: {clean_url}")
                return {
                    'success': False,
                    'email_pro': '',
                    'email_perso': '',
                    'telephone': '',
                    'entreprise_verifiee': '',
                    'poste_verifie': '',
                    'statut': 'non_trouve',
                    'linkedin_url': clean_url,
                    'nom_complet': ''
                }
            elif response.status_code == 401 or response.status_code == 403:
                logger.error(f"Authentification échouée: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'email_pro': '',
                    'email_perso': '',
                    'telephone': '',
                    'entreprise_verifiee': '',
                    'poste_verifie': '',
                    'statut': 'api_key_invalide',
                    'linkedin_url': clean_url,
                    'nom_complet': ''
                }
            elif response.status_code == 429:
                logger.warning("Rate limit atteint, pause de 60 secondes")
                time.sleep(60)
                return self.enrich_profile(linkedin_url)
            else:
                logger.error(f"Erreur API FullEnrich: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'email_pro': '',
                    'email_perso': '',
                    'telephone': '',
                    'entreprise_verifiee': '',
                    'poste_verifie': '',
                    'statut': f'erreur_{response.status_code}',
                    'linkedin_url': clean_url,
                    'nom_complet': ''
                }
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Erreur de connexion: {e}")
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': 'erreur_connexion',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }
        except requests.exceptions.Timeout:
            logger.error("Timeout lors de l'appel à FullEnrich")
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': 'timeout',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement: {e}", exc_info=True)
            return {
                'success': False,
                'email_pro': '',
                'email_perso': '',
                'telephone': '',
                'entreprise_verifiee': '',
                'poste_verifie': '',
                'statut': f'erreur: {str(e)[:50]}',
                'linkedin_url': linkedin_url,
                'nom_complet': ''
            }


def enrich_profiles(df: pd.DataFrame, api_key: str, 
                   progress_callback=None, status_callback=None) -> pd.DataFrame:
    """
    Enrichit un DataFrame de profils LinkedIn avec FullEnrich
    
    Args:
        df: DataFrame contenant une colonne 'URL du profil'
        api_key: Clé API FullEnrich
        progress_callback: Fonction de callback pour la progression
        status_callback: Fonction de callback pour le statut
        
    Returns:
        DataFrame enrichi avec les nouvelles colonnes
    """
    
    if 'URL du profil' not in df.columns:
        raise ValueError("Le DataFrame doit contenir une colonne 'URL du profil'")
    
    logger.info(f"Démarrage enrichissement de {len(df)} profils")
    
    client = FullEnrichAPI(api_key)
    
    # Créer les nouvelles colonnes
    df['Email Pro'] = ''
    df['Email Perso'] = ''
    df['Téléphone'] = ''
    df['Entreprise (vérifiée)'] = ''
    df['Poste (vérifié)'] = ''
    df['Statut Enrichissement'] = ''
    
    total = len(df)
    enrichis = 0
    erreurs = 0
    
    for idx, row in df.iterrows():
        if status_callback:
            status_callback(f"📧 Enrichissement {idx + 1}/{total}")
        
        linkedin_url = row['URL du profil']
        
        if pd.isna(linkedin_url) or linkedin_url == '':
            df.at[idx, 'Statut Enrichissement'] = 'url_manquante'
            erreurs += 1
            continue
        
        logger.info(f"Enrichissement {idx + 1}/{total}: {linkedin_url}")
        
        # Enrichir le profil
        result = client.enrich_profile(linkedin_url)
        
        # Remplir les colonnes
        df.at[idx, 'Email Pro'] = result['email_pro']
        df.at[idx, 'Email Perso'] = result['email_perso']
        df.at[idx, 'Téléphone'] = result['telephone']
        df.at[idx, 'Entreprise (vérifiée)'] = result['entreprise_verifiee']
        df.at[idx, 'Poste (vérifié)'] = result['poste_verifie']
        df.at[idx, 'Statut Enrichissement'] = result['statut']
        
        if result['success']:
            enrichis += 1
            logger.info(f"✅ Profil enrichi: {result.get('nom_complet', 'Inconnu')}")
        else:
            erreurs += 1
            logger.warning(f"❌ Échec enrichissement: {result['statut']}")
        
        if progress_callback:
            progress_callback((idx + 1) / total)
        
        # Pause pour éviter le rate limiting
        time.sleep(2)
    
    logger.info(f"Enrichissement terminé: {enrichis}/{total} profils enrichis, {erreurs} erreurs")
    
    return df