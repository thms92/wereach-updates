# Recherche par critères — refonte des onglets Candidats et Clients

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les onglets « Candidats » et « Clients et entreprises » par un seul onglet « Par critères » qui cherche d'abord, laisse choisir les profils trouvés, puis invite les seuls profils choisis — le même parcours que « Profils similaires ».

**Architecture:** La recherche ne lance plus d'invitations : `run_scraper(..., inviter=False)` rend la liste ; elle est gardée en session et affichée par un composant de sélection commun aux deux onglets (extrait du code de « Profils similaires ») ; l'étape d'envoi réutilise `bloc_recuperer_inviter` (invitations via `run_url_scraper`, récapitulatif de confirmation inchangé).

**Tech Stack:** Streamlit 1.58, pytest + AppTest.

**Spec (analyse du 2026-10-21, captures dans le scratchpad `onglets/`) :**
1. **On invite à l'aveugle.** « Rechercher et inviter (jusqu'à 10) » invite les profils au fil de la recherche, sans les voir ni les choisir ; « Profils similaires » laisse désormais choisir. Deux logiques pour le même geste.
2. **Deux onglets pour un seul formulaire.** « Clients et entreprises » est « Candidats » sans écoles, secteurs ni cabinets ; même moteur, mêmes options d'invitation.
3. **Règle obscure.** « Avec les invitations, le nombre de profils devient le nombre d'invitations visées : seuls les profils invités sont gardés » — conséquence du point 1.
4. **Mise en page déséquilibrée** (Candidats) : colonne gauche longue (Qui, Où, Combien), colonne droite courte (écoles, secteurs).
5. **Jargon** dans l'exemple de mots-clés de Clients (`"Head of Data" OR CDO OR "Directeur Data"`), sans aide sur la syntaxe.
6. **Jauge en double** : barre latérale + grande jauge de 20 crans dans le bloc Invitations.

## Global Constraints

- Vouvoiement, pas d'émoji, pas de « scraping », limite d'invitations **conseillée et non bloquante** (`utils/budget.py::message_depassement`).
- Toute invitation passe par le récapitulatif « Confirmer et lancer / Annuler » (`ui/invitations.py::confirmation`).
- Les filtres de recherche restent retenus d'une page à l'autre (motif de réaffectation en tête de `app_advanced.py`).
- Aucune donnée personnelle dans les tests (profils fictifs).

## Review Focus

- Une recherche relancée remplace la liste et décoche tout ce qui ne s'y trouve plus → test Task 1.
- Une recherche qui ne trouve rien n'affiche ni tableau ni étape 3 → test Task 2.
- Changer de page puis revenir garde la liste trouvée et les choix → test Task 2.
- Les profils déjà dans le fichier restent signalés (pas réinvités par défaut) → test Task 2.
- Au-delà de 20 invitations choisies, l'avertissement non bloquant s'affiche → couvert par `bloc_recuperer_inviter` existant ; test Task 2.

---

### Task 1: Composant de sélection commun

**Files:**
- Create: `ui/selection.py`
- Modify: `ui/page_recherche.py` (onglet Profils similaires : remplacer le bloc tableau + tout/rien par l'appel au composant)
- Test: `tests/test_selection.py`

**Interfaces:**
- Produces: `choisir_profils(profils: list[dict], prefixe: str) -> list[dict]` — affiche « Tout sélectionner / Tout désélectionner », le compteur « N profils choisis sur M » et le tableau à cases (colonnes Choisir, Nom, Intitulé, Relation, Invitable, Profil) ; rend les profils cochés. Choix gardés dans `st.session_state[f"{prefixe}_choix"]` (`{url: bool}`), tout coché par défaut ; `reinitialiser_choix(prefixe)` à appeler quand une nouvelle liste arrive.

- [ ] **Step 1:** tests AppTest via `AppTest.from_function` : par défaut tous choisis ; « Tout désélectionner » → `[]` ; une nouvelle liste après `reinitialiser_choix` → tout choisi ; un profil sans `degre`/`intitule` ne fait pas planter.
- [ ] **Step 2:** `venv/bin/python -m pytest -q tests/test_selection.py` → FAIL.
- [ ] **Step 3:** extraire le code de sélection de l'onglet Profils similaires dans `ui/selection.py` ; l'onglet l'appelle (`prefixe="sim"`).
- [ ] **Step 4:** suite complète → PASS (les tests de Profils similaires ne changent pas).
- [ ] **Step 5:** commit `refactor(recherche): composant de sélection des profils commun`.

### Task 2: Onglet « Par critères » en trois temps

**Files:**
- Modify: `ui/page_recherche.py` (supprimer les onglets Candidats et Clients ; `ONGLETS = ["Par critères", "Profils similaires"]`)
- Modify: `utils/tutoriel.py` (étape « Inviter en toute sécurité » : cible et texte), `tests/test_tutoriel.py`
- Test: `tests/test_recherche_criteres.py` ; adapter `tests/test_refonte_recherche.py`, `tests/test_onglet_clients.py`, `tests/test_phase4_actions.py`

**Interfaces:**
- Consumes: `choisir_profils`, `reinitialiser_choix` (Task 1) ; `bloc_recuperer_inviter(urls, "crit", nom_export="recherche")`.

Contenu de l'onglet :
1. **« 1. Critères »** — *Qui* : Mots-clés (placeholder « Ex : Product Manager, Head of Data » ; aide : « Plusieurs intitulés : séparez-les par OR, et mettez une expression entre guillemets. ») ; *Où* : Entreprises, Cabinets concurrents, Île-de-France ; repliable « Filtres avancés : écoles et secteurs » (fermé par défaut, ouvert si une valeur est choisie) ; *Combien* : nombre de profils (1–80). Bouton principal « Rechercher » (jamais d'invitation ici).
2. **« 2. Choisir les profils »** — après la recherche : `choisir_profils(profils, "crit")` ; les profils déjà dans le fichier sont signalés dans la colonne Intitulé ou une colonne « Déjà au fichier » (Oui/Non) et **décochés** par défaut.
3. **« 3. Inviter ou enregistrer »** — `bloc_recuperer_inviter(urls choisies, "crit", ...)`.
Clés conservées pour la persistance : `keyword` (mots-clés), `entreprise_libre`, `concurrents`, `ecoles_pills_candidat`, `secteurs_candidat`, `idf`, `nb_profils` — à harmoniser avec les clés réelles du code des Candidats (garder celles-là).

- [ ] **Step 1:** tests (scraper factice qui rend 3 profils dont 1 déjà au fichier) : la recherche appelle `run_scraper` avec `inviter=False` ; le tableau montre 3 lignes, 2 cochées ; « Inviter 2 profils choisis » puis « Confirmer et lancer » appelle `run_url_scraper` avec les 2 URLs ; recherche vide → ni tableau ni étape 3 ; aller-retour par Historique → liste et choix intacts ; nouvelle recherche → nouvelle liste, tout recoché sauf déjà-au-fichier.
- [ ] **Step 2:** lancer les nouveaux tests → FAIL.
- [ ] **Step 3:** implémenter ; supprimer `_bloc_invitations`, `_recap_recherche`, `libelle_bouton_recherche` s'ils ne servent plus ; adapter le tutoriel (cible `.st-key-bloc_crit_inviter` ou le bloc Invitations de l'onglet).
- [ ] **Step 4:** suite complète → PASS.
- [ ] **Step 5:** commit `feat(recherche): un onglet Par critères qui cherche, fait choisir, puis invite`.

### Task 3: Jauge compacte dans le bloc Invitations

**Files:**
- Modify: `wefiit_theme.py` (`.wf-jauge:not(.wf-jauge--sombre)` dans un bloc : `max-width: 360px`), `tests/test_theme_refonte.py`

- [ ] **Step 1:** test : la règle CSS existe.
- [ ] **Step 2:** FAIL → **Step 3:** ajouter la règle → **Step 4:** PASS + vérification visuelle (port 8502, captures 1440 px).
- [ ] **Step 5:** commit `style(recherche): jauge compacte dans le bloc Invitations`.
