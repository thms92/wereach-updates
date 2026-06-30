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

            # Table des templates de recherche
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom TEXT UNIQUE NOT NULL,
                    keyword TEXT,
                    entreprise TEXT,
                    ecoles TEXT,
                    message_invitation TEXT,
                    nb_profils INTEGER DEFAULT 10,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index pour performances
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_url ON profiles(url)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_ecole ON profiles(ecole)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invitations_statut ON invitations(statut)")

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

    def sauvegarder_template(self, nom: str, keyword: str, entreprise: str,
                           ecoles: str, message: str, nb_profils: int) -> bool:
        """Sauvegarde un template de recherche"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO templates
                (nom, keyword, entreprise, ecoles, message_invitation, nb_profils)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nom, keyword, entreprise, ecoles, message, nb_profils))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Erreur sauvegarde template: {e}")
            return False

    def get_templates(self) -> List[Dict]:
        """Récupère tous les templates"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM templates ORDER BY date_creation DESC")

            columns = [desc[0] for desc in cursor.description]
            templates = [dict(zip(columns, row)) for row in cursor.fetchall()]

            conn.close()
            return templates

        except Exception as e:
            logger.error(f"Erreur récupération templates: {e}")
            return []
