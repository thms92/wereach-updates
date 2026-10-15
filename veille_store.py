# -*- coding: utf-8 -*-
"""Stockage de la veille entreprises, dans la base SQLite de l'utilisateur.

Même fichier que les profils et les invitations : un contact trouvé par la
veille est un profil comme un autre, et la sauvegarde de la base sauvegarde
tout. Les tables sont créées par `CREATE TABLE IF NOT EXISTS`, comme celles
de `database.py` : aucune migration, rien de détruit chez qui a déjà une base.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date

from utils.browsemap import normaliser_url

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entreprises_suivies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    nom_cle TEXT NOT NULL UNIQUE,
    url_linkedin TEXT,
    company_id TEXT,
    etat TEXT NOT NULL DEFAULT 'a_identifier',
    ajoutee_le TEXT NOT NULL,
    derniere_veille TEXT,
    curseur_page INTEGER NOT NULL DEFAULT 0,
    signature_familles TEXT
);
CREATE TABLE IF NOT EXISTS fiche_entreprise (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id INTEGER NOT NULL,
    champ TEXT NOT NULL,
    valeur TEXT NOT NULL,
    source TEXT NOT NULL,
    precedente TEXT,
    releve_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts_veille (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entreprise_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    nom TEXT,
    poste TEXT,
    famille TEXT,
    degre TEXT,
    decouvert_le TEXT NOT NULL,
    nouveau INTEGER NOT NULL,
    UNIQUE (entreprise_id, url)
);
CREATE TABLE IF NOT EXISTS fiche_lectures (
    entreprise_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    lue_le TEXT NOT NULL,
    PRIMARY KEY (entreprise_id, source)
);
CREATE TABLE IF NOT EXISTS coordonnees_contacts (
    url TEXT PRIMARY KEY,
    email TEXT,
    telephone TEXT,
    partage TEXT NOT NULL,
    releve_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS essais_coordonnees (
    url TEXT PRIMARY KEY,
    essai_le TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passages_veille (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debut TEXT NOT NULL,
    fin TEXT NOT NULL,
    entreprises TEXT NOT NULL,
    pages INTEGER NOT NULL,
    cause TEXT NOT NULL,
    erreurs TEXT NOT NULL
);
"""


# Les changements de fiche qui méritent le récap. Les autres (nombre de
# membres, description, constat de recherche, motif de rapprochement) bougent
# à chaque relecture sans rien dire de l'entreprise : ils noieraient le reste.
CHANGEMENTS_SIGNALES = {("linkedin", "taille"), ("linkedin", "siege"), ("linkedin", "secteur"),
                        ("annuaire", "dirigeants"), ("annuaire", "effectif")}

# Coordonnées d'une personne relues au plus tous les 90 jours : elles changent
# peu, et chaque lecture coûte une page LinkedIn du budget.
RELECTURE_COORDONNEES_JOURS = 90
# Après un essai manqué (lien absent, fenêtre fermée) : assez long pour ne pas
# repayer une page à chaque passage, assez court pour une panne passagère.
NOUVEL_ESSAI_COORDONNEES_JOURS = 7

# Degré lu sur une carte de résultats, quelle que soit la langue de LinkedIn.
_DEGRES = {"1er": "1er", "1st": "1er", "2e": "2e", "2nd": "2e", "3e": "3e", "3rd": "3e"}


def normaliser_degre(brut) -> str:
    """« · 1er », « 1st », « 3e+ » → « 1er » / « 2e » / « 3e » ; inconnu → ""."""
    t = (brut or "").replace("·", " ").replace("•", " ").replace("+", " ").strip().lower()
    return _DEGRES.get(t.split()[0] if t else "", "")


# Passages refusés avant tout travail : ils ne remplacent pas le résumé du
# dernier vrai passage, que la personne a encore besoin de lire.
_CAUSES_SANS_PASSAGE = ("occupe", "rien_a_faire")


def _cle_nom(nom: str) -> str:
    return " ".join((nom or "").split()).lower()


class VeilleStore:
    def __init__(self, db_file: str):
        self.db_file = db_file
        with self._con() as con:
            con.executescript(_SCHEMA)

    @contextmanager
    def _con(self):
        # `with sqlite3.connect()` valide mais ne ferme pas : le store est rouvert
        # à chaque rechargement de Streamlit, les connexions s'accumuleraient.
        con = sqlite3.connect(self.db_file)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    # ── Entreprises suivies ────────────────────────────────────────────

    def ajouter_entreprise(self, nom: str, quand: str, url_linkedin=None) -> int:
        nom = " ".join((nom or "").split())
        with self._con() as con:
            ligne = con.execute("SELECT id FROM entreprises_suivies WHERE nom_cle = ?",
                                (_cle_nom(nom),)).fetchone()
            if ligne:
                if url_linkedin:
                    self._attacher(con, ligne["id"], url_linkedin)
                return ligne["id"]
            cur = con.execute(
                "INSERT INTO entreprises_suivies (nom, nom_cle, url_linkedin, ajoutee_le) VALUES (?, ?, ?, ?)",
                (nom, _cle_nom(nom), url_linkedin, quand))
            return cur.lastrowid

    @staticmethod
    def _attacher(con, entreprise_id, url_linkedin):
        # Un nouveau lien annule l'identification passée : l'identifiant et
        # l'état venaient d'une autre page (homonyme, page illisible). Le
        # prochain passage relira la page collée.
        con.execute("""UPDATE entreprises_suivies
                       SET url_linkedin = ?, etat = 'a_identifier', company_id = NULL
                       WHERE id = ? AND COALESCE(url_linkedin, '') != ?""",
                    (url_linkedin, entreprise_id, url_linkedin))

    def attacher_lien(self, entreprise_id, url_linkedin: str) -> None:
        """Colle le lien de sa page LinkedIn à une entreprise déjà suivie."""
        with self._con() as con:
            self._attacher(con, entreprise_id, url_linkedin)

    def renommer(self, entreprise_id, nom: str) -> bool:
        """Renomme ; False si une autre entreprise suivie porte déjà ce nom."""
        nom = " ".join((nom or "").split())
        if not nom:
            return False
        with self._con() as con:
            autre = con.execute("SELECT id FROM entreprises_suivies WHERE nom_cle = ? AND id != ?",
                                (_cle_nom(nom), entreprise_id)).fetchone()
            if autre:
                return False
            con.execute("UPDATE entreprises_suivies SET nom = ?, nom_cle = ? WHERE id = ?",
                        (nom, _cle_nom(nom), entreprise_id))
        return True

    def retirer_entreprise(self, entreprise_id: int) -> None:
        with self._con() as con:
            tables = [("fiche_entreprise", "entreprise_id"),
                      ("fiche_lectures", "entreprise_id"),
                      ("contacts_veille", "entreprise_id"),
                      ("entreprises_suivies", "id")]
            # L'actualité a été retirée de la veille, mais les bases créées par
            # une version précédente gardent leur table (jamais supprimée) :
            # on la nettoie si elle est là, sans la créer ni échouer si elle manque.
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='actualites'").fetchone():
                tables.insert(3, ("actualites", "entreprise_id"))
            for table, colonne in tables:
                con.execute(f"DELETE FROM {table} WHERE {colonne} = ?", (entreprise_id,))
            # Coordonnées et essais sont rangés par personne : on ne garde que
            # ceux d'une personne encore suivie sous une autre entreprise. Une
            # donnée personnelle sans usage ne reste pas dans la base.
            for table in ("coordonnees_contacts", "essais_coordonnees"):
                con.execute(f"DELETE FROM {table} WHERE url NOT IN (SELECT url FROM contacts_veille)")

    def entreprises(self) -> list:
        with self._con() as con:
            lignes = con.execute("""
                SELECT e.*, (SELECT COUNT(*) FROM contacts_veille c WHERE c.entreprise_id = e.id) AS nb_contacts
                FROM entreprises_suivies e ORDER BY e.nom COLLATE NOCASE""").fetchall()
        return [{k: l[k] for k in l.keys() if k != "nom_cle"} for l in lignes]

    def maj_identification(self, entreprise_id, etat, company_id=None, url_linkedin=None) -> None:
        with self._con() as con:
            con.execute("""UPDATE entreprises_suivies
                           SET etat = ?, company_id = COALESCE(?, company_id),
                               url_linkedin = COALESCE(?, url_linkedin)
                           WHERE id = ?""", (etat, company_id, url_linkedin, entreprise_id))

    def maj_curseur(self, entreprise_id, page: int, signature: str) -> None:
        with self._con() as con:
            con.execute("UPDATE entreprises_suivies SET curseur_page = ?, signature_familles = ? WHERE id = ?",
                        (page, signature, entreprise_id))

    def marquer_passage(self, entreprise_id, quand: str) -> None:
        with self._con() as con:
            con.execute("UPDATE entreprises_suivies SET derniere_veille = ? WHERE id = ?", (quand, entreprise_id))

    # ── Fiche ──────────────────────────────────────────────────────────

    def _derniere(self, con, entreprise_id, champ, source):
        return con.execute("""SELECT valeur FROM fiche_entreprise
                              WHERE entreprise_id = ? AND champ = ? AND source = ?
                              ORDER BY id DESC LIMIT 1""", (entreprise_id, champ, source)).fetchone()

    def enregistrer_fiche(self, entreprise_id, valeurs: dict, source: str, quand: str) -> list:
        """Enregistre les valeurs qui ont changé ; renvoie les champs changés.

        Une première valeur n'est pas un changement : sinon le premier passage
        sur une entreprise remplirait le récap de « nouveautés » qui n'en sont
        pas.
        """
        changes = []
        with self._con() as con:
            for champ, valeur in valeurs.items():
                valeur = (valeur or "").strip()
                if not valeur:
                    continue
                avant = self._derniere(con, entreprise_id, champ, source)
                if avant and avant["valeur"] == valeur:
                    continue
                con.execute("""INSERT INTO fiche_entreprise
                               (entreprise_id, champ, valeur, source, precedente, releve_le)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (entreprise_id, champ, valeur, source, avant["valeur"] if avant else None, quand))
                if avant:
                    changes.append(champ)
        return changes

    def fiche(self, entreprise_id) -> dict:
        with self._con() as con:
            lignes = con.execute("""SELECT champ, valeur, source, releve_le FROM fiche_entreprise
                                    WHERE entreprise_id = ? ORDER BY id""", (entreprise_id,)).fetchall()
        return {f"{l['source']}.{l['champ']}": {"valeur": l["valeur"], "source": l["source"],
                                                 "releve_le": l["releve_le"]} for l in lignes}

    def marquer_lecture(self, entreprise_id, source: str, quand: str) -> None:
        """Date de la dernière lecture réussie d'une source, valeurs changées ou non.

        `enregistrer_fiche` n'écrit que ce qui change : une fiche relue à
        l'identique ne laisserait aucune trace, et passé 30 jours la page
        « À propos » serait rechargée à chaque passage.
        """
        with self._con() as con:
            con.execute("INSERT OR REPLACE INTO fiche_lectures (entreprise_id, source, lue_le) VALUES (?, ?, ?)",
                        (entreprise_id, source, quand))

    def lectures(self, entreprise_id) -> dict:
        """{source: date de dernière lecture}."""
        with self._con() as con:
            return {l["source"]: l["lue_le"] for l in con.execute(
                "SELECT source, lue_le FROM fiche_lectures WHERE entreprise_id = ?", (entreprise_id,))}

    def age_fiche_jours(self, entreprise_id, source: str, aujourd_hui: str):
        with self._con() as con:
            l = con.execute("SELECT lue_le AS d FROM fiche_lectures WHERE entreprise_id = ? AND source = ?",
                            (entreprise_id, source)).fetchone()
            if not l:
                # Fiche relevée avant que les lectures soient datées. Le constat
                # de recherche s'écrit au passage sur les employés, pas en
                # lisant la fiche : il ne la rajeunit pas.
                l = con.execute("""SELECT MAX(releve_le) AS d FROM fiche_entreprise
                                   WHERE entreprise_id = ? AND source = ? AND champ != 'recherche'""",
                                (entreprise_id, source)).fetchone()
        if not l or not l["d"]:
            return None
        return (date.fromisoformat(aujourd_hui[:10]) - date.fromisoformat(l["d"][:10])).days

    # ── Contacts ───────────────────────────────────────────────────────

    def relier_contact(self, entreprise_id, contact: dict, famille: str, quand: str, urls_au_fichier: set) -> bool:
        """Relie un contact à l'entreprise ; True s'il est réellement nouveau.

        Nouveau = jamais relié à cette entreprise ET absent de `urls_au_fichier`,
        ensemble d'URL **canoniques** (`normaliser_url`) : le fichier contient
        des liens copiés à la main, avec leurs paramètres de suivi. L'appelant
        le normalise une fois par passage plutôt qu'à chaque contact.
        """
        url = normaliser_url(contact.get("url"))
        if url is None:
            return False
        nouveau = url not in (urls_au_fichier or ())
        with self._con() as con:
            if con.execute("SELECT 1 FROM contacts_veille WHERE entreprise_id = ? AND url = ?",
                           (entreprise_id, url)).fetchone():
                return False
            con.execute("""INSERT INTO contacts_veille
                           (entreprise_id, url, nom, poste, famille, degre, decouvert_le, nouveau)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (entreprise_id, url, contact.get("nom"), contact.get("poste"), famille,
                         contact.get("connexions") or "", quand, int(nouveau)))
        return nouveau

    def contacts(self, entreprise_id) -> list:
        with self._con() as con:
            return [dict(l) for l in con.execute(
                "SELECT * FROM contacts_veille WHERE entreprise_id = ? ORDER BY famille, nom",
                (entreprise_id,)).fetchall()]

    def nouveautes_depuis(self, quand) -> dict:
        borne = quand or ""
        with self._con() as con:
            contacts = [dict(l) for l in con.execute("""
                SELECT c.*, e.nom AS entreprise FROM contacts_veille c
                JOIN entreprises_suivies e ON e.id = c.entreprise_id
                WHERE c.nouveau = 1 AND c.decouvert_le > ?
                ORDER BY e.nom COLLATE NOCASE, c.famille, c.nom""", (borne,)).fetchall()]
            changements = [{"entreprise": l["entreprise"], "champ": l["champ"], "source": l["source"],
                            "avant": l["precedente"], "apres": l["valeur"], "releve_le": l["releve_le"]}
                           for l in con.execute("""
                SELECT f.*, e.nom AS entreprise FROM fiche_entreprise f
                JOIN entreprises_suivies e ON e.id = f.entreprise_id
                WHERE f.precedente IS NOT NULL AND f.releve_le > ?
                ORDER BY e.nom COLLATE NOCASE""", (borne,)).fetchall()
                           if (l["source"], l["champ"]) in CHANGEMENTS_SIGNALES]
        return {"contacts": contacts, "changements": changements}

    def maj_degre(self, entreprise_id, url, degre) -> None:
        """Degré de relation lu sur la carte de résultats.

        Un degré illisible n'efface pas celui qu'on connaît : une carte mal
        lue ne doit pas faire oublier qu'une personne est en relation.
        """
        url, degre = normaliser_url(url), normaliser_degre(degre)
        if not url or not degre:
            return
        with self._con() as con:
            con.execute("UPDATE contacts_veille SET degre = ? WHERE entreprise_id = ? AND url = ?",
                        (degre, entreprise_id, url))

    # ── Coordonnées des personnes ──────────────────────────────────────

    def enregistrer_coordonnees(self, url, email, telephone, quand: str) -> None:
        """Coordonnées lues dans la fenêtre « Coordonnées » d'un profil.

        Ni email ni téléphone : la fenêtre a été lue et la personne ne partage
        rien — c'est un constat daté (`partage = "rien"`), pas une absence de
        lecture, et il n'est pas relu avant 90 jours.
        """
        url = normaliser_url(url)
        if not url:
            return
        email, telephone = (email or "").strip(), (telephone or "").strip()
        partage = "oui" if email or telephone else "rien"
        with self._con() as con:
            con.execute("""INSERT OR REPLACE INTO coordonnees_contacts (url, email, telephone, partage, releve_le)
                           VALUES (?, ?, ?, ?, ?)""", (url, email, telephone, partage, quand))
            con.execute("DELETE FROM essais_coordonnees WHERE url = ?", (url,))

    def noter_echec_coordonnees(self, url, quand: str) -> None:
        """Essai manqué : la fenêtre n'a pas pu être lue (lien absent, fermée…).

        À part des coordonnées : ce n'est pas une lecture (rien à afficher,
        « non lu »), mais sans date, cette personne repasserait en tête à
        chaque passage et prendrait les places des autres.
        """
        url = normaliser_url(url)
        if url:
            with self._con() as con:
                con.execute("INSERT OR REPLACE INTO essais_coordonnees (url, essai_le) VALUES (?, ?)", (url, quand))

    def coordonnees(self, url):
        url = normaliser_url(url)
        with self._con() as con:
            l = con.execute("SELECT * FROM coordonnees_contacts WHERE url = ?", (url,)).fetchone()
        return dict(l) if l else None

    def _urls_invitation_acceptee(self, con) -> set:
        # Canonisées ici : `profiles.url` garde le lien tel qu'il a été copié
        # (paramètres de suivi, casse), une égalité SQL manquerait la personne.
        try:
            brutes = con.execute("""SELECT p.url FROM invitations i JOIN profiles p ON p.id = i.profile_id
                                    WHERE i.statut = 'acceptee'""").fetchall()
        except sqlite3.OperationalError:
            return set()  # base sans table d'invitations : personne n'a accepté
        return {u for u in (normaliser_url(l[0]) for l in brutes) if u}

    def contacts_en_relation(self, entreprise_id, aujourd_hui: str,
                             max_age_jours: int = RELECTURE_COORDONNEES_JOURS) -> list:
        """Contacts en relation dont les coordonnées sont à lire.

        En relation = 1er degré lu sur la carte, ou invitation acceptée : seuls
        ceux-là montrent leurs coordonnées, une visite à quelqu'un d'autre
        coûterait une page pour rien.

        Ordre : jamais essayés (jamais lus, puis lus il y a longtemps), puis
        ceux dont le dernier essai a échoué, le plus ancien d'abord — un échec
        répété ne doit pas occuper les places à chaque passage.
        """
        jour = date.fromisoformat(aujourd_hui[:10])
        age = lambda d: (jour - date.fromisoformat(d[:10])).days
        with self._con() as con:
            acceptees = self._urls_invitation_acceptee(con)
            lignes = [dict(l) for l in con.execute("""
                SELECT c.*, k.releve_le AS coordonnees_le, e.essai_le AS echec_le FROM contacts_veille c
                LEFT JOIN coordonnees_contacts k ON k.url = c.url
                LEFT JOIN essais_coordonnees e ON e.url = c.url
                WHERE c.entreprise_id = ? ORDER BY c.id""", (entreprise_id,)).fetchall()]
        retenus = []
        for c in lignes:
            if normaliser_degre(c["degre"]) != "1er" and c["url"] not in acceptees:
                continue
            lu, echec = c.pop("coordonnees_le"), c.pop("echec_le")
            if lu and age(lu) < max_age_jours:
                continue
            if echec and age(echec) < NOUVEL_ESSAI_COORDONNEES_JOURS:
                continue
            retenus.append(((1, echec) if echec else (0, lu or ""), c))
        return [c for _, c in sorted(retenus, key=lambda r: r[0])]

    # ── Passages ───────────────────────────────────────────────────────

    def enregistrer_passage(self, debut, fin, entreprises, pages, cause, erreurs) -> None:
        with self._con() as con:
            con.execute("""INSERT INTO passages_veille (debut, fin, entreprises, pages, cause, erreurs)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (debut, fin, json.dumps(entreprises, ensure_ascii=False), pages, cause,
                         json.dumps(erreurs, ensure_ascii=False)))

    def dernier_passage(self):
        """Le dernier passage réel ; un refus (session occupée, rien à faire) n'en est pas un."""
        trous = ",".join("?" * len(_CAUSES_SANS_PASSAGE))
        with self._con() as con:
            l = con.execute(f"SELECT * FROM passages_veille WHERE cause NOT IN ({trous}) ORDER BY id DESC LIMIT 1",
                            _CAUSES_SANS_PASSAGE).fetchone()
        if not l:
            return None
        p = dict(l)
        p["entreprises"] = json.loads(p["entreprises"])
        p["erreurs"] = json.loads(p["erreurs"])
        return p

    # ── Fichier existant ───────────────────────────────────────────────

    def societes_du_fichier(self) -> list:
        """Sociétés distinctes des profils déjà récupérés, pour proposer l'ajout."""
        try:
            with self._con() as con:
                brutes = [l[0] for l in con.execute(
                    "SELECT entreprise FROM profiles WHERE entreprise IS NOT NULL AND TRIM(entreprise) != ''")]
        except sqlite3.OperationalError:
            return []
        vues = {}
        for nom in brutes:
            vues.setdefault(_cle_nom(nom), nom.strip())
        return sorted(vues.values(), key=str.lower)
