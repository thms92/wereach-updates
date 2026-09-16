# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from config import ScraperConfig
from logger import logger


class DatabaseManager:
    """Gestion de la base de données SQLite pour les profils LinkedIn"""

    def __init__(self, db_file: str = None):
        self.db_file = db_file or ScraperConfig.DATABASE_FILE
        self.init_database()

    def init_database(self):
        """Initialise la base de données avec les tables nécessaires"""
        try:
            import os
            parent = os.path.dirname(self.db_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            # Table des profils
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT NOT NULL,
                    poste TEXT,
                    entreprise TEXT,
                    ecole TEXT,
                    localisation TEXT,
                    nb_connexions TEXT,
                    url TEXT UNIQUE NOT NULL,
                    photo_url TEXT,
                    resume TEXT,
                    date_scraping TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    derniere_mise_a_jour TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des invitations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id INTEGER NOT NULL,
                    date_envoi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_personnalise TEXT,
                    statut TEXT DEFAULT 'envoyee',
                    date_acceptation TIMESTAMP,
                    FOREIGN KEY (profile_id) REFERENCES profiles(id)
                )
            """)

            # Table des recherches
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recherches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    entreprise TEXT,
                    ecole TEXT,
                    nb_profils_trouves INTEGER,
                    nb_invitations_envoyees INTEGER,
                    date_recherche TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    duree_secondes INTEGER,
                    erreurs TEXT
                )
            """)

            # Index pour performances
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_url ON profiles(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_ecole ON profiles(ecole)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invitations_statut ON invitations(statut)")

            # Migration douce : colonne date_message (envoi du message post-acceptation)
            try:
                cursor.execute("ALTER TABLE invitations ADD COLUMN date_message TIMESTAMP")
            except Exception:
                pass  # colonne déjà présente

            conn.commit()
            conn.close()
            logger.info("Base de données initialisée avec succès")

        except Exception as e:
            logger.error(f"Erreur initialisation DB: {e}")

    def ajouter_profil(self, nom: str, poste: str, entreprise: str,
                       ecole: str, url: str, localisation: str = "",
                       nb_connexions: str = "", photo_url: str = "",
                       resume: str = "") -> Optional[int]:
        """Ajoute un profil à la base de données"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR IGNORE INTO profiles
                (nom, poste, entreprise, ecole, url, localisation, nb_connexions, photo_url, resume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (nom, poste, entreprise, ecole, url, localisation, nb_connexions, photo_url, resume))

            profile_id = cursor.lastrowid

            # Si le profil existait déjà, récupérer son ID
            if profile_id == 0:
                cursor.execute("SELECT id FROM profiles WHERE url = ?", (url,))
                result = cursor.fetchone()
                if result:
                    profile_id = result[0]
                    # Mettre à jour la date de dernière mise à jour
                    cursor.execute("""
                        UPDATE profiles
                        SET derniere_mise_a_jour = CURRENT_TIMESTAMP,
                            nom = ?, poste = ?, entreprise = ?, ecole = ?,
                            localisation = ?, nb_connexions = ?
                        WHERE id = ?
                    """, (nom, poste, entreprise, ecole, localisation, nb_connexions, profile_id))

            conn.commit()
            conn.close()
            return profile_id

        except Exception as e:
            logger.error(f"Erreur ajout profil: {e}")
            return None

    def ajouter_invitation(self, profile_id: int, message: str = "") -> bool:
        """Enregistre une invitation envoyée"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO invitations (profile_id, message_personnalise, statut)
                VALUES (?, ?, 'envoyee')
            """, (profile_id, message))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Erreur ajout invitation: {e}")
            return False

    def profil_existe(self, url: str) -> bool:
        """Vérifie si un profil existe déjà"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM profiles WHERE url = ?", (url,))
            count = cursor.fetchone()[0]

            conn.close()
            return count > 0

        except Exception as e:
            logger.error(f"Erreur vérification profil: {e}")
            return False

    def invitation_envoyee(self, url: str) -> bool:
        """Vérifie si une invitation a déjà été envoyée à ce profil"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) FROM invitations i
                JOIN profiles p ON i.profile_id = p.id
                WHERE p.url = ?
            """, (url,))

            count = cursor.fetchone()[0]
            conn.close()
            return count > 0

        except Exception as e:
            logger.error(f"Erreur vérification invitation: {e}")
            return False

    # ------------------------------------------------------------------
    # Suivi des acceptations & messages (page "Messages")
    # ------------------------------------------------------------------
    def invitations_en_attente(self) -> List[Dict]:
        """Profils invités dont l'invitation est encore 'envoyee' (pas encore acceptée)."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.url, p.nom, p.poste, p.entreprise
                FROM invitations i JOIN profiles p ON i.profile_id = p.id
                WHERE i.statut = 'envoyee'
                ORDER BY i.date_envoi ASC
            """)
            rows = cursor.fetchall()
            conn.close()
            return [{"url": r[0], "nom": r[1], "poste": r[2], "entreprise": r[3]} for r in rows]
        except Exception as e:
            logger.error(f"Erreur invitations_en_attente: {e}")
            return []

    def marquer_acceptee(self, url: str) -> bool:
        """Passe l'invitation d'un profil au statut 'acceptee'."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE invitations SET statut = 'acceptee', date_acceptation = CURRENT_TIMESTAMP
                WHERE statut = 'envoyee' AND profile_id = (SELECT id FROM profiles WHERE url = ?)
            """, (url,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erreur marquer_acceptee: {e}")
            return False

    def acceptees_non_messagees(self) -> List[Dict]:
        """Profils ayant accepté mais pas encore messagés."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.url, p.nom, p.poste, p.entreprise, i.date_acceptation
                FROM invitations i JOIN profiles p ON i.profile_id = p.id
                WHERE i.statut = 'acceptee' AND i.date_message IS NULL
                ORDER BY i.date_acceptation DESC
            """)
            rows = cursor.fetchall()
            conn.close()
            return [{"url": r[0], "nom": r[1], "poste": r[2], "entreprise": r[3],
                     "date_acceptation": r[4]} for r in rows]
        except Exception as e:
            logger.error(f"Erreur acceptees_non_messagees: {e}")
            return []

    def marquer_messagee(self, url: str) -> bool:
        """Marque le message comme envoyé (date_message) pour un profil accepté."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE invitations SET date_message = CURRENT_TIMESTAMP
                WHERE statut = 'acceptee' AND profile_id = (SELECT id FROM profiles WHERE url = ?)
            """, (url,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erreur marquer_messagee: {e}")
            return False

    def get_statistiques(self) -> Dict:
        """Récupère les statistiques globales"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            stats = {}

            # Total profils
            cursor.execute("SELECT COUNT(*) FROM profiles")
            stats['total_profils'] = cursor.fetchone()[0]

            # Total invitations
            cursor.execute("SELECT COUNT(*) FROM invitations")
            stats['total_invitations'] = cursor.fetchone()[0]

            # Invitations aujourd'hui
            cursor.execute("""
                SELECT COUNT(*) FROM invitations
                WHERE DATE(date_envoi) = DATE('now')
            """)
            stats['invitations_aujourdhui'] = cursor.fetchone()[0]

            # Profils par école
            cursor.execute("""
                SELECT ecole, COUNT(*)
                FROM profiles
                WHERE ecole != ''
                GROUP BY ecole
            """)
            stats['par_ecole'] = dict(cursor.fetchall())

            # Dernière recherche
            cursor.execute("""
                SELECT keyword, date_recherche, nb_profils_trouves
                FROM recherches
                ORDER BY date_recherche DESC
                LIMIT 1
            """)
            derniere = cursor.fetchone()
            if derniere:
                stats['derniere_recherche'] = {
                    'keyword': derniere[0],
                    'date': derniere[1],
                    'nb_profils': derniere[2]
                }

            conn.close()
            return stats

        except Exception as e:
            logger.error(f"Erreur récupération stats: {e}")
            return {}

    def sauvegarder_recherche(self, keyword: str, entreprise: str, ecole: str,
                             nb_profils: int, nb_invitations: int,
                             duree: int, erreurs: List[str] = None):
        """Enregistre une recherche effectuée"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            erreurs_str = "\n".join(erreurs) if erreurs else ""

            cursor.execute("""
                INSERT INTO recherches
                (keyword, entreprise, ecole, nb_profils_trouves,
                 nb_invitations_envoyees, duree_secondes, erreurs)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (keyword, entreprise, ecole, nb_profils, nb_invitations, duree, erreurs_str))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Erreur sauvegarde recherche: {e}")

    def get_tous_profils(self, limit: int = 1000) -> List[Dict]:
        """Récupère tous les profils"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT p.*,
                       CASE WHEN i.id IS NOT NULL THEN 'Oui' ELSE 'Non' END as invitation_envoyee
                FROM profiles p
                LEFT JOIN invitations i ON p.id = i.profile_id
                ORDER BY p.date_scraping DESC
                LIMIT ?
            """, (limit,))

            columns = [desc[0] for desc in cursor.description]
            profils = [dict(zip(columns, row)) for row in cursor.fetchall()]

            conn.close()
            return profils

        except Exception as e:
            logger.error(f"Erreur récupération profils: {e}")
            return []

