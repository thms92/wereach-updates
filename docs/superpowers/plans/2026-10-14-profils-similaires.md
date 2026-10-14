# Profils similaires — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Partir de l'URL d'un profil réussi pour obtenir, filtrée, la liste des profils voisins que LinkedIn propose lui-même — puis la confier à la chaîne de récupération et d'invitation déjà en service.

**Architecture :** La fonctionnalité ne scrape pas et n'invite pas. Elle fabrique une liste d'URLs en lisant le panneau browsemap de LinkedIn (`/in/<vanity>/overlay/browsemap-recommendations/`), puis la passe à `run_url_scraper`, qui fait déjà les deux dans l'onglet Par URLs. Le code nouveau se partage en trois couches : un module pur (`utils/browsemap.py`) qui normalise les URLs et filtre, testable sans navigateur ; un extracteur JavaScript dans `utils/dom_selectors.py` ; une méthode de navigation dans `scraper_v2.py` qui réutilise `_open_linkedin_page`.

**Tech Stack :** Python 3.10+, Playwright (Chromium canal `chrome`), Streamlit 1.58, SQLite, pytest, `streamlit.testing.v1.AppTest`.

**Spec :** [docs/superpowers/specs/2026-10-14-profils-similaires-design.md](../specs/2026-10-14-profils-similaires-design.md)

## Global Constraints

- **Langue :** tout code, commentaire, docstring, nom de fonction et texte à l'écran en **français**. C'est la convention du dépôt entier.
- **Commentaires :** ils expliquent **pourquoi**, jamais quoi. Chaque module et chaque fonction non triviale porte une docstring qui donne la raison d'être, pas la paraphrase du code.
- **Version visée :** `1.5.0`. Le fichier `VERSION` est la source unique, lue par `version.py`.
- **Un échec ne doit jamais être silencieux.** Le défaut corrigé en 1.4.7 — une recherche qui renvoyait zéro résultat sans rien expliquer — ne doit pas se reproduire sous une autre forme. Toute liste vide est accompagnée de son motif à l'écran.
- **Aucune écriture dans les données réelles du poste** depuis les tests : `tests/conftest.py` fournit l'isolation (`donnees_de_test_isolees`, `scraper_espion`).
- **Nommage des widgets Streamlit :** toutes les clés du nouvel onglet sont préfixées `sim_`, pour ne pas heurter celles de l'onglet Par URLs qui vit dans le même script.
- **Jamais de lancement de navigateur dans un test.** Les tests valident la logique pure et le câblage ; le navigateur se vérifie par un essai réel, documenté en Task 7.

## Review Focus

Cinq entrées que la spec implique et qu'un test doit pincer, de la plus probable à la moins :

1. **URL de profil portant des paramètres de suivi** (`…/in/jean-dupont/?miniProfileUrn=urn%3Ali%3A…`) — LinkedIn sert ses liens ainsi ; sans normalisation la même personne apparaît deux fois et le filtre « déjà en base » la laisse passer. → test en Task 1.
2. **`entreprise_reference` vaut `None`** — la page n'a pas permis de la lire. L'exclusion ne doit ni planter ni tout écarter. → test en Task 2.
3. **Toutes les suggestions écartées** — le tableau vide doit être remplacé par les motifs. Sinon on croit que le profil n'a pas de voisins. → tests en Task 2 et Task 6.
4. **Le profil de référence lui-même présent dans le panneau** — son propre lien figure dans la page ; il n'est pas une suggestion. → test en Task 4.
5. **Mot attendu saisi avec une autre casse ou des espaces** (` product `) — la comparaison doit être insensible à la casse et aux espaces de bord, sans quoi le filtre vide la liste sans raison visible. → test en Task 2.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `utils/browsemap.py` | Adressage du panneau et filtrage des suggestions. Aucune dépendance à Playwright, Streamlit ou SQLite. | Créer |
| `utils/dom_selectors.py` | `extract_browsemap_js()` — lecture du panneau dans le navigateur. | Modifier |
| `scraper_v2.py` | `recolter_browsemap_async`, `_derouler_panneau`, `_dumper_panneau`. | Modifier |
| `scraper_v2_sync.py` | `recolter_browsemap` — appel synchrone depuis Streamlit. | Modifier |
| `database.py` | `urls_connues()` — l'ensemble des URLs déjà au fichier. | Modifier |
| `app_advanced.py` | 4ᵉ onglet de la page Recherche. | Modifier |
| `tests/test_browsemap.py` | Adressage et filtrage. | Créer |
| `tests/test_recolte_browsemap.py` | Garde-fous de la couche navigateur, sans navigateur. | Créer |
| `tests/test_onglet_profils_similaires.py` | Câblage de l'onglet. | Créer |
| `NOUVEAUTES.md`, `VERSION` | Annonce à l'équipe, bump en 1.5.0. | Modifier |

La séparation qui compte : **tout ce qui décide** vit dans `utils/browsemap.py`, où un test l'atteint en une milliseconde. `scraper_v2.py` ne fait que naviguer et lire.

---

## Task 1 : Adressage du panneau

**Files:**
- Create: `utils/browsemap.py`
- Test: `tests/test_browsemap.py`

**Interfaces:**
- Consumes: rien.
- Produces: `vanity_depuis_url(url) -> str | None`, `normaliser_url(url) -> str | None`, `url_panneau(url) -> str | None`, constante `CHEMIN_PANNEAU: str`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_browsemap.py` :

```python
# -*- coding: utf-8 -*-
"""Adressage du panneau « Plus de profils pour vous » et filtrage de son contenu.

Tout ce qui est testé ici décide sans navigateur : c'est la couche où les
erreurs se paient en doublons dans le fichier et en profils écartés à tort.
"""

from utils.browsemap import (
    CHEMIN_PANNEAU,
    normaliser_url,
    url_panneau,
    vanity_depuis_url,
)

URL_SIMPLE = "https://www.linkedin.com/in/jean-dupont-12345/"


def test_le_vanity_est_extrait_d_une_url_simple():
    assert vanity_depuis_url(URL_SIMPLE) == "jean-dupont-12345"


def test_les_parametres_de_suivi_sont_ignores():
    # LinkedIn sert ses liens ainsi depuis le panneau : sans ça, la même
    # personne entre deux fois au fichier.
    url = URL_SIMPLE + "?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_un_sous_chemin_de_profil_est_ignore():
    url = "https://www.linkedin.com/in/jean-dupont-12345/details/experience/"
    assert vanity_depuis_url(url) == "jean-dupont-12345"


def test_la_casse_du_vanity_est_normalisee():
    assert vanity_depuis_url("https://www.linkedin.com/in/Jean-Dupont/") == "jean-dupont"


def test_une_page_entreprise_n_est_pas_un_profil():
    assert vanity_depuis_url("https://www.linkedin.com/company/thiga/") is None


def test_une_saisie_vide_n_est_pas_un_profil():
    assert vanity_depuis_url("") is None
    assert vanity_depuis_url(None) is None


def test_deux_liens_vers_la_meme_personne_donnent_la_meme_url():
    autre = "http://linkedin.com/in/JEAN-DUPONT-12345?trk=public_profile"
    assert normaliser_url(autre) == normaliser_url(URL_SIMPLE) == URL_SIMPLE


def test_l_url_du_panneau_se_construit_depuis_celle_du_profil():
    assert url_panneau(URL_SIMPLE) == URL_SIMPLE + CHEMIN_PANNEAU


def test_l_url_du_panneau_est_nulle_si_ce_n_est_pas_un_profil():
    assert url_panneau("https://www.linkedin.com/company/thiga/") is None
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_browsemap.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.browsemap'`

- [ ] **Step 3 : Écrire le module**

Créer `utils/browsemap.py` :

```python
# -*- coding: utf-8 -*-
"""Profils voisins d'un profil de référence : adressage et filtrage.

LinkedIn entretient pour chaque profil une liste de profils voisins — le
panneau « Plus de profils pour vous » — fondée sur la co-consultation : les
gens qui ont regardé ce profil ont aussi regardé ceux-là. C'est un signal
qu'on ne saurait pas reconstruire, puisqu'il repose sur des parcours de
navigation que LinkedIn seul observe.

Ce module ne connaît ni Playwright, ni Streamlit, ni la base : il adresse le
panneau et trie son contenu. Tout s'y teste sans navigateur.
"""

import re

# Le segment qui suit /in/ : on s'arrête au premier /, ? ou #, ce qui écarte
# d'un coup les paramètres de suivi et les sous-pages (/details/experience/).
_MOTIF_VANITY = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)

CHEMIN_PANNEAU = "overlay/browsemap-recommendations/"


def vanity_depuis_url(url):
    """Identifiant du profil dans son URL, ou None si ce n'est pas un profil.

    Minuscule à dessein : LinkedIn traite ces identifiants sans égard à la
    casse, et deux écritures du même profil doivent se reconnaître.
    """
    correspondance = _MOTIF_VANITY.search(url or "")
    if not correspondance:
        return None
    return correspondance.group(1).strip().lower() or None


def normaliser_url(url):
    """URL canonique du profil, ou None. C'est la clé de comparaison.

    Le panneau sert ses liens avec des paramètres de suivi. Sans forme
    canonique, le filtre « déjà dans ton fichier » ne reconnaît pas quelqu'un
    qui y est déjà, et la personne ressort une seconde fois.
    """
    vanity = vanity_depuis_url(url)
    if vanity is None:
        return None
    return f"https://www.linkedin.com/in/{vanity}/"


def url_panneau(url):
    """URL du panneau « Plus de profils pour vous » de ce profil, ou None.

    Le panneau est directement adressable : pas de clic à simuler, pas de
    menu à déplier.
    """
    canonique = normaliser_url(url)
    return None if canonique is None else canonique + CHEMIN_PANNEAU
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_browsemap.py -v`
Expected: PASS — 9 tests

- [ ] **Step 5 : Commit**

```bash
git add utils/browsemap.py tests/test_browsemap.py
git commit -m "feat(similaires): adressage du panneau de profils voisins"
```

---

## Task 2 : Filtrage des suggestions

**Files:**
- Modify: `utils/browsemap.py`
- Test: `tests/test_browsemap.py`

**Interfaces:**
- Consumes: `normaliser_url` (Task 1).
- Produces: `filtrer_suggestions(suggestions, urls_en_base=(), entreprise_reference=None, invitables_seulement=False, mot_intitule=None) -> tuple[list, list]`. Chaque suggestion entrante est un dict `{"nom", "url", "degre", "intitule", "invitable"}`. Chaque retenue est un **nouveau** dict, identique mais dont `url` porte la forme canonique. Chaque écartée est un nouveau dict portant en plus `"motif"`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_browsemap.py` :

```python
# --- Filtrage des suggestions --------------------------------------------

from utils.browsemap import filtrer_suggestions


def suggestion(**champs):
    """Une entrée de panneau, par défaut retenable, surchargeable au besoin."""
    base = {
        "nom": "Jean Dupont",
        "url": URL_SIMPLE,
        "degre": "2e",
        "intitule": "Product Manager, Thiga",
        "invitable": True,
    }
    base.update(champs)
    return base


def motifs(ecartees):
    return [e["motif"] for e in ecartees]


def test_une_suggestion_ordinaire_est_retenue():
    retenues, ecartees = filtrer_suggestions([suggestion()])
    assert [r["nom"] for r in retenues] == ["Jean Dupont"]
    assert ecartees == []


def test_l_url_retenue_est_canonique():
    # Ce qui sort d'ici part dans run_url_scraper : les paramètres de suivi
    # n'ont rien à y faire.
    brute = URL_SIMPLE + "?miniProfileUrn=urn%3Ali%3Afsd_profile%3AACoAAA"
    retenues, _ = filtrer_suggestions([suggestion(url=brute)])
    assert retenues[0]["url"] == URL_SIMPLE


def test_le_premier_degre_est_ecarte():
    _, ecartees = filtrer_suggestions([suggestion(degre="1er")])
    assert "réseau" in motifs(ecartees)[0]


def test_les_autres_degres_sont_retenus():
    retenues, _ = filtrer_suggestions(
        [suggestion(degre="2e"), suggestion(url="https://www.linkedin.com/in/marie/", degre="3e")]
    )
    assert len(retenues) == 2


def test_un_profil_deja_au_fichier_est_ecarte():
    _, ecartees = filtrer_suggestions([suggestion()], urls_en_base=[URL_SIMPLE])
    assert "fichier" in motifs(ecartees)[0]


def test_le_fichier_est_compare_sous_forme_canonique():
    # La base peut contenir le lien tel qu'il avait été copié jadis.
    stockee = "http://www.linkedin.com/in/JEAN-DUPONT-12345?trk=x"
    _, ecartees = filtrer_suggestions([suggestion()], urls_en_base=[stockee])
    assert len(ecartees) == 1


def test_l_entreprise_de_reference_est_ecartee():
    # « Le même profil ailleurs » : celui qui y est encore n'est pas la cible.
    _, ecartees = filtrer_suggestions([suggestion()], entreprise_reference="Thiga")
    assert "Thiga" in motifs(ecartees)[0]


def test_l_entreprise_de_reference_se_compare_sans_tenir_compte_de_la_casse():
    _, ecartees = filtrer_suggestions([suggestion()], entreprise_reference="thiga")
    assert len(ecartees) == 1


def test_une_entreprise_de_reference_inconnue_n_ecarte_personne():
    # La page n'a pas permis de la lire : on ne doit ni planter ni tout vider.
    retenues, ecartees = filtrer_suggestions([suggestion()], entreprise_reference=None)
    assert len(retenues) == 1 and ecartees == []


def test_une_entreprise_de_reference_vide_n_ecarte_personne():
    retenues, _ = filtrer_suggestions([suggestion()], entreprise_reference="   ")
    assert len(retenues) == 1


def test_les_non_invitables_sont_ecartes_sur_demande():
    _, ecartees = filtrer_suggestions(
        [suggestion(invitable=False)], invitables_seulement=True
    )
    assert "invitable" in motifs(ecartees)[0]


def test_les_non_invitables_sont_gardes_par_defaut():
    retenues, _ = filtrer_suggestions([suggestion(invitable=False)])
    assert len(retenues) == 1


def test_le_mot_attendu_filtre_sur_l_intitule():
    _, ecartees = filtrer_suggestions([suggestion()], mot_intitule="Data")
    assert "Data" in motifs(ecartees)[0]


def test_le_mot_attendu_ignore_la_casse_et_les_espaces_de_bord():
    # Une saisie « product » ne doit pas vider la liste sans raison visible.
    retenues, _ = filtrer_suggestions([suggestion()], mot_intitule="  product  ")
    assert len(retenues) == 1


def test_un_mot_attendu_vide_ne_filtre_rien():
    retenues, _ = filtrer_suggestions([suggestion()], mot_intitule="")
    assert len(retenues) == 1


def test_un_lien_illisible_est_ecarte_avec_son_motif():
    _, ecartees = filtrer_suggestions([suggestion(url="https://example.com/x")])
    assert "illisible" in motifs(ecartees)[0]


def test_le_motif_affiche_est_le_plus_sur_des_motifs_applicables():
    # 1er degré ET déjà au fichier : le degré est une certitude, l'autre aussi,
    # mais l'ordre doit être stable pour que l'écran soit compréhensible.
    _, ecartees = filtrer_suggestions(
        [suggestion(degre="1er")], urls_en_base=[URL_SIMPLE]
    )
    assert "réseau" in motifs(ecartees)[0]


def test_une_liste_entierement_ecartee_rend_tous_les_motifs():
    # L'écran s'en sert : une liste vide sans explication passerait pour un
    # profil sans voisins.
    entrees = [suggestion(degre="1er"), suggestion(url="https://www.linkedin.com/in/marie/", degre="1er")]
    retenues, ecartees = filtrer_suggestions(entrees)
    assert retenues == [] and len(ecartees) == 2


def test_un_panneau_vide_ne_rend_rien_sans_echouer():
    assert filtrer_suggestions([]) == ([], [])
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_browsemap.py -v`
Expected: FAIL — `ImportError: cannot import name 'filtrer_suggestions'`

- [ ] **Step 3 : Écrire le filtre**

Ajouter à `utils/browsemap.py` :

```python
MOTIF_URL_ILLISIBLE = "lien de profil illisible"
MOTIF_PREMIER_DEGRE = "déjà dans ton réseau (1er degré)"
MOTIF_DEJA_AU_FICHIER = "déjà dans ton fichier"
MOTIF_NON_INVITABLE = "non invitable (« Suivre » seulement)"


def filtrer_suggestions(suggestions, urls_en_base=(), entreprise_reference=None,
                        invitables_seulement=False, mot_intitule=None):
    """Trie les entrées du panneau en (retenues, écartées).

    Chaque écartée porte son motif, affiché à l'écran : une liste qui se vide
    doit dire pourquoi, sinon elle passe pour un profil sans voisins — c'est
    précisément le défaut corrigé en 1.4.7, sous une autre forme.

    L'ordre des exclusions n'est pas indifférent. On écarte d'abord sur ce qui
    est certain — lien illisible, réseau, fichier —, ensuite sur ce qui est
    approximatif — l'entreprise, lue dans un intitulé écrit à la main —, enfin
    sur le choix de la personne. Le motif affiché est donc toujours le plus sûr
    des motifs applicables.
    """
    connues = {normaliser_url(u) for u in (urls_en_base or ())}
    connues.discard(None)

    entreprise = (entreprise_reference or "").strip().lower()
    mot = (mot_intitule or "").strip().lower()

    retenues, ecartees = [], []

    for entree in suggestions or ():
        canonique = normaliser_url(entree.get("url"))
        intitule = (entree.get("intitule") or "").lower()

        if canonique is None:
            motif = MOTIF_URL_ILLISIBLE
        elif (entree.get("degre") or "").strip() == "1er":
            motif = MOTIF_PREMIER_DEGRE
        elif canonique in connues:
            motif = MOTIF_DEJA_AU_FICHIER
        elif entreprise and entreprise in intitule:
            # Best effort assumé : qui ne mentionne pas son employeur dans son
            # intitulé passera le filtre. Le tableau de l'étape 2 affiche la
            # société lue sur la page de profil, où on le verra.
            motif = f"encore chez {entreprise_reference.strip()}"
        elif invitables_seulement and not entree.get("invitable"):
            motif = MOTIF_NON_INVITABLE
        elif mot and mot not in intitule:
            motif = f"l'intitulé ne contient pas « {mot_intitule.strip()} »"
        else:
            retenues.append(dict(entree, url=canonique))
            continue

        ecartees.append(dict(entree, motif=motif))

    return retenues, ecartees
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_browsemap.py -v`
Expected: PASS — 28 tests

- [ ] **Step 5 : Commit**

```bash
git add utils/browsemap.py tests/test_browsemap.py
git commit -m "feat(similaires): filtrage des profils voisins, chaque exclusion motivee"
```

---

## Task 3 : Les URLs déjà au fichier

**Files:**
- Modify: `database.py` (après `profil_existe`, l. 150-164)
- Test: `tests/test_urls_connues.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: `DatabaseManager.urls_connues() -> set[str]`.

**Pourquoi cette tâche existe.** La spec annonçait `database.py` inchangé, en tablant sur `profil_existe()`. C'est insuffisant : `profil_existe()` compare des URLs brutes, et la base contient les liens tels qu'ils ont été copiés au fil des ans. Comparer des formes canoniques des deux côtés suppose de pouvoir lire celles qui sont stockées. `get_tous_profils()` existe mais plafonne à 1000 lignes et rapatrie toutes les colonnes : une méthode dédiée coûte moins et ne mentira pas.

- [ ] **Step 1 : Écrire le test qui échoue**

Créer `tests/test_urls_connues.py` :

```python
# -*- coding: utf-8 -*-
"""L'ensemble des URLs déjà au fichier, pour le filtre des profils voisins.

`profil_existe()` ne suffit pas : il compare des URLs brutes, et la base
contient les liens tels qu'ils ont été copiés. La comparaison se fait sur des
formes canoniques, des deux côtés — ce qui suppose de lire celles stockées.
"""

from database import DatabaseManager


def base_jetable(tmp_path):
    return DatabaseManager(db_file=str(tmp_path / "test.db"))


def test_une_base_vide_ne_connait_aucune_url(tmp_path):
    assert base_jetable(tmp_path).urls_connues() == set()


def test_les_urls_ajoutees_sont_connues(tmp_path):
    db = base_jetable(tmp_path)
    db.ajouter_profil("Jean Dupont", "PM", "Thiga", "Dauphine",
                      "https://www.linkedin.com/in/jean-dupont/")
    db.ajouter_profil("Marie Martin", "Dev", "Kering", "ESCP",
                      "https://www.linkedin.com/in/marie-martin/")

    assert db.urls_connues() == {
        "https://www.linkedin.com/in/jean-dupont/",
        "https://www.linkedin.com/in/marie-martin/",
    }


def test_les_urls_sont_rendues_telles_qu_elles_sont_stockees(tmp_path):
    # La normalisation appartient à utils.browsemap, pas à la base : celle-ci
    # dit ce qu'elle contient, sans l'interpréter.
    db = base_jetable(tmp_path)
    brute = "http://LINKEDIN.com/in/Jean-Dupont?trk=x"
    db.ajouter_profil("Jean", "PM", "Thiga", "", brute)

    assert db.urls_connues() == {brute}


def test_un_echec_de_lecture_ne_rend_pas_None(tmp_path):
    # Les méthodes de cette classe avalent leurs exceptions. Celle-ci doit
    # alors rendre un ensemble vide : l'appelant fait `url in connues`.
    db = DatabaseManager(db_file=str(tmp_path / "pas-une-base" / "x.db"))
    assert db.urls_connues() == set()
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

Run: `python -m pytest tests/test_urls_connues.py -v`
Expected: FAIL — `AttributeError: 'DatabaseManager' object has no attribute 'urls_connues'`

- [ ] **Step 3 : Écrire la méthode**

Insérer dans `database.py`, juste après `profil_existe` :

```python
    def urls_connues(self) -> set:
        """Toutes les URLs déjà au fichier, telles qu'elles sont stockées.

        Sert au filtre des profils voisins : comparer une à une avec
        `profil_existe()` demanderait autant de requêtes que de suggestions,
        et surtout ne permettrait pas de confronter des formes canoniques —
        la base contient les liens tels qu'ils ont été copiés, avec leurs
        paramètres de suivi.

        Rend un ensemble vide en cas d'échec, jamais None : l'appelant écrit
        `url in connues`.
        """
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM profiles WHERE url IS NOT NULL")
            urls = {ligne[0] for ligne in cursor.fetchall() if ligne[0]}
            conn.close()
            return urls

        except Exception as e:
            logger.error(f"Erreur lecture des URLs connues: {e}")
            return set()
```

- [ ] **Step 4 : Lancer le test pour vérifier qu'il passe**

Run: `python -m pytest tests/test_urls_connues.py -v`
Expected: PASS — 4 tests

- [ ] **Step 5 : Commit**

```bash
git add database.py tests/test_urls_connues.py
git commit -m "feat(similaires): lire les URLs deja au fichier"
```

---

## Task 4 : Lecture du panneau dans le navigateur

**Files:**
- Modify: `utils/dom_selectors.py` (ajouter une méthode statique à `DOMSelectors`)
- Modify: `scraper_v2.py` (après `extraire_profil_depuis_page`, l. 1769)
- Modify: `scraper_v2_sync.py` (après `run_url_scraper`, l. ~133)
- Test: `tests/test_recolte_browsemap.py` (créer)

**Interfaces:**
- Consumes: `url_panneau`, `vanity_depuis_url` (Task 1) ; `self._open_linkedin_page(p, cookie, status_callback) -> (browser, page)` ; `self.network_manager.safe_page_goto(page, url) -> bool` ; `self.extraire_profil_depuis_page(page) -> {"nom","poste","entreprise"}` ; `self.human.human_delay(mean_ms, std_ms)`.
- Produces:
  - `DOMSelectors.extract_browsemap_js() -> str`
  - `LinkedInScraperV2.recolter_browsemap_async(cookie, url_reference, status_callback=None) -> (list[dict], str | None)`
  - `LinkedInScraperV2Sync.recolter_browsemap(cookie, url_reference, status_callback=None) -> (list[dict], str | None)`
  - Chaque dict : `{"nom", "url", "degre", "intitule", "invitable"}` — la forme attendue par `filtrer_suggestions`.

**Écart assumé avec la spec.** §8 promettait deux messages distincts — « le
panneau n'existe pas pour ce profil » et « le panneau a changé de structure ».
Le code ne peut pas les distinguer : dans les deux cas il lit zéro entrée. Le
message unique dit donc les deux, et laisse la personne trancher (« Si ce
profil en affiche bien sur LinkedIn, sa structure a changé »). Inventer une
heuristique pour les séparer reviendrait à deviner, et à se tromper en silence.

**Note sur les tests.** Aucun test ne lance de navigateur. Deux choses sont pourtant vérifiables sans lui, et ce sont celles qui cassent le plus souvent : le refus d'une URL qui n'est pas un profil **avant** tout lancement, et la remontée fidèle du résultat par le wrapper synchrone. Le reste se vérifie en Task 7, par un essai réel.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_recolte_browsemap.py` :

```python
# -*- coding: utf-8 -*-
"""Garde-fous de la récolte des profils voisins, sans lancer de navigateur.

Deux choses se vérifient sans Chrome, et ce sont celles qui cassent : qu'une
URL qui n'est pas un profil soit refusée AVANT tout lancement — sinon on
ouvre un navigateur pour rien et l'erreur arrive deux minutes trop tard — et
que le wrapper synchrone remonte fidèlement ce que la couche async a trouvé.
"""

import asyncio

import pytest

from scraper_v2 import LinkedInScraperV2
from scraper_v2_sync import LinkedInScraperV2Sync
from utils.dom_selectors import DOMSelectors


@pytest.fixture
def scraper(tmp_path):
    return LinkedInScraperV2(use_database=False, config_dir=str(tmp_path))


def recolter(scraper, url):
    return asyncio.run(
        scraper.recolter_browsemap_async(cookie="COOKIE-DE-TEST", url_reference=url)
    )


def test_une_page_entreprise_est_refusee_sans_lancer_de_navigateur(scraper):
    suggestions, entreprise = recolter(scraper, "https://www.linkedin.com/company/thiga/")

    assert suggestions == []
    assert entreprise is None
    assert any("profil LinkedIn" in e for e in scraper.errors)


def test_une_saisie_vide_est_refusee(scraper):
    suggestions, entreprise = recolter(scraper, "")

    assert (suggestions, entreprise) == ([], None)
    assert scraper.errors


def test_le_wrapper_synchrone_remonte_ce_qu_a_trouve_la_couche_async(tmp_path, monkeypatch):
    attendu = ([{"nom": "Jean Dupont", "url": "https://www.linkedin.com/in/jd/"}], "Thiga")
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def fausse_recolte(cookie, url_reference, status_callback=None):
        return attendu

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", fausse_recolte)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == attendu


def test_le_wrapper_synchrone_ne_leve_pas_sur_un_echec(tmp_path, monkeypatch):
    # Streamlit afficherait une trace à l'écran : le wrapper rend une liste
    # vide et consigne l'erreur, comme ses voisins.
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def recolte_qui_echoue(cookie, url_reference, status_callback=None):
        raise RuntimeError("Chrome introuvable")

    monkeypatch.setattr(wrapper.scraper, "recolter_browsemap_async", recolte_qui_echoue)

    assert wrapper.recolter_browsemap("COOKIE", "https://www.linkedin.com/in/jd/") == ([], None)
    assert any("Chrome introuvable" in e for e in wrapper.errors)


def test_l_extracteur_javascript_lit_bien_le_panneau():
    # Garde-fou minimal : le JS n'est pas testable sans navigateur, mais une
    # suppression accidentelle de ses points d'ancrage doit se voir.
    js = DOMSelectors.extract_browsemap_js()

    assert js.strip().startswith("()")
    for ancre in ('role="dialog"', '/in/', 'invitable', 'intitule', 'degre'):
        assert ancre in js, f"ancre manquante dans l'extracteur : {ancre}"
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_recolte_browsemap.py -v`
Expected: FAIL — `AttributeError: … has no attribute 'recolter_browsemap_async'`

- [ ] **Step 3 : Écrire l'extracteur JavaScript**

Ajouter à la fin de la classe `DOMSelectors` dans `utils/dom_selectors.py` :

```python
    @staticmethod
    def extract_browsemap_js() -> str:
        """Lecture du panneau « Plus de profils pour vous ».

        Le panneau est un overlay : on part de `div[role="dialog"]` plutôt
        que de `main`, qui porte encore le profil de référence dessous.

        Écrit défensivement, comme `extract_profiles_data_js` : on n'ancre sur
        aucune classe CSS — LinkedIn les regénère — mais sur les liens `/in/`
        et sur le texte des cartes. Quand rien n'est lu, le HTML du conteneur
        est renvoyé pour être enregistré : c'est la seule façon de rattraper
        un changement de structure.
        """
        return """() => {
            const racine = document.querySelector('div[role="dialog"]')
                        || document.querySelector('main')
                        || document.body;

            // Libellés de boutons et marqueurs de degré : du bruit, jamais un
            // nom ni un intitulé.
            const bruit = /^(se connecter|suivre|s'abonner|message|inviter|· ?(1er|2e|3e)|(1er|2e|3e) ?·?)$/i;

            const vus = new Set();
            const entrees = [];

            for (const lien of racine.querySelectorAll('a[href*="/in/"]')) {
                const href = lien.href || '';
                const m = href.match(/\\/in\\/([^/?#]+)/);
                if (!m) continue;
                const vanity = m[1].toLowerCase();
                if (vus.has(vanity)) continue;

                const carte = lien.closest('li')
                           || lien.closest('div[role="listitem"]')
                           || lien.parentElement;
                if (!carte) continue;

                const texte = (carte.innerText || '').trim();
                if (!texte) continue;
                const lignes = texte.split('\\n').map(s => s.trim()).filter(Boolean);

                // Nom : la première ligne qui n'est pas du bruit.
                let nom = '';
                for (const ligne of lignes) {
                    if (bruit.test(ligne)) continue;
                    if (ligne.length < 2 || ligne.length > 120) continue;
                    nom = ligne;
                    break;
                }
                if (!nom) continue;

                // Degré : LinkedIn l'écrit « · 2e » à côté du nom.
                const degre = (texte.match(/\\b(1er|2e|3e)\\b/) || [''])[0];

                // Intitulé : la plus longue ligne restante. Gardé brut — il est
                // écrit à la main, dans tous les formats imaginables, et un
                // champ structuré faux vaut moins qu'un texte exact.
                let intitule = '';
                for (const ligne of lignes) {
                    if (ligne === nom || bruit.test(ligne)) continue;
                    if (/^(1er|2e|3e)$/.test(ligne)) continue;
                    if (ligne.length > intitule.length) intitule = ligne;
                }

                const bas = texte.toLowerCase();
                const invitable = bas.includes('se connecter') || bas.includes('inviter');

                vus.add(vanity);
                entrees.push({nom, url: href, degre, intitule, invitable});
            }

            return {
                entrees: entrees,
                html: entrees.length ? '' : racine.innerHTML.slice(0, 20000)
            };
        }"""
```

- [ ] **Step 4 : Écrire la navigation**

Dans `scraper_v2.py`, ajouter l'import en tête du fichier, à côté des autres imports `utils` :

```python
from utils.browsemap import url_panneau, vanity_depuis_url
```

Puis insérer ces trois méthodes juste après `extraire_profil_depuis_page` (l. 1769) :

```python
    # ==================================================================
    # PROFILS VOISINS (panneau « Plus de profils pour vous »)
    # ==================================================================

    async def _derouler_panneau(self, page: Page, limite_tours: int = 12) -> int:
        """Déroule le panneau jusqu'à ce qu'il cesse de s'allonger.

        Faire défiler la fenêtre ne suffit pas : le panneau est un overlay,
        c'est son propre conteneur qu'il faut pousser — et ce conteneur n'est
        pas forcément le `div[role="dialog"]` lui-même, souvent un descendant.
        On pousse donc tout ce qui peut défiler.

        `limite_tours` borne la boucle : un panneau qui s'alimenterait sans
        fin ne doit pas immobiliser l'outil.
        """
        precedent = -1
        for _ in range(limite_tours):
            actuel = await page.evaluate(
                """() => (document.querySelector('div[role="dialog"]')
                       || document.body).querySelectorAll('a[href*="/in/"]').length"""
            )
            if actuel == precedent:
                break
            precedent = actuel
            await page.evaluate(
                """() => {
                    const d = document.querySelector('div[role="dialog"]');
                    const cibles = d ? [d, ...d.querySelectorAll('*')] : [];
                    let pousse = false;
                    for (const el of cibles) {
                        if (el.scrollHeight > el.clientHeight + 40) {
                            el.scrollTop = el.scrollHeight;
                            pousse = true;
                        }
                    }
                    if (!pousse) window.scrollTo(0, document.body.scrollHeight);
                }"""
            )
            await self.human.human_delay(1200, 300)

        logger.info(f"📜 Panneau déroulé : {precedent} liens de profil visibles")
        return max(precedent, 0)

    def _dumper_panneau(self, html: str) -> None:
        """Écrit le panneau sur disque quand on n'y a rien lu.

        Même geste que `extraire_profils_page` : le jour où LinkedIn change sa
        structure, la seule façon de la rattraper est d'avoir le HTML sous les
        yeux — faute de quoi on cherche à l'aveugle.
        """
        if not html:
            return
        try:
            from pathlib import Path
            dossier = Path(__file__).parent / 'logs'
            dossier.mkdir(exist_ok=True)
            fichier = dossier / 'browsemap_dump.html'
            fichier.write_text(html, encoding='utf-8')
            logger.warning(f"⚠️ Panneau illisible — HTML enregistré dans {fichier}")
        except Exception as err:
            logger.warning(f"⚠️ Impossible d'enregistrer le panneau: {err}")

    async def recolter_browsemap_async(
        self,
        cookie: str,
        url_reference: str,
        status_callback: Optional[Callable] = None
    ) -> tuple:
        """Profils voisins que LinkedIn propose pour `url_reference`.

        Rend `(suggestions, entreprise_reference)`. Ne scrape rien et n'invite
        personne : la liste d'URLs part ensuite dans `run_url_scraper`, qui
        fait déjà les deux.

        `entreprise_reference` vaut None si la page n'a pas permis de la lire
        — le panneau est un overlay, le profil est rendu dessous mais rien ne
        le garantit. L'appelant la demande alors à la personne plutôt que
        d'abandonner l'exclusion « ailleurs » en silence.
        """
        self.errors = []

        cible = url_panneau(url_reference)
        if cible is None:
            # Refusé avant tout lancement : ouvrir Chrome pour apprendre ça
            # deux minutes plus tard n'aiderait personne.
            self.errors.append(
                "Ce lien n'est pas celui d'un profil LinkedIn "
                "(il doit contenir « /in/ »)."
            )
            return [], None

        reference = vanity_depuis_url(url_reference)

        async with async_playwright() as p:
            if status_callback:
                status_callback("🚀 Lancement du navigateur...")

            browser, page = await self._open_linkedin_page(p, cookie, status_callback)
            if page is None:
                self.errors.append("Cookie invalide ou expiré — reconnectez-vous.")
                return [], None

            try:
                if status_callback:
                    status_callback("👥 Ouverture des profils voisins...")

                if not await self.network_manager.safe_page_goto(page, cible):
                    self.errors.append(f"Impossible d'ouvrir le panneau : {cible}")
                    return [], None

                if any(x in page.url for x in ["login", "authwall"]):
                    self.errors.append("Redirigé vers login — cookie invalide.")
                    return [], None

                await self.human.human_delay(2000, 500)

                # L'entreprise actuelle du profil de référence, lue au passage
                # sur la même page : c'est tout ce dont le « ailleurs » a besoin.
                entreprise = (
                    await self.extraire_profil_depuis_page(page)
                ).get("entreprise") or None

                if status_callback:
                    status_callback("📜 Déroulement de la liste...")
                await self._derouler_panneau(page)

                brut = await page.evaluate(DOMSelectors.extract_browsemap_js())
                entrees = brut.get("entrees", [])

                if not entrees:
                    self._dumper_panneau(brut.get("html", ""))
                    self.errors.append(
                        "Aucun profil voisin lu dans le panneau. Si ce profil "
                        "en affiche bien sur LinkedIn, sa structure a changé : "
                        "le contenu de la page est enregistré dans logs/ pour "
                        "analyse."
                    )

                # Le lien du profil de référence figure dans sa propre page :
                # ce n'est pas une suggestion.
                suggestions = [
                    e for e in entrees
                    if vanity_depuis_url(e.get("url")) not in (None, reference)
                ]

                logger.info(f"✅ {len(suggestions)} profils voisins retenus du panneau")
                return suggestions, entreprise

            finally:
                await browser.close()
```

- [ ] **Step 5 : Écrire le wrapper synchrone**

Dans `scraper_v2_sync.py`, insérer après `run_url_scraper` :

```python
    def recolter_browsemap(self, cookie, url_reference, status_callback=None):
        """Version synchrone : profils voisins d'un profil de référence.

        Rend `([], None)` sur échec plutôt que de lever : Streamlit
        afficherait une trace à l'écran, là où l'utilisateur attend une
        phrase.
        """
        try:
            logger.info(f"👥 Récolte des profils voisins de {url_reference}")

            result = asyncio.run(
                self.scraper.recolter_browsemap_async(
                    cookie=cookie,
                    url_reference=url_reference,
                    status_callback=status_callback,
                )
            )

            self.errors = self.scraper.errors.copy()
            return result

        except Exception as e:
            logger.error(f"❌ Erreur récolte profils voisins: {e}", exc_info=True)
            self.errors.append(f"Erreur: {e}")
            return [], None
```

- [ ] **Step 6 : Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_recolte_browsemap.py -v`
Expected: PASS — 5 tests

Si `LinkedInScraperV2(use_database=False, config_dir=…)` échoue à la construction, c'est un signal, pas un obstacle à contourner : lire le `__init__` et passer les arguments qu'il réclame, sans jamais le laisser écrire dans les données réelles du poste.

- [ ] **Step 7 : Lancer toute la suite**

Run: `python -m pytest -q`
Expected: PASS — les 174 tests existants plus les nouveaux.

- [ ] **Step 8 : Commit**

```bash
git add utils/dom_selectors.py scraper_v2.py scraper_v2_sync.py tests/test_recolte_browsemap.py
git commit -m "feat(similaires): lire le panneau de profils voisins de LinkedIn"
```

---

## Task 5 : L'onglet — étape 1, trouver

**Files:**
- Modify: `app_advanced.py` (l. 469-471 pour les onglets ; nouveau bloc après la fin de `tab3`, l. 838)
- Test: `tests/test_onglet_profils_similaires.py` (créer)

**Interfaces:**
- Consumes: `vanity_depuis_url`, `filtrer_suggestions` (Tasks 1-2) ; `DatabaseManager.urls_connues` (Task 3) ; `LinkedInScraperV2Sync.recolter_browsemap` (Task 4).
- Produces: clés `st.session_state` `sim_retenues` (list), `sim_ecartees` (list), `sim_entreprise` (str | None), `sim_erreurs` (list) — lues par Task 6.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_onglet_profils_similaires.py` :

```python
# -*- coding: utf-8 -*-
"""Onglet « Profils similaires » : du lien de référence à la liste filtrée.

L'onglet ne scrape pas et n'invite pas : il récolte le panneau de LinkedIn,
filtre, et confie les URLs retenues à la chaîne de l'onglet Par URLs. Ces
tests vérifient ce câblage — ce qui part dans la récolte, ce que le filtre
reçoit, ce qui reste à l'écran.
"""

import pandas as pd
import pytest

import scraper_v2_sync
from tests.conftest import lancer_app, verifier_page_affichee

URL_REFERENCE = "https://www.linkedin.com/in/jean-dupont-12345/"
BOUTON_TROUVER = "👥 Trouver des profils similaires"


def voisin(nom, vanity, degre="2e", intitule="Product Manager, Kering", invitable=True):
    return {
        "nom": nom,
        "url": f"https://www.linkedin.com/in/{vanity}/",
        "degre": degre,
        "intitule": intitule,
        "invitable": invitable,
    }


@pytest.fixture
def recolte_espionne(monkeypatch):
    """Remplace le scraper : rien n'est lancé, la récolte est dictée.

    `reponse` est modifiable par le test ; `appels` capture ce qui a été
    demandé.
    """
    etat = {"reponse": ([], None), "appels": []}

    class FauxScraper:
        def __init__(self, **kwargs):
            self.errors = []
            self.use_database = False

        def recolter_browsemap(self, **kwargs):
            etat["appels"].append(kwargs)
            return etat["reponse"]

        def run_url_scraper(self, **kwargs):
            etat["appels"].append(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(scraper_v2_sync, "LinkedInScraperV2Sync", FauxScraper)
    return etat


def _page_recherche():
    at = lancer_app("🔍 Recherche")
    verifier_page_affichee(at, "🔍 Recherche")
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    return at


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def _trouver(at, url=URL_REFERENCE):
    at.text_input(key="sim_url").set_value(url)
    _bouton(at, BOUTON_TROUVER).click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_l_onglet_existe_dans_la_page_recherche():
    at = _page_recherche()
    assert at.text_input(key="sim_url") is not None


def test_le_lien_de_reference_part_dans_la_recolte(recolte_espionne):
    at = _trouver(_page_recherche())

    assert recolte_espionne["appels"][0]["url_reference"] == URL_REFERENCE
    assert recolte_espionne["appels"][0]["cookie"] == "COOKIE-DE-TEST"


def test_un_lien_qui_n_est_pas_un_profil_est_refuse_sans_rien_lancer(recolte_espionne):
    at = _trouver(_page_recherche(), "https://www.linkedin.com/company/thiga/")

    assert recolte_espionne["appels"] == []
    assert at.error, "aucun message d'erreur affiché"


def test_les_profils_retenus_sont_mis_en_session(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")],
        "Thiga",
    )
    at = _trouver(_page_recherche())

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == [
        "Marie Martin", "Paul Durand"
    ]
    assert at.session_state["sim_entreprise"] == "Thiga"


def test_le_premier_degre_est_ecarte_a_l_ecran(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", degre="1er")], None
    )
    at = _trouver(_page_recherche())

    assert at.session_state["sim_retenues"] == []
    assert len(at.session_state["sim_ecartees"]) == 1


def test_l_entreprise_de_reference_est_transmise_au_filtre(recolte_espionne):
    # « ailleurs » : celui qui est encore chez Thiga n'est pas la cible.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", intitule="Lead Dev, Thiga")], "Thiga"
    )
    at = _trouver(_page_recherche())

    assert at.session_state["sim_retenues"] == []
    assert "Thiga" in at.session_state["sim_ecartees"][0]["motif"]


def test_une_liste_entierement_ecartee_affiche_ses_motifs(recolte_espionne):
    # Le défaut de la 1.4.7 sous une autre forme : une liste vide sans
    # explication passerait pour un profil sans voisins.
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin", degre="1er")], None
    )
    at = _trouver(_page_recherche())

    textes = [m.value for m in at.markdown] + [c.value for c in at.caption]
    assert any("réseau" in t for t in textes), (
        f"le motif n'est pas affiché. Textes rendus : {textes}"
    )


def test_le_mot_attendu_resserre_la_liste(recolte_espionne):
    recolte_espionne["reponse"] = (
        [
            voisin("Marie Martin", "marie-martin", intitule="Product Manager, Kering"),
            voisin("Paul Durand", "paul-durand", intitule="Data Engineer, Kering"),
        ],
        None,
    )
    at = _page_recherche()
    at.text_input(key="sim_mot").set_value("Product")
    at = _trouver(at)

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]


def test_un_cookie_absent_est_signale(recolte_espionne):
    at = lancer_app("🔍 Recherche")
    at.session_state["global_cookie"] = ""
    at = _trouver(at)

    assert recolte_espionne["appels"] == []
    assert at.error
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_onglet_profils_similaires.py -v`
Expected: FAIL — `KeyError` sur la clé `sim_url` : le widget n'existe pas.

- [ ] **Step 3 : Ajouter l'import et le quatrième onglet**

Dans `app_advanced.py`, ajouter aux imports `utils` :

```python
from utils.browsemap import filtrer_suggestions, vanity_depuis_url
```

Remplacer l. 469-471 :

```python
    tab1, tab2, tab3 = st.tabs(
        ["👤 Candidats", "🏢 Clients/Entreprises", "🔗 Par URLs"]
    )
```

par :

```python
    tab1, tab2, tab3, tab4 = st.tabs(
        ["👤 Candidats", "🏢 Clients/Entreprises", "🔗 Par URLs",
         "👥 Profils similaires"]
    )
```

- [ ] **Step 4 : Écrire le corps de l'onglet**

Insérer à la fin du bloc `elif page == "🔍 Recherche":`, après la fin de `with tab3:` (l. 838) et avant `elif page == "💾 Historique":` :

```python
    # TAB 4: PROFILS SIMILAIRES
    with tab4:
        st.subheader("Retrouver un profil comme celui-là, ailleurs")
        st.caption(
            "Partez d'un profil qui vous a donné satisfaction : LinkedIn "
            "propose lui-même les profils que les mêmes personnes consultent. "
            "Les gens déjà dans votre réseau ou déjà dans votre fichier sont "
            "écartés."
        )

        col1, col2 = st.columns([2, 1])

        with col1:
            sim_url = st.text_input(
                "Lien du profil de référence",
                placeholder="https://www.linkedin.com/in/jean-dupont-12345/",
                key="sim_url",
                help="Le profil de quelqu'un que vous avez déjà placé, par exemple.",
            )

        with col2:
            sim_invitables = st.checkbox(
                "Seulement les profils invitables",
                value=True,
                key="sim_invitables",
                help="Écarte ceux qui ne proposent que « Suivre » : ils ne "
                     "peuvent pas recevoir d'invitation.",
            )
            sim_mot = st.text_input(
                "Mot attendu dans l'intitulé (optionnel)",
                placeholder="Product",
                key="sim_mot",
                help="Pour resserrer si la liste part dans une direction qui "
                     "ne vous intéresse pas.",
            )

        if st.button("👥 Trouver des profils similaires", type="primary",
                     use_container_width=True, key="sim_btn_trouver"):
            if not st.session_state.global_cookie:
                st.error("❌ Cookie manquant")
            elif vanity_depuis_url(sim_url) is None:
                st.error(
                    "❌ Ce lien n'est pas celui d'un profil LinkedIn — "
                    "il doit contenir « /in/ »"
                )
            else:
                scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                status_text = st.empty()
                with st.spinner("🔄 Lecture des profils voisins..."):
                    suggestions, entreprise = scraper.recolter_browsemap(
                        cookie=st.session_state.global_cookie,
                        url_reference=sim_url,
                        status_callback=lambda s: status_text.text(s),
                    )

                # Les URLs du fichier servent de filtre, comparées sous forme
                # canonique des deux côtés — la base contient les liens tels
                # qu'ils ont été copiés.
                urls_en_base = (
                    scraper.db.urls_connues() if scraper.use_database else ()
                )

                retenues, ecartees = filtrer_suggestions(
                    suggestions,
                    urls_en_base=urls_en_base,
                    entreprise_reference=entreprise,
                    invitables_seulement=sim_invitables,
                    mot_intitule=sim_mot,
                )

                st.session_state["sim_retenues"] = retenues
                st.session_state["sim_ecartees"] = ecartees
                st.session_state["sim_entreprise"] = entreprise
                st.session_state["sim_erreurs"] = list(scraper.errors)
                status_text.empty()

        sim_retenues = st.session_state.get("sim_retenues")
        sim_ecartees = st.session_state.get("sim_ecartees") or []

        for erreur in st.session_state.get("sim_erreurs") or []:
            st.warning(f"⚠️ {erreur}")

        if sim_retenues is not None:
            if st.session_state.get("sim_entreprise"):
                st.caption(
                    f"Entreprise du profil de référence : "
                    f"**{st.session_state['sim_entreprise']}** — ceux qui y "
                    f"sont encore ont été écartés."
                )
            else:
                st.caption(
                    "L'entreprise du profil de référence n'a pas pu être lue : "
                    "ceux qui y travaillent encore n'ont donc pas été écartés."
                )

            if sim_retenues:
                st.success(f"✅ {len(sim_retenues)} profil(s) retenu(s)")
                st.dataframe(
                    pd.DataFrame(sim_retenues).reindex(
                        # reindex et non un simple [[...]] : une clé absente
                        # ferait planter la page entière au lieu d'afficher
                        # une colonne vide.
                        columns=["nom", "degre", "intitule", "invitable", "url"]
                    ).rename(columns={
                        "nom": "Nom", "degre": "Degré", "intitule": "Intitulé",
                        "invitable": "Invitable", "url": "Lien",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
            elif not st.session_state.get("sim_erreurs"):
                st.info(
                    "Aucun profil retenu — tout a été écarté par les filtres. "
                    "Le détail est juste en dessous."
                )

            if sim_ecartees:
                with st.expander(f"🚫 {len(sim_ecartees)} profil(s) écarté(s) — pourquoi"):
                    for e in sim_ecartees:
                        st.markdown(f"- **{e.get('nom') or '(sans nom)'}** — {e['motif']}")
```

- [ ] **Step 5 : Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_onglet_profils_similaires.py -v`
Expected: PASS — 9 tests

- [ ] **Step 6 : Vérifier que la navigation n'a pas bougé**

Run: `python -m pytest tests/test_navigation.py tests/test_pages_smoke.py -v`
Expected: PASS — un onglet n'est pas une page ; `PAGES` reste à cinq entrées.

- [ ] **Step 7 : Commit**

```bash
git add app_advanced.py tests/test_onglet_profils_similaires.py
git commit -m "feat(similaires): onglet Profils similaires, etape trouver"
```

---

## Task 6 : L'onglet — étape 2, récupérer et inviter

**Files:**
- Modify: `app_advanced.py` (dans `with tab4:`, à la suite de Task 5)
- Test: `tests/test_onglet_profils_similaires.py`

**Interfaces:**
- Consumes: `st.session_state["sim_retenues"]` (Task 5) ; `LinkedInScraperV2Sync.run_url_scraper(cookie, urls, inviter, message_invitation, progress_callback, status_callback) -> DataFrame`.
- Produces: rien pour les tâches suivantes.

**Pourquoi une étape séparée.** Les invitations sont rares et irréversibles. Une fonctionnalité exploratoire, qui ramène une liste dont on ne connaît pas encore la taille, ne doit pas pouvoir en consommer avant qu'on ait regardé ce qu'elle a trouvé.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `tests/test_onglet_profils_similaires.py` :

```python
# --- Étape 2 : récupérer et inviter --------------------------------------

BOUTON_RECUPERER = "🚀 Récupérer les infos"


def test_l_etape_2_n_apparait_pas_avant_d_avoir_trouve():
    at = _page_recherche()
    assert not [b for b in at.button if b.label == BOUTON_RECUPERER], (
        "le bouton de récupération s'affiche alors qu'aucune liste n'existe"
    )


def test_les_urls_retenues_partent_dans_la_chaine_existante(recolte_espionne):
    recolte_espionne["reponse"] = (
        [voisin("Marie Martin", "marie-martin"), voisin("Paul Durand", "paul-durand")],
        None,
    )
    at = _trouver(_page_recherche())
    recolte_espionne["appels"].clear()

    _bouton(at, BOUTON_RECUPERER).click()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    assert recolte_espionne["appels"][0]["urls"] == [
        "https://www.linkedin.com/in/marie-martin/",
        "https://www.linkedin.com/in/paul-durand/",
    ]


def test_les_invitations_ne_partent_pas_sans_l_avoir_demande(recolte_espionne):
    # Le quota d'invitations est rare et l'envoi irréversible : la case doit
    # être décochée par défaut.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    recolte_espionne["appels"].clear()

    _bouton(at, BOUTON_RECUPERER).click()
    at.run()

    assert recolte_espionne["appels"][0]["inviter"] is False


def test_la_case_cochee_fait_partir_les_invitations(recolte_espionne):
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())
    at.checkbox(key="sim_inviter").set_value(True)
    at.run()
    recolte_espionne["appels"].clear()

    _bouton(at, BOUTON_RECUPERER).click()
    at.run()

    assert recolte_espionne["appels"][0]["inviter"] is True


def test_la_liste_trouvee_survit_au_rerun_de_l_etape_2(recolte_espionne):
    # Elle vit dans session_state justement pour ça : un clic sur l'étape 2
    # relance le script, et la liste ne doit pas disparaître de l'écran.
    recolte_espionne["reponse"] = ([voisin("Marie Martin", "marie-martin")], None)
    at = _trouver(_page_recherche())

    _bouton(at, BOUTON_RECUPERER).click()
    at.run()

    assert [p["nom"] for p in at.session_state["sim_retenues"]] == ["Marie Martin"]
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m pytest tests/test_onglet_profils_similaires.py -v -k "etape or urls or invitations or survit"`
Expected: FAIL — le bouton `🚀 Récupérer les infos` n'existe pas.

- [ ] **Step 3 : Écrire l'étape 2**

Ajouter à la fin de `with tab4:`, à l'intérieur du `if sim_retenues is not None:` et après le bloc des écartés :

```python
            if sim_retenues:
                st.markdown("---")
                st.markdown("**Étape 2 — récupérer les infos de ces profils**")
                st.caption(
                    "Chaque profil est ouvert pour en lire le poste et la "
                    "société. Cochez la case pour envoyer en même temps une "
                    "invitation."
                )

                sim_inviter = st.checkbox(
                    "Envoyer des invitations", value=False, key="sim_inviter"
                )
                if sim_inviter:
                    sim_message = st.text_area(
                        "Message d'invitation",
                        placeholder="Message personnalisé...",
                        max_chars=200,
                        key="sim_message",
                    )
                else:
                    sim_message = ""

                if st.button("🚀 Récupérer les infos", type="primary",
                             use_container_width=True, key="sim_btn_recuperer"):
                    if not st.session_state.global_cookie:
                        st.error("❌ Cookie manquant")
                    else:
                        scraper = LinkedInScraperV2Sync(use_database=True, proxy=st.session_state.get('user_proxy'), db_file=str(st.session_state.user_paths.db_file), profiles_csv=str(st.session_state.user_paths.profiles_csv), config_dir=str(st.session_state.user_paths.config_dir))

                        urls = [p["url"] for p in sim_retenues]
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        with st.spinner(f"🔄 {len(urls)} profils en cours..."):
                            df = scraper.run_url_scraper(
                                cookie=st.session_state.global_cookie,
                                urls=urls,
                                inviter=sim_inviter,
                                message_invitation=sim_message,
                                progress_callback=lambda p: progress_bar.progress(min(p, 1.0)),
                                status_callback=lambda s: status_text.text(s),
                            )

                        if not df.empty:
                            st.success(f"✅ {len(df)} profils récupérés sur {len(urls)} !")
                            st.dataframe(df, use_container_width=True)

                            excel_data = st.session_state.export_manager.export_to_excel(df.to_dict('records'))
                            st.download_button(
                                label="📥 Télécharger Excel",
                                data=excel_data,
                                file_name=f"profils_similaires_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="sim_dl_excel",
                            )

                            csv_data = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                            st.download_button(
                                label="📥 Télécharger CSV",
                                data=csv_data,
                                file_name=f"profils_similaires_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv",
                                key="sim_dl_csv",
                            )
                        else:
                            st.warning("⚠️ Aucun profil récupéré")

                        if scraper.errors:
                            with st.expander(f"⚠️ Erreurs ({len(scraper.errors)})"):
                                for err in scraper.errors:
                                    st.write(f"- {err}")
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `python -m pytest tests/test_onglet_profils_similaires.py -v`
Expected: PASS — 14 tests

- [ ] **Step 5 : Lancer toute la suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add app_advanced.py tests/test_onglet_profils_similaires.py
git commit -m "feat(similaires): etape recuperer et inviter, reutilise la chaine par URLs"
```

---

## Task 7 : Essai réel, puis publication

**Files:**
- Modify: `NOUVEAUTES.md`, `VERSION`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: la version 1.5.0 publiée.

**Pourquoi cette tâche n'est pas facultative.** Aucun test ne lance de navigateur : l'extracteur JavaScript et le déroulement du panneau n'ont jamais été exécutés sur du vrai HTML. Tant que l'essai réel n'a pas eu lieu, la fonctionnalité n'est pas vérifiée, quel que soit le compte des tests verts.

- [ ] **Step 1 : Essai réel avec Thomas**

À faire avec lui, sur un vrai profil de référence, l'outil lancé localement :

```bash
cd "/Users/thxms/Desktop/Projets Dev/LinkedIn Scraper Pro" && ./"LinkedIn Scraper Pro Advanced.command"
```

Quatre questions auxquelles cet essai doit répondre, et dont aucune n'a de réponse aujourd'hui :

1. **Combien de profils le panneau contient-il déroulé jusqu'en bas ?** Dix en font un complément de recherche ; cinquante, une source de prospection à part entière.
2. **Le nom, le degré, l'intitulé et le bouton sont-ils lus correctement ?** Comparer le tableau à l'écran avec le panneau dans un navigateur.
3. **L'entreprise du profil de référence est-elle lue ?** C'est le pari de la spec : le profil est rendu sous l'overlay. Si le bandeau affiche « n'a pas pu être lue », le pari est perdu et il faut ajouter un champ de saisie manuelle.
4. **Le déroulement atteint-il le bas ?** `logger` écrit « Panneau déroulé : N liens » — comparer N au nombre visible.

Si l'extraction rend zéro, `logs/browsemap_dump.html` contient le panneau : c'est là qu'on lit ce qu'il faut corriger.

- [ ] **Step 2 : Corriger ce que l'essai révèle, puis relancer la suite**

Run: `python -m pytest -q`
Expected: PASS

Toute correction de l'extracteur ou du déroulement reste dans `utils/dom_selectors.py` et `scraper_v2.py`. Si une règle de filtrage se révèle fausse, elle se corrige dans `utils/browsemap.py` **avec son test**, jamais sans.

- [ ] **Step 3 : Écrire l'annonce pour l'équipe**

Insérer en tête de `NOUVEAUTES.md`, juste après le préambule et avant `## 1.4.9`. Écrire pour l'équipe : ce qui change à l'écran, pas ce qui change dans le code.

```markdown
## 1.5.0

**Partez d'un profil qui a marché pour en trouver d'autres.**
Nouvel onglet **Profils similaires** dans Recherche : collez le lien d'un
profil qui vous a donné satisfaction, et l'outil vous propose les profils que
les mêmes personnes consultent — ceux que LinkedIn rapproche lui-même. Les
gens déjà dans votre réseau, déjà dans votre fichier, ou encore en poste dans
l'entreprise du profil de départ sont écartés : vous ne voyez que des pistes
neuves. Chaque profil écarté est expliqué.

Puis, en un second clic, l'outil récupère leur poste et leur société, et
envoie les invitations si vous le demandez. L'envoi est volontairement séparé
de la recherche : vous voyez la liste avant que quoi que ce soit ne parte.
```

Le nombre de profils que le panneau ramène — constaté à l'étape 1 — mérite d'être mentionné si l'essai montre qu'il est très faible ou très élevé : l'équipe doit savoir à quoi s'attendre.

- [ ] **Step 4 : Vérifier que l'annonce sera bien lue par l'application**

Run: `python -m pytest tests/test_nouveautes.py tests/test_annonce_nouveautes.py -v`
Expected: PASS — la section `## 1.5.0` est reconnue par `lire_sections`.

- [ ] **Step 5 : Bump de version**

```bash
cd "/Users/thxms/Desktop/Projets Dev/LinkedIn Scraper Pro" && echo "1.5.0" > VERSION && python -c "from version import get_version; print(get_version())"
```

Expected: `1.5.0`

- [ ] **Step 6 : Commit**

```bash
git add NOUVEAUTES.md VERSION
git commit -m "feat: retrouver un profil comme celui-la, ailleurs (v1.5.0)"
```

- [ ] **Step 7 : Publier — seulement sur accord explicite de Thomas**

La publication pousse la version sur les postes de l'équipe au prochain lancement. Elle ne se fait **jamais** sans son accord, et jamais avant que l'essai réel de l'étape 1 ait réussi.

```bash
git push origin HEAD:main
```

---

## Notes d'exécution

**Rien de tout cela ne consomme de quota tant que l'étape 1 seule est utilisée.** La récolte lit une page ; ce sont les invitations de l'étape 2 qui coûtent, et elles passent par le compteur déjà en place dans `human_behavior.py`.

**La récursion est hors périmètre, et doit le rester.** Prendre le panneau de chaque profil trouvé donnerait des centaines de pistes et multiplierait les chargements de pages — le comportement qui fait repérer un compte. Si l'envie revient, elle se discute, elle ne s'ajoute pas.
