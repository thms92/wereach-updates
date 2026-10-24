# Tableau de bord chiffré — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre justes les données d'invitations et d'acceptations, puis remplacer le parcours du Tableau de bord par un suivi chiffré personnel et filtrable.

**Architecture:** Quatre corrections de données d'abord (base SQLite, moteur Playwright, page Messages), chacune testée. Ensuite, un module de calcul pur (`utils/chiffres.py`), sans Streamlit, alimenté par une seule lecture de la base (`DatabaseManager.lignes_suivi`). Enfin, un bloc d'affichage (`ui/bloc_chiffres.py`) appelé par le Tableau de bord.

**Tech Stack:** Python 3.10+, Streamlit 1.58 (AppTest pour les tests d'écran), SQLite, Playwright, Plotly, pytest.

**Spec:** `docs/superpowers/specs/2026-10-24-tableau-de-bord-chiffres-design.md`

## Global Constraints

- Branche `feature/tableau-de-bord-chiffres` (partie de `feature/budget-sans-veille`, 1.8.4).
- Règle du projet : Thomas valide **avant** toute modification. Le plan approuvé couvre ce qu'il énonce, rien de plus. Un écart au plan se demande d'abord.
- Textes à l'écran : français courant, vouvoiement, pas de jargon technique (`PRODUCT.md`).
- Thème : `wefiit_theme.py`, `PALETTE_GRAPHIQUES`, police Inter. Pas de composant JS sur mesure.
- Horodatages SQLite en UTC (`CURRENT_TIMESTAMP`) ; tout calcul de jour ou de semaine se fait en **heure locale**.
- Seuil d'affichage d'un taux : **5 invitations** (`SEUIL_TAUX = 5`). Sous le seuil : `trop peu (n)`.
- Postes : les **15** plus invités, puis une ligne `Autres` (`LIMITE_POSTES = 15`).
- Période par défaut : **30 jours**. Choix : `7 jours`, `30 jours`, `Plage personnalisée`.
- Une période regroupe les invitations **envoyées** dans la période ; acceptées, messages, en attente et taux portent sur ces mêmes invitations.
- Les profils comptent une fois (profils distincts).
- Libellés vides : `Non renseignée` (école), `Non renseignée` (entreprise), `Non renseigné` (poste).
- Plafond de vérification : 30 par passage, inchangé.
- Pas de nouvelle dépendance.
- Suite de tests : `pytest -q` doit rester verte à chaque commit.

## Review Focus

1. **Invitation sur un profil dont l'extraction a échoué** (pas de `nom` lu) : l'invitation part quand même et doit être enregistrée, rattachée à un profil créé avec le nom déduit de l'URL. → Tâche 2, `test_invitation_sans_extraction_est_enregistree`.
2. **Invitation envoyée peu après minuit à Paris** (ex. 00:30 locale = 22:30 UTC la veille) : elle compte le jour local, pas la veille. → Tâche 5, `test_minuit_local_compte_le_bon_jour`.
3. **Plage personnalisée à moitié choisie** : pendant la sélection, `st.date_input` renvoie une seule date. La page ne plante pas et traite la plage comme ce seul jour. → Tâche 6, `test_plage_a_une_seule_date`.
4. **Base ancienne** sans colonnes `date_message` ni `date_verification` : la page s'affiche, avec 0 message et sans erreur. → Tâche 5, `test_lignes_suivi_base_ancienne`.
5. **Session LinkedIn expirée au milieu d'une vérification** : seules les invitations dont la page a été lue sont marquées vérifiées ; la date de dernière vérification n'est pas écrite. → Tâche 4, `test_session_expiree_ne_marque_que_les_pages_lues`.

---

### Task 1 : une mise à jour de profil n'efface plus rien

**Files:**
- Modify: `database.py` (`ajouter_profil`, la requête `UPDATE`, vers les lignes 115-125)
- Test: `tests/test_donnees_profil.py` (nouveau)

**Interfaces:**
- Produces : `ajouter_profil` garde sa signature. Comportement : une valeur vide ne remplace jamais une valeur connue (`nom`, `poste`, `entreprise`, `ecole`, `localisation`, `nb_connexions`). Une valeur non vide différente remplace l'ancienne, sauf `ecole` : une école déjà renseignée est conservée.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
def test_mise_a_jour_vide_garde_l_ecole_et_le_reste(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "p.db"))
    pid = db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL, localisation="Paris")
    assert db.ajouter_profil("Ana Test", "", "", "", URL) == pid
    assert _profil(db, URL) == {"poste": "PM", "entreprise": "Orbique",
                                "ecole": "Dauphine", "localisation": "Paris"}

def test_nouvelle_valeur_remplace_sauf_l_ecole(tmp_path):
    db = DatabaseManager(db_file=str(tmp_path / "p.db"))
    db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL)
    db.ajouter_profil("Ana Test", "Head of Product", "Nexa", "ESCP", URL)
    assert _profil(db, URL)["poste"] == "Head of Product"
    assert _profil(db, URL)["entreprise"] == "Nexa"
    assert _profil(db, URL)["ecole"] == "Dauphine"
```

(`_profil` : petite aide de test qui lit la ligne `profiles` par URL avec `sqlite3` ; `URL = "https://www.linkedin.com/in/ana-test"`.)

- [ ] **Step 2 : lancer, vérifier l'échec** — `pytest tests/test_donnees_profil.py -v` → FAIL (école et poste vidés).
- [ ] **Step 3 : implémenter** — dans l'`UPDATE`, `col = COALESCE(NULLIF(?, ''), col)` pour chaque colonne, et `ecole = COALESCE(NULLIF(ecole, ''), NULLIF(?, ''), ecole)` pour l'école.
- [ ] **Step 4 : relancer** — `pytest tests/test_donnees_profil.py -v` puis `pytest -q` → PASS.
- [ ] **Step 5 : commit** — `fix(base): une mise à jour de profil n'efface plus une valeur connue`

### Task 2 : les invitations de « Par critères » et « Profils similaires » sont enregistrées

**Files:**
- Modify: `scraper_v2.py` (`run_url_scraper_async`, autour des lignes 2078-2115)
- Test: `tests/test_donnees_profil.py`

**Interfaces:**
- Consumes : `ajouter_profil` de la tâche 1.
- Produces : `LinkedInScraperV2._enregistrer_invitation(self, url: str, nom: str, profile_data: dict, message: str) -> None`. Crée ou retrouve le profil (`ecole=''`, ce qui grâce à la tâche 1 ne touche pas une école connue), puis appelle `db.ajouter_invitation(profile_id, message)`. Ne fait rien si `self.use_database` est faux ou `self.db` absent. N'échoue jamais : une erreur est journalisée.

- [ ] **Step 1 : écrire les tests qui échouent** (scraper construit avec `use_database=True, db_file=tmp, config_dir=tmp`, sans navigateur)

```python
def test_invitation_enregistree_garde_l_ecole_de_la_recherche(tmp_path):
    sc = _scraper(tmp_path)
    sc.db.ajouter_profil("Ana Test", "PM", "Orbique", "Dauphine", URL)
    sc._enregistrer_invitation(URL, "Ana Test", {"nom": "Ana Test", "poste": "PM", "entreprise": "Orbique"}, "")
    assert sc.db.compter_parcours()["invites"] == 1
    assert _profil(sc.db, URL)["ecole"] == "Dauphine"

def test_invitation_sans_extraction_est_enregistree(tmp_path):
    sc = _scraper(tmp_path)
    sc._enregistrer_invitation(URL, "Ana Test", {}, "")
    assert sc.db.compter_parcours() == {"trouves": 1, "invites": 1, "acceptes": 0, "messages": 0}
```

- [ ] **Step 2 : lancer, vérifier l'échec** → FAIL (`_enregistrer_invitation` absent).
- [ ] **Step 3 : implémenter** `_enregistrer_invitation`, puis l'appeler dans `run_url_scraper_async` juste après `if invited:` (à côté de `increment_invitations`), avec `nom` (déjà le nom lu ou `nom_affiche`).
- [ ] **Step 4 : relancer** → PASS, `pytest -q` vert.
- [ ] **Step 5 : commit** — `fix(moteur): les invitations envoyées depuis une sélection sont enregistrées`

### Task 3 : chaque invitation garde sa date de vérification

**Files:**
- Modify: `database.py` (migration, `invitations_en_attente`, nouvelle `marquer_verifiees`)
- Create: `utils/verification.py`
- Test: `tests/test_verification_acceptations.py` (nouveau)

**Interfaces:**
- Produces :
  - colonne `invitations.date_verification TIMESTAMP`, ajoutée par migration douce comme `date_message` ;
  - `invitations_en_attente()` : même retour, nouvel ordre : jamais vérifiées d'abord (les plus récemment envoyées en tête), puis vérifiées le moins récemment ;
  - `DatabaseManager.marquer_verifiees(self, urls: List[str]) -> None` : `date_verification = CURRENT_TIMESTAMP` sur les invitations `envoyee` de ces profils ;
  - `utils/verification.py` : `enregistrer_verification(config_dir: str, moment: Optional[datetime] = None) -> None` et `derniere_verification(config_dir: str) -> Optional[datetime]`, fichier `<config_dir>/derniere_verification.json` (`{"moment": iso8601}`). Lecture d'un fichier absent ou illisible → `None`.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
def test_jamais_verifiees_d_abord_les_plus_recentes_en_tete(tmp_path): ...
    # 3 invitations : A (envoyée J-10, vérifiée J-1), B (J-5, jamais), C (J-2, jamais)
    assert [p["url"] for p in db.invitations_en_attente()] == [URL_C, URL_B, URL_A]

def test_marquer_verifiees_fait_passer_en_fin_de_liste(tmp_path): ...
    db.marquer_verifiees([URL_C])
    assert [p["url"] for p in db.invitations_en_attente()][-1] == URL_C

def test_derniere_verification_aller_retour(tmp_path):
    moment = datetime(2026, 10, 24, 9, 30, tzinfo=timezone.utc)
    enregistrer_verification(str(tmp_path), moment)
    assert derniere_verification(str(tmp_path)) == moment

def test_derniere_verification_absente_ou_illisible(tmp_path):
    assert derniere_verification(str(tmp_path)) is None
    (tmp_path / "derniere_verification.json").write_text("{pas du json")
    assert derniere_verification(str(tmp_path)) is None
```

(Les dates d'envoi et de vérification se posent dans le test par `UPDATE` SQL direct.)

- [ ] **Step 2 : lancer, vérifier l'échec.**
- [ ] **Step 3 : implémenter** — ordre SQL : `ORDER BY i.date_verification IS NOT NULL, i.date_verification ASC, i.date_envoi DESC`.
- [ ] **Step 4 : relancer** → PASS, `pytest -q` vert.
- [ ] **Step 5 : commit** — `feat(acceptations): chaque invitation garde la date de sa dernière vérification`

### Task 4 : une acceptation = une relation de 1er degré, et la vérification est tracée

**Files:**
- Modify: `scraper_v2.py` (`verifier_acceptations_async`, lignes ~890-935 ; nouvelle fonction de module)
- Modify: `scraper_v2_sync.py` (`verifier_acceptations`, lignes ~178-196)
- Modify: `ui/page_messages.py` (bloc `if lancer:`, lignes ~132-158)
- Test: `tests/test_verification_acceptations.py`, `tests/test_page_messages.py`

**Interfaces:**
- Consumes : `marquer_verifiees`, `enregistrer_verification` (tâche 3).
- Produces :
  - `degre_depuis_entete(texte: str) -> str` (module `scraper_v2`) : lit le degré dans le texte de l'en-tête d'un profil. Renvoie `"1er"`, `"2e"`, `"3e"` ou `""`. Reconnaît `· 1er`, `· 2e`, `· 3e` et les formes anglaises `· 1st`, `· 2nd`, `· 3rd` (ramenées aux formes françaises). Jamais un « 2e » au milieu d'un intitulé (même règle que `utils/dom_selectors.py` ~ligne 1010) ;
  - `verifier_acceptations_async` : une personne est acceptée seulement si `degre_depuis_entete(<texte de la première section de main>) == "1er"`. Le bouton « Message » ne suffit plus. Degré illisible = non acceptée. Nouvel attribut `self.verifiees: List[str]` : URLs dont la page a été lue (chargée, sans redirection login) ;
  - `LinkedInScraperV2Sync.verifiees: List[str]` : copie de `self.scraper.verifiees` après succès, `[]` si verrou occupé ou erreur ;
  - page Messages : après la vérification, `db.marquer_verifiees(sc.verifiees)` ; `enregistrer_verification(config_dir)` seulement si la session n'était pas occupée et qu'aucune `SESSION_EXPIREE` n'est dans `sc.errors`.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
@pytest.mark.parametrize("texte,attendu", [
    ("Ana Test · 1er\nProduct Manager chez Orbique", "1er"),
    ("Ana Test · 2e\nPM", "2e"),
    ("Ana Test · 1st\nPM", "1er"),
    ("Ana Test\nAlternante 2e année · Paris", ""),
    ("", ""),
])
def test_degre_depuis_entete(texte, attendu):
    assert degre_depuis_entete(texte) == attendu

def test_session_expiree_ne_marque_que_les_pages_lues(...):
    # page Messages, scraper factice : verifiees=[URL_A], errors=[SESSION_EXPIREE]
    # → URL_A a une date_verification, URL_B non ; derniere_verification(config_dir) is None

def test_verification_reussie_enregistre_la_date(...):
    # scraper factice : verifiees=[URL_A, URL_B], errors=[] → derniere_verification non None
```

(Les tests d'écran suivent le patron de `tests/test_page_messages.py` : `monkeypatch` de `scraper_v2_sync.LinkedInScraperV2Sync` par une classe factice qui expose `verifier_acceptations`, `errors`, `verifiees`.)

- [ ] **Step 2 : lancer, vérifier l'échec.**
- [ ] **Step 3 : implémenter** `degre_depuis_entete`, le nouveau critère et `verifiees` dans le moteur, la copie dans le wrapper, le câblage dans la page Messages.
- [ ] **Step 4 : relancer** → PASS, `pytest -q` vert.
- [ ] **Step 5 : vérification en réel, avec Thomas** — lancer l'app en local, cliquer « Vérifier qui a accepté » avec au moins une relation de 1er degré connue et une personne de 2e degré au profil ouvert parmi les invitations en attente. Attendu : seule la première est comptée. Si le texte de l'en-tête ne contient pas le degré, s'arrêter et rapporter le texte lu (journal) avant de changer de sélecteur.
- [ ] **Step 6 : commit** — `fix(acceptations): seule une relation de 1er degré compte comme acceptée`

### Task 5 : le calcul des chiffres

**Files:**
- Modify: `database.py` (nouvelle `lignes_suivi`)
- Create: `utils/chiffres.py`
- Test: `tests/test_chiffres.py` (nouveau)

**Interfaces:**
- Consumes : colonnes `date_message`, `date_verification` (tâche 3), `ecoles_du_libelle` (`utils/ecoles.py`).
- Produces :
  - `DatabaseManager.lignes_suivi(self) -> List[Dict]` : une ligne par **profil invité** : `url`, `ecole`, `entreprise`, `poste`, `date_envoi` (première invitation, texte UTC brut), `acceptee: bool`, `messagee: bool`, `verifiee: bool`. Colonnes absentes d'une base ancienne → `False`. Erreur → `[]` ;
  - dans `utils/chiffres.py` (pur, sans Streamlit) :
    - `SEUIL_TAUX = 5`, `LIMITE_POSTES = 15`, `AUTRES = "Autres"` ;
    - `@dataclass(frozen=True) Periode: debut: date, fin: date` (bornes incluses, jours locaux) ;
    - `periode_glissante(jours: int, aujourd_hui: date) -> Periode` (`7` → aujourd'hui et les 6 jours d'avant) ;
    - `jour_local(brut: str) -> Optional[date]` (UTC → date locale ; illisible → `None`) ;
    - `filtrer(lignes, periode, ecoles=(), entreprises=(), postes=()) -> List[Dict]` (filtres vides = tout ; une école filtrée retient les libellés composites qui la contiennent) ;
    - `@dataclass(frozen=True) ChiffresCles: invitations, acceptees, messages, en_attente, jamais_verifiees: int` ; `chiffres_cles(lignes) -> ChiffresCles` (`jamais_verifiees` = en attente et non vérifiées) ;
    - `texte_taux(acceptes: int, invites: int) -> str` : `"33 %"` (espace fine insécable ` `), `"trop peu (3)"` sous le seuil ;
    - `par_semaine(lignes, periode) -> List[Tuple[date, int, int]]` : (lundi, invitations, acceptées), une entrée par semaine touchée par la période, semaines vides comprises ;
    - `@dataclass(frozen=True) LigneTableau: libelle: str, invites: int, acceptes: int` ; `par_categorie(lignes, cle: str) -> List[LigneTableau]` pour `cle` dans `"ecole"`, `"entreprise"`, `"poste"`. Trié par `invites` décroissant puis libellé. Regroupement sans casse ni espaces en trop, libellé affiché = première orthographe rencontrée. École : un libellé composite compte pour chaque école. `"poste"` : 15 premières lignes puis `Autres` (somme du reste) ;
    - `options_filtres(lignes) -> Dict[str, List[str]]` : valeurs proposées par filtre (`ecole` éclatée en écoles), triées.

- [ ] **Step 1 : écrire les tests qui échouent** (lignes construites à la main, pas de base, sauf pour `lignes_suivi`)

```python
def test_minuit_local_compte_le_bon_jour(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Paris"); time.tzset()
    assert jour_local("2026-10-23 22:30:00") == date(2026, 10, 24)

def test_texte_taux():
    assert texte_taux(61, 184) == "33 %"
    assert texte_taux(2, 3) == "trop peu (3)"
    assert texte_taux(0, 5) == "0 %"

def test_chiffres_cles_d_une_periode():
    # 6 lignes dans la période : 2 acceptées dont 1 messagée, 4 en attente dont 3 jamais vérifiées
    assert chiffres_cles(lignes) == ChiffresCles(6, 2, 1, 4, 3)

def test_filtre_ecole_retient_les_libelles_composites(): ...
def test_par_semaine_inclut_les_semaines_vides(): ...
def test_par_categorie_regroupe_sans_casse_et_non_renseignee(): ...
    # "Orbique", "orbique ", "" → [LigneTableau("Orbique", 2, ...), LigneTableau("Non renseignée", 1, ...)]
def test_postes_au_dela_de_15_vont_dans_autres(): ...
def test_lignes_suivi_compte_un_profil_invite_deux_fois_une_fois(tmp_path): ...
def test_lignes_suivi_base_ancienne(tmp_path): ...  # tables sans date_message ni date_verification
```

- [ ] **Step 2 : lancer, vérifier l'échec.**
- [ ] **Step 3 : implémenter** `lignes_suivi` puis `utils/chiffres.py`.
- [ ] **Step 4 : relancer** → PASS, `pytest -q` vert.
- [ ] **Step 5 : commit** — `feat(chiffres): calcul des chiffres du tableau de bord`

### Task 6 : le nouveau Tableau de bord

**Files:**
- Create: `ui/bloc_chiffres.py`
- Modify: `ui/page_tableau_de_bord.py` (retirer `_bloc_derniere_recherche`, `_bloc_ecoles`, `_bloc_parcours` et leurs imports devenus inutiles ; « À faire » sur toute la largeur ; appeler le nouveau bloc)
- Modify: `utils/tutoriel.py` (étape « Votre parcours », ligne ~46-48)
- Modify: `tests/test_refonte_tableau_de_bord.py`, `tests/test_tutoriel*.py` et tout test qui vise le parcours retiré (adapter, ne pas supprimer en bloc)
- Test: `tests/test_bloc_chiffres.py` (nouveau)

**Interfaces:**
- Consumes : tout `utils/chiffres.py` (tâche 5), `db.lignes_suivi()`, `derniere_verification(config_dir)` (tâche 3), `date_locale` (déjà dans `page_tableau_de_bord.py`).
- Produces : `afficher_bloc_chiffres(db, config_dir: str, aujourd_hui: Optional[date] = None) -> None` dans un `st.container(key="tdb_chiffres")`. Clés de widgets : `tdb_periode` (choix `7 jours` / `30 jours` / `Plage personnalisée`, défaut `30 jours`), `tdb_plage`, `tdb_f_ecole`, `tdb_f_entreprise`, `tdb_f_poste`.

Contenu, dans l'ordre (spec, « La page, de haut en bas ») :
1. filtres sur une ligne ;
2. cinq tuiles : `Invitations`, `Acceptées`, `Taux d'acceptation` (avec `X sur Y` dessous), `Messages envoyés`, `En attente` ;
3. ligne de vérification, copie exacte :
   - `Acceptations vérifiées pour la dernière fois le {jj/mm} à {hh:mm}, depuis la page Messages.`
   - `Acceptations jamais vérifiées : utilisez « Vérifier qui a accepté » dans la page Messages.`
   - si `jamais_verifiees > 0` : `{n} invitation(s) de la période n'ont jamais été vérifiées.` (accord par `pluriel`) ;
4. graphique Plotly, barres groupées invitations / acceptations par semaine (`PALETTE_GRAPHIQUES[0]` et l'orange `#F98F03`) ;
5. trois tableaux `Par école`, `Par entreprise`, `Par poste` : colonnes `Invités`, `Acceptés`, `Taux` (`texte_taux`).

États vides : aucune ligne du tout → `afficher_etat_vide` avec les étapes existantes (session, recherche, inviter) ; des invitations, mais aucune après filtres → `Aucune invitation sur cette période avec ces filtres.`

Tutoriel : l'étape devient « Vos chiffres », cible `.st-key-tdb_chiffres, .wf-vide`, texte : `Invitations, acceptations, messages : vos chiffres sur la période choisie, filtrables par école, entreprise et poste.`

- [ ] **Step 1 : écrire les tests qui échouent** (AppTest via `lancer_app("📊 Dashboard")`, base de test remplie par `ajouter_profil` / `ajouter_invitation` comme `tests/test_phase4_coque.py`)

```python
def test_tableau_de_bord_affiche_les_cinq_tuiles(...): ...
def test_plus_de_parcours_ni_derniere_recherche(...):  # ol.wf-entonnoir et "Dernière recherche" absents
def test_taux_sous_le_seuil_affiche_trop_peu(...): ...
def test_filtre_sans_resultat_dit_pourquoi(...): ...
def test_plage_a_une_seule_date(...):  # session_state tdb_periode="Plage personnalisée", tdb_plage=(date,) → pas d'exception
def test_jamais_verifiees_signalees(...): ...
def test_etape_tutoriel_vise_le_bloc_chiffres():
    assert ".st-key-tdb_chiffres" in _etape_tdb("Vos chiffres")["cible"]
```

- [ ] **Step 2 : lancer, vérifier l'échec.**
- [ ] **Step 3 : implémenter** `ui/bloc_chiffres.py`, alléger `ui/page_tableau_de_bord.py`, mettre à jour l'étape du tutoriel et adapter les anciens tests.
- [ ] **Step 4 : relancer** → `pytest -q` vert.
- [ ] **Step 5 : vérification visuelle** — lancer l'app en local (skill `run`), capture du Tableau de bord en clair et en sombre, à 1440 px ; contrôler que le tutoriel trouve bien sa cible « Vos chiffres ».
- [ ] **Step 6 : commit** — `feat(tableau-de-bord): vos chiffres, filtrables par période, école, entreprise et poste`

### Task 7 : version et nouveautés

**Files:**
- Modify: `VERSION` (`1.9.0`), `NOUVEAUTES.md` (section `## 1.9.0` en tête)

- [ ] **Step 1 : rédiger la section**, pour les utilisateurs (style des sections existantes) :
  - **Vos chiffres sur le Tableau de bord.** Invitations, acceptations, messages, par période, école, entreprise et poste.
  - **Des acceptations plus justes.** Seules vos vraies relations comptent, et chaque vérification passe en revue les invitations pas encore vérifiées.
  - Une phrase : `Les invitations envoyées avant cette version depuis « Par critères » ou « Profils similaires » n'apparaissent pas dans les chiffres.`
- [ ] **Step 2 : `pytest -q`** → vert (dont les tests de nouveautés).
- [ ] **Step 3 : commit** — `chore: version 1.9.0`
- [ ] **Step 4 : s'arrêter.** Publication (`publish_update.sh`) seulement sur demande de Thomas.
