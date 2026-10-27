# Rythme humain et arrêt sur page d'alerte — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que l'outil charge peu de pages LinkedIn, à un rythme de personne, compte chacune d'elles, et s'arrête net sur une page d'alerte LinkedIn.

**Architecture:** Toutes les navigations de `scraper_v2.py` passent par une seule méthode `_naviguer`, qui vérifie les budgets (jour et séance), compte la page, attend le rythme humain et appelle le détecteur d'alerte (`utils/alerte_linkedin.py`). Les séances (fenêtre de 30 min, pause de 20 min, 4 par jour) sont un petit état persistant par personne (`utils/seances.py`), contrôlé par l'enveloppe synchrone `scraper_v2_sync.py` avant chaque action. Les limites vivent dans `config.py`.

**Tech Stack:** Python 3.10+, Playwright, Streamlit 1.58, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-rythme-humain-design.md`

## Global Constraints

- Branche `feature/tableau-de-bord-chiffres` (version 1.9.0, non publiée). Ne rien pousser, ne rien publier.
- Constantes dans `config.py` (`ScraperConfig`), valeurs exactes :
  `MAX_PAGES_PER_DAY = 60`, `MAX_INVITATIONS_PER_DAY = 20` (désormais **bloquant**), `MAX_PROFILES_PER_RUN = 25`, `MAX_PAGES_PER_SEANCE = 25`, `SEANCE_FENETRE_MIN = 30`, `PAUSE_ENTRE_SEANCES_MIN = 20`, `MAX_SEANCES_PER_DAY = 4`, `DELAI_PAGE_MIN_S = 8`, `DELAI_PAGE_MAX_S = 20`, `PAUSE_LECTURE_PROBA = 1/6`, `PAUSE_LECTURE_MIN_S = 30`, `PAUSE_LECTURE_MAX_S = 90`, `MAX_VERIFICATIONS_PAR_JOUR = 1`, `MAX_VERIFICATIONS_PAR_PASSAGE = 10`, `MAX_MESSAGES_PAR_SEANCE = 10`.
- **Aucune** période de repos, aucun message d'alerte, aucun bandeau, aucun bouton « avertissement », aucune limite d'horaire (décisions de Thomas, 2026-10-27).
- **Aucune** dissimulation de l'automatisation : pas de fausse empreinte, pas de masquage de `navigator.webdriver`, pas de rotation d'IP/proxy, pas de résolution de captcha. `SCRAPER_STEALTH` reste désactivé.
- Une page = une navigation de l'outil vers linkedin.com (chargement, page de résultats suivante, profil, panneau, fil du warm-up). Clic « Se connecter » et fenêtre d'envoi = 0 page.
- Textes : français courant, vouvoiement. Les refus disent pourquoi et quand ce sera possible.
- Tests : `venv/bin/python -m pytest -q` vert à chaque commit (652 au départ). Aucun test ne lance de navigateur ni ne touche LinkedIn.

## Review Focus

Chaque ligne dit ce que **voit la personne**, pas seulement ce que fait le code.

1. **Plafond de pages atteint au milieu d'une recherche** : l'action s'arrête à la page qui atteint 60, ce qui est déjà trouvé ou invité reste affiché et enregistré, et la personne lit sous les résultats « Limite du jour atteinte : 60 pages LinkedIn consultées. Vous pourrez reprendre demain. » → Tâche 3, `test_budget_pages_atteint_en_cours_garde_le_travail_fait`.
2. **Deuxième temps d'une tâche (inviter après avoir cherché) dans la fenêtre de 30 min** : il n'est pas refusé par la pause de 20 min ; la personne ne voit aucun refus. → Tâche 4, `test_deuxieme_appel_dans_la_fenetre_continue_la_seance`.
3. **Page d'alerte LinkedIn pendant une invitation** : Chrome se ferme, aucune page de plus n'est chargée, l'invitation en cours n'est pas comptée comme envoyée, et la personne voit le libellé d'erreur existant « session interrompue » (pas de nouveau texte). → Tâche 3, `test_page_alerte_arrete_la_boucle_sans_compter_l_action`.
4. **Profil normal contenant le mot « restreint »** : rien ne s'arrête, la personne ne voit rien. → Tâche 2, `test_mot_restreint_sur_un_profil_n_est_pas_une_alerte`.
5. **Refus de pause** : bouton cliqué 5 min après une séance → la personne lit « Pause entre deux séances : prochaine action possible à 14:35. » et aucune fenêtre Chrome ne s'ouvre. → Tâche 4, `test_refus_de_pause_dit_l_heure_et_n_ouvre_pas_chrome`.

---

### Task 1 : constantes et compteur de pages

**Files:**
- Modify: `config.py` (bloc des limites, ~l.26-47), `utils/human_behavior.py` (`DailyLimitsTracker`, ~l.30-110 ; construction dans `HumanBehavior.__init__` ~l.200-212)
- Test: `tests/test_rythme_humain.py` (nouveau)

**Interfaces:**
- Produces : constantes de Global Constraints dans `ScraperConfig` ; `DailyLimitsTracker(max_pages: int = 60, ...)` avec `increment_pages(n: int = 1) -> None`, `pages_today -> int` (clé JSON `"pages_linkedin"`), `remaining_pages() -> int`, `can_navigate() -> bool`. `HumanBehavior` passe `MAX_PAGES_PER_DAY` au tracker. Les compteurs existants restent.

- [ ] **Step 1 : tests rouges**

```python
def test_compteur_de_pages_par_jour(tmp_path):
    t = DailyLimitsTracker(max_pages=3, limits_file=str(tmp_path / "l.json"))
    t.increment_pages(); t.increment_pages(2)
    assert t.pages_today == 3 and t.remaining_pages() == 0 and not t.can_navigate()

def test_compteur_de_pages_relu_et_remis_a_zero_le_lendemain(tmp_path): ...
    # fichier daté d'hier avec pages_linkedin=50 → pages_today == 0

def test_constantes_du_rythme():
    assert (ScraperConfig.MAX_PAGES_PER_DAY, ScraperConfig.MAX_PROFILES_PER_RUN,
            ScraperConfig.MAX_PAGES_PER_SEANCE, ScraperConfig.PAUSE_ENTRE_SEANCES_MIN) == (60, 25, 25, 20)
```

- [ ] **Step 2 : lancer, vérifier l'échec.**
- [ ] **Step 3 : implémenter** les constantes et les méthodes.
- [ ] **Step 4 : `pytest -q` vert** (adapter les tests qui figeaient 80 profils par recherche).
- [ ] **Step 5 : commit** — `feat(rythme): compteur de pages LinkedIn par jour et constantes du rythme`

### Task 2 : détecteur de page d'alerte

**Files:**
- Create: `utils/alerte_linkedin.py`
- Test: `tests/test_alerte_linkedin.py`

**Interfaces:**
- Produces : `nature_page(url: str, texte: Optional[str] = None, statut: Optional[int] = None) -> Optional[str]` → `"session"` (login/authwall simple), `"alerte"` (checkpoint, challenge, texte d'alerte, 429, 999), ou `None`. Constantes `CHEMINS_ALERTE = ("/checkpoint/", "/challenge/")`, `CHEMINS_SESSION = ("/authwall", "/uas/login", "/login")`, `CHEMINS_TRAVAIL = ("/in/", "/search/", "/feed/", "/mynetwork/", "/company/", "/school/")`, `TEXTES_ALERTE` (au moins : « activité inhabituelle », « unusual activity », « vérifions qu'il s'agit bien de vous », « let's do a quick security check », « votre compte a été restreint », « your account has been restricted » ; comparaison sans casse). Le texte n'est examiné **que** si le chemin n'est pas dans `CHEMINS_TRAVAIL`.

- [ ] **Step 1 : tests rouges** (table paramétrée)

```python
@pytest.mark.parametrize("url,texte,statut,attendu", [
    ("https://www.linkedin.com/checkpoint/challenge/AgGun67__rMi0g", "", 200, "alerte"),
    ("https://www.linkedin.com/authwall?trk=x", "", 200, "session"),
    ("https://www.linkedin.com/uas/login?session_redirect=x", "", 200, "session"),
    ("https://www.linkedin.com/in/ana-test/", "Compte restreint aux membres", 200, None),
    ("https://www.linkedin.com/feed/", "", 429, "alerte"),
    ("https://www.linkedin.com/in/ana-test/", "", 999, "alerte"),
    ("https://www.linkedin.com/some/other/", "Nous avons remarqué une activité inhabituelle sur votre compte", 200, "alerte"),
    ("https://www.linkedin.com/search/results/people/?keywords=x", "", 200, None),
])
def test_nature_page(url, texte, statut, attendu): ...

def test_mot_restreint_sur_un_profil_n_est_pas_une_alerte(): ...
```

- [ ] **Step 2 : échec.** - [ ] **Step 3 : implémenter.** - [ ] **Step 4 : vert.**
- [ ] **Step 5 : commit** — `feat(rythme): reconnaître une page d'alerte LinkedIn`

### Task 3 : une seule porte de navigation, comptée, rythmée, arrêtée sur alerte

**Files:**
- Modify: `scraper_v2.py` — toutes les navigations (`safe_page_goto` ~l.372, 606, 812, 945, 1217, 1445, 1895, 2121, et le `page.goto` de `_resoudre_company_urn_via_navigation` ~l.358), les boucles qui les entourent, les plafonds par passage ; `utils/human_behavior.py` — `warmup_session` (`page.goto` du fil ~l.552) et nouvelle pause humaine
- Test: `tests/test_rythme_humain.py`

**Interfaces:**
- Consumes : tâche 1 (`can_navigate`, `increment_pages`), tâche 2 (`nature_page`).
- Produces :
  - exceptions de module `ArretLinkedIn(Exception)` avec `.motif in {"alerte", "session", "budget_jour", "budget_seance"}` ;
  - `LinkedInScraperV2.limite_pages_seance: Optional[int]` (posée par l'enveloppe, tâche 4 ; `None` = pas de plafond de séance) et `pages_cette_seance: int` ;
  - `async def _naviguer(self, page, url: str) -> bool` : refuse **avant** de charger si `can_navigate()` est faux (`ArretLinkedIn("budget_jour")`) ou si `pages_cette_seance >= limite_pages_seance` (`ArretLinkedIn("budget_seance")`) ; sinon attend `await self.human.pause_entre_pages()`, charge via `network_manager.safe_page_goto`, compte 1 page (jour et séance) même si le chargement échoue après envoi de la requête, lit `page.url`, le statut de la réponse principale et — hors `CHEMINS_TRAVAIL` — `page.locator("body").inner_text()` court, puis lève `ArretLinkedIn(nature)` si `nature_page(...)` n'est pas `None` ; renvoie le booléen de `safe_page_goto`. Ne recharge pas une URL déjà ouverte dans ce passage (ensemble `self._deja_ouvertes`, URL normalisée sans `?` ni `/` final) : renvoie `True` sans compter si la page courante est déjà celle-là, sinon recharge (cas d'un retour nécessaire) mais compte ;
  - `HumanBehavior.pause_entre_pages() -> None` : attente aléatoire entre `DELAI_PAGE_MIN_S` et `DELAI_PAGE_MAX_S`, et avec la probabilité `PAUSE_LECTURE_PROBA` une attente supplémentaire entre `PAUSE_LECTURE_MIN_S` et `PAUSE_LECTURE_MAX_S` ; remplace les `human_delay(DELAY_BETWEEN_PROFILES_…)` des boucles (pas les petits délais d'interface après un clic) ;
  - `warmup_session(page, naviguer=None)` : quand `naviguer` est fourni, le fil passe par lui (le warm-up compte 1 page et passe le détecteur) ;
  - dans chaque point d'entrée async (`run_scraper_async`, `run_url_scraper_async`, `recolter_browsemap_async`, `verifier_acceptations_async`, `envoyer_messages_async`, résolution d'entreprise) : `except ArretLinkedIn` ferme Chrome, garde ce qui est fait, n'ajoute pas l'action en cours, et range dans `self.errors` : `SESSION_EXPIREE` pour `"session"` et `"alerte"` (libellé existant, aucun texte nouveau pour l'alerte) ; pour `"budget_jour"` : `Limite du jour atteinte : {n} pages LinkedIn consultées. Vous pourrez reprendre demain.` ; pour `"budget_seance"` : `Séance terminée : {n} pages consultées. Prochaine séance possible dans 20 minutes.` ; l'alerte est aussi écrite au journal (`logger.error`, avec l'URL) ;
  - plafonds par passage : recherche `MAX_PROFILES_PER_RUN` (25), vérification `MAX_VERIFICATIONS_PAR_PASSAGE` (10), messages `MAX_MESSAGES_PAR_SEANCE` (10) — valeurs par défaut des signatures et des appels dans `ui/page_messages.py` (`max_check=30` → constante, `MAX_ENVOIS` → constante) ;
  - l'ancien `can_scrape`/`increment_profiles` de la recherche reste comme statistique mais ne bloque plus (le plafond de pages remplace le plafond de profils).

- [ ] **Step 1 : tests rouges** (page et `network_manager` factices, `pause_entre_pages` remplacée par une coroutine immédiate, aucun navigateur)

```python
def test_chaque_navigation_compte_une_page(...): ...       # 3 _naviguer → pages_today == 3
def test_budget_jour_refuse_avant_de_charger(...): ...      # can_navigate False → ArretLinkedIn("budget_jour"), goto jamais appelé
def test_budget_seance(...): ...                            # limite_pages_seance=2 → 3e appel lève "budget_seance"
def test_page_alerte_leve_alerte(...): ...                  # page.url = …/checkpoint/challenge/… → ArretLinkedIn("alerte")
def test_meme_profil_pas_rouvert_dans_le_passage(...): ...  # 2e _naviguer même URL, page déjà dessus → goto appelé 1 fois, 1 page
def test_page_alerte_arrete_la_boucle_sans_compter_l_action(...): ...
    # run_url_scraper_async, 3 URLs, la 2e renvoie une page checkpoint :
    # 1 seule ligne de résultat, errors == [SESSION_EXPIREE], invitations_today == 1, browser.close appelé
def test_budget_pages_atteint_en_cours_garde_le_travail_fait(...): ...
    # plafond atteint à la 3e URL : 2 lignes gardées, errors contient « Limite du jour atteinte : 60 pages »
def test_pause_entre_pages_respecte_les_bornes(monkeypatch): ...  # random fixé → durée dans [8, 20] ou [38, 110]
def test_warmup_passe_par_la_porte(...): ...                # le fil compte 1 page
```

- [ ] **Step 2 : échec.**
- [ ] **Step 3 : implémenter** `_naviguer`, l'exception, la pause, puis remplacer **chaque** navigation listée (grep de contrôle : `rg "safe_page_goto|page\.goto" scraper_v2.py utils/human_behavior.py` ne doit plus montrer d'appel hors de `_naviguer` et de `NetworkManager`).
- [ ] **Step 4 : `pytest -q` vert.**
- [ ] **Step 5 : commit** — `feat(rythme): une seule porte de navigation, comptée, rythmée, arrêtée sur alerte`

### Task 4 : séances et pauses

**Files:**
- Create: `utils/seances.py`
- Modify: `scraper_v2_sync.py` (chaque méthode publique, avant `session_linkedin(...)` et après), `ui/page_messages.py` (une vérification par jour)
- Test: `tests/test_seances.py`

**Interfaces:**
- Consumes : constantes de la tâche 1 ; `limite_pages_seance`, `pages_cette_seance`, `ArretLinkedIn` (tâche 3).
- Produces (`utils/seances.py`, état dans `<config_dir>/seances.json`, illisible ou absent = aucun historique) :
  - `debut_action(config_dir: str, maintenant: datetime) -> Tuple[Optional[str], int]` : renvoie `(refus, pages_restantes_seance)`. Règles : si une séance est ouverte depuis moins de `SEANCE_FENETRE_MIN` minutes et a encore des pages → on continue (pas de refus). Sinon on ouvre une nouvelle séance, à condition que : le nombre de séances du jour < `MAX_SEANCES_PER_DAY` (refus : `Vous avez fait 4 séances aujourd'hui. Vous pourrez reprendre demain.`) et que `PAUSE_ENTRE_SEANCES_MIN` minutes se soient écoulées depuis la fin de la dernière action (refus : `Pause entre deux séances : prochaine action possible à {HH:MM}.`).
  - `fin_action(config_dir: str, maintenant: datetime, pages: int) -> None` : ajoute les pages à la séance ouverte et note l'heure de fin ; une séance dont les pages atteignent `MAX_PAGES_PER_SEANCE` est close.
  - `verification_permise(config_dir: str, maintenant: datetime) -> Optional[str]` et `noter_verification(config_dir, maintenant)` : au plus `MAX_VERIFICATIONS_PAR_JOUR` ; refus : `Vérification déjà faite aujourd'hui. Vous pourrez la refaire demain.`
- Câblage dans `LinkedInScraperV2Sync` : avant chaque action, `debut_action` ; refus → `self.errors = [refus]`, renvoyer le résultat vide habituel **sans** ouvrir Chrome ni prendre le verrou ; sinon `self.scraper.limite_pages_seance = pages_restantes` et `pages_cette_seance = 0`, puis l'action, puis `fin_action(..., self.scraper.pages_cette_seance)` dans un `finally`. `verifier_acceptations` contrôle aussi `verification_permise` et appelle `noter_verification` quand au moins une page a été lue.
- L'affichage des refus passe par les blocs d'erreurs existants des pages (vérifier dans `ui/invitations.py`, `ui/page_recherche.py`, `ui/page_messages.py`, onglet profils similaires que `errors` est montré en clair et non comme « 0 résultat » ; sinon l'ajouter comme pour `message_occupe`).

- [ ] **Step 1 : tests rouges** (horloge passée en paramètre)

```python
def test_premiere_action_ouvre_une_seance(tmp_path): ...
def test_deuxieme_appel_dans_la_fenetre_continue_la_seance(tmp_path): ...
    # début 10:00, fin 10:05 (8 pages) ; 10:12 → pas de refus, pages restantes 17
def test_refus_de_pause_dit_l_heure_et_n_ouvre_pas_chrome(tmp_path, monkeypatch): ...
    # séance close à 10:00 (fenêtre dépassée à 10:31) ; appel à 10:40 → refus « … possible à 10:51. » ;
    # via LinkedInScraperV2Sync avec async_playwright espionné → jamais appelé, errors == [refus]
def test_cinquieme_seance_refusee(tmp_path): ...
def test_seance_close_a_25_pages(tmp_path): ...
def test_une_verification_par_jour(tmp_path): ...
def test_etat_illisible_repart_de_zero(tmp_path): ...
```

- [ ] **Step 2 : échec.** - [ ] **Step 3 : implémenter et câbler.** - [ ] **Step 4 : `pytest -q` vert.**
- [ ] **Step 5 : commit** — `feat(rythme): séances courtes et pauses entre séances`

### Task 5 : 20 invitations par jour, bloquantes, et jauge des pages

**Files:**
- Modify: `scraper_v2.py` (recherche avec invitation, `run_url_scraper_async`, `envoyer_invitation` : ne plus inviter quand `can_invite()` est faux), `utils/budget.py` (`message_depassement` devient un refus), `ui/invitations.py` (~l.230-240 : la confirmation refuse au-delà du reste au lieu d'avertir), `ui/composants.py` (`jauge_budget` : plus de « conseillées », plus de dépassement ; nouvelle jauge des pages), barre latérale dans `app_advanced.py` (jauge « Pages LinkedIn du jour » sous celle des invitations), `utils/tutoriel.py` si la cible de la jauge change
- Test: tests existants des jauges/budget à adapter (`tests/test_composants.py`, `tests/test_budget.py`, `tests/test_interface_audit.py`, `tests/test_phase4_*`), plus `tests/test_rythme_humain.py`

**Interfaces:**
- Consumes : `DailyLimitsTracker` (tâche 1).
- Produces : `budget_pages_du_jour(config_dir: str) -> Budget` dans `utils/budget.py` (même `Budget(utilisees, plafond)`) ; `jauge_pages(utilisees: int, plafond: int) -> str` dans `ui/composants.py`, libellé `Pages LinkedIn du jour`, texte `{restantes} restantes sur 60`, même structure ARIA que `jauge_budget`. Textes des invitations : `{restantes} restantes sur 20` (plus « conseillées ») ; refus à la confirmation : `Il vous reste {r} invitation(s) aujourd'hui : sélectionnez-en {r} au plus.` ; refus moteur quand le plafond est atteint en cours : `Limite du jour atteinte : 20 invitations envoyées. Vous pourrez reprendre demain.`

- [ ] **Step 1 : tests rouges** — `test_invitation_refusee_au_dela_de_20`, `test_confirmation_refuse_une_selection_trop_grande`, `test_jauge_des_pages`, `test_jauge_invitations_sans_conseillees`.
- [ ] **Step 2 : échec.** - [ ] **Step 3 : implémenter.** - [ ] **Step 4 : `pytest -q` vert.**
- [ ] **Step 5 : commit** — `feat(rythme): 20 invitations par jour bloquantes et jauge des pages LinkedIn`

### Task 6 : « Tester la session » compté et surveillé

**Files:**
- Modify: `diagnostic_cookie.py` (le chargement du fil ~l.108-120 ; lecture du `config_dir` de la personne déjà transmis ou à transmettre par l'appelant dans `ui/page_recherche.py` `_tester_session`)
- Test: `tests/test_diagnostic_session.py`

**Interfaces:**
- Consumes : `DailyLimitsTracker.increment_pages`, `nature_page`.
- Produces : le diagnostic compte 1 page dans le fichier de limites de la personne et classe une page d'alerte comme « session interrompue » (même rendu que l'expiration). Il n'est pas soumis aux séances ni au plafond de pages (c'est le seul moyen de vérifier sa session).

- [ ] **Step 1 : test rouge** `test_tester_la_session_compte_une_page` (fichier de limites dans `tmp_path`, Playwright simulé).
- [ ] **Step 2-4 : échec, implémenter, vert.**
- [ ] **Step 5 : commit** — `feat(rythme): « Tester la session » compte sa page`

### Task 7 : vérification des acceptations par listes — **avec Thomas, en réel**

Cette tâche ne démarre que lorsque Thomas est présent : elle charge de vraies pages LinkedIn de son compte, en lecture seule.

**Files:**
- Modify: `scraper_v2.py` (`verifier_acceptations_async`), `ui/page_messages.py` si le texte d'explication cite « 30 profils »
- Test: `tests/test_verification_acceptations.py` (fixtures HTML enregistrées pendant la sonde, anonymisées : noms remplacés)

**Interfaces:**
- Produces : `verifier_acceptations_async` lit, via `_naviguer`, la liste des invitations envoyées (`https://www.linkedin.com/mynetwork/invitation-manager/sent/`) et la liste des relations triée par ajout récent (`https://www.linkedin.com/mynetwork/invite-connect/connections/`), au plus 3 pages en tout. Une personne en attente présente dans les relations → acceptée (et vérifiée) ; présente dans les envoyées → vérifiée, en attente ; absente des deux → vérifiée, non acceptée (statut inchangé, journal). `verifiees` et `errors` gardent leur contrat de la 1.9.0. Repli si une liste est illisible : méthode actuelle (profil par profil) plafonnée à `MAX_VERIFICATIONS_PAR_PASSAGE`.

- [ ] **Step 1 : sonde en réel** (script jetable hors dépôt, Chrome visible, `_naviguer`) : enregistrer le HTML des deux listes, noter les sélecteurs. **S'arrêter et rapporter** si l'une des listes ne montre pas les adresses de profil. Dans la même sonde, sur une page de résultats de recherche, noter si chaque carte porte un bouton « Se connecter » utilisable sans ouvrir le profil (spec § 3, « pas de page inutile ») ; si oui, le rapporter pour une tâche suivante, sans l'implémenter ici.
- [ ] **Step 2 : tests rouges** sur les fixtures enregistrées.
- [ ] **Step 3 : implémenter.** - [ ] **Step 4 : vert.**
- [ ] **Step 5 : essai réel avec Thomas** : une vérification, comparer au contenu des deux listes à l'écran.
- [ ] **Step 6 : commit** — `feat(acceptations): vérifier en lisant les listes, pas profil par profil`

### Task 8 : nouveautés

**Files:**
- Modify: `NOUVEAUTES.md` (section `## 1.9.0` existante : ajouter)

- [ ] **Step 1 : ajouter** à la section 1.9.0, pour les utilisateurs :
  - **Un rythme plus humain.** We.Reach charge au plus 60 pages LinkedIn par jour, par séances courtes avec une pause de 20 minutes entre deux séances, et 20 invitations par jour au plus.
  - **Arrêt immédiat si LinkedIn intervient.** Si LinkedIn affiche une page de vérification, We.Reach s'arrête aussitôt.
- [ ] **Step 2 : `pytest -q` vert.** - [ ] **Step 3 : commit** — `docs(nouveautés): rythme humain`
