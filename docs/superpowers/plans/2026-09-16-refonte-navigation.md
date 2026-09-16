# Refonte de la navigation We.Reach — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ramener les neuf pages de l'application à cinq entrées de menu, sans page orpheline ni fonctionnalité dupliquée, et interdire durablement la réapparition du défaut.

**Architecture :** Le menu cesse d'être une liste littérale au milieu du script et devient une constante `PAGES`, unique source de vérité, lue à la fois par le widget de navigation et par un test qui la confronte aux branches `if page == …`. Les pages conservées ne bougent pas ; deux pages disparaissent, deux deviennent respectivement un onglet et un volet latéral. Le widget de navigation passe en dernier du `st.radio` à des boutons à icônes, une fois toutes les structures stabilisées.

**Tech Stack :** Python 3.13, Streamlit 1.58, pytest, `ast` (analyse statique), `streamlit.testing.v1.AppTest`.

**Spec :** [`docs/superpowers/specs/2026-09-16-refonte-navigation-design.md`](../specs/2026-09-16-refonte-navigation-design.md)

## Global Constraints

- Environnement : toutes les commandes utilisent `./venv/bin/python`, depuis la racine du dépôt.
- Suite de tests : `./venv/bin/python -m pytest -q` doit être **verte à la fin de chaque tâche**, sans exception.
- Le thème visuel (`wefiit_theme.py`) n'est pas modifié, à la seule exception de la règle CSS ajoutée en Tâche 7.
- Les filtres de recherche (écoles, entreprises, secteurs) ne sont pas touchés : ils vivent dans `scraper_v2.construire_url_recherche` et restent inchangés, y compris pendant la suppression de la page Chasse.
- Les identifiants Streamlit (`key=`) des widgets déplacés sont conservés tels quels, afin de ne pas perdre l'état des sessions ouvertes.
- Libellés de menu, à la lettre près : `📊 Dashboard`, `🔍 Recherche`, `✉️ Messages`, `💾 Historique`, `📜 Logs`.
- Chaque tâche se termine par un commit.

---

### Task 1: Source de vérité du menu + garde-fou de structure

C'est la tâche fondatrice : elle crée la constante que tout le reste utilisera, et le test qui constate le défaut. Le test échouera volontairement jusqu'à la Tâche 6 — il est marqué `xfail(strict=True)`, ce qui le rend vert tant que le défaut existe **et rouge dès qu'il disparaît**, signalant de lui-même qu'il faut retirer le marqueur.

**Files:**
- Modify: `app_advanced.py:110-113`
- Test: `tests/test_navigation.py` (créer)

**Interfaces:**
- Consumes: rien.
- Produces: `app_advanced.PAGES: list[str]` (constante de module) ; `st.session_state["page"]` porte désormais le libellé de la page courante ; `tests/test_navigation.py` expose `arbre_app() -> ast.Module`, `pages_du_menu(arbre) -> list[str]`, `pages_definies(arbre) -> list[str]`, réutilisés par la Tâche 2.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_navigation.py` :

```python
# -*- coding: utf-8 -*-
"""Garde-fou : le menu et les pages définies doivent coïncider.

C'est l'absence de cette vérification qui a laissé quatre pages
inatteignables pendant deux mois (commit c6035c0).
L'analyse est statique — Streamlit n'est pas exécuté.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app_advanced.py"


def arbre_app() -> ast.Module:
    return ast.parse(APP.read_text(encoding="utf-8"))


def pages_du_menu(arbre: ast.Module) -> list:
    """Libellés de la constante PAGES — la source de vérité du menu."""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id == "PAGES":
                    return [e.value for e in noeud.value.elts]
    raise AssertionError("Constante PAGES introuvable dans app_advanced.py")


def pages_definies(arbre: ast.Module) -> list:
    """Libellés comparés à `page` dans les branches if/elif."""
    trouves = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Compare) and isinstance(noeud.left, ast.Name):
            if noeud.left.id != "page":
                continue
            for comp in noeud.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    trouves.append(comp.value)
    return trouves


@pytest.mark.xfail(
    strict=True,
    reason="4 pages orphelines depuis c6035c0 — résorbé par la Tâche 6 du plan "
           "2026-09-16-refonte-navigation ; retirer ce marqueur à ce moment-là.",
)
def test_toute_page_definie_est_atteignable_depuis_le_menu():
    arbre = arbre_app()
    orphelines = set(pages_definies(arbre)) - set(pages_du_menu(arbre))
    assert orphelines == set()


def test_toute_entree_de_menu_correspond_a_une_page():
    arbre = arbre_app()
    fantomes = set(pages_du_menu(arbre)) - set(pages_definies(arbre))
    assert fantomes == set()


def test_aucun_doublon_dans_le_menu():
    pages = pages_du_menu(arbre_app())
    assert len(pages) == len(set(pages))
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Run : `./venv/bin/python -m pytest tests/test_navigation.py -q`
Expected : **FAIL** — `AssertionError: Constante PAGES introuvable dans app_advanced.py` sur les trois tests. La constante n'existe pas encore.

- [ ] **Step 3: Créer la constante et router la page par session_state**

Dans `app_advanced.py`, remplacer les lignes 110-113 :

```python
page = st.sidebar.radio(
    "Choisir une page",
    ["📊 Dashboard", "🔍 Recherche", "🎯 Chasse", "💾 Historique", "✉️ Messages", "📜 Logs"]
)
```

par :

```python
# Source de vérité du menu. tests/test_navigation.py la confronte aux
# branches `if page == …` : toute page définie doit figurer ici.
PAGES = [
    "📊 Dashboard",
    "🔍 Recherche",
    "🎯 Chasse",
    "💾 Historique",
    "✉️ Messages",
    "📜 Logs",
]

# La page courante transite par session_state : le test de fumée peut la
# fixer sans piloter le widget, qui changera de nature en Tâche 7.
_page_memorisee = st.session_state.get("page")
_index_initial = PAGES.index(_page_memorisee) if _page_memorisee in PAGES else 0
page = st.sidebar.radio("Choisir une page", PAGES, index=_index_initial)
st.session_state["page"] = page
```

- [ ] **Step 4: Relancer et vérifier que l'échec a changé de nature**

Run : `./venv/bin/python -m pytest tests/test_navigation.py -q`
Expected : **2 passed, 1 xfailed**. L'`xfail` est le défaut réel : `pages_definies` contient `🔗 Scraping URLs`, `📋 Templates` et `⚙️ Configuration`, absents de `PAGES`.

Pour le constater explicitement :

Run : `./venv/bin/python -m pytest tests/test_navigation.py -q -rx --runxfail`
Expected : **FAIL** avec `AssertionError: assert {'⚙️ Configuration', '📋 Templates', '🔗 Scraping URLs'} == set()`

- [ ] **Step 5: Lancer la suite complète**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS**, aucune régression (le `xfail` compte comme attendu).

- [ ] **Step 6: Commit**

```bash
git add tests/test_navigation.py app_advanced.py
git commit -m "test(nav): garde-fou pages definies vs menu + constante PAGES"
```

---

### Task 2: Test de fumée sur chaque page du menu

Le second garde-fou, posé avant toute modification : il charge réellement chaque page et échoue sur n'importe quelle exception. C'est lui qui protégera les déplacements de blocs des Tâches 5 et 6.

**Files:**
- Test: `tests/test_pages_smoke.py` (créer)

**Interfaces:**
- Consumes: `tests.test_navigation.arbre_app`, `tests.test_navigation.pages_du_menu` ; `st.session_state["page"]` (Tâche 1).
- Produces: rien pour les tâches suivantes.

- [ ] **Step 1: Écrire le test**

Créer `tests/test_pages_smoke.py` :

```python
# -*- coding: utf-8 -*-
"""Chaque page du menu doit se charger sans lever d'exception."""

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_navigation import arbre_app, pages_du_menu

PAGES = pages_du_menu(arbre_app())


@pytest.mark.parametrize("page", PAGES)
def test_la_page_se_charge_sans_exception(page):
    at = AppTest.from_file("app_advanced.py", default_timeout=90)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["page"] == page
```

- [ ] **Step 2: Lancer le test**

Run : `./venv/bin/python -m pytest tests/test_pages_smoke.py -q`
Expected : **6 passed** — une par entrée du menu actuel. Si une page échoue ici, c'est un défaut préexistant : le corriger avant de continuer.

- [ ] **Step 3: Lancer la suite complète**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS**

- [ ] **Step 4: Commit**

```bash
git add tests/test_pages_smoke.py
git commit -m "test(nav): fumee AppTest sur chaque page du menu"
```

---

### Task 3: Supprimer la page Chasse

`🎯 Chasse` est un sous-ensemble strict de `Recherche › Candidats` : mêmes champs en moins riche, même appel `run_scraper`. Sa suppression retire l'ambiguïté « laquelle des deux j'utilise ».

**Files:**
- Modify: `app_advanced.py` — bloc `elif page == "🎯 Chasse":` (lignes 763-834) et l'entrée correspondante de `PAGES`

**Interfaces:**
- Consumes: `PAGES` (Tâche 1), les deux tests garde-fous (Tâches 1 et 2).
- Produces: `PAGES` à 5 entrées.

- [ ] **Step 1: Retirer l'entrée du menu**

Dans la constante `PAGES`, supprimer la ligne :

```python
    "🎯 Chasse",
```

- [ ] **Step 2: Supprimer le bloc de la page**

Supprimer le bloc entier commençant par `elif page == "🎯 Chasse":` jusqu'à la ligne précédant `elif page == "✉️ Messages":` (lignes 763-834 avant modification). Ne toucher à aucun autre bloc.

- [ ] **Step 3: Vérifier qu'aucun symbole ne devient orphelin**

Run : `./venv/bin/python -c "import ast,sys; ast.parse(open('app_advanced.py',encoding='utf-8').read()); print('syntaxe OK')"`
Expected : `syntaxe OK`

Run : `./venv/bin/python -c "
src = open('app_advanced.py', encoding='utf-8').read()
for nom in ('SECTEURS', 'CONCURRENTS', 'ECOLES', 'parse_entreprises'):
    n = src.count(nom)
    print(nom, n)
    assert n >= 2, nom + ' n est plus utilise : retirer son import'
"`
Expected : chaque symbole reste utilisé (import + au moins un usage). `SECTEURS` et `parse_entreprises` restent employés par `Recherche › Candidats`.

- [ ] **Step 4: Lancer les tests**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS** — le test de fumée tourne maintenant sur 5 pages, `test_toute_entree_de_menu_correspond_a_une_page` reste vert, et le garde-fou reste `xfailed` (3 orphelines subsistent).

- [ ] **Step 5: Commit**

```bash
git add app_advanced.py
git commit -m "refac(nav): supprime la page Chasse, doublon de Recherche > Candidats"
```

---

### Task 4: Supprimer Templates — page et code de persistance

La fonctionnalité est retirée en entier : la page, les deux méthodes de base et la création de table. La table déjà présente chez les utilisateurs n'est pas détruite ; elle cesse simplement d'être lue et écrite.

**Files:**
- Modify: `app_advanced.py` — bloc `elif page == "📋 Templates":` (lignes 629-703 d'origine)
- Modify: `database.py:72-84` (création de table), `database.py:373-410` (les deux méthodes)
- Test: `tests/test_templates_supprimes.py` (créer)

**Interfaces:**
- Consumes: `PAGES` (Tâche 1).
- Produces: `DatabaseManager` sans `sauvegarder_template` ni `get_templates`.

- [ ] **Step 1: Écrire le test qui échoue**

Créer `tests/test_templates_supprimes.py` :

```python
# -*- coding: utf-8 -*-
"""La fonctionnalité Templates a été retirée (décision du 2026-09-16).

Ce test empêche sa réintroduction par inadvertance — du code de
persistance qui ne sert plus finit par être relu, maintenu, voire recyclé.
"""

import sqlite3

from database import DatabaseManager


def test_le_gestionnaire_n_expose_plus_de_methodes_template():
    restantes = [n for n in dir(DatabaseManager) if "template" in n.lower()]
    assert restantes == []


def test_une_base_neuve_ne_cree_plus_la_table_templates(tmp_path):
    chemin = tmp_path / "essai.db"
    DatabaseManager(db_file=str(chemin))

    conn = sqlite3.connect(chemin)
    noms = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()

    assert "templates" not in noms
    # Les tables utiles restent créées
    assert "profiles" in noms
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Run : `./venv/bin/python -m pytest tests/test_templates_supprimes.py -q`
Expected : **2 failed** — `assert ['get_templates', 'sauvegarder_template'] == []`, et `'templates' in noms`.

- [ ] **Step 3: Supprimer la page**

Dans `app_advanced.py`, supprimer le bloc entier `elif page == "📋 Templates":` jusqu'à la ligne précédant `elif page == "💾 Historique":`. `📋 Templates` n'est pas dans `PAGES` — rien à y retirer.

- [ ] **Step 4: Supprimer la création de table**

Dans `database.py`, supprimer ces lignes (72-84) :

```python
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
```

- [ ] **Step 5: Supprimer les deux méthodes**

Dans `database.py`, supprimer intégralement `def sauvegarder_template(...)` et `def get_templates(...)` (lignes 373-410), en conservant les méthodes qui les entourent.

- [ ] **Step 6: Relancer le test**

Run : `./venv/bin/python -m pytest tests/test_templates_supprimes.py -q`
Expected : **2 passed**

- [ ] **Step 7: Lancer la suite complète**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS** — le garde-fou reste `xfailed` (2 orphelines : Scraping URLs, Configuration).

- [ ] **Step 8: Commit**

```bash
git add app_advanced.py database.py tests/test_templates_supprimes.py
git commit -m "refac: supprime la fonctionnalite Templates (page + persistance)"
```

---

### Task 5: Scraping URLs devient l'onglet « Par URLs » de Recherche

Le bloc est déplacé tel quel dans un troisième onglet. Aucune logique n'est réécrite : mêmes widgets, mêmes `key=`, même appel `run_url_scraper`.

**Files:**
- Modify: `app_advanced.py:288` (déclaration des onglets), bloc `elif page == "🔗 Scraping URLs":` (lignes 524-628 d'origine)

**Interfaces:**
- Consumes: `PAGES` (Tâche 1) ; les garde-fous des Tâches 1 et 2.
- Produces: `Recherche` comporte trois onglets ; plus de branche `page == "🔗 Scraping URLs"`.

- [ ] **Step 1: Ouvrir un troisième onglet**

Dans `app_advanced.py`, remplacer la ligne 288 :

```python
    tab1, tab2 = st.tabs(["👤 Candidats", "🏢 Clients/Entreprises"])
```

par :

```python
    tab1, tab2, tab3 = st.tabs(
        ["👤 Candidats", "🏢 Clients/Entreprises", "🔗 Par URLs"]
    )
```

- [ ] **Step 2: Déplacer le corps de la page dans l'onglet**

Le bloc à déplacer va de la ligne qui suit `elif page == "🔗 Scraping URLs":` — elle commence par `    st.header("🔗 Scraping par URLs de profils")` — jusqu'à la dernière ligne avant `elif page == "📋 Templates":` (supprimé en Tâche 4) ou, celui-ci retiré, avant `elif page == "💾 Historique":`.

Couper ce corps (sans la ligne `elif` elle-même) et le coller à la fin du bloc `elif page == "🔍 Recherche":`, sous un nouvel en-tête :

```python
    # TAB 3: PAR URLS (ancienne page « Scraping URLs »)
    with tab3:
        <corps déplacé, réindenté d'un niveau>
```

Le corps déplacé conserve ses `key=` (`inviter_urls`, `btn_url_scraping`, …) et son appel `scraper.run_url_scraper(...)`. Adapter uniquement l'indentation : le corps passe de 4 espaces (sous `elif`) à 8 espaces (sous `with tab3:`). Remplacer son `st.header("🔗 Scraping par URLs de profils")` par `st.subheader("Traiter une liste d'URLs de profils")`, puisqu'il n'est plus une page mais un onglet.

- [ ] **Step 3: Supprimer la branche devenue vide**

Supprimer la ligne `elif page == "🔗 Scraping URLs":` et tout ce qu'il en reste.

- [ ] **Step 4: Vérifier la syntaxe et l'absence de clés en conflit**

Run : `./venv/bin/python -c "
import ast, collections
src = open('app_advanced.py', encoding='utf-8').read()
ast.parse(src)
cles = [n.value for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.keyword) and n.arg == 'key'
        and isinstance(n.value, ast.Constant)]
vals = [c.value for c in cles]
doublons = [k for k, n in collections.Counter(vals).items() if n > 1]
print('doublons de key:', doublons)
assert not doublons, doublons
print('syntaxe OK, aucune cle en double')
"`
Expected : `syntaxe OK, aucune cle en double`

- [ ] **Step 5: Lancer les tests**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS** — le test de fumée charge `🔍 Recherche` avec ses trois onglets sans exception ; le garde-fou reste `xfailed` (1 orpheline : Configuration).

- [ ] **Step 6: Commit**

```bash
git add app_advanced.py
git commit -m "refac(nav): Scraping URLs devient l'onglet Par URLs de Recherche"
```

---

### Task 6: Configuration devient le volet « Réglages » — le garde-fou passe au vert

Dernière réconciliation : après cette tâche, pages définies et entrées de menu coïncident. Le `xfail(strict=True)` de la Tâche 1 le signalera de lui-même en faisant échouer la suite — c'est le signal attendu pour retirer le marqueur.

**Files:**
- Modify: `app_advanced.py` — bloc `elif page == "⚙️ Configuration":` (lignes 956-1011 d'origine), zone barre latérale (après la ligne 115)
- Modify: `tests/test_navigation.py` — retrait du marqueur `xfail`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces: `set(pages_definies) == set(pages_du_menu)` — l'invariant du garde-fou est enfin vrai.

- [ ] **Step 1: Déplacer le bloc dans un volet de la barre latérale**

Le bloc à déplacer va de la ligne qui suit `elif page == "⚙️ Configuration":` — elle commence par `    st.header("⚙️ Configuration")` — jusqu'à la dernière ligne avant le commentaire `# Footer` en fin de fichier.

Couper ce corps et le coller dans `app_advanced.py` juste après la fin du volet `🌐 Mon proxy (recommandé)` (qui commence ligne 115), sous :

```python
with st.sidebar.expander("⚙️ Réglages"):
    <corps déplacé, réindenté>
```

Remplacer son `st.header("⚙️ Configuration")` par rien (le titre du volet suffit) et rétrograder ses `st.subheader(...)` en `st.markdown("**…**")`, l'espace latéral étant étroit.

- [ ] **Step 2: Supprimer la branche devenue vide**

Supprimer la ligne `elif page == "⚙️ Configuration":` et son reliquat.

- [ ] **Step 3: Lancer la suite et constater l'échec attendu du xfail strict**

Run : `./venv/bin/python -m pytest -q`
Expected : **FAIL** — `[XPASS(strict)] 4 pages orphelines depuis c6035c0…`. C'est le succès de la refonte : le test réussit alors qu'on le déclarait en échec.

- [ ] **Step 4: Retirer le marqueur**

Dans `tests/test_navigation.py`, supprimer le décorateur complet :

```python
@pytest.mark.xfail(
    strict=True,
    reason="4 pages orphelines depuis c6035c0 — résorbé par la Tâche 6 du plan "
           "2026-09-16-refonte-navigation ; retirer ce marqueur à ce moment-là.",
)
```

Supprimer aussi l'import `pytest` s'il n'est plus utilisé dans le fichier.

- [ ] **Step 5: Relancer la suite**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS**, sans aucun `xfailed`. Les cinq pages du menu sont exactement les cinq pages définies.

- [ ] **Step 6: Commit**

```bash
git add app_advanced.py tests/test_navigation.py
git commit -m "refac(nav): Configuration devient un volet lateral, plus aucune page orpheline"
```

---

### Task 7: Navigation à boutons et icônes vectorielles

Le `st.radio` ne sait afficher que du texte : les icônes de la maquette imposent de passer à des boutons. Streamlit 1.58 accepte les icônes Material (`icon=":material/search:"`), qui sont vectorielles comme les SVG de la maquette — c'est leur équivalent implémentable, sans HTML injecté ni widget tiers.

**Files:**
- Modify: `app_advanced.py` — zone `PAGES` / navigation (Tâche 1)
- Modify: `wefiit_theme.py` — une règle CSS pour l'état actif
- Test: `tests/test_navigation.py` — ajout d'un test sur la table d'icônes

**Interfaces:**
- Consumes: `PAGES` (Tâche 1), `st.session_state["page"]`.
- Produces: `app_advanced.ICONES_PAGES: dict[str, str]` — un libellé de `PAGES` vers une icône Material.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `tests/test_navigation.py` :

```python
def icones_pages(arbre: ast.Module) -> dict:
    """Table ICONES_PAGES : un libellé de menu vers une icône Material."""
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id == "ICONES_PAGES":
                    return {k.value: v.value for k, v in
                            zip(noeud.value.keys, noeud.value.values)}
    raise AssertionError("Table ICONES_PAGES introuvable dans app_advanced.py")


def test_chaque_entree_de_menu_a_une_icone():
    arbre = arbre_app()
    assert set(icones_pages(arbre)) == set(pages_du_menu(arbre))


def test_les_icones_sont_des_symboles_material():
    # Les emoji sont écartés au profit d'icônes vectorielles (maquette validée
    # le 2026-09-16). Le format Material est le seul que Streamlit sache rendre.
    for icone in icones_pages(arbre_app()).values():
        assert icone.startswith(":material/") and icone.endswith(":"), icone
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Run : `./venv/bin/python -m pytest tests/test_navigation.py -q`
Expected : **2 failed** — `AssertionError: Table ICONES_PAGES introuvable dans app_advanced.py`

- [ ] **Step 3: Remplacer le radio par des boutons**

Les libellés de `PAGES` **gardent leur emoji** : ce sont les clés comparées dans les branches `if page == "📊 Dashboard"`, et les renommer obligerait à retoucher chaque branche pour aucun gain. L'emoji est simplement retiré à l'affichage (`split(" ", 1)[1]`), l'icône Material le remplaçant à l'écran.

Dans `app_advanced.py`, remplacer le bloc de navigation créé en Tâche 1 par :

```python
# Source de vérité du menu. tests/test_navigation.py la confronte aux
# branches `if page == …` : toute page définie doit figurer ici.
PAGES = [
    "📊 Dashboard",
    "🔍 Recherche",
    "✉️ Messages",
    "💾 Historique",
    "📜 Logs",
]

# Icônes vectorielles Material — st.radio ne rend que du texte, d'où les
# boutons ci-dessous (maquette validée le 2026-09-16).
ICONES_PAGES = {
    "📊 Dashboard": ":material/dashboard:",
    "🔍 Recherche": ":material/search:",
    "✉️ Messages": ":material/mail:",
    "💾 Historique": ":material/database:",
    "📜 Logs": ":material/terminal:",
}

_page_memorisee = st.session_state.get("page")
if _page_memorisee not in PAGES:
    st.session_state["page"] = PAGES[0]

st.sidebar.markdown("**Navigation**")
for _libelle in PAGES:
    _actif = st.session_state["page"] == _libelle
    if st.sidebar.button(
        _libelle.split(" ", 1)[1],
        icon=ICONES_PAGES[_libelle],
        key=f"nav_{_libelle}",
        type="primary" if _actif else "secondary",
        use_container_width=True,
    ):
        st.session_state["page"] = _libelle
        st.rerun()

page = st.session_state["page"]
```

- [ ] **Step 4: Styler l'état actif**

Dans `wefiit_theme.py`, insérer juste avant le commentaire `/* Badge / pilule utilitaire (statuts) */` :

```css
/* Navigation latérale : l'item actif est une pilule teintée, pas un bouton
   plein — le navy massif de .stButton[kind="primary"] écraserait le menu. */
section[data-testid="stSidebar"] .stButton > button {{ justify-content:flex-start !important; border:none !important; background:transparent !important; font-weight:500 !important; border-radius:11px !important; padding:10px 12px !important; }}
section[data-testid="stSidebar"] .stButton > button:hover {{ background:var(--wf-surface2) !important; }}
section[data-testid="stSidebar"] .stButton > button[kind="primary"],
section[data-testid="stSidebar"] .stButton > button[kind="primary"] * {{ background:var(--wf-accent-tint) !important; color:var(--wf-accent) !important; font-weight:700 !important; box-shadow:none !important; }}
```

Attention : le fichier construit ce CSS dans une f-string — les accolades CSS y sont doublées (`{{` et `}}`). Respecter cette convention, sinon l'injection lève une erreur de formatage.

- [ ] **Step 5: Relancer les tests**

Run : `./venv/bin/python -m pytest tests/test_navigation.py -q`
Expected : **5 passed**

- [ ] **Step 6: Adapter le test de fumée s'il pilotait le radio**

Le test de la Tâche 2 fixe `at.session_state["page"]` et ne touche pas au widget : il doit passer sans modification.

Run : `./venv/bin/python -m pytest tests/test_pages_smoke.py -q`
Expected : **5 passed**

- [ ] **Step 7: Lancer la suite complète**

Run : `./venv/bin/python -m pytest -q`
Expected : **PASS**

- [ ] **Step 8: Vérifier à l'œil**

Run : `SCRAPER_HEADLESS=false SCRAPER_STEALTH=false ./venv/bin/streamlit run app_advanced.py --server.port 8501`
Ouvrir `http://localhost:8501` : cinq boutons à icônes dans la barre latérale, l'actif en pilule teintée, les trois volets dessous (cookie, proxy, Réglages), et l'onglet « Par URLs » présent dans Recherche.

- [ ] **Step 9: Commit**

```bash
git add app_advanced.py wefiit_theme.py tests/test_navigation.py
git commit -m "feat(nav): boutons a icones Material dans la barre laterale"
```

---

## Hors périmètre de ce plan

- L'extraction des pages en modules (`pages/recherche.py`, …) — section 7 de la spec, décision distincte.
- Le bandeau « Ce que LinkedIn recevra » de la maquette : il relève de la page Recherche, pas de la navigation. À planifier séparément.
- Toute modification des filtres de recherche livrés le 2026-09-16.
