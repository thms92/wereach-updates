# Veille — les contacts des entreprises (livraison 1 bis) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Recentrer la veille sur les contacts des entreprises : retirer l'actualité, réparer l'identification (recherche d'entreprises LinkedIn), et récupérer les coordonnées — générales de l'entreprise depuis son site, et personnelles pour les personnes en relation depuis leur rubrique « Coordonnées » LinkedIn — exportables depuis la fiche.

**Architecture :** On garde l'architecture de la livraison 1 (moteur `veille.py` sans Streamlit, logique pure dans `utils/`, stockage `veille_store.py`, page `ui/page_veille.py`). Deux modules purs nouveaux : `utils/identification.py` (choix d'une entreprise parmi les résultats de recherche) et `utils/coordonnees_site.py` (lecture d'emails et de téléphones dans du HTML). Deux extracteurs JS nouveaux dans `utils/dom_selectors.py` (résultats de recherche d'entreprises ; fenêtre « Coordonnées »), et un troisième pour le degré de relation sur les cartes de résultats de personnes.

**Tech Stack :** Python 3.10+, Playwright, Streamlit 1.58, SQLite, `urllib`, pytest, AppTest, Chromium headless pour les extracteurs (set_content, réseau coupé).

**Spec :** [docs/superpowers/specs/2026-10-15-veille-entreprises-design.md](../specs/2026-10-15-veille-entreprises-design.md) — **Amendement n° 2** fait autorité sur ce plan.

## Global Constraints

- Français partout ; commentaires = pourquoi.
- Version visée : `1.6.0` (la livraison 1 n'a jamais été publiée).
- Aucune dépendance nouvelle ; aucune IA, aucune clé.
- **Aucune liste vide sans explication, aucune donnée plausible mais fausse.** Pas de devinette d'email. Une entreprise n'est identifiée que sur un nom exact.
- **Aucune invitation automatique.**
- Tests : jamais de réseau ni de visite LinkedIn ; Chromium headless autorisé seulement pour exécuter un extracteur sur une fixture **synthétique** via `set_content`, réseau coupé ; jamais d'écriture dans les données réelles ni dans `logs/` du dépôt ; **aucune donnée réelle dans le dépôt** (les captures réelles restent dans le scratchpad).
- `venv/bin/python -m pytest` (pas de `python`).
- Commits en français, terminés par une ligne vide et `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Les fonctions partagées du scraper existant (`_resoudre_company_urn_via_typeahead`, `extraire_profils_page`, `envoyer_invitation`…) ne changent pas de comportement pour leurs autres appelants.

## Ce qu'on sait des vraies pages (captures du 2026-10-15, scratchpad, hors dépôt)

- **Recherche d'entreprises** `https://www.linkedin.com/search/results/companies/?keywords=<nom>` : dans `<main>`, 10 cartes `role="listitem"` (aussi des `<li>`) ; chaque carte contient des liens `a[href*="/company/<slug>/"]` (souvent deux par carte : logo et nom) dont le texte est le nom de l'entreprise (« BNP Paribas », « BNP Paribas Cardif », « Arval BNP Paribas Group »…). Le lien a parfois des paramètres ; l'URL canonique est `https://www.linkedin.com/company/<slug>/`.
- **Coordonnées d'un profil** : `…/in/<vanity>/overlay/contact-info/` en accès direct est **redirigé** vers le profil. Sur le profil, un lien `a[href*="overlay/contact-info"]` (« Coordonnées ») ; un clic ouvre un `<dialog open>` dont le texte contient des rubriques (« Votre profil », « E-mail », parfois « Téléphone », « Site web »…), l'email étant un lien `a[href^="mailto:"]`, le téléphone éventuellement `a[href^="tel:"]` ou du texte.
- **Résultats de recherche de personnes** : l'extracteur existant renvoie `connexions: ''` (le degré n'est jamais lu). Les cartes sont des `div[role="listitem"]` contenant un lien `/in/<vanity>/` ; le degré y apparaît sous la forme « · 1er », « · 2e », « · 3e » (forme constatée sur d'autres listes LinkedIn ; **à vérifier à l'essai**).
- **Invitations acceptées** : table `invitations` (statut `'acceptee'`, mis par `DatabaseManager.marquer_acceptee` depuis la page Messages), jointe à `profiles` par `profile_id`.

## Review Focus

1. **Homonymes à la recherche d'entreprises** : un seul nom exact → retenu ; filiales au nom plus long écartées ; deux noms exacts ou aucun → « non identifiée » avec les noms proposés. → Task 2.
2. **Email d'un autre domaine sur le site** (agence web, hébergeur, `exemple@gmail.com`, `image@2x.png`) : écarté ; seuls les emails du domaine de l'entreprise (ou d'un sous-domaine) sont gardés. → Task 3.
3. **Site injoignable, lent, énorme ou redirigé ailleurs** : délai court, taille plafonnée, pas d'arrêt de la veille, message unique. → Task 3/4.
4. **Fenêtre « Coordonnées » sans email** (la personne ne partage rien) : enregistré comme « rien de partagé », daté, pas relu avant 90 jours, pas d'erreur. → Task 4/5.
5. **Personne hors relation** : jamais de lecture de ses coordonnées (la page ne les montrerait pas, et chaque tentative coûte une page). → Task 5.

---

## Task 1 : Retirer l'actualité

**Files:** delete `utils/actualite.py`, `tests/test_actualite.py` ; modify `veille.py`, `veille_store.py`, `utils/veille_regles.py` (`resume_fiche`), `ui/page_veille.py`, and the tests touching news (`tests/test_moteur_veille.py`, `tests/test_veille_store.py`, `tests/test_veille_regles.py`, `tests/test_page_veille.py`).

**Interfaces :**
- `resume_fiche(fiche, contacts, depuis) -> str` (le paramètre `actualites` disparaît ; plus de « 📰 … » ni « aucune actualité »).
- `VeilleStore.nouveautes_depuis(quand) -> {"contacts", "changements"}` ; `enregistrer_actualites`/`actualites` supprimées ; la table `actualites` **n'est plus créée** par le schéma mais n'est **pas supprimée** des bases existantes ; `retirer_entreprise` ne la touche plus si elle n'existe pas (garder un `DELETE` protégé par une vérification d'existence, ou rien : choisir et expliquer).
- `passage_async(...)` perd le paramètre `actualite` et la phase 0 ; `RapportPassage.nouvelles_actualites` supprimé.
- Page : plus de section actualité (récap, fiche), plus de mention dans le résumé du passage.

- [ ] Step 1 : adapter les tests existants (retirer ceux de l'actualité, mettre à jour les attentes de `resume_fiche` : `resume_fiche({}, [], None) == "Fiche pas encore remplie · aucun contact ciblé"`) ; vérifier qu'ils échouent.
- [ ] Step 2 : supprimer le code ; `grep -rn "actualit" --include="*.py" .` (hors venv) ne doit plus rien renvoyer d'autre que des commentaires historiques justifiés.
- [ ] Step 3 : suite complète verte. Commit `refactor(veille): retirer l'actualite`.

---

## Task 2 : Identifier une entreprise par la recherche d'entreprises

**Files:** Create `utils/identification.py`, `tests/test_identification.py` ; Modify `utils/dom_selectors.py` (+ `extract_recherche_entreprises_js`), `tests/test_extracteur_recherche_entreprises.py` (créer), `veille.py`.

**Interfaces :**
- `DOMSelectors.extract_recherche_entreprises_js() -> str` : JS `() => ({resultats: [{nom, url}], html})` — résultats dédoublonnés par slug, dans l'ordre de la page, `url` canonique `https://www.linkedin.com/company/<slug>/`, `nom` = texte non vide le plus long des liens de la carte vers ce slug ; `html` = HTML de `main` si aucun résultat.
- `choisir_entreprise(resultats: list[dict], nom_suivi: str) -> tuple[str | None, str]` : URL retenue et `""`, ou `None` et un motif. Retenu ssi **exactement un** résultat a `normaliser_nom(r["nom"]) == normaliser_nom(nom_suivi)` (fonction de `utils.annuaire`). Motifs : `"aucune entreprise « X » sur LinkedIn (proposées : A, B, C)"` (3 noms au plus) ; `"plusieurs entreprises « X » sur LinkedIn : collez le lien de la bonne"`.
- `url_recherche_entreprises(nom) -> str`.

```python
# utils/identification.py
# -*- coding: utf-8 -*-
"""Identifier une entreprise suivie par la recherche d'entreprises de LinkedIn.

Le service interne qui le faisait (« typeahead ») répond 404 depuis le
2026-10-15. La page de recherche, elle, liste dix cartes : « BNP Paribas »
y côtoie Cardif, Arval, Personal Finance… On ne retient qu'un nom
**exactement** identique — sinon on demande le lien plutôt que de deviner.
"""

import urllib.parse

from utils.annuaire import normaliser_nom


def url_recherche_entreprises(nom: str) -> str:
    return ("https://www.linkedin.com/search/results/companies/?"
            + urllib.parse.urlencode({"keywords": nom}))


def choisir_entreprise(resultats, nom_suivi: str):
    cible = normaliser_nom(nom_suivi)
    exacts = [r for r in resultats or [] if cible and normaliser_nom(r.get("nom", "")) == cible]
    urls = list(dict.fromkeys(r["url"] for r in exacts))
    if len(urls) == 1:
        return urls[0], ""
    if len(urls) > 1:
        return None, f"plusieurs entreprises « {nom_suivi} » sur LinkedIn : collez le lien de la bonne"
    proposees = ", ".join(dict.fromkeys(r.get("nom", "") for r in resultats or [] if r.get("nom")))
    proposees = ", ".join(proposees.split(", ")[:3]) if proposees else "aucune"
    return None, f"aucune entreprise « {nom_suivi} » sur LinkedIn (proposées : {proposees})"
```

Tests `tests/test_identification.py` (inventés) : nom exact unique parmi des filiales → URL ; casse/accents/forme juridique (« Orbique SAS » vs « ORBIQUE ») → retenu ; deux cartes au même slug (logo + nom) → un seul ; deux slugs au même nom exact → None + « plusieurs » ; aucun exact → None + « proposées : … » avec 3 noms au plus ; liste vide → « proposées : aucune » ; nom suivi vide → None.

Tests `tests/test_extracteur_recherche_entreprises.py` : fixture synthétique fidèle (main, 4 cartes `div[role=listitem]` dans des `li`, deux liens par carte dont un logo sans texte, un lien avec `?trk=`, un lien `/company/` hors `main` à ignorer) → résultats exacts dans l'ordre ; page sans carte → `resultats == []` et `html` non vide. Même harnais Chromium que `tests/test_extracteur_apropos.py`.

Moteur (`veille.py`) : remplacer l'appel au typeahead par : `charger(page, url_recherche_entreprises(nom))` (1 page du budget) → `page.evaluate(extract_recherche_entreprises_js())` → `choisir_entreprise` → si URL : `store.attacher_lien` n'est **pas** appelé (le nom choisi par la personne reste) ; on enregistre `url_linkedin` via `maj_identification(eid, "a_identifier", url_linkedin=url)` puis la suite (page « À propos ») utilise ce lien ; sinon `maj_identification(eid, "non_identifiee")` + motif dans le rapport ; aucun résultat **et** `html` non vide → dump `recherche_entreprises_dump.html` + message honnête. Le contrôle de nom après « À propos » (`_meme_entreprise`) reste. Le paramètre `echecs` et la logique d'échec technique du typeahead disparaissent du moteur (la méthode partagée reste intacte pour l'onglet Candidats). Tests moteur : nom exact → lien enregistré, « À propos » lu ; plusieurs/aucun → non identifiée + motif ; budget compté (1 page pour la recherche).

- [ ] TDD : tests → RED → code → GREEN → suite → commit `feat(veille): identifier les entreprises par la recherche LinkedIn`.

---

## Task 3 : Coordonnées générales depuis le site de l'entreprise (module pur + lecture HTTP)

**Files:** Create `utils/coordonnees_site.py`, `tests/test_coordonnees_site.py`.

**Interfaces :**
- `domaine_de(site: str) -> str | None` — `"https://www.exemple.fr/fr"` → `"exemple.fr"` (retire `www.`) ; None si pas http(s).
- `pages_a_lire(site: str) -> list[str]` — accueil, puis `contact`, `nous-contacter`, `contactez-nous`, `contact-us`, `mentions-legales`, `legal`, `mentions-legales.html` sur la même origine ; **au plus 4 pages effectivement lues** (le moteur s'arrête dès qu'il a un email et un téléphone).
- `extraire_coordonnees(html: str, domaine: str) -> {"emails": list[str], "telephones": list[str]}` — emails depuis `mailto:` et depuis le texte (motif standard), en minuscules, **gardés seulement si le domaine de l'email est `domaine` ou un sous-domaine** ; exclusion des faux positifs (`…@2x.png`, `.jpg`, `.svg`, `.webp`, `example.com`, `sentry`, `wixpress`) ; téléphones depuis `tel:` et motifs français (`+33 1 23 45 67 89`, `01 23 45 67 89`, `01.23.45.67.89`, `0123456789`), normalisés `+33 1 23 45 67 89` ; dédoublonnés, ordre d'apparition, 3 au plus chacun.
- `class SiteInjoignable(Exception)`
- `lire_site(site, transport=None, delai=6.0, taille_max=1_500_000) -> {"emails", "telephones", "pages_lues": list[str]}` — `transport(url, delai) -> (url_finale, bytes)` injectable ; défaut `urllib.request` avec User-Agent « We.Reach », lecture plafonnée à `taille_max` octets ; une page en erreur est sautée ; si l'accueil redirige vers un **autre domaine**, ce domaine n'est pas adopté (on garde celui de LinkedIn) ; si aucune page n'a pu être lue → `SiteInjoignable`.

Tests (sans réseau, transport simulé) : mailto + texte ; email d'un autre domaine (agence, gmail) écarté ; sous-domaine accepté ; `logo@2x.png` écarté ; téléphones dans les 4 formats → même forme normalisée ; doublons ; arrêt dès email+téléphone trouvés (la 3e page n'est pas demandée) ; page en erreur sautée ; tout en erreur → `SiteInjoignable` ; taille plafonnée (le transport par défaut est testé à part avec un faux `urlopen` monkeypatché — jamais de vrai réseau) ; redirection vers un autre domaine → emails de ce domaine écartés ; site `None`/`ftp://` → `SiteInjoignable`.

Le code complet est à écrire par l'implémenteur à partir de ces contrats et de ces tests (module pur d'une centaine de lignes ; regex et normalisation à documenter).

- [ ] TDD → commit `feat(veille): coordonnees generales lues sur le site de l'entreprise`.

---

## Task 4 : Stockage et moteur — coordonnées de l'entreprise et des personnes

**Files:** Modify `veille_store.py`, `veille.py`, `utils/dom_selectors.py` (+ `extract_coordonnees_js`, + `extract_degres_js`) ; Tests `tests/test_veille_store.py`, `tests/test_moteur_veille.py`, `tests/test_extracteur_coordonnees.py` (créer).

**Stockage (non destructif) :**
- table `coordonnees_contacts (url TEXT PRIMARY KEY, email TEXT, telephone TEXT, partage TEXT NOT NULL, releve_le TEXT NOT NULL)` — `partage` ∈ `"oui"`, `"rien"` (fenêtre lue, rien de partagé) ; `url` canonique.
- `enregistrer_coordonnees(url, email, telephone, quand)`, `coordonnees(url) -> dict | None`, `contacts_en_relation(entreprise_id, aujourd_hui, max_age_jours=90) -> list[dict]` = contacts de l'entreprise dont (a) `degre` normalisé est `1er`, **ou** (b) l'URL canonique a une invitation au statut `acceptee` dans `invitations`⋈`profiles` (comparaison canonique), **et** sans coordonnées relevées depuis moins de 90 jours.
- `maj_degre(entreprise_id, url, degre)` (le degré lu sur la carte).
- Les coordonnées générales de l'entreprise vont dans la fiche existante, source `"site"`, champs `email`, `telephone`, plus `site_lu_le` via `marquer_lecture(eid, "site", quand)`.

**Extracteurs JS** (tests Chromium sur fixtures synthétiques) :
- `extract_degres_js()` : sur une page de résultats de personnes, `{vanity: "1er"|"2e"|"3e"}` à partir du texte de chaque carte (`div[role=listitem]` contenant un lien `/in/<vanity>/`), motif `[·•]\s*(1er|2e|3e)`.
- `extract_coordonnees_js()` : dans le `dialog[open]` (ou `[role=dialog]`/`[aria-modal=true]` visible) contenant « Coordonnées » : `{email, telephone, html}` — email depuis `a[href^="mailto:"]`, téléphone depuis `a[href^="tel:"]` sinon le texte sous la rubrique « Téléphone » ; `html` du dialogue si aucune rubrique reconnue (dump).

**Moteur :**
1. Après la recherche de personnes de chaque page : `degres = page.evaluate(extract_degres_js())` puis `store.maj_degre(...)` pour les contacts de la page.
2. Coordonnées générales : si la fiche a un `linkedin.site` et que `site` n'a pas été lu depuis 30 jours → `lire_site(site)` (pas de coût LinkedIn) → `enregistrer_fiche(eid, {"email": ", ".join(emails), "telephone": …}, "site", maintenant)` ; `SiteInjoignable` → une ligne dans le rapport, pas d'arrêt ; rien trouvé → fiche `{"email": "non publié"}` datée (pas de liste vide muette).
3. Coordonnées des personnes en relation : après la recherche de l'entreprise, pour `store.contacts_en_relation(eid, maintenant)` (au plus `COORDONNEES_PAR_ENTREPRISE = 3` par passage), tant que le budget le permet : `charger(page, url_du_profil)` (1 page) → cliquer `a[href*="overlay/contact-info"]` (helper humain existant) → attendre le dialogue (≤ 8 s) → `extract_coordonnees_js()` → `enregistrer_coordonnees` (`partage="rien"` si ni email ni téléphone) ; lien « Coordonnées » absent ou dialogue jamais ouvert → ligne dans le rapport, `partage` non enregistré (nouvel essai plus tard) ; dump si dialogue illisible.
4. Le contrôle de sécurité, les délais humains et le verrou existants s'appliquent.

Tests : store (degré, relation par degré **et** par invitation acceptée avec URL écrite autrement, 90 jours, `partage="rien"`) ; moteur (site lu et enregistré ; site injoignable → message ; aucune personne hors relation n'est visitée ; budget épuisé avant les coordonnées → arrêt propre ; dialogue sans email → `rien`) ; extracteurs.

- [ ] TDD → commits `feat(veille): degre de relation et coordonnees des contacts` (+ éventuellement un commit séparé pour les extracteurs).

---

## Task 5 : Page — les contacts et leurs coordonnées, exportables

**Files:** Modify `ui/page_veille.py` ; Tests `tests/test_page_veille.py`.

- Fiche : rubrique **Coordonnées de l'entreprise** (téléphone LinkedIn, email(s) et téléphone du site, avec source et date ; « non publié » s'il y a lieu).
- Tableau des contacts : colonnes **Degré**, **Email**, **Téléphone** ; pour un contact hors relation : « en relation après acceptation » plutôt qu'une case vide.
- **Exporter** : bouton de téléchargement Excel et CSV des contacts de l'entreprise avec leurs coordonnées (via `st.session_state.export_manager.export_to_excel` comme ailleurs), clés `veille_dl_…`.
- Récap : nouvelles coordonnées obtenues depuis la dernière visite (« Jeanne Exemple a partagé son email »).
- Tests AppTest : coordonnées entreprise affichées ; contact en relation avec email affiché ; contact hors relation → mention ; export présent avec les bonnes colonnes.

- [ ] TDD → commit `feat(veille): coordonnees dans la fiche, export des contacts`.

---

## Task 6 : Essai réel, notes de version, publication

Avec Thomas, sur la branche lancée en port 8502, sauvegarde préalable de ses données. Vérifier : identification de BNP Paribas, Kering, Winamax par la recherche d'entreprises ; « À propos » ; annuaire ; recherche de personnes et **degré lu sur les cartes** (sinon : relation seulement par invitation acceptée — à noter) ; site lu (email/téléphone généraux) ; coordonnées d'une personne en relation (choisir une relation connue). Puis `NOUVEAUTES.md` (1.6.0, écrit pour l'équipe, sans l'actualité), `VERSION`, publication **sur accord explicite**.
