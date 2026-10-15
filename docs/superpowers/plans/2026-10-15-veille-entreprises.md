# Veille entreprises (livraison 1) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Une page **🏢 Veille** où chacun suit 20 à 50 entreprises : un moteur lit la page « À propos » LinkedIn de chacune, la recoupe avec l'annuaire officiel de l'État, cherche ses employés Product / Data / IA, et un récap « Nouveau aujourd'hui » montre ce qui est apparu depuis la dernière visite.

**Architecture :** Un **moteur de veille sans Streamlit** (`veille.py`) appelé par un bouton de l'application — et, en livraison 3, par un réveil programmé. Toute la logique de décision vit dans deux modules purs testables sans navigateur ni réseau (`utils/veille_regles.py`, `utils/annuaire.py`) ; le stockage dans `veille_store.py` (mêmes fichier SQLite que le reste) ; un verrou empêche deux sessions LinkedIn simultanées. La page est écrite dans son propre module (`ui/page_veille.py`).

**Tech Stack :** Python 3.10+, Playwright (Chromium canal `chrome`), Streamlit 1.58, SQLite, `urllib` (pas de dépendance nouvelle), pytest, `streamlit.testing.v1.AppTest`.

**Spec :** [docs/superpowers/specs/2026-10-15-veille-entreprises-design.md](../specs/2026-10-15-veille-entreprises-design.md)

## Global Constraints

- **Langue :** code, commentaires, docstrings, noms et textes à l'écran en **français**. Commentaires = pourquoi, jamais quoi.
- **Version visée :** `1.6.0` (fichier `VERSION`, source unique).
- **Aucune dépendance nouvelle** : l'annuaire s'interroge avec `urllib.request`. Rien à installer chez les collègues.
- **Aucune IA, aucune clé API** dans cette livraison.
- **Aucune invitation automatique.** Une invitation ne part que sur clic, case décochée par défaut, plafond quotidien vérifié avant l'envoi.
- **Aucune liste vide sans explication, aucune donnée plausible mais fausse** : l'annuaire n'est retenu que s'il recoupe LinkedIn ; sinon « non rapprochée » avec motif.
- **Tests :** jamais d'appel réseau ni de visite LinkedIn ; un Chromium local headless est autorisé uniquement pour exécuter un extracteur JS sur une fixture synthétique via `page.set_content` (réseau coupé) ; jamais d'écriture dans les données réelles du poste ni dans `logs/` du dépôt ; aucune donnée réelle (nom, URL, SIREN) dans le dépôt — fixtures inventées.
- **Python :** `venv/bin/python -m pytest` (pas de `python` dans le PATH).
- **Commits :** messages en français dans le style du dépôt, terminés par une ligne vide puis `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Écarts assumés avec la spec (à relire par Thomas)

1. **Une seule recherche par entreprise**, mots-clés de toutes les familles cochées en OU, puis classement de chaque contact dans sa famille d'après son intitulé — au lieu d'une recherche par famille. Trois fois moins de pages LinkedIn. Conséquence : **un curseur de reprise par entreprise**, remis à zéro quand les familles cochées changent (spec §7 disait « par famille »).
2. **Le budget se compte en pages LinkedIn chargées**, dans un compteur à part (`pages_veille`) du fichier de limites quotidiennes : page « À propos » = 1, page de résultats = 1. **Par défaut 20 pages par jour**, réglable de 5 à 40 — et non « 50 % du quota de 80 profils » (spec §6). Motif : la spec demandait de « ne pas solliciter LinkedIn davantage qu'aujourd'hui » ; 80 profils récupérés par recherche représentent ~8 pages de résultats, et les comptes gratuits ont une limite mensuelle de recherches (« commercial use limit »). 20 pages ≈ 6 entreprises par jour ≈ une entreprise revue tous les 4 à 8 jours pour 25 à 50 suivies. Les contacts trouvés en veille n'incrémentent pas le compteur de profils.
3. **La fiche LinkedIn et l'annuaire ne sont relus que tous les 30 jours** : une fiche ne change pas chaque matin, et chaque relecture coûte une page. Les recherches de personnes, elles, ont lieu à chaque passage.

## Ce qu'on sait de la vraie page (capture du 2026-10-15, hors dépôt)

`https://www.linkedin.com/company/<slug>/about/` affiche un `<dl>` dont les `<dt>` sont, en français : `Site web`, `Téléphone`, `Page vérifiée`, `Secteur`, `Taille de l’entreprise` (apostrophe typographique U+2019), `Siège social`, `Fondée en`, `Spécialisations`. Chaque `<dt>` est suivi d'un ou plusieurs `<dd>`. Exemple de valeurs : `https://www.exemple.co` ; `+33 1 00 00 00 00` puis `Le numéro de téléphone est le +33 1 00 00 00 00` ; `Services et conseil aux entreprises` ; `201-500 employés` puis `198 membres associés` ; `Paris, Paris` ; `2014`. L'identifiant numérique de l'entreprise figure dans le lien « voir les employés » : `…/search/results/people/?currentCompany=%5B%224998677%22%5D&origin=COMPANY_PAGE_CANNED_SEARCH`. La page contient d'autres `h1`/`h2` (« 0 notification au total »…) : le nom se lit dans `main h1`.

L'annuaire (`https://recherche-entreprises.api.gouv.fr/search?q=<nom>&per_page=25`, sans clé) renvoie `{"results": [...], "total_results": N}`. Chaque résultat : `siren`, `nom_complet`, `nom_raison_sociale`, `sigle`, `activite_principale` (ex. `70.22Z`), `tranche_effectif_salarie` (code INSEE, ex. `22`), `annee_tranche_effectif_salarie`, `date_creation`, `etat_administratif` (`A` actif / `C` cessé), `categorie_entreprise`, `siege` (`libelle_commune` en majuscules, `code_postal`…), `dirigeants` — liste d'objets `{"type_dirigeant": "personne physique", "nom", "prenoms", "qualite"}` ou `{"type_dirigeant": "personne morale", "denomination", "siren", "qualite"}`. La recherche « thiga » renvoie 14 sociétés, dont une seule a son siège à `PARIS` : le recoupement par commune suffit à lever l'homonymie.

**Mots-clés LinkedIn :** une requête **entièrement** entre parenthèses renvoie 0 résultat (constaté, cf. `LinkedInScraperV2._normalize_keyword`). L'expression OU s'écrit donc `"a" OR "b"` **sans** parenthèses englobantes.

## Review Focus

1. **Homonyme dans l'annuaire** (« Thiga » → 14 sociétés) : seule celle dont la commune du siège égale celle de LinkedIn est retenue ; deux candidates ou zéro → « non rapprochée » avec motif. → tests Task 2.
2. **Entreprise sans `company_id` lisible** (page « À propos » illisible ou entreprise introuvable par son nom) : état « non identifiée » ou « illisible », aucune recherche de personnes lancée avec un identifiant vide (qui renverrait tout LinkedIn). → tests Task 2 (url) et Task 6.
3. **Budget épuisé au milieu d'une entreprise** : la page suivante n'est pas chargée, le curseur garde la dernière page lue, le rapport dit « budget ». → test Task 6.
4. **Recherche manuelle pendant la veille** : refusée avec un message clair, pas d'exception à l'écran ; verrou abandonné par un processus mort → considéré libre. → tests Task 4.
5. **Contact déjà au fichier** (URL écrite autrement : `http://`, majuscules, `?miniProfileUrn=`) : relié à l'entreprise mais **pas** compté « nouveau ». → test Task 3.

---

## File Structure

| Fichier | Responsabilité | Action |
|---|---|---|
| `utils/veille_regles.py` | Familles de postes, expression de recherche, URL de recherche, classement d'un intitulé, lecture des champs « À propos », réglages (lecture/écriture JSON), sélection du lot | Créer |
| `utils/annuaire.py` | Appel de l'annuaire officiel, normalisation des noms/communes, choix du candidat, tranches d'effectif, dirigeants utiles | Créer |
| `veille_store.py` | Tables et requêtes de la veille dans la base SQLite de l'utilisateur | Créer |
| `utils/verrou_linkedin.py` | Verrou « une seule session LinkedIn à la fois » par utilisateur | Créer |
| `utils/human_behavior.py` | Compteur quotidien `pages_veille` | Modifier |
| `scraper_v2_sync.py` | Les méthodes existantes respectent le verrou | Modifier |
| `utils/dom_selectors.py` | `extract_page_apropos_js()` | Modifier |
| `veille.py` | Moteur : un passage de veille ; ligne de commande | Créer |
| `ui/__init__.py`, `ui/invitations.py` | Bloc « récupérer et inviter » partagé (Profils similaires + Veille) | Créer |
| `ui/page_veille.py` | La page 🏢 Veille | Créer |
| `app_advanced.py` | Menu, branche de page, Profils similaires branché sur `ui/invitations.py` | Modifier |
| `tests/test_veille_regles.py`, `tests/test_annuaire.py`, `tests/test_veille_store.py`, `tests/test_verrou_linkedin.py`, `tests/test_extracteur_apropos.py`, `tests/test_moteur_veille.py`, `tests/test_page_veille.py` | Tests | Créer |
| `NOUVEAUTES.md`, `VERSION` | 1.6.0 | Modifier |

---

## Task 1 : Règles de la veille (module pur)

**Files:**
- Create: `utils/veille_regles.py`
- Test: `tests/test_veille_regles.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `FAMILLES: dict[str, tuple[str, ...]]` — clés `"Product"`, `"Data"`, `"IA"`.
  - `expression_mots_cles(familles: list[str], intitules_libres: list[str]) -> str`
  - `url_recherche_personnes(company_id: str, expression: str, page: int) -> str` — lève `ValueError` si `company_id` n'est pas numérique.
  - `famille_de_l_intitule(intitule: str, familles: list[str], intitules_libres: list[str]) -> str` — une clé de `FAMILLES`, `"Autre"` sinon.
  - `signature_familles(familles, intitules_libres) -> str`
  - `fiche_depuis_apropos(champs: dict[str, list[str]]) -> dict[str, str]` — clés possibles : `site`, `telephone`, `secteur`, `taille`, `membres`, `siege`, `fondee`, `specialisations`.
  - `@dataclass ReglagesVeille(familles: list[str], intitules_libres: list[str], pages_par_jour: int)` ; `charger_reglages(config_dir) -> ReglagesVeille` ; `sauver_reglages(config_dir, reglages) -> None` ; constantes `PAGES_PAR_JOUR_DEFAUT = 20`, `PAGES_MIN = 5`, `PAGES_MAX = 40`, `PAGES_MAX_PAR_ENTREPRISE = 2`, `RELECTURE_FICHE_JOURS = 30`.
  - `ordre_du_lot(entreprises: list[dict]) -> list[dict]` — entreprises identifiables triées : jamais passées d'abord, puis `derniere_veille` croissante ; exclut l'état `"non_identifiee"` sans `url_linkedin`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_veille_regles.py` :

```python
# -*- coding: utf-8 -*-
"""Règles de la veille : ce qu'on cherche, comment on classe, ce qu'on lit.

Tout ici décide sans navigateur ni réseau. Une erreur dans ces règles se
paie en pages LinkedIn gaspillées ou en contacts mal rangés.
"""

import pytest

from utils.veille_regles import (
    FAMILLES, PAGES_PAR_JOUR_DEFAUT, ReglagesVeille, charger_reglages,
    expression_mots_cles, famille_de_l_intitule, fiche_depuis_apropos,
    ordre_du_lot, sauver_reglages, signature_familles, url_recherche_personnes,
)


def test_les_trois_familles_existent():
    assert set(FAMILLES) == {"Product", "Data", "IA"}


def test_l_expression_n_est_pas_entierement_parenthesee():
    # LinkedIn renvoie 0 résultat pour « ("a" OR "b") » : constaté en 2026.
    expr = expression_mots_cles(["Product"], [])
    assert not (expr.startswith("(") and expr.endswith(")"))
    assert '"product manager"' in expr.lower()
    assert " OR " in expr


def test_l_expression_combine_familles_et_intitules_libres_sans_doublon():
    expr = expression_mots_cles(["Product", "Data"], ["Product Manager", "Growth Lead"])
    termes = [t.strip().strip('"').lower() for t in expr.split(" OR ")]
    assert "growth lead" in termes
    assert "data scientist" in termes
    assert termes.count("product manager") == 1


def test_une_expression_vide_leve():
    with pytest.raises(ValueError):
        expression_mots_cles([], [])


def test_l_url_de_recherche_filtre_sur_l_entreprise_et_pagine():
    url = url_recherche_personnes("4998677", '"a" OR "b"', 2)
    assert url.startswith("https://www.linkedin.com/search/results/people/?")
    assert "currentCompany=%5B%224998677%22%5D" in url
    assert "page=2" in url
    assert "keywords=" in url


def test_l_url_refuse_un_identifiant_vide_ou_non_numerique():
    # Sans filtre entreprise, la recherche renverrait tout LinkedIn.
    for mauvais in ("", None, "thiga", "12a"):
        with pytest.raises(ValueError):
            url_recherche_personnes(mauvais, '"a"', 1)


@pytest.mark.parametrize("intitule,famille", [
    ("Senior Product Manager @Acme", "Product"),
    ("Head of Data & Analytics", "Data"),
    ("Machine Learning Engineer", "IA"),
    ("Responsable IA générative", "IA"),
    ("Directeur commercial", "Autre"),
])
def test_un_intitule_est_range_dans_sa_famille(intitule, famille):
    assert famille_de_l_intitule(intitule, ["Product", "Data", "IA"], []) == famille


def test_une_famille_non_cochee_n_est_pas_attribuee():
    assert famille_de_l_intitule("Data Scientist", ["Product"], []) == "Autre"


def test_un_intitule_libre_range_dans_sa_propre_categorie():
    assert famille_de_l_intitule("Growth Lead Europe", ["Product"], ["Growth Lead"]) == "Growth Lead"


def test_la_signature_change_quand_les_familles_changent():
    assert signature_familles(["Product"], []) != signature_familles(["Product", "Data"], [])
    assert signature_familles(["Data", "Product"], []) == signature_familles(["Product", "Data"], [])


def test_la_fiche_se_lit_dans_les_champs_a_propos():
    champs = {
        "Site web": ["https://www.exemple.co"],
        "Téléphone": ["+33 1 00 00 00 00", "Le numéro de téléphone est le +33 1 00 00 00 00"],
        "Secteur": ["Services et conseil aux entreprises"],
        "Taille de l’entreprise": ["201-500 employés", "198 membres associés"],
        "Siège social": ["Paris, Paris"],
        "Fondée en": ["2014"],
        "Spécialisations": ["Product Management, Discovery"],
        "Page vérifiée": ["1 juin 2024"],
    }
    assert fiche_depuis_apropos(champs) == {
        "site": "https://www.exemple.co",
        "telephone": "+33 1 00 00 00 00",
        "secteur": "Services et conseil aux entreprises",
        "taille": "201-500 employés",
        "membres": "198",
        "siege": "Paris, Paris",
        "fondee": "2014",
        "specialisations": "Product Management, Discovery",
    }


def test_l_apostrophe_droite_est_aussi_reconnue():
    assert fiche_depuis_apropos({"Taille de l'entreprise": ["11-50 employés"]}) == {
        "taille": "11-50 employés"
    }


def test_des_champs_vides_donnent_une_fiche_vide():
    assert fiche_depuis_apropos({}) == {}


def test_les_reglages_par_defaut(tmp_path):
    r = charger_reglages(tmp_path)
    assert r.familles == ["Product", "Data", "IA"]
    assert r.intitules_libres == []
    assert r.pages_par_jour == PAGES_PAR_JOUR_DEFAUT == 20


def test_les_reglages_survivent_a_un_aller_retour(tmp_path):
    sauver_reglages(tmp_path, ReglagesVeille(["Data"], ["Growth Lead"], 12))
    assert charger_reglages(tmp_path) == ReglagesVeille(["Data"], ["Growth Lead"], 12)


def test_un_budget_hors_bornes_est_ramene_dans_les_bornes(tmp_path):
    sauver_reglages(tmp_path, ReglagesVeille(["Data"], [], 500))
    assert charger_reglages(tmp_path).pages_par_jour == 40


def test_un_fichier_de_reglages_corrompu_donne_les_defauts(tmp_path):
    (tmp_path / "reglages_veille.json").write_text("{pas du json", encoding="utf-8")
    assert charger_reglages(tmp_path).pages_par_jour == 20


def test_le_lot_commence_par_les_jamais_passees_puis_les_plus_anciennes():
    entreprises = [
        {"id": 1, "etat": "identifiee", "url_linkedin": "u", "derniere_veille": "2026-10-10"},
        {"id": 2, "etat": "a_identifier", "url_linkedin": None, "derniere_veille": None},
        {"id": 3, "etat": "identifiee", "url_linkedin": "u", "derniere_veille": "2026-10-01"},
        {"id": 4, "etat": "non_identifiee", "url_linkedin": None, "derniere_veille": "2026-09-01"},
    ]
    assert [e["id"] for e in ordre_du_lot(entreprises)] == [2, 3, 1]


def test_une_entreprise_non_identifiee_avec_un_lien_colle_revient_dans_le_lot():
    entreprises = [{"id": 4, "etat": "non_identifiee", "url_linkedin": "https://www.linkedin.com/company/x/", "derniere_veille": None}]
    assert [e["id"] for e in ordre_du_lot(entreprises)] == [4]
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_veille_regles.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.veille_regles'`

- [ ] **Step 3 : Écrire le module**

Créer `utils/veille_regles.py` :

```python
# -*- coding: utf-8 -*-
"""Règles de la veille entreprises : quoi chercher, comment ranger, quoi lire.

Module pur (hors lecture/écriture du petit fichier de réglages) : aucune
dépendance à Playwright, Streamlit ni SQLite. Toute décision de la veille
qui peut se tester sans navigateur vit ici.
"""

import json
import unicodedata
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Intitulés cherchés par famille. Ils servent deux fois : dans la recherche
# LinkedIn (mots-clés en OU) et pour ranger chaque contact trouvé.
FAMILLES = {
    "Product": ("product manager", "product owner", "head of product",
                "vp product", "chief product officer", "product director",
                "directeur produit", "responsable produit"),
    "Data": ("data scientist", "data engineer", "data analyst",
             "head of data", "chief data officer", "data manager",
             "responsable data"),
    "IA": ("machine learning", "ml engineer", "ai engineer", "head of ai",
           "intelligence artificielle", "responsable ia", "mlops",
           "ia générative", "generative ai"),
}

PAGES_PAR_JOUR_DEFAUT = 20
PAGES_MIN = 5
PAGES_MAX = 40
# Au-delà, une seule grande entreprise mangerait le budget du matin.
PAGES_MAX_PAR_ENTREPRISE = 2
# Une fiche ne change pas chaque matin ; chaque relecture coûte une page.
RELECTURE_FICHE_JOURS = 30

_FICHIER_REGLAGES = "reglages_veille.json"

# Libellés des <dt> de la page « À propos », apostrophes normalisées.
_CHAMPS_APROPOS = {
    "site web": "site",
    "telephone": "telephone",
    "secteur": "secteur",
    "taille de l'entreprise": "taille",
    "siege social": "siege",
    "fondee en": "fondee",
    "specialisations": "specialisations",
}


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _cle(libelle: str) -> str:
    return _sans_accents(libelle).replace("’", "'").strip().lower()


def _termes(familles, intitules_libres):
    vus, termes = set(), []
    for terme in [t for f in familles for t in FAMILLES.get(f, ())] + list(intitules_libres or []):
        cle = terme.strip().lower()
        if cle and cle not in vus:
            vus.add(cle)
            termes.append(terme.strip())
    return termes


def expression_mots_cles(familles, intitules_libres) -> str:
    """`"a" OR "b" OR …` — sans parenthèses englobantes.

    LinkedIn renvoie zéro résultat pour une requête entièrement entre
    parenthèses : constaté, et corrigé ailleurs par `_normalize_keyword`.
    """
    termes = _termes(familles, intitules_libres)
    if not termes:
        raise ValueError("aucun intitulé à chercher : cochez au moins une famille")
    return " OR ".join('"{}"'.format(t.replace('"', "")) for t in termes)


def url_recherche_personnes(company_id, expression: str, page: int) -> str:
    """Recherche de personnes chez une entreprise, page `page`.

    Refuse un identifiant absent ou non numérique : sans le filtre
    `currentCompany`, la recherche porterait sur tout LinkedIn et la veille
    rangerait des inconnus dans la fiche de l'entreprise.
    """
    if not company_id or not str(company_id).isdigit():
        raise ValueError(f"identifiant d'entreprise invalide : {company_id!r}")
    facette = urllib.parse.quote(f'["{company_id}"]', safe="")
    mots = urllib.parse.quote(expression, safe="")
    return ("https://www.linkedin.com/search/results/people/?"
            f"currentCompany={facette}&keywords={mots}"
            f"&origin=FACETED_SEARCH&page={int(page)}")


def famille_de_l_intitule(intitule: str, familles, intitules_libres) -> str:
    """La famille cochée dont un terme apparaît dans l'intitulé, sinon « Autre ».

    Les intitulés libres forment chacun leur propre catégorie : c'est ce que
    la personne a demandé explicitement, on ne le noie pas dans une famille.
    """
    bas = _sans_accents(intitule or "").lower()
    for libre in intitules_libres or []:
        if _sans_accents(libre).lower().strip() and _sans_accents(libre).lower().strip() in bas:
            return libre.strip()
    for famille in familles:
        for terme in FAMILLES.get(famille, ()):
            if _sans_accents(terme).lower() in bas:
                return famille
    return "Autre"


def signature_familles(familles, intitules_libres) -> str:
    """Empreinte des critères : si elle change, le curseur repart de zéro."""
    return "|".join(sorted(f.lower() for f in familles)) + "#" + \
        "|".join(sorted(t.strip().lower() for t in intitules_libres or []))


def fiche_depuis_apropos(champs: dict) -> dict:
    """Champs de la page « À propos » → fiche à plat.

    Prend la première valeur de chaque rubrique ; la taille est accompagnée
    d'une seconde ligne « N membres associés », gardée à part.
    """
    fiche = {}
    for libelle, valeurs in (champs or {}).items():
        cle = _CHAMPS_APROPOS.get(_cle(libelle))
        if not cle or not valeurs:
            continue
        fiche[cle] = valeurs[0].strip()
        if cle == "taille":
            for v in valeurs[1:]:
                chiffres = "".join(c for c in v.split("membres")[0] if c.isdigit())
                if "membres" in v and chiffres:
                    fiche["membres"] = chiffres
    return fiche


@dataclass
class ReglagesVeille:
    familles: list = field(default_factory=lambda: ["Product", "Data", "IA"])
    intitules_libres: list = field(default_factory=list)
    pages_par_jour: int = PAGES_PAR_JOUR_DEFAUT


def charger_reglages(config_dir) -> ReglagesVeille:
    """Réglages de la personne, ou les défauts si absents ou illisibles."""
    try:
        brut = json.loads((Path(config_dir) / _FICHIER_REGLAGES).read_text(encoding="utf-8"))
        r = ReglagesVeille(
            familles=[f for f in brut.get("familles", []) if f in FAMILLES],
            intitules_libres=[str(t) for t in brut.get("intitules_libres", []) if str(t).strip()],
            pages_par_jour=int(brut.get("pages_par_jour", PAGES_PAR_JOUR_DEFAUT)),
        )
    except Exception:
        return ReglagesVeille()
    r.pages_par_jour = max(PAGES_MIN, min(PAGES_MAX, r.pages_par_jour))
    return r


def sauver_reglages(config_dir, reglages: ReglagesVeille) -> None:
    dossier = Path(config_dir)
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / _FICHIER_REGLAGES).write_text(
        json.dumps(asdict(reglages), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ordre_du_lot(entreprises: list) -> list:
    """Les entreprises à passer, les plus en retard d'abord.

    Une entreprise « non identifiée » n'est reprise que si on lui a collé un
    lien : la rechercher encore par son nom referait la même erreur.
    """
    candidates = [
        e for e in entreprises
        if e.get("etat") != "non_identifiee" or e.get("url_linkedin")
    ]
    return sorted(candidates, key=lambda e: (e.get("derniere_veille") is not None,
                                             e.get("derniere_veille") or ""))
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `venv/bin/python -m pytest tests/test_veille_regles.py -q`
Expected: PASS (23 tests)

- [ ] **Step 5 : Commit**

```bash
git add utils/veille_regles.py tests/test_veille_regles.py
git commit -m "feat(veille): regles de recherche, de classement et de lecture"
```

---

## Task 2 : Annuaire officiel et recoupement

**Files:**
- Create: `utils/annuaire.py`
- Test: `tests/test_annuaire.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `class AnnuaireIndisponible(Exception)`
  - `interroger(nom: str, transport=None, delai: float = 8.0) -> list[dict]` — `transport(url, delai) -> bytes` injectable ; défaut `urllib.request`. Lève `AnnuaireIndisponible` sur erreur réseau, HTTP ou JSON.
  - `normaliser_nom(nom: str) -> str`
  - `commune_du_siege_linkedin(siege: str) -> str` — `"Paris, Paris"` → `"PARIS"`.
  - `choisir_candidat(resultats: list[dict], nom_linkedin: str, siege_linkedin: str) -> tuple[dict | None, str]` — `(candidat, "")` ou `(None, motif)`.
  - `fiche_depuis_annuaire(candidat: dict) -> dict[str, str]` — clés `siren`, `activite`, `effectif`, `creation`, `categorie`, `commune`, `dirigeants` (texte « Prénom Nom (qualité) ; … »).
  - `TRANCHES_EFFECTIF: dict[str, str]`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_annuaire.py` :

```python
# -*- coding: utf-8 -*-
"""Annuaire officiel : interrogé, puis recoupé avec LinkedIn — jamais seul.

La recherche « thiga » renvoie 14 sociétés dont une exploitation agricole
des Ardennes : sans recoupement, la fiche d'un cabinet de conseil parisien
afficherait les gérants d'une ferme. Données inventées ci-dessous, même
structure que les vraies réponses.
"""

import json

import pytest

from utils.annuaire import (
    AnnuaireIndisponible, choisir_candidat, commune_du_siege_linkedin,
    fiche_depuis_annuaire, interroger, normaliser_nom,
)


def societe(siren, nom, commune, etat="A", dirigeants=None, **autres):
    base = {
        "siren": siren, "nom_complet": nom, "nom_raison_sociale": nom, "sigle": None,
        "activite_principale": "70.22Z", "tranche_effectif_salarie": "22",
        "annee_tranche_effectif_salarie": "2024", "date_creation": "2014-04-28",
        "etat_administratif": etat, "categorie_entreprise": "PME",
        "siege": {"libelle_commune": commune, "code_postal": "75009"},
        "dirigeants": dirigeants or [],
    }
    base.update(autres)
    return base


HOMONYMES = [
    societe("111111111", "ORBIQUE", "CORNY-MACHEROMENIL"),
    societe("222222222", "ORBIQUE", "MARENNES-HIERS-BROUAGE"),
    societe("333333333", "ORBIQUE", "PARIS"),
    societe("444444444", "ORBIQUE IMMOBILIER", "PARIS"),
]


def test_la_commune_du_siege_linkedin():
    assert commune_du_siege_linkedin("Paris, Paris") == "PARIS"
    assert commune_du_siege_linkedin("Saint-Étienne, Auvergne-Rhône-Alpes") == "SAINT-ETIENNE"
    assert commune_du_siege_linkedin("") == ""


def test_le_nom_est_normalise_sans_forme_juridique():
    assert normaliser_nom("Orbique SAS") == normaliser_nom("ORBIQUE") == "ORBIQUE"
    assert normaliser_nom("Café & Cie S.A.") == "CAFE & CIE"


def test_l_homonyme_est_leve_par_la_commune():
    candidat, motif = choisir_candidat(HOMONYMES, "Orbique", "Paris, Paris")
    assert candidat["siren"] == "333333333"
    assert motif == ""


def test_un_nom_qui_ne_fait_que_commencer_pareil_n_est_pas_retenu():
    candidat, _ = choisir_candidat([HOMONYMES[3]], "Orbique", "Paris, Paris")
    assert candidat is None


def test_aucune_commune_compatible():
    candidat, motif = choisir_candidat(HOMONYMES[:2], "Orbique", "Lyon, Auvergne-Rhône-Alpes")
    assert candidat is None and "aucune" in motif


def test_plusieurs_candidats_compatibles():
    doublon = HOMONYMES + [societe("555555555", "ORBIQUE", "PARIS")]
    candidat, motif = choisir_candidat(doublon, "Orbique", "Paris, Paris")
    assert candidat is None and "plusieurs" in motif


def test_sans_siege_linkedin_on_ne_devine_pas():
    candidat, motif = choisir_candidat(HOMONYMES, "Orbique", "")
    assert candidat is None and "siège" in motif


def test_une_societe_cessee_est_ignoree():
    candidat, _ = choisir_candidat([societe("333333333", "ORBIQUE", "PARIS", etat="C")], "Orbique", "Paris, Paris")
    assert candidat is None


def test_un_arrondissement_ne_bloque_pas_le_recoupement():
    candidat, _ = choisir_candidat([societe("666666666", "ORBIQUE", "LYON 3EME")], "Orbique", "Lyon, Auvergne-Rhône-Alpes")
    assert candidat["siren"] == "666666666"


def test_la_fiche_annuaire():
    dirigeants = [
        {"type_dirigeant": "personne physique", "nom": "EXEMPLE", "prenoms": "Jeanne", "qualite": "Présidente"},
        {"type_dirigeant": "personne morale", "denomination": "HOLDING FICTIVE", "siren": "999999999", "qualite": "Président de SAS"},
        {"type_dirigeant": "personne morale", "denomination": "CABINET AUDIT", "siren": "888888888", "qualite": "Commissaire aux comptes titulaire"},
    ]
    fiche = fiche_depuis_annuaire(societe("333333333", "ORBIQUE", "PARIS", dirigeants=dirigeants))
    assert fiche == {
        "siren": "333333333",
        "activite": "70.22Z",
        "effectif": "100 à 199 salariés (2024)",
        "creation": "2014-04-28",
        "categorie": "PME",
        "commune": "PARIS",
        "dirigeants": "Jeanne EXEMPLE (Présidente) ; HOLDING FICTIVE (Président de SAS)",
    }


def test_une_tranche_inconnue_ou_non_employeuse():
    assert fiche_depuis_annuaire(societe("1", "X", "PARIS", tranche_effectif_salarie="NN"))["effectif"] == "non employeuse ou non renseignée"


def test_interroger_lit_les_resultats():
    def transport(url, delai):
        assert url.startswith("https://recherche-entreprises.api.gouv.fr/search?")
        assert "q=Orbique" in url and "per_page=25" in url
        return json.dumps({"results": HOMONYMES, "total_results": 4}).encode()
    assert [r["siren"] for r in interroger("Orbique", transport=transport)] == [
        "111111111", "222222222", "333333333", "444444444"
    ]


@pytest.mark.parametrize("panne", [OSError("réseau"), ValueError("pas du json")])
def test_une_panne_de_l_annuaire_est_signalee(panne):
    def transport(url, delai):
        raise panne
    with pytest.raises(AnnuaireIndisponible):
        interroger("Orbique", transport=transport)


def test_un_json_illisible_est_signale():
    with pytest.raises(AnnuaireIndisponible):
        interroger("Orbique", transport=lambda url, delai: b"<html>")
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_annuaire.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.annuaire'`

- [ ] **Step 3 : Écrire le module**

Créer `utils/annuaire.py` :

```python
# -*- coding: utf-8 -*-
"""Annuaire officiel des entreprises (API Recherche d'entreprises, data.gouv).

Gratuit, sans clé, public. Il donne ce que LinkedIn ne donne pas — dirigeants,
SIREN, activité, tranche d'effectif INSEE — mais il ne sait pas *quelle*
entreprise on veut : « thiga » renvoie 14 sociétés. Il n'est donc jamais
interrogé seul ; `choisir_candidat` ne retient un résultat que s'il recoupe
la page LinkedIn (même nom, même commune de siège), et refuse de deviner
sinon.
"""

import json
import re
import unicodedata
import urllib.parse
import urllib.request

URL = "https://recherche-entreprises.api.gouv.fr/search"

# Codes INSEE de tranche d'effectif salarié.
TRANCHES_EFFECTIF = {
    "00": "0 salarié", "01": "1 à 2 salariés", "02": "3 à 5 salariés",
    "03": "6 à 9 salariés", "11": "10 à 19 salariés", "12": "20 à 49 salariés",
    "21": "50 à 99 salariés", "22": "100 à 199 salariés", "31": "200 à 249 salariés",
    "32": "250 à 499 salariés", "41": "500 à 999 salariés", "42": "1 000 à 1 999 salariés",
    "51": "2 000 à 4 999 salariés", "52": "5 000 à 9 999 salariés", "53": "10 000 salariés et plus",
}

_FORMES = {"SAS", "SASU", "SA", "SARL", "EURL", "SNC", "SCI", "SE", "SCA", "GIE"}


class AnnuaireIndisponible(Exception):
    """L'annuaire n'a pas répondu de façon exploitable."""


def _transport_http(url: str, delai: float) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": "We.Reach"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.read()


def interroger(nom: str, transport=None, delai: float = 8.0) -> list:
    """Sociétés dont le nom ressemble à `nom` (25 au plus)."""
    url = URL + "?" + urllib.parse.urlencode({"q": nom, "per_page": 25})
    try:
        brut = (transport or _transport_http)(url, delai)
        return list(json.loads(brut).get("results") or [])
    except Exception as e:
        raise AnnuaireIndisponible(str(e)) from e


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def normaliser_nom(nom: str) -> str:
    """Majuscules, sans accents, sans forme juridique ni points."""
    mots = _sans_accents(nom).upper().replace(".", "").split()
    return " ".join(m for m in mots if m not in _FORMES).strip()


def _normaliser_commune(commune: str) -> str:
    c = _sans_accents(commune).upper().strip()
    # « LYON 3EME », « PARIS 9 », « MARSEILLE 1ER » : l'arrondissement ne
    # change pas la ville ; LinkedIn ne le donne jamais.
    return re.sub(r"\s+\d+\s*(E|ER|EME)?$", "", c).strip()


def commune_du_siege_linkedin(siege: str) -> str:
    """« Paris, Paris » → « PARIS » : LinkedIn écrit « ville, région »."""
    return _normaliser_commune((siege or "").split(",")[0])


def choisir_candidat(resultats, nom_linkedin: str, siege_linkedin: str):
    """(société retenue, "") ou (None, motif). Jamais de devinette."""
    commune = commune_du_siege_linkedin(siege_linkedin)
    if not commune:
        return None, "siège LinkedIn inconnu : impossible de recouper"
    cible = normaliser_nom(nom_linkedin)
    compatibles = []
    for r in resultats or []:
        if r.get("etat_administratif") != "A":
            continue
        noms = {normaliser_nom(r.get(k) or "") for k in ("nom_raison_sociale", "nom_complet", "sigle")}
        siege = r.get("siege") or {}
        if cible in noms and _normaliser_commune(siege.get("libelle_commune") or "") == commune:
            compatibles.append(r)
    if len(compatibles) == 1:
        return compatibles[0], ""
    if not compatibles:
        return None, f"aucune société « {nom_linkedin} » active avec un siège à {commune.title()}"
    return None, f"plusieurs sociétés « {nom_linkedin} » à {commune.title()} : impossible de choisir"


def _dirigeants(candidat) -> str:
    noms = []
    for d in candidat.get("dirigeants") or []:
        qualite = d.get("qualite") or ""
        # Le commissaire aux comptes contrôle, il ne dirige pas.
        if "commissaire aux comptes" in qualite.lower():
            continue
        if d.get("type_dirigeant") == "personne physique":
            nom = " ".join(x for x in ((d.get("prenoms") or "").split(" ")[0], d.get("nom") or "") if x)
        else:
            nom = d.get("denomination") or ""
        if nom:
            noms.append(f"{nom} ({qualite})" if qualite else nom)
    return " ; ".join(noms)


def fiche_depuis_annuaire(candidat: dict) -> dict:
    tranche = candidat.get("tranche_effectif_salarie")
    annee = candidat.get("annee_tranche_effectif_salarie")
    effectif = TRANCHES_EFFECTIF.get(tranche)
    effectif = f"{effectif} ({annee})" if effectif and annee else (effectif or "non employeuse ou non renseignée")
    return {
        "siren": candidat.get("siren") or "",
        "activite": candidat.get("activite_principale") or "",
        "effectif": effectif,
        "creation": candidat.get("date_creation") or "",
        "categorie": candidat.get("categorie_entreprise") or "",
        "commune": (candidat.get("siege") or {}).get("libelle_commune") or "",
        "dirigeants": _dirigeants(candidat),
    }
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `venv/bin/python -m pytest tests/test_annuaire.py -q`
Expected: PASS (15 tests)

- [ ] **Step 5 : Commit**

```bash
git add utils/annuaire.py tests/test_annuaire.py
git commit -m "feat(veille): annuaire officiel, retenu seulement s'il recoupe LinkedIn"
```

---

## Task 3 : Stockage de la veille

**Files:**
- Create: `veille_store.py`
- Test: `tests/test_veille_store.py`

**Interfaces:**
- Consumes: `utils.browsemap.normaliser_url(url) -> str | None` (existant).
- Produces: `class VeilleStore(db_file: str)` avec :
  - `ajouter_entreprise(nom: str, quand: str, url_linkedin: str | None = None) -> int` (doublon de nom, casse ignorée → id existant)
  - `retirer_entreprise(entreprise_id: int) -> None` (supprime aussi fiche et contacts)
  - `entreprises() -> list[dict]` — clés `id, nom, url_linkedin, company_id, etat, ajoutee_le, derniere_veille, curseur_page, signature_familles, nb_contacts`
  - `maj_identification(entreprise_id, etat: str, company_id: str | None = None, url_linkedin: str | None = None) -> None` — états : `a_identifier`, `identifiee`, `non_identifiee`, `illisible`
  - `maj_curseur(entreprise_id, page: int, signature: str) -> None`
  - `marquer_passage(entreprise_id, quand: str) -> None`
  - `enregistrer_fiche(entreprise_id, valeurs: dict, source: str, quand: str) -> list[str]` — champs **changés** (pas les premières valeurs)
  - `fiche(entreprise_id) -> dict[str, dict]` — `{"<source>.<champ>": {"valeur", "source", "releve_le"}}`, dernière valeur par champ et source
  - `age_fiche_jours(entreprise_id, source: str, aujourd_hui: str) -> int | None`
  - `relier_contact(entreprise_id, contact: dict, famille: str, quand: str, urls_au_fichier: set) -> bool` — `contact` a `nom, poste, url, connexions` ; renvoie True si **nouveau**
  - `contacts(entreprise_id) -> list[dict]`
  - `nouveautes_depuis(quand: str | None) -> dict` — `{"contacts": [...], "changements": [...]}` ; chaque contact porte `entreprise` ; chaque changement `entreprise, champ, source, avant, apres, releve_le`
  - `enregistrer_passage(debut, fin, entreprises: list[str], pages: int, cause: str, erreurs: list[str]) -> None` ; `dernier_passage() -> dict | None`
  - `societes_du_fichier() -> list[str]` — sociétés distinctes de la table `profiles`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_veille_store.py` :

```python
# -*- coding: utf-8 -*-
"""Stockage de la veille : dans la base de l'utilisateur, à côté des profils.

Ce qui compte : un contact déjà au fichier n'est pas « nouveau » ; un
changement de fiche se voit ; rien n'est détruit chez quelqu'un qui a déjà
une base.
"""

import sqlite3

from database import DatabaseManager
from veille_store import VeilleStore


def store(tmp_path):
    db = str(tmp_path / "profils.db")
    DatabaseManager(db_file=db)  # la base existe déjà chez tout le monde
    return VeilleStore(db), db


def contact(vanity, poste="Product Manager", connexions="2e"):
    return {"nom": vanity.title(), "poste": poste, "url": f"https://www.linkedin.com/in/{vanity}/",
            "connexions": connexions}


def test_les_tables_de_la_base_existante_sont_intactes(tmp_path):
    s, db = store(tmp_path)
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"profiles", "invitations", "recherches", "entreprises_suivies",
            "fiche_entreprise", "contacts_veille", "passages_veille"} <= tables


def test_ajout_et_doublon_insensible_a_la_casse(tmp_path):
    s, _ = store(tmp_path)
    a = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.ajouter_entreprise("orbique ", "2026-10-16") == a
    [e] = s.entreprises()
    assert e["nom"] == "Orbique" and e["etat"] == "a_identifier" and e["nb_contacts"] == 0


def test_un_lien_colle_est_garde(tmp_path):
    s, _ = store(tmp_path)
    s.ajouter_entreprise("Orbique", "2026-10-15", url_linkedin="https://www.linkedin.com/company/orbique/")
    assert s.entreprises()[0]["url_linkedin"] == "https://www.linkedin.com/company/orbique/"


def test_identification_curseur_et_passage(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.maj_identification(i, "identifiee", company_id="123", url_linkedin="https://www.linkedin.com/company/orbique/")
    s.maj_curseur(i, 2, "sig")
    s.marquer_passage(i, "2026-10-15T08:00:00")
    e = s.entreprises()[0]
    assert (e["etat"], e["company_id"], e["curseur_page"], e["signature_familles"], e["derniere_veille"]) == \
        ("identifiee", "123", 2, "sig", "2026-10-15T08:00:00")


def test_la_premiere_fiche_n_est_pas_un_changement(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-10-15") == []
    assert s.fiche(i)["linkedin.taille"]["valeur"] == "11-50 employés"


def test_une_valeur_identique_n_est_pas_reenregistree_et_un_changement_se_voit(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-10-15")
    assert s.enregistrer_fiche(i, {"taille": "11-50 employés"}, "linkedin", "2026-11-15") == []
    assert s.enregistrer_fiche(i, {"taille": "51-200 employés"}, "linkedin", "2026-12-15") == ["taille"]
    [chg] = s.nouveautes_depuis("2026-12-01")["changements"]
    assert (chg["entreprise"], chg["champ"], chg["avant"], chg["apres"]) == \
        ("Orbique", "taille", "11-50 employés", "51-200 employés")


def test_age_de_la_fiche(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.age_fiche_jours(i, "linkedin", "2026-10-15") is None
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-10-01T08:00:00")
    assert s.age_fiche_jours(i, "linkedin", "2026-10-15") == 14


def test_un_contact_inconnu_est_nouveau_une_fois(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-15", set()) is True
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-16", set()) is False
    assert len(s.contacts(i)) == 1


def test_un_contact_deja_au_fichier_est_relie_mais_pas_nouveau(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    au_fichier = {"http://LINKEDIN.com/in/Jeanne-Exemple?miniProfileUrn=x"}
    assert s.relier_contact(i, contact("jeanne-exemple"), "Product", "2026-10-15", au_fichier) is False
    assert len(s.contacts(i)) == 1
    assert s.nouveautes_depuis(None)["contacts"] == []


def test_nouveautes_depuis_une_date(tmp_path):
    s, _ = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.relier_contact(i, contact("ancien"), "Data", "2026-10-14T09:00:00", set())
    s.relier_contact(i, contact("recent"), "IA", "2026-10-15T08:00:00", set())
    noms = [c["nom"] for c in s.nouveautes_depuis("2026-10-15T00:00:00")["contacts"]]
    assert noms == ["Recent"]
    assert s.nouveautes_depuis("2026-10-15T00:00:00")["contacts"][0]["entreprise"] == "Orbique"


def test_retirer_supprime_fiche_et_contacts(tmp_path):
    s, db = store(tmp_path)
    i = s.ajouter_entreprise("Orbique", "2026-10-15")
    s.enregistrer_fiche(i, {"taille": "x"}, "linkedin", "2026-10-15")
    s.relier_contact(i, contact("a"), "Data", "2026-10-15", set())
    s.retirer_entreprise(i)
    con = sqlite3.connect(db)
    assert s.entreprises() == []
    assert con.execute("SELECT COUNT(*) FROM fiche_entreprise").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM contacts_veille").fetchone()[0] == 0


def test_passages(tmp_path):
    s, _ = store(tmp_path)
    assert s.dernier_passage() is None
    s.enregistrer_passage("2026-10-15T08:00", "2026-10-15T08:20", ["Orbique"], 3, "budget", ["x"])
    p = s.dernier_passage()
    assert (p["entreprises"], p["pages"], p["cause"], p["erreurs"]) == (["Orbique"], 3, "budget", ["x"])


def test_les_societes_du_fichier(tmp_path):
    s, db = store(tmp_path)
    dbm = DatabaseManager(db_file=db)
    dbm.ajouter_profil("A", "PM", "Orbique", "", "https://www.linkedin.com/in/a/")
    dbm.ajouter_profil("B", "PM", "orbique", "", "https://www.linkedin.com/in/b/")
    dbm.ajouter_profil("C", "PM", "", "", "https://www.linkedin.com/in/c/")
    dbm.ajouter_profil("D", "PM", "Zéphyr", "", "https://www.linkedin.com/in/d/")
    assert s.societes_du_fichier() == ["Orbique", "Zéphyr"]
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_veille_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'veille_store'`

- [ ] **Step 3 : Écrire le module**

Créer `veille_store.py` :

```python
# -*- coding: utf-8 -*-
"""Stockage de la veille entreprises, dans la base SQLite de l'utilisateur.

Même fichier que les profils et les invitations : un contact trouvé par la
veille est un profil comme un autre, et la sauvegarde de la base sauvegarde
tout. Les tables sont créées par `CREATE TABLE IF NOT EXISTS`, comme celles
de `database.py` : aucune migration, rien de détruit chez qui a déjà une base.
"""

import json
import sqlite3
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


def _cle_nom(nom: str) -> str:
    return " ".join((nom or "").split()).lower()


class VeilleStore:
    def __init__(self, db_file: str):
        self.db_file = db_file
        with self._con() as con:
            con.executescript(_SCHEMA)

    def _con(self):
        con = sqlite3.connect(self.db_file)
        con.row_factory = sqlite3.Row
        return con

    # ── Entreprises suivies ────────────────────────────────────────────

    def ajouter_entreprise(self, nom: str, quand: str, url_linkedin=None) -> int:
        nom = " ".join((nom or "").split())
        with self._con() as con:
            ligne = con.execute("SELECT id FROM entreprises_suivies WHERE nom_cle = ?",
                                (_cle_nom(nom),)).fetchone()
            if ligne:
                if url_linkedin:
                    con.execute("UPDATE entreprises_suivies SET url_linkedin = ? WHERE id = ?",
                                (url_linkedin, ligne["id"]))
                return ligne["id"]
            cur = con.execute(
                "INSERT INTO entreprises_suivies (nom, nom_cle, url_linkedin, ajoutee_le) VALUES (?, ?, ?, ?)",
                (nom, _cle_nom(nom), url_linkedin, quand))
            return cur.lastrowid

    def retirer_entreprise(self, entreprise_id: int) -> None:
        with self._con() as con:
            for table, colonne in (("fiche_entreprise", "entreprise_id"),
                                   ("contacts_veille", "entreprise_id"),
                                   ("entreprises_suivies", "id")):
                con.execute(f"DELETE FROM {table} WHERE {colonne} = ?", (entreprise_id,))

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

    def age_fiche_jours(self, entreprise_id, source: str, aujourd_hui: str):
        with self._con() as con:
            l = con.execute("SELECT MAX(releve_le) AS d FROM fiche_entreprise WHERE entreprise_id = ? AND source = ?",
                            (entreprise_id, source)).fetchone()
        if not l or not l["d"]:
            return None
        return (date.fromisoformat(aujourd_hui[:10]) - date.fromisoformat(l["d"][:10])).days

    # ── Contacts ───────────────────────────────────────────────────────

    def relier_contact(self, entreprise_id, contact: dict, famille: str, quand: str, urls_au_fichier: set) -> bool:
        """Relie un contact à l'entreprise ; True s'il est réellement nouveau.

        Nouveau = jamais relié à cette entreprise ET absent du fichier avant ce
        passage (comparé sous forme canonique : le fichier contient des liens
        copiés à la main, avec leurs paramètres de suivi).
        """
        url = normaliser_url(contact.get("url"))
        if url is None:
            return False
        connus = {normaliser_url(u) for u in urls_au_fichier or ()}
        nouveau = url not in connus
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
                ORDER BY e.nom COLLATE NOCASE""", (borne,)).fetchall()]
        return {"contacts": contacts, "changements": changements}

    # ── Passages ───────────────────────────────────────────────────────

    def enregistrer_passage(self, debut, fin, entreprises, pages, cause, erreurs) -> None:
        with self._con() as con:
            con.execute("""INSERT INTO passages_veille (debut, fin, entreprises, pages, cause, erreurs)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (debut, fin, json.dumps(entreprises, ensure_ascii=False), pages, cause,
                         json.dumps(erreurs, ensure_ascii=False)))

    def dernier_passage(self):
        with self._con() as con:
            l = con.execute("SELECT * FROM passages_veille ORDER BY id DESC LIMIT 1").fetchone()
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
```

- [ ] **Step 4 : Vérifier qu'ils passent**

Run: `venv/bin/python -m pytest tests/test_veille_store.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5 : Commit**

```bash
git add veille_store.py tests/test_veille_store.py
git commit -m "feat(veille): stockage des entreprises suivies, fiches et contacts"
```

---

## Task 4 : Verrou de session LinkedIn et compteur de pages

**Files:**
- Create: `utils/verrou_linkedin.py`
- Modify: `utils/human_behavior.py` (classe `DailyLimitsTracker`, l. 36-101)
- Modify: `scraper_v2_sync.py` (méthodes `__init__`, `run_scraper`, `run_url_scraper`, `recolter_browsemap`, `verifier_acceptations`, `envoyer_messages`)
- Test: `tests/test_verrou_linkedin.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `class VerrouOccupe(Exception)` avec attribut `activite: str`
  - `session_linkedin(config_dir, activite: str)` — gestionnaire de contexte ; `config_dir=None` → pas de verrou (tests, scripts)
  - `MESSAGE_OCCUPE = "Une autre session LinkedIn de We.Reach est en cours ({activite}) — attendez qu'elle se termine."`
  - `DailyLimitsTracker.pages_veille_today -> int`, `DailyLimitsTracker.increment_pages_veille(n=1) -> None`
  - `LinkedInScraperV2Sync.config_dir` (attribut)

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_verrou_linkedin.py` :

```python
# -*- coding: utf-8 -*-
"""Une seule session LinkedIn à la fois par utilisateur.

Deux fenêtres Chrome sur le même compte — la veille et une recherche manuelle
— c'est exactement le comportement qui fait repérer un compte.
"""

import json
import os
import time

import pandas as pd
import pytest

from scraper_v2_sync import LinkedInScraperV2Sync
from utils.human_behavior import DailyLimitsTracker
from utils.verrou_linkedin import MESSAGE_OCCUPE, VerrouOccupe, session_linkedin


def test_le_verrou_est_pris_puis_rendu(tmp_path):
    with session_linkedin(tmp_path, "veille"):
        assert (tmp_path / "session_linkedin.lock").exists()
    assert not (tmp_path / "session_linkedin.lock").exists()


def test_une_seconde_session_est_refusee(tmp_path):
    with session_linkedin(tmp_path, "veille"):
        with pytest.raises(VerrouOccupe) as e:
            with session_linkedin(tmp_path, "recherche"):
                pass
    assert e.value.activite == "veille"


def test_le_verrou_est_rendu_meme_sur_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with session_linkedin(tmp_path, "veille"):
            raise RuntimeError("boum")
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_le_verrou_d_un_processus_mort_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text(
        json.dumps({"pid": 999999, "activite": "veille", "debut": time.time()}))
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_un_verrou_trop_ancien_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text(
        json.dumps({"pid": os.getpid(), "activite": "veille", "debut": time.time() - 4 * 3600}))
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_un_verrou_illisible_est_libre(tmp_path):
    (tmp_path / "session_linkedin.lock").write_text("{cassé")
    with session_linkedin(tmp_path, "recherche"):
        pass


def test_sans_dossier_pas_de_verrou():
    with session_linkedin(None, "veille"):
        with session_linkedin(None, "recherche"):
            pass


def test_une_recherche_manuelle_pendant_la_veille_est_refusee_proprement(tmp_path, monkeypatch):
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))

    async def ne_doit_pas_tourner(**kwargs):
        raise AssertionError("la recherche a tourné malgré le verrou")

    monkeypatch.setattr(wrapper.scraper, "run_scraper_async", ne_doit_pas_tourner)
    with session_linkedin(tmp_path, "veille"):
        df = wrapper.run_scraper(cookie="c", keyword="pm", entreprises=[], nb_profils=10, ecoles_ids=[])
    assert isinstance(df, pd.DataFrame) and df.empty
    assert wrapper.errors == [MESSAGE_OCCUPE.format(activite="veille")]


@pytest.mark.parametrize("methode,kwargs,vide", [
    ("run_url_scraper", {"cookie": "c", "urls": ["https://www.linkedin.com/in/a/"]}, "df"),
    ("recolter_browsemap", {"cookie": "c", "url_reference": "https://www.linkedin.com/in/a/"}, ([], None)),
    ("verifier_acceptations", {"cookie": "c", "profils": []}, []),
    ("envoyer_messages", {"cookie": "c", "cibles": [], "message": "m"}, []),
])
def test_toutes_les_sessions_respectent_le_verrou(tmp_path, methode, kwargs, vide):
    wrapper = LinkedInScraperV2Sync(use_database=False, config_dir=str(tmp_path))
    with session_linkedin(tmp_path, "veille"):
        resultat = getattr(wrapper, methode)(**kwargs)
    if vide == "df":
        assert resultat.empty
    else:
        assert resultat == vide
    assert wrapper.errors == [MESSAGE_OCCUPE.format(activite="veille")]


def test_le_compteur_de_pages_veille(tmp_path):
    fichier = str(tmp_path / "daily_limits.json")
    t = DailyLimitsTracker(limits_file=fichier)
    assert t.pages_veille_today == 0
    t.increment_pages_veille(3)
    assert DailyLimitsTracker(limits_file=fichier).pages_veille_today == 3
    assert t.profiles_today == 0  # les pages de veille ne mangent pas le quota de profils
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_verrou_linkedin.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.verrou_linkedin'`

- [ ] **Step 3 : Écrire le verrou**

Créer `utils/verrou_linkedin.py` :

```python
# -*- coding: utf-8 -*-
"""Une seule session LinkedIn de We.Reach à la fois, par utilisateur.

La veille du matin et une recherche lancée à la main ouvriraient deux
fenêtres Chrome sur le même compte : c'est le comportement qui fait repérer
un compte. Le verrou est un petit fichier dans le dossier de config de la
personne ; il porte le pid et l'heure, pour qu'un verrou laissé par un
processus mort, ou vieux de plus de trois heures, ne bloque personne.
"""

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

_NOM = "session_linkedin.lock"
_DUREE_MAX = 3 * 3600

MESSAGE_OCCUPE = ("Une autre session LinkedIn de We.Reach est en cours ({activite}) "
                  "— attendez qu'elle se termine.")


class VerrouOccupe(Exception):
    def __init__(self, activite: str):
        super().__init__(MESSAGE_OCCUPE.format(activite=activite))
        self.activite = activite


def _vivant(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _occupant(chemin: Path):
    try:
        info = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception:
        return None
    if time.time() - float(info.get("debut", 0)) > _DUREE_MAX or not _vivant(info.get("pid")):
        return None
    return info


@contextmanager
def session_linkedin(config_dir, activite: str):
    """Prend le verrou pour la durée du bloc ; lève `VerrouOccupe` sinon."""
    if config_dir is None:
        yield
        return
    chemin = Path(config_dir) / _NOM
    occupant = _occupant(chemin)
    if occupant:
        raise VerrouOccupe(occupant.get("activite") or "inconnue")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    moi = {"pid": os.getpid(), "activite": activite, "debut": time.time()}
    chemin.write_text(json.dumps(moi), encoding="utf-8")
    try:
        yield
    finally:
        try:
            if json.loads(chemin.read_text(encoding="utf-8")).get("debut") == moi["debut"]:
                chemin.unlink()
        except Exception:
            pass
```

Note : un même processus Streamlit qui tient le verrou dans une session et voit une autre session tenter une recherche la refuse — c'est voulu (même compte LinkedIn).

- [ ] **Step 4 : Ajouter le compteur de pages**

Dans `utils/human_behavior.py`, classe `DailyLimitsTracker`, ajouter après `increment_sessions` :

```python
    def increment_pages_veille(self, n: int = 1):
        """Pages LinkedIn chargées par la veille (« À propos », résultats).

        Compteur à part : la veille ne récupère pas des profils un par un,
        elle charge des pages ; son budget se règle en pages.
        """
        self._data["pages_veille"] = self._data.get("pages_veille", 0) + n
        self._save()

    @property
    def pages_veille_today(self) -> int:
        return self._data.get("pages_veille", 0)
```

(`_load` réinitialise déjà tout le dictionnaire au changement de jour : aucune autre modification.)

- [ ] **Step 5 : Faire respecter le verrou par le wrapper synchrone**

Dans `scraper_v2_sync.py` :

1. Importer : `from utils.verrou_linkedin import VerrouOccupe, session_linkedin`
2. Dans `__init__`, après `self.errors = []` : `self.config_dir = config_dir`
3. Dans **chacune** des méthodes `run_scraper`, `run_url_scraper`, `recolter_browsemap`, `verifier_acceptations`, `envoyer_messages`, envelopper l'appel `asyncio.run(...)` ainsi (exemple pour `run_url_scraper` ; même forme partout, avec l'activité et la valeur vide propres à chaque méthode — `"recherche"`/`pd.DataFrame()`, `"récupération par URLs"`/`pd.DataFrame()`, `"profils similaires"`/`([], None)`, `"vérification des acceptations"`/`[]`, `"envoi de messages"`/`[]`) :

```python
        try:
            with session_linkedin(self.config_dir, "récupération par URLs"):
                result = asyncio.run(
                    self.scraper.run_url_scraper_async(
                        cookie=cookie,
                        urls=urls,
                        inviter=inviter,
                        message_invitation=message_invitation,
                        message_direct=message_direct,
                        progress_callback=progress_callback,
                        status_callback=status_callback
                    )
                )
        except VerrouOccupe as occupe:
            self.errors = [str(occupe)]
            return pd.DataFrame()
```

Le `except VerrouOccupe` se place **avant** le `except Exception` existant de chaque méthode, à l'intérieur du même `try`, et remplace `self.errors` (la seule erreur pertinente est le verrou).

- [ ] **Step 6 : Vérifier**

Run: `venv/bin/python -m pytest tests/test_verrou_linkedin.py -q`
Expected: PASS (13 tests)

Run: `venv/bin/python -m pytest -q`
Expected: PASS — aucun test existant ne doit casser (les AppTest construisent le scraper avec un `config_dir` de test isolé : le verrou y est libre).

- [ ] **Step 7 : Commit**

```bash
git add utils/verrou_linkedin.py utils/human_behavior.py scraper_v2_sync.py tests/test_verrou_linkedin.py
git commit -m "feat(veille): une seule session LinkedIn a la fois, et un compteur de pages de veille"
```

---

## Task 5 : Extracteur de la page « À propos »

**Files:**
- Modify: `utils/dom_selectors.py` (ajouter une méthode statique à `DOMSelectors`)
- Test: `tests/test_extracteur_apropos.py`

**Interfaces:**
- Consumes: rien.
- Produces: `DOMSelectors.extract_page_apropos_js() -> str` — fonction JS `() => ({nom, champs, company_id, description, html})` où `champs: {<libellé dt>: [<valeurs dd>]}`, `company_id` numérique ou `""`, `html` = HTML de `main` (≤ 1 000 000 caractères) **uniquement** si `champs` est vide.

- [ ] **Step 1 : Écrire le test (fixture synthétique fidèle à la capture)**

Créer `tests/test_extracteur_apropos.py` :

```python
# -*- coding: utf-8 -*-
"""Le vrai JavaScript de lecture « À propos », exécuté dans un Chromium local.

Fixture inventée, structure copiée de la capture réelle du 2026-10-15 :
<dl> avec <dt>/<dd>, apostrophe typographique dans « Taille de l’entreprise »,
lien « voir les employés » porteur de currentCompany, et d'autres titres
(« 0 notification au total ») hors de <main>. Réseau coupé : rien ne sort.
"""

import pytest

from utils.dom_selectors import DOMSelectors

playwright = pytest.importorskip("playwright.sync_api")

PAGE = """<!doctype html><html><body>
<header><h1>0 notification au total</h1></header>
<main>
  <section><h1>Orbique</h1>
    <a href="https://www.linkedin.com/search/results/people/?currentCompany=%5B%227654321%22%5D&origin=COMPANY_PAGE_CANNED_SEARCH">Voir les 198 employés</a>
  </section>
  <section><h2>Vue d’ensemble</h2><p>Orbique conseille   les entreprises
  sur le produit.</p>
    <dl>
      <dt><h3>Site web</h3></dt><dd><a href="https://www.orbique.example">https://www.orbique.example</a></dd>
      <dt><h3>Téléphone</h3></dt><dd><span>+33 1 00 00 00 00</span><span class="visually-hidden">Le numéro de téléphone est le +33 1 00 00 00 00</span></dd>
      <dt><h3>Page vérifiée</h3></dt><dd>1 juin 2024</dd>
      <dt><h3>Secteur</h3></dt><dd>Services et conseil aux entreprises</dd>
      <dt><h3>Taille de l’entreprise</h3></dt><dd>201-500 employés</dd><dd>198 membres associés</dd>
      <dt><h3>Siège social</h3></dt><dd>Paris, Paris</dd>
      <dt><h3>Fondée en</h3></dt><dd>2014</dd>
      <dt><h3>Spécialisations</h3></dt><dd>Product Management, Discovery</dd>
    </dl>
  </section>
  <aside><h2>Pages également consultées</h2>
    <a href="https://www.linkedin.com/search/results/people/?currentCompany=%5B%221111%22%5D">Autre</a></aside>
</main></body></html>"""

PAGE_SANS_DL = "<html><body><main><h1>Orbique</h1><p>Contenu inattendu</p></main></body></html>"


@pytest.fixture(scope="module")
def navigateur():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium indisponible : {e}")
        page = b.new_page()
        page.route("**/*", lambda route: route.abort())
        yield page
        b.close()


def lire(page, html):
    page.set_content(html)
    return page.evaluate(DOMSelectors.extract_page_apropos_js())


def test_les_rubriques_sont_lues(navigateur):
    r = lire(navigateur, PAGE)
    assert r["champs"]["Site web"] == ["https://www.orbique.example"]
    assert r["champs"]["Taille de l’entreprise"] == ["201-500 employés", "198 membres associés"]
    assert r["champs"]["Siège social"] == ["Paris, Paris"]
    assert r["champs"]["Téléphone"][0].startswith("+33 1 00 00 00 00")


def test_le_nom_vient_de_main_et_pas_de_l_en_tete(navigateur):
    assert lire(navigateur, PAGE)["nom"] == "Orbique"


def test_l_identifiant_vient_du_premier_lien_employes_de_main(navigateur):
    assert lire(navigateur, PAGE)["company_id"] == "7654321"


def test_la_description(navigateur):
    assert lire(navigateur, PAGE)["description"] == "Orbique conseille les entreprises sur le produit."


def test_pas_de_html_renvoye_quand_tout_est_lu(navigateur):
    assert lire(navigateur, PAGE)["html"] == ""


def test_une_page_inattendue_renvoie_son_html(navigateur):
    r = lire(navigateur, PAGE_SANS_DL)
    assert r["champs"] == {} and r["company_id"] == ""
    assert "Contenu inattendu" in r["html"]
```

- [ ] **Step 2 : Vérifier qu'il échoue**

Run: `venv/bin/python -m pytest tests/test_extracteur_apropos.py -q`
Expected: FAIL — `AttributeError: type object 'DOMSelectors' has no attribute 'extract_page_apropos_js'`

- [ ] **Step 3 : Écrire l'extracteur**

Ajouter à la fin de la classe `DOMSelectors` dans `utils/dom_selectors.py` :

```python
    @staticmethod
    def extract_page_apropos_js() -> str:
        """Lecture de la page « À propos » d'une entreprise.

        Ancrée sur la structure sémantique (<dl>/<dt>/<dd>, <main>, lien
        « voir les employés ») et jamais sur les classes CSS, que LinkedIn
        regénère. Quand aucune rubrique n'est lue, le HTML de <main> est
        renvoyé pour être enregistré : c'est la seule façon de rattraper un
        changement de structure.
        """
        return r"""() => {
            const net = s => (s || '').replace(/\s+/g, ' ').trim();
            const racine = document.querySelector('main') || document.body;
            const champs = {};
            for (const dt of racine.querySelectorAll('dl dt')) {
                const cle = net(dt.innerText);
                const valeurs = [];
                let el = dt.nextElementSibling;
                while (el && el.tagName === 'DD') {
                    // Le premier enfant porte la valeur ; un second, souvent
                    // masqué, la répète en phrase (« Le numéro est le … »).
                    const v = net((el.firstElementChild || el).innerText || el.innerText);
                    if (v) valeurs.push(v);
                    el = el.nextElementSibling;
                }
                if (cle && valeurs.length) champs[cle] = valeurs;
            }
            let companyId = '';
            const lien = racine.querySelector('a[href*="currentCompany"]');
            if (lien) {
                let href = lien.getAttribute('href') || '';
                try { href = decodeURIComponent(href); } catch (e) {}
                const m = href.match(/currentCompany=\["?(\d+)/);
                if (m) companyId = m[1];
            }
            const h1 = racine.querySelector('h1');
            let description = '';
            for (const h of racine.querySelectorAll('h2')) {
                const t = net(h.innerText).replace('’', "'");
                if (t === "Vue d'ensemble") {
                    const p = h.parentElement && h.parentElement.querySelector('p');
                    if (p) description = net(p.innerText);
                    break;
                }
            }
            return {
                nom: h1 ? net(h1.innerText) : '',
                champs: champs,
                company_id: companyId,
                description: description,
                html: Object.keys(champs).length ? '' : racine.innerHTML.slice(0, 1000000)
            };
        }"""
```

- [ ] **Step 4 : Vérifier**

Run: `venv/bin/python -m pytest tests/test_extracteur_apropos.py -q`
Expected: PASS (6 tests, ~1 s)

Si la capture réelle est disponible dans le scratchpad du contrôleur, le contrôleur vérifie en plus l'extracteur sur elle (script jetable hors dépôt) : 8 rubriques lues, `company_id` égal à celui du lien « voir les employés », `nom` = nom de l'entreprise.

- [ ] **Step 5 : Commit**

```bash
git add utils/dom_selectors.py tests/test_extracteur_apropos.py
git commit -m "feat(veille): lire la page A propos d'une entreprise LinkedIn"
```

---

## Task 6 : Le moteur de veille

**Files:**
- Create: `veille.py`
- Test: `tests/test_moteur_veille.py`

**Interfaces:**
- Consumes:
  - Task 1 : `charger_reglages`, `expression_mots_cles`, `url_recherche_personnes`, `famille_de_l_intitule`, `signature_familles`, `fiche_depuis_apropos`, `ordre_du_lot`, `PAGES_MAX_PAR_ENTREPRISE`, `RELECTURE_FICHE_JOURS`
  - Task 2 : `interroger`, `choisir_candidat`, `fiche_depuis_annuaire`, `AnnuaireIndisponible`
  - Task 3 : `VeilleStore` (toutes les méthodes listées)
  - Task 4 : `session_linkedin`, `VerrouOccupe`, `DailyLimitsTracker.pages_veille_today`, `.increment_pages_veille`
  - Task 5 : `DOMSelectors.extract_page_apropos_js()`
  - Existant : `LinkedInScraperV2(use_database, proxy, db_file, profiles_csv, config_dir)`, `._open_linkedin_page(p, cookie, status_callback) -> (browser, page)`, `.network_manager.safe_page_goto(page, url) -> bool`, `.human.human_delay(ms, std)`, `.human.daily_limits`, `.extraire_profils_page(page) -> list[dict]` (clés `nom, poste, entreprise, url, localisation, connexions`), `._resoudre_company_urn_via_typeahead(nom, page) -> str | None`, `._est_page_de_connexion(url) -> bool` (ajouté au correctif Profils similaires ; s'il n'existe pas sous ce nom, utiliser le test de chemin de `recolter_browsemap_async`), `._dumper_panneau` pour modèle de dump ; `DatabaseManager.urls_connues() -> set`, `DatabaseManager.ajouter_profil(nom, poste, entreprise, ecole, url, localisation="")`.
- Produces:
  - `@dataclass RapportPassage(debut: str, fin: str, entreprises: list[str], pages: int, cause: str, erreurs: list[str], nouveaux_contacts: int)` ; causes : `"termine"`, `"budget"`, `"cookie"`, `"deconnecte"`, `"occupe"`, `"rien_a_faire"`, `"erreur"`
  - `async def passage_async(scraper, store, db, reglages, cookie, maintenant, status=None, annuaire=interroger) -> RapportPassage`
  - `def lancer_passage(chemins, cookie, proxy=None, status=None) -> RapportPassage` — synchrone, prend le verrou, enregistre le passage
  - `python -m veille --email <email>` (ligne de commande ; la livraison 3 l'appellera)

- [ ] **Step 1 : Écrire les tests (faux navigateur, comme `test_recolte_browsemap.py`)**

Créer `tests/test_moteur_veille.py` :

```python
# -*- coding: utf-8 -*-
"""Le moteur de veille, sans navigateur : chaque page LinkedIn est simulée.

On vérifie l'enchaînement — budget, identification, annuaire recoupé,
recherche paginée avec curseur, nouveautés — et surtout les arrêts : budget
épuisé, cookie expiré, entreprise introuvable. Aucune visite LinkedIn,
aucun appel à l'annuaire réel.
"""

import asyncio
import json

import pytest

import veille
from database import DatabaseManager
from utils.annuaire import AnnuaireIndisponible
from utils.veille_regles import ReglagesVeille
from veille_store import VeilleStore

ABOUT_OK = {
    "nom": "Orbique", "company_id": "7654321", "description": "Conseil produit", "html": "",
    "champs": {"Site web": ["https://www.orbique.example"], "Siège social": ["Paris, Paris"],
               "Taille de l’entreprise": ["201-500 employés", "198 membres associés"],
               "Secteur": ["Conseil"]},
}
ANNUAIRE_OK = [{
    "siren": "333333333", "nom_complet": "ORBIQUE", "nom_raison_sociale": "ORBIQUE", "sigle": None,
    "activite_principale": "70.22Z", "tranche_effectif_salarie": "22", "annee_tranche_effectif_salarie": "2024",
    "date_creation": "2014-04-28", "etat_administratif": "A", "categorie_entreprise": "PME",
    "siege": {"libelle_commune": "PARIS"},
    "dirigeants": [{"type_dirigeant": "personne physique", "nom": "EXEMPLE", "prenoms": "Jeanne", "qualite": "Présidente"}],
}]


def personne(v, poste):
    return {"nom": v.title(), "poste": poste, "entreprise": "Orbique",
            "url": f"https://www.linkedin.com/in/{v}/", "localisation": "Paris", "connexions": "2e"}


class FauxLimites:
    def __init__(self, deja=0):
        self.pages_veille_today = deja

    def increment_pages_veille(self, n=1):
        self.pages_veille_today += n


class FauxHumain:
    def __init__(self, limites):
        self.daily_limits = limites

    async def human_delay(self, *a, **k):
        pass


class FauxReseau:
    def __init__(self, page):
        self.page = page

    async def safe_page_goto(self, page, url):
        self.page.url = url
        self.page.visites.append(url)
        return True


class FaussePage:
    def __init__(self, about=ABOUT_OK, resultats=None, url_apres_goto=None):
        self.about = about
        self.resultats = resultats or {}
        self.visites = []
        self.url = ""
        self.url_apres_goto = url_apres_goto

    async def evaluate(self, js):
        return self.about


class FauxNavigateur:
    def __init__(self):
        self.ferme = False

    async def close(self):
        self.ferme = True


class FauxScraper:
    def __init__(self, page, limites, typeahead="7654321", cookie_ok=True):
        self.page = page
        self.navigateur = FauxNavigateur()
        self.human = FauxHumain(limites)
        self.network_manager = FauxReseau(page)
        self.typeahead = typeahead
        self.cookie_ok = cookie_ok
        self.dumps = []

    async def _open_linkedin_page(self, p, cookie, status_callback=None):
        return (self.navigateur, self.page) if self.cookie_ok else (None, None)

    async def _resoudre_company_urn_via_typeahead(self, nom, page):
        return self.typeahead

    def _est_page_de_connexion(self, url):
        return "/login" in url or "/authwall" in url

    async def extraire_profils_page(self, page):
        import re
        m = re.search(r"page=(\d+)", page.url)
        return list(self.page.resultats.get(int(m.group(1)) if m else 1, []))

    def _dumper_panneau(self, html):
        self.dumps.append(html)
        return True


class FauxPlaywright:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def sans_vrai_playwright(monkeypatch):
    monkeypatch.setattr(veille, "async_playwright", lambda: FauxPlaywright())


@pytest.fixture
def base(tmp_path):
    db = str(tmp_path / "p.db")
    DatabaseManager(db_file=db)
    return VeilleStore(db), DatabaseManager(db_file=db)


def passer(store, db, scraper, reglages=None, annuaire=lambda nom: ANNUAIRE_OK, maintenant="2026-10-15T08:00:00"):
    return asyncio.run(veille.passage_async(
        scraper, store, db, reglages or ReglagesVeille(["Product", "Data", "IA"], [], 20),
        "COOKIE", maintenant, annuaire=annuaire))


def test_premier_passage_complet(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("jeanne-exemple", "Product Manager"),
                                     personne("paul-exemple", "Data Engineer")]})
    limites = FauxLimites()
    r = passer(store, db, FauxScraper(page, limites))

    assert r.cause == "termine" and r.entreprises == ["Orbique"] and r.nouveaux_contacts == 2
    e = store.entreprises()[0]
    assert e["etat"] == "identifiee" and e["company_id"] == "7654321"
    fiche = store.fiche(i)
    assert fiche["linkedin.taille"]["valeur"] == "201-500 employés"
    assert fiche["annuaire.siren"]["valeur"] == "333333333"
    assert {c["famille"] for c in store.contacts(i)} == {"Product", "Data"}
    assert limites.pages_veille_today == r.pages == 3  # « À propos » + page 1 + page 2 vide
    assert page.visites[0] == "https://www.linkedin.com/company/7654321/about/"


def test_les_contacts_entrent_au_fichier(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]}), FauxLimites()))
    assert "https://www.linkedin.com/in/jeanne-exemple/" in db.urls_connues()


def test_un_contact_deja_au_fichier_n_est_pas_nouveau(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    db.ajouter_profil("Jeanne", "PM", "Orbique", "", "http://linkedin.com/in/Jeanne-Exemple?trk=x")
    r = passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("jeanne-exemple", "PM")]}), FauxLimites()))
    assert r.nouveaux_contacts == 0


def test_budget_epuise_au_milieu(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")]})
    limites = FauxLimites(deja=18)  # 2 pages restantes sur 20
    r = passer(store, db, FauxScraper(page, limites))
    assert r.cause == "budget"
    assert len(page.visites) == 2  # « À propos » + page 1, pas de page 2
    assert store.entreprises()[0]["curseur_page"] == 1


def test_budget_nul_aucune_page(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites(deja=20)))
    assert r.cause == "budget" and page.visites == [] and r.pages == 0


def test_le_curseur_reprend_et_repart_a_zero_en_fin_de_liste(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")], 2: [personne("b", "PM")], 3: [personne("c", "PM")]})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert store.entreprises()[0]["curseur_page"] == 2
    page.visites.clear()
    passer(store, db, FauxScraper(page, FauxLimites()), maintenant="2026-10-16T08:00:00")
    # Fiche fraîche : pas de « À propos » ; pages 3 puis 4 (vide) → curseur remis à 0
    assert [v for v in page.visites if "about" in v] == []
    assert store.entreprises()[0]["curseur_page"] == 0


def test_changer_de_familles_remet_le_curseur_a_zero(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.maj_identification(i, "identifiee", company_id="7654321")
    store.maj_curseur(i, 2, "ancienne-signature")
    store.enregistrer_fiche(i, {"site": "x"}, "linkedin", "2026-10-14")
    page = FaussePage(resultats={1: [personne("a", "PM")]})
    passer(store, db, FauxScraper(page, FauxLimites()))
    assert any("page=1" in v for v in page.visites)


def test_entreprise_introuvable_par_son_nom(base):
    store, db = base
    store.ajouter_entreprise("Inconnue", "2026-10-14")
    page = FaussePage()
    r = passer(store, db, FauxScraper(page, FauxLimites(), typeahead=None))
    assert store.entreprises()[0]["etat"] == "non_identifiee"
    assert page.visites == []  # aucune recherche lancée sans identifiant
    assert any("Inconnue" in e for e in r.erreurs)


def test_page_a_propos_illisible(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage(about={"nom": "", "champs": {}, "company_id": "", "description": "", "html": "<main>?</main>"})
    s = FauxScraper(page, FauxLimites())
    r = passer(store, db, s)
    assert store.entreprises()[0]["etat"] == "illisible"
    assert s.dumps == ["<main>?</main>"]
    assert any("illisible" in e for e in r.erreurs)
    assert [v for v in page.visites if "search" in v] == []


def test_un_lien_colle_est_utilise_au_lieu_du_nom(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14", url_linkedin="https://www.linkedin.com/company/orbique/")
    page = FaussePage()
    passer(store, db, FauxScraper(page, FauxLimites(), typeahead=None))
    assert page.visites[0] == "https://www.linkedin.com/company/orbique/about/"


def test_annuaire_non_rapproche(base):
    store, db = base
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    autre = [dict(ANNUAIRE_OK[0], siege={"libelle_commune": "LYON"})]
    passer(store, db, FauxScraper(FaussePage(), FauxLimites()), annuaire=lambda nom: autre)
    fiche = store.fiche(i)
    assert "annuaire.siren" not in fiche
    assert "aucune" in fiche["annuaire.rapprochement"]["valeur"]


def test_annuaire_indisponible_n_arrete_pas_la_veille(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")

    def panne(nom):
        raise AnnuaireIndisponible("délai dépassé")

    r = passer(store, db, FauxScraper(FaussePage(resultats={1: [personne("a", "PM")]}), FauxLimites()), annuaire=panne)
    assert r.cause == "termine" and r.nouveaux_contacts == 1
    assert any("annuaire" in e.lower() for e in r.erreurs)


def test_cookie_expire(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites(), cookie_ok=False))
    assert r.cause == "cookie" and r.entreprises == []


def test_deconnexion_en_cours_de_route(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    page = FaussePage()
    s = FauxScraper(page, FauxLimites())

    async def vers_login(p, url):
        p.url = "https://www.linkedin.com/login"
        p.visites.append(url)
        return True

    s.network_manager.safe_page_goto = vers_login
    r = passer(store, db, s)
    assert r.cause == "deconnecte"
    assert s.navigateur.ferme


def test_rien_a_faire(base):
    store, db = base
    r = passer(store, db, FauxScraper(FaussePage(), FauxLimites()))
    assert r.cause == "rien_a_faire" and r.pages == 0


def test_le_navigateur_est_toujours_ferme(base):
    store, db = base
    store.ajouter_entreprise("Orbique", "2026-10-14")
    s = FauxScraper(FaussePage(), FauxLimites())
    passer(store, db, s)
    assert s.navigateur.ferme


def test_lancer_passage_respecte_le_verrou_et_enregistre(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from utils.verrou_linkedin import session_linkedin

    db_file = str(tmp_path / "p.db")
    DatabaseManager(db_file=db_file)
    chemins = SimpleNamespace(db_file=db_file, profiles_csv=str(tmp_path / "p.csv"), config_dir=str(tmp_path))
    with session_linkedin(tmp_path, "recherche"):
        r = veille.lancer_passage(chemins, "COOKIE")
    assert r.cause == "occupe"
    assert VeilleStore(db_file).dernier_passage()["cause"] == "occupe"
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_moteur_veille.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'veille'`

- [ ] **Step 3 : Écrire le moteur**

Créer `veille.py` :

```python
# -*- coding: utf-8 -*-
"""Moteur de veille entreprises : un passage, du lot au rapport.

Sans Streamlit : l'application l'appelle par un bouton, et la livraison 3
l'appellera par un réveil programmé (`python -m veille --email …`). La
logique n'existe qu'ici.

Un passage prend les entreprises les plus en retard et, tant que le budget
de pages du jour le permet : identifie l'entreprise sur LinkedIn, relit sa
fiche si elle a plus de 30 jours (page « À propos » + annuaire officiel
recoupé), puis parcourt quelques pages de la recherche de ses employés
Product / Data / IA, en reprenant là où le passage précédent s'était arrêté.
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime

from playwright.async_api import async_playwright

from database import DatabaseManager
from logger import logger
from utils.annuaire import AnnuaireIndisponible, choisir_candidat, fiche_depuis_annuaire, interroger
from utils.dom_selectors import DOMSelectors
from utils.veille_regles import (
    PAGES_MAX_PAR_ENTREPRISE, RELECTURE_FICHE_JOURS, charger_reglages, expression_mots_cles,
    famille_de_l_intitule, fiche_depuis_apropos, ordre_du_lot, signature_familles,
    url_recherche_personnes,
)
from utils.verrou_linkedin import VerrouOccupe, session_linkedin
from veille_store import VeilleStore


@dataclass
class RapportPassage:
    debut: str
    fin: str = ""
    entreprises: list = field(default_factory=list)
    pages: int = 0
    cause: str = "termine"
    erreurs: list = field(default_factory=list)
    nouveaux_contacts: int = 0


class _Arret(Exception):
    """Fin anticipée du passage : budget, déconnexion."""

    def __init__(self, cause):
        super().__init__(cause)
        self.cause = cause


def _url_apropos(entreprise) -> str:
    if entreprise.get("url_linkedin"):
        return entreprise["url_linkedin"].split("?")[0].rstrip("/") + "/about/"
    return f"https://www.linkedin.com/company/{entreprise['company_id']}/about/"


async def passage_async(scraper, store, db, reglages, cookie, maintenant, status=None, annuaire=interroger):
    rapport = RapportPassage(debut=maintenant)
    limites = scraper.human.daily_limits

    def dire(texte):
        logger.info(f"🏢 {texte}")
        if status:
            status(texte)

    def restant():
        return reglages.pages_par_jour - limites.pages_veille_today

    lot = ordre_du_lot(store.entreprises())
    if not lot:
        rapport.cause, rapport.fin = "rien_a_faire", maintenant
        return rapport
    if restant() <= 0:
        rapport.cause, rapport.fin = "budget", maintenant
        rapport.erreurs.append(f"Budget de veille du jour déjà consommé ({reglages.pages_par_jour} pages).")
        return rapport

    async def charger(page, url):
        if restant() <= 0:
            raise _Arret("budget")
        limites.increment_pages_veille(1)
        rapport.pages += 1
        await scraper.network_manager.safe_page_goto(page, url)
        if scraper._est_page_de_connexion(page.url):
            raise _Arret("deconnecte")
        await scraper.human.human_delay(1500, 400)

    expression = expression_mots_cles(reglages.familles, reglages.intitules_libres)
    signature = signature_familles(reglages.familles, reglages.intitules_libres)

    async with async_playwright() as p:
        dire("Ouverture de LinkedIn…")
        navigateur, page = await scraper._open_linkedin_page(p, cookie, status)
        if page is None:
            rapport.cause, rapport.fin = "cookie", maintenant
            rapport.erreurs.append("Cookie LinkedIn invalide ou expiré — reconnectez-vous dans le panneau de gauche.")
            return rapport
        try:
            urls_au_fichier = db.urls_connues()
            for entreprise in lot:
                eid, nom = entreprise["id"], entreprise["nom"]
                dire(f"{nom}…")

                # 1. Identification
                if not entreprise.get("company_id") and not entreprise.get("url_linkedin"):
                    company_id = await scraper._resoudre_company_urn_via_typeahead(nom, page)
                    if not company_id:
                        store.maj_identification(eid, "non_identifiee")
                        rapport.erreurs.append(
                            f"{nom} : introuvable sur LinkedIn par son nom — collez le lien de sa page entreprise.")
                        continue
                    entreprise["company_id"] = company_id

                # 2. Fiche, si absente ou trop ancienne
                age = store.age_fiche_jours(eid, "linkedin", maintenant)
                if age is None or age >= RELECTURE_FICHE_JOURS or not entreprise.get("company_id"):
                    await charger(page, _url_apropos(entreprise))
                    lu = await page.evaluate(DOMSelectors.extract_page_apropos_js())
                    fiche = fiche_depuis_apropos(lu.get("champs") or {})
                    if not fiche or not lu.get("company_id"):
                        scraper._dumper_panneau(lu.get("html") or "")
                        store.maj_identification(eid, "illisible")
                        rapport.erreurs.append(
                            f"{nom} : page « À propos » illisible — sa structure a peut-être changé "
                            "(page enregistrée dans logs/).")
                        continue
                    if lu.get("description"):
                        fiche["description"] = lu["description"][:500]
                    store.maj_identification(eid, "identifiee", company_id=lu["company_id"])
                    entreprise["company_id"] = lu["company_id"]
                    store.enregistrer_fiche(eid, fiche, "linkedin", maintenant)

                    # 3. Annuaire officiel, recoupé — sans coût LinkedIn
                    try:
                        candidat, motif = choisir_candidat(annuaire(nom), nom, fiche.get("siege", ""))
                    except AnnuaireIndisponible as e:
                        rapport.erreurs.append(f"{nom} : annuaire officiel injoignable ({e}) — fiche annuaire inchangée.")
                    else:
                        if candidat:
                            store.enregistrer_fiche(eid, dict(fiche_depuis_annuaire(candidat), rapprochement="rapprochée"),
                                                    "annuaire", maintenant)
                        else:
                            store.enregistrer_fiche(eid, {"rapprochement": motif}, "annuaire", maintenant)

                # 4. Employés, à partir du curseur
                curseur = entreprise.get("curseur_page") or 0
                if entreprise.get("signature_familles") != signature:
                    curseur = 0
                for numero in range(curseur + 1, curseur + 1 + PAGES_MAX_PAR_ENTREPRISE):
                    await charger(page, url_recherche_personnes(entreprise["company_id"], expression, numero))
                    trouves = await scraper.extraire_profils_page(page)
                    if not trouves:
                        curseur = 0  # fin de liste : le prochain cycle repart du début
                        break
                    for personne in trouves:
                        famille = famille_de_l_intitule(personne.get("poste", ""), reglages.familles,
                                                        reglages.intitules_libres)
                        if store.relier_contact(eid, personne, famille, maintenant, urls_au_fichier):
                            rapport.nouveaux_contacts += 1
                        db.ajouter_profil(personne.get("nom", ""), personne.get("poste", ""), nom, "",
                                          personne.get("url", ""), personne.get("localisation", ""))
                    curseur = numero
                    store.maj_curseur(eid, curseur, signature)
                store.maj_curseur(eid, curseur, signature)
                store.marquer_passage(eid, maintenant)
                rapport.entreprises.append(nom)
        except _Arret as arret:
            rapport.cause = arret.cause
            if arret.cause == "deconnecte":
                rapport.erreurs.append("LinkedIn a demandé de se reconnecter : passage interrompu.")
        finally:
            await navigateur.close()
    rapport.fin = datetime.now().isoformat(timespec="seconds")
    return rapport


def lancer_passage(chemins, cookie, proxy=None, status=None) -> RapportPassage:
    """Un passage complet, verrou pris, rapport enregistré."""
    from scraper_v2 import LinkedInScraperV2

    maintenant = datetime.now().isoformat(timespec="seconds")
    store = VeilleStore(str(chemins.db_file))
    try:
        with session_linkedin(chemins.config_dir, "veille"):
            scraper = LinkedInScraperV2(use_database=True, proxy=proxy, db_file=str(chemins.db_file),
                                        profiles_csv=str(chemins.profiles_csv), config_dir=str(chemins.config_dir))
            rapport = asyncio.run(passage_async(
                scraper, store, DatabaseManager(db_file=str(chemins.db_file)),
                charger_reglages(chemins.config_dir), cookie, maintenant, status))
    except VerrouOccupe as occupe:
        rapport = RapportPassage(debut=maintenant, fin=maintenant, cause="occupe", erreurs=[str(occupe)])
    except Exception as e:
        logger.error(f"❌ Veille interrompue : {e}", exc_info=True)
        rapport = RapportPassage(debut=maintenant, fin=datetime.now().isoformat(timespec="seconds"),
                                 cause="erreur", erreurs=[f"Erreur inattendue : {e}"])
    store.enregistrer_passage(rapport.debut, rapport.fin, rapport.entreprises, rapport.pages,
                              rapport.cause, rapport.erreurs)
    return rapport


def main(argv=None) -> int:
    from cookie_utils import CookieManager
    from utils.user_context import user_paths_for

    args = argparse.ArgumentParser(description="Un passage de veille We.Reach.")
    args.add_argument("--email", required=True)
    email = args.parse_args(argv).email
    chemins = user_paths_for(email)
    cookie = CookieManager(config_dir=str(chemins.config_dir)).load_cookie()
    if not cookie:
        print("Aucun cookie LinkedIn enregistré pour cet utilisateur.", file=sys.stderr)
        return 2
    rapport = lancer_passage(chemins, cookie)
    print(f"{rapport.cause} — {len(rapport.entreprises)} entreprise(s), {rapport.pages} page(s), "
          f"{rapport.nouveaux_contacts} nouveau(x) contact(s)")
    return 0 if rapport.cause in ("termine", "budget", "rien_a_faire") else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4 : Vérifier**

Run: `venv/bin/python -m pytest tests/test_moteur_veille.py -q`
Expected: PASS (17 tests)

Si `LinkedInScraperV2._est_page_de_connexion` n'existe pas sous ce nom (`grep -n "_est_page_de_connexion" scraper_v2.py`), utiliser le nom réel du test de chemin introduit par le correctif post-essai des Profils similaires, et l'adapter dans `FauxScraper`.

Run: `venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add veille.py tests/test_moteur_veille.py
git commit -m "feat(veille): moteur de veille, du lot au rapport"
```

---

## Task 7 : Bloc d'invitation partagé

**Files:**
- Create: `ui/__init__.py` (vide), `ui/invitations.py`
- Modify: `app_advanced.py` (onglet Profils similaires : remplacer le bloc « Étape 2 » par un appel)
- Test: les tests existants `tests/test_onglet_profils_similaires.py` doivent passer **sans modification** ; ajouter `tests/test_bloc_invitations.py`

**Interfaces:**
- Consumes: `LinkedInScraperV2Sync.run_url_scraper(...)`, `scraper.scraper.human.daily_limits.remaining_invitations()`, `st.session_state.user_paths`, `st.session_state.global_cookie`, `st.session_state.export_manager`.
- Produces: `bloc_recuperer_inviter(urls: list[str], prefixe: str, libelle_bouton: str = "🚀 Récupérer les infos") -> None` — clés `{prefixe}_inviter`, `{prefixe}_message`, `{prefixe}_btn_recuperer`, `{prefixe}_dl_excel`, `{prefixe}_dl_csv`.

- [ ] **Step 1 : Lire le bloc actuel**

Run: `grep -n "Étape 2\|sim_inviter\|sim_btn_recuperer\|remaining_invitations\|sim_dl_csv" app_advanced.py`
Le bloc va du titre « Étape 2 — récupérer les infos de ces profils » jusqu'à l'affichage des erreurs du scraper qui suit `sim_dl_csv`.

- [ ] **Step 2 : Écrire le test du bloc partagé**

Créer `tests/test_bloc_invitations.py` :

```python
# -*- coding: utf-8 -*-
"""Le bloc « récupérer et inviter » partagé par Profils similaires et Veille.

Les garde-fous sont les mêmes partout : case décochée par défaut, plafond du
jour vérifié avant l'envoi. Ce test les fige au niveau du bloc ; les tests
de l'onglet Profils similaires, inchangés, prouvent le branchement.
"""

import ast
from pathlib import Path


def test_profils_similaires_utilise_le_bloc_partage():
    source = Path("app_advanced.py").read_text(encoding="utf-8")
    appels = [n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "bloc_recuperer_inviter"]
    assert appels, "l'onglet Profils similaires doit appeler bloc_recuperer_inviter"
    assert "remaining_invitations" not in source, "le plafond ne doit plus être recodé dans app_advanced.py"


def test_le_bloc_porte_les_garde_fous():
    source = Path("ui/invitations.py").read_text(encoding="utf-8")
    assert "remaining_invitations" in source
    assert 'setdefault(f"{prefixe}_inviter", False)' in source
```

- [ ] **Step 3 : Créer le module en déplaçant le bloc**

Créer `ui/__init__.py` vide, puis `ui/invitations.py` : **déplacer** le corps du bloc « Étape 2 » de l'onglet Profils similaires dans une fonction, en remplaçant chaque clé `sim_xxx` par `f"{prefixe}_xxx"`, `sim_retenues` par le paramètre `urls`, et le libellé du bouton par `libelle_bouton`. Squelette (le corps vient du code existant, déplacé tel quel) :

```python
# -*- coding: utf-8 -*-
"""« Récupérer les infos et inviter » : un seul bloc pour tout l'outil.

Utilisé par l'onglet Profils similaires et la page Veille. Les invitations
sont rares et irréversibles : les garde-fous (case décochée par défaut,
plafond du jour vérifié avant tout envoi) n'existent qu'ici, pour qu'aucun
écran ne les oublie.
"""

from datetime import datetime

import streamlit as st

from scraper_v2_sync import LinkedInScraperV2Sync


def bloc_recuperer_inviter(urls, prefixe: str, libelle_bouton: str = "🚀 Récupérer les infos") -> None:
    st.session_state.setdefault(f"{prefixe}_inviter", False)
    inviter = st.checkbox("Envoyer des invitations", key=f"{prefixe}_inviter")
    # … (corps déplacé depuis app_advanced.py : message, bouton, contrôle
    #    remaining_invitations, run_url_scraper, tableau, Excel/CSV, erreurs)
```

> Ce squelette n'est **pas** un espace réservé à inventer : le corps est le code existant de `app_advanced.py`, déplacé. L'implémenteur colle le bloc, renomme les clés, et vérifie que `tests/test_onglet_profils_similaires.py` passe inchangé. Attention : la case `sim_inviter` utilise aujourd'hui `value=False` ; la remplacer par le `setdefault` ci-dessus (même valeur, sans l'avertissement Streamlit « default value … Session State API » que le test dédié surveille).

Dans `app_advanced.py`, remplacer le bloc par :

```python
                bloc_recuperer_inviter([p["url"] for p in sim_retenues], "sim")
```

et ajouter l'import `from ui.invitations import bloc_recuperer_inviter`.

- [ ] **Step 4 : Vérifier**

Run: `venv/bin/python -m pytest tests/test_bloc_invitations.py tests/test_onglet_profils_similaires.py -q`
Expected: PASS — les tests de l'onglet passent **sans avoir été modifiés** (`git diff --stat tests/test_onglet_profils_similaires.py` vide).

Run: `venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5 : Commit**

```bash
git add ui/__init__.py ui/invitations.py app_advanced.py tests/test_bloc_invitations.py
git commit -m "refactor(invitations): un seul bloc recuperer-et-inviter pour tout l'outil"
```

---

## Task 8 : La page 🏢 Veille

**Files:**
- Create: `ui/page_veille.py`
- Modify: `app_advanced.py` (`PAGES`, `ICONES_PAGES`, branche `elif page == "🏢 Veille":`)
- Test: `tests/test_page_veille.py`

**Interfaces:**
- Consumes: `VeilleStore` (Task 3), `charger_reglages`/`sauver_reglages`/`ReglagesVeille`/`FAMILLES`/`PAGES_MIN`/`PAGES_MAX` (Task 1), `veille.lancer_passage(chemins, cookie, proxy, status) -> RapportPassage` (Task 6), `bloc_recuperer_inviter(urls, prefixe)` (Task 7), `st.session_state.user_paths` (`db_file`, `config_dir`, `profiles_csv`), `st.session_state.global_cookie`, `st.session_state.get('user_proxy')`.
- Produces: `afficher_page_veille() -> None` ; clés de widgets préfixées `veille_` ; fichier `derniere_visite_veille.txt` dans `config_dir`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_page_veille.py` :

```python
# -*- coding: utf-8 -*-
"""Page Veille : liste suivie, lancement, récap, fiche.

Le moteur est remplacé : aucune session LinkedIn ne s'ouvre. La base est
celle de l'utilisateur de test, isolée par conftest.
"""

import pytest

import veille
from tests.conftest import chemins_de_test, lancer_app, verifier_page_affichee
from veille import RapportPassage
from veille_store import VeilleStore

PAGE = "🏢 Veille"


@pytest.fixture
def store():
    s = VeilleStore(str(chemins_de_test().db_file))
    for e in s.entreprises():
        s.retirer_entreprise(e["id"])
    return s


@pytest.fixture
def moteur_espion(monkeypatch):
    appels = []

    def faux(chemins, cookie, proxy=None, status=None):
        appels.append(cookie)
        return RapportPassage(debut="2026-10-15T08:00:00", fin="2026-10-15T08:10:00",
                              entreprises=["Orbique"], pages=3, cause="budget",
                              erreurs=["Orbique : annuaire officiel injoignable"], nouveaux_contacts=2)

    monkeypatch.setattr(veille, "lancer_passage", faux)
    return appels


def _page():
    at = lancer_app(PAGE)
    verifier_page_affichee(at, PAGE)
    return at


def _bouton(at, libelle):
    return [b for b in at.button if b.label == libelle][0]


def test_la_page_est_au_menu():
    _page()


def test_ajouter_une_entreprise_par_son_lien(store):
    at = _page()
    at.text_input(key="veille_lien").set_value("https://www.linkedin.com/company/orbique/")
    _bouton(at, "Ajouter").click()
    at.run()
    assert [e["url_linkedin"] for e in store.entreprises()] == ["https://www.linkedin.com/company/orbique/"]


def test_un_lien_qui_n_est_pas_une_page_entreprise_est_refuse(store):
    at = _page()
    at.text_input(key="veille_lien").set_value("https://www.linkedin.com/in/jeanne/")
    _bouton(at, "Ajouter").click()
    at.run()
    assert store.entreprises() == []
    assert any("/company/" in e.value for e in at.error)


def test_lancer_la_veille_affiche_le_rapport(store, moteur_espion):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = "COOKIE-DE-TEST"
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert moteur_espion == ["COOKIE-DE-TEST"]
    textes = " ".join(m.value for m in list(at.markdown) + list(at.warning) + list(at.info) + list(at.success))
    assert "budget" in textes.lower()
    assert "annuaire officiel injoignable" in textes


def test_sans_cookie_la_veille_ne_part_pas(store, moteur_espion):
    store.ajouter_entreprise("Orbique", "2026-10-14")
    at = _page()
    at.session_state["global_cookie"] = ""
    _bouton(at, "🏢 Lancer la veille").click()
    at.run()
    assert moteur_espion == []
    assert any("Cookie" in e.value for e in at.error)


def test_le_recap_montre_les_nouveaux_contacts(store):
    i = store.ajouter_entreprise("Orbique", "2026-10-14")
    store.relier_contact(i, {"nom": "Jeanne Exemple", "poste": "Product Manager",
                             "url": "https://www.linkedin.com/in/jeanne-exemple/", "connexions": "2e"},
                         "Product", "2999-01-01T08:00:00", set())
    at = _page()
    tableaux = [d.value for d in at.dataframe]
    assert any("Jeanne Exemple" in df.to_string() for df in tableaux)


def test_le_recap_vide_le_dit(store):
    at = _page()
    assert any("Rien de nouveau" in i.value for i in at.info)


def test_les_reglages_se_sauvent(store):
    from utils.veille_regles import charger_reglages
    at = _page()
    at.number_input(key="veille_pages").set_value(12)
    _bouton(at, "Enregistrer les réglages").click()
    at.run()
    assert charger_reglages(chemins_de_test().config_dir).pages_par_jour == 12
```

- [ ] **Step 2 : Vérifier qu'ils échouent**

Run: `venv/bin/python -m pytest tests/test_page_veille.py -q`
Expected: FAIL — la page n'existe pas dans le menu.

- [ ] **Step 3 : Écrire la page**

Créer `ui/page_veille.py` :

```python
# -*- coding: utf-8 -*-
"""Page 🏢 Veille : entreprises suivies, lancement, récap, fiche.

Écrite hors de `app_advanced.py`, déjà très long. N'ouvre jamais LinkedIn
elle-même : elle appelle le moteur (`veille.lancer_passage`), le même que le
réveil programmé de la livraison 3.
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import veille
from ui.invitations import bloc_recuperer_inviter
from utils.veille_regles import FAMILLES, PAGES_MAX, PAGES_MIN, ReglagesVeille, charger_reglages, sauver_reglages
from veille_store import VeilleStore

_VISITE = "derniere_visite_veille.txt"
_MOTIF_LIEN = re.compile(r"^https?://([a-z]+\.)?linkedin\.com/company/[^/?#]+", re.I)

_CAUSES = {
    "termine": "Passage terminé.",
    "budget": "Budget de pages du jour atteint : les entreprises restantes passeront en tête la prochaine fois.",
    "cookie": "Cookie LinkedIn invalide ou expiré.",
    "deconnecte": "LinkedIn a demandé de se reconnecter : passage interrompu.",
    "occupe": "Une autre session LinkedIn était en cours.",
    "rien_a_faire": "Aucune entreprise à passer.",
    "erreur": "Le passage s'est interrompu sur une erreur.",
}

_ETATS = {"a_identifier": "à identifier", "identifiee": "identifiée",
          "non_identifiee": "non identifiée — collez son lien", "illisible": "page illisible"}


def _visite_precedente(config_dir) -> str | None:
    """Date de la visite précédente, lue une fois par session.

    Lue au premier affichage puis remplacée par maintenant : sinon chaque
    clic (qui relance la page) viderait le récap qu'on est en train de lire.
    """
    if "veille_visite_precedente" not in st.session_state:
        chemin = Path(config_dir) / _VISITE
        try:
            precedente = chemin.read_text(encoding="utf-8").strip() or None
        except Exception:
            precedente = None
        st.session_state["veille_visite_precedente"] = precedente
        try:
            chemin.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        except Exception:
            pass
    return st.session_state["veille_visite_precedente"]


def _afficher_rapport(rapport) -> None:
    resume = (f"**{_CAUSES.get(rapport.cause, rapport.cause)}** — "
              f"{len(rapport.entreprises)} entreprise(s), {rapport.pages} page(s) LinkedIn, "
              f"{rapport.nouveaux_contacts} nouveau(x) contact(s).")
    (st.success if rapport.cause in ("termine", "rien_a_faire") else st.warning)(resume)
    for erreur in rapport.erreurs:
        st.warning(f"⚠️ {erreur}")


def afficher_page_veille() -> None:
    chemins = st.session_state.user_paths
    store = VeilleStore(str(chemins.db_file))
    st.header("🏢 Veille entreprises")

    # ── Nouveau aujourd'hui ────────────────────────────────────────────
    st.subheader("Nouveau depuis votre dernière visite")
    nouveautes = store.nouveautes_depuis(_visite_precedente(chemins.config_dir))
    if not nouveautes["contacts"] and not nouveautes["changements"]:
        st.info("Rien de nouveau depuis votre dernière visite.")
    if nouveautes["contacts"]:
        df = pd.DataFrame(nouveautes["contacts"])[["entreprise", "famille", "nom", "poste", "degre", "url"]]
        df.insert(0, "Inviter", False)
        choix = st.data_editor(
            df.rename(columns={"entreprise": "Entreprise", "famille": "Famille", "nom": "Nom",
                               "poste": "Intitulé", "degre": "Degré", "url": "Lien"}),
            key="veille_recap", hide_index=True, use_container_width=True,
            disabled=["Entreprise", "Famille", "Nom", "Intitulé", "Degré", "Lien"],
        )
        urls = list(choix.loc[choix["Inviter"], "Lien"])
        if urls:
            bloc_recuperer_inviter(urls, "veille")
    for c in nouveautes["changements"]:
        st.markdown(f"- **{c['entreprise']}** — {c['champ']} : {c['avant']} → **{c['apres']}** "
                    f"({c['source']}, {c['releve_le'][:10]})")

    dernier = store.dernier_passage()
    if dernier:
        st.caption(f"Dernier passage : {dernier['fin'][:16].replace('T', ' ')} — "
                   f"{_CAUSES.get(dernier['cause'], dernier['cause'])}")

    # ── Lancer ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption("Une fenêtre Chrome va s'ouvrir et travailler quelques minutes : c'est normal, "
               "LinkedIn l'exige. Laissez-la faire.")
    if st.button("🏢 Lancer la veille", type="primary", key="veille_lancer"):
        if not st.session_state.get("global_cookie"):
            st.error("❌ Cookie manquant — renseignez-le dans le panneau de gauche.")
        else:
            with st.status("Veille en cours…", expanded=True) as statut:
                rapport = veille.lancer_passage(chemins, st.session_state.global_cookie,
                                                proxy=st.session_state.get("user_proxy"),
                                                status=lambda t: statut.update(label=t))
                statut.update(label="Veille terminée", state="complete")
            _afficher_rapport(rapport)

    # ── Mes entreprises ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Mes entreprises")
    entreprises = store.entreprises()
    if entreprises:
        st.dataframe(pd.DataFrame([{
            "Entreprise": e["nom"], "État": _ETATS.get(e["etat"], e["etat"]),
            "Dernier passage": (e["derniere_veille"] or "jamais")[:10], "Contacts": e["nb_contacts"],
        } for e in entreprises]), hide_index=True, use_container_width=True)
    else:
        st.info("Aucune entreprise suivie : ajoutez-en ci-dessous.")

    col1, col2 = st.columns(2)
    with col1:
        proposees = [s for s in store.societes_du_fichier()
                     if s.lower() not in {e["nom"].lower() for e in entreprises}]
        depuis_fichier = st.multiselect("Depuis mon fichier", proposees, key="veille_depuis_fichier")
        if st.button("Ajouter la sélection", key="veille_ajouter_fichier") and depuis_fichier:
            for nom in depuis_fichier:
                store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"))
            st.rerun()
    with col2:
        lien = st.text_input("Ou le lien de sa page LinkedIn", key="veille_lien",
                             placeholder="https://www.linkedin.com/company/…")
        if st.button("Ajouter", key="veille_ajouter_lien"):
            m = _MOTIF_LIEN.match((lien or "").strip())
            if not m:
                st.error("❌ Ce lien n'est pas celui d'une page entreprise LinkedIn (…/company/…).")
            else:
                url = m.group(0).rstrip("/") + "/"
                nom = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                store.ajouter_entreprise(nom, datetime.now().isoformat(timespec="seconds"), url_linkedin=url)
                st.rerun()

    if entreprises:
        a_retirer = st.selectbox("Retirer une entreprise", ["—"] + [e["nom"] for e in entreprises],
                                 key="veille_retirer")
        if a_retirer != "—" and st.button(f"Retirer {a_retirer}", key="veille_btn_retirer"):
            store.retirer_entreprise(next(e["id"] for e in entreprises if e["nom"] == a_retirer))
            st.rerun()

        # ── Fiche ──────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Fiche entreprise")
        nom = st.selectbox("Entreprise", [e["nom"] for e in entreprises], key="veille_fiche")
        e = next(x for x in entreprises if x["nom"] == nom)
        fiche = store.fiche(e["id"])
        if not fiche:
            st.info("Pas encore de fiche : elle sera remplie au prochain passage de la veille.")
        else:
            st.dataframe(pd.DataFrame([{
                "Information": cle.split(".", 1)[1], "Valeur": v["valeur"],
                "Source": "LinkedIn" if v["source"] == "linkedin" else "Annuaire officiel",
                "Relevé le": v["releve_le"][:10]} for cle, v in fiche.items()]),
                hide_index=True, use_container_width=True)
        contacts = store.contacts(e["id"])
        if contacts:
            st.dataframe(pd.DataFrame(contacts)[["famille", "nom", "poste", "degre", "decouvert_le", "url"]]
                         .rename(columns={"famille": "Famille", "nom": "Nom", "poste": "Intitulé",
                                          "degre": "Degré", "decouvert_le": "Trouvé le", "url": "Lien"}),
                         hide_index=True, use_container_width=True)
        elif e["derniere_veille"]:
            st.caption(f"Aucun contact trouvé au passage du {e['derniere_veille'][:10]}.")

    # ── Réglages ───────────────────────────────────────────────────────
    with st.expander("⚙️ Réglages de la veille"):
        r = charger_reglages(chemins.config_dir)
        familles = st.multiselect("Familles de postes", list(FAMILLES), default=r.familles, key="veille_familles")
        libres = st.text_input("Intitulés en plus (séparés par des virgules)",
                               value=", ".join(r.intitules_libres), key="veille_libres")
        pages = st.number_input("Pages LinkedIn par jour pour la veille", min_value=PAGES_MIN,
                                max_value=PAGES_MAX, value=r.pages_par_jour, key="veille_pages",
                                help="Chaque page « À propos » ou de résultats compte pour une. "
                                     "20 par défaut : environ six entreprises par matin.")
        if st.button("Enregistrer les réglages", key="veille_enregistrer"):
            if not familles and not libres.strip():
                st.error("❌ Cochez au moins une famille ou saisissez un intitulé.")
            else:
                sauver_reglages(chemins.config_dir, ReglagesVeille(
                    familles, [t.strip() for t in libres.split(",") if t.strip()], int(pages)))
                st.success("✅ Réglages enregistrés.")
```

Note : la fonction appelle `veille.lancer_passage` par le module (`veille.lancer_passage`, pas un import direct) pour que les tests puissent le remplacer.

- [ ] **Step 4 : Brancher la page**

Dans `app_advanced.py` :
1. `PAGES` : insérer `"🏢 Veille",` après `"🔍 Recherche",`.
2. `ICONES_PAGES` : ajouter `"🏢 Veille": ":material/domain:",`.
3. Import : `from ui.page_veille import afficher_page_veille`.
4. Ajouter, juste avant `elif page == "✉️ Messages":` :

```python
elif page == "🏢 Veille":
    afficher_page_veille()
```

- [ ] **Step 5 : Vérifier**

Run: `venv/bin/python -m pytest tests/test_page_veille.py tests/test_navigation.py tests/test_pages_smoke.py -q`
Expected: PASS — `test_navigation` compare pages définies et menu : les deux contiennent « 🏢 Veille ».

Run: `venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6 : Commit**

```bash
git add ui/page_veille.py app_advanced.py tests/test_page_veille.py
git commit -m "feat(veille): page Veille — entreprises suivies, recap, fiche, reglages"
```

---

## Task 9 : Essai réel, notes de version, publication

**Files:**
- Modify: `NOUVEAUTES.md`, `VERSION`

**Pourquoi cette tâche n'est pas facultative.** La recherche de l'identifiant par le nom (typeahead), l'URL `…/company/<id>/about/` et la pagination de la recherche de personnes filtrée n'ont jamais été vues en vrai. Les Profils similaires ont montré qu'une URL supposée directe peut être redirigée.

- [ ] **Step 1 : Essai réel avec Thomas** — lancer la branche sur le port 8502 sans toucher à son instance du 8501 :

```bash
cd "/Users/thxms/Desktop/Projets Dev/LinkedIn Scraper Pro" && SCRAPER_HEADLESS=false SCRAPER_STEALTH=false venv/bin/python -m streamlit run app_advanced.py --server.headless=true --server.port=8502
```

Ajouter trois entreprises : une par son lien LinkedIn, deux depuis le fichier (dont une au nom ambigu). Lancer la veille. Vérifier : identification, fiche (8 rubriques LinkedIn, annuaire rapproché ou motif clair), contacts classés par famille, pages consommées (lire `daily_limits.json` du dossier de config), récap au rechargement. Si une étape échoue : capture de la page (script jetable hors dépôt, comme pour les Profils similaires), correction **avec test** sur fixture synthétique.

- [ ] **Step 2 : Notes de version** — insérer avant la section la plus récente de `NOUVEAUTES.md` :

```markdown
## 1.6.0

**Une veille sur vos entreprises cibles.**
Nouvelle page **🏢 Veille** : ajoutez les entreprises que vous suivez — depuis
votre fichier ou par le lien de leur page LinkedIn. En un clic, l'outil
remplit leur fiche (site, taille, secteur, siège, et, pour les sociétés
françaises, dirigeants et SIREN depuis l'annuaire officiel) et cherche leurs
Product, Data et IA. Chaque visite de la page montre ce qui est nouveau
depuis la précédente ; vous choisissez qui inviter, rien ne part tout seul.
La veille avance un peu chaque jour, pour ménager votre compte LinkedIn :
une vingtaine de pages par jour, réglable.
```

- [ ] **Step 3 : Version**

```bash
echo "1.6.0" > VERSION && venv/bin/python -m pytest -q
```

Expected: PASS

- [ ] **Step 4 : Commit**

```bash
git add NOUVEAUTES.md VERSION
git commit -m "feat: veille entreprises (v1.6.0)"
```

- [ ] **Step 5 : Publier — uniquement sur accord explicite de Thomas**, et seulement après un essai réel réussi : `git push origin HEAD:main`, puis vérifier que `https://raw.githubusercontent.com/thms92/wereach-updates/main/VERSION` sert `1.6.0` (compter jusqu'à ~4 min de cache).
