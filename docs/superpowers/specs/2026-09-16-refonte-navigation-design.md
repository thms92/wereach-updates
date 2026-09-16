# Refonte de la navigation — spec de conception

**Date :** 2026-09-16
**Statut :** en attente de relecture
**Décisions validées par :** Thomas, le 2026-09-16

---

## 1. Le problème

L'application définit **neuf pages**. Le menu latéral n'en expose que **cinq**. Quatre pages fonctionnelles — `🔗 Scraping URLs`, `📋 Templates`, `⚙️ Configuration` et, jusqu'à aujourd'hui, `🎯 Chasse` — sont inatteignables depuis l'interface.

La cause est identifiée : le commit `c6035c0`, intitulé *« refac(nav): match Claude Design »*, a réduit la liste du menu pour la faire correspondre à une maquette. Les blocs de code des pages retirées sont restés en place, mais plus aucun chemin n'y mène. Personne ne s'en est aperçu pendant deux mois, parce qu'aucun test ne vérifie qu'une page définie est atteignable.

Deux défauts s'y ajoutent :

- **`🎯 Chasse` fait double emploi avec `🔍 Recherche › Candidats`.** Mêmes champs (mots-clés, entreprises, secteurs, Île-de-France, invitation, note), même appel `run_scraper`, mais sans les écoles ni les cabinets concurrents. C'est un sous-ensemble strict.
- **`📋 Templates` ne mène nulle part.** Son bouton « 🚀 Utiliser ce template » n'exécute aucune action : il affiche le message « Allez dans la page Recherche pour lancer le scraping ». Un template qu'on ne peut pas appliquer.

## 2. Objectif

Une interface où **toute page définie est atteignable**, **aucune fonctionnalité n'est dupliquée**, et où le menu reste court. Le travail consiste majoritairement à déplacer et supprimer des blocs existants, non à réécrire des fonctionnalités.

## 3. Décisions

| Question | Décision | Motif |
|---|---|---|
| Page `🎯 Chasse` | **Supprimée** | Sous-ensemble strict de `Recherche › Candidats` |
| Fonctionnalité Templates | **Supprimée**, code compris | Jugée non nécessaire |
| Page `🔗 Scraping URLs` | **Devient un onglet** de `Recherche` | Même tâche : constituer une liste de profils à traiter |
| Page `⚙️ Configuration` | **Devient un volet** de la barre latérale | Réglages rarement touchés, regroupés avec cookie et proxy |
| Cookie `li_at` et proxy | **Restent dans la barre latérale** | Le cookie expire souvent ; il doit rester accessible de partout |
| Page `📜 Logs` | **Reste une entrée du menu** | L'échec de chargement est l'incident le plus fréquent (58 occurrences au journal) ; le diagnostic fait partie de l'usage quotidien |
| Icônes du menu | **Vectorielles, plus d'emoji** | Décidé le 2026-09-16 à la validation de la maquette, après la rédaction initiale de cette spec. `st.radio` ne rendant que du texte, la navigation passe à des boutons portant une icône Material — ce qui ajoute une règle CSS au thème (voir §8) |

## 4. Structure cible

```
📊 Tableau de bord     KPIs · quotas du jour · alertes

🔍 Recherche           ┌ Candidats              écoles · entreprises · secteurs · géo
                       ├ Clients/Entreprises    entreprises · secteurs · géo
                       ├ Par URLs               ← ancienne page « Scraping URLs »
                       └ File d'attente

✉️ Messages            détection des acceptations → envoi des messages

💾 Historique          profils scrapés, filtrables

📜 Logs                journal d'exécution

BARRE LATÉRALE         navigation
                       ▸ 🍪 Cookie li_at
                       ▸ 🌐 Mon proxy
                       ▸ ⚙️ Réglages          écoles · limites · base de données
```

Cinq entrées de menu. Des neuf pages définies aujourd'hui : **cinq restent des pages**, **une devient un onglet** (`Scraping URLs`), **une devient un volet latéral** (`Configuration`), **deux sont supprimées** (`Chasse`, `Templates`). Plus aucune orpheline.

## 5. Changements par fichier

### `app_advanced.py` (1010 lignes aujourd'hui)

| Bloc | Taille | Action |
|---|---|---|
| `elif page == "🎯 Chasse"` | 72 l. | Supprimé |
| `elif page == "📋 Templates"` | 75 l. | Supprimé |
| `elif page == "🔗 Scraping URLs"` | 105 l. | Déplacé en onglet de `Recherche` |
| `elif page == "⚙️ Configuration"` | 56 l. | Déplacé en `st.sidebar.expander` |
| Liste du menu (l. 110-113) | — | Réduite à cinq entrées |
| Import `SECTEURS` / `parse_entreprises` | — | Conservés (utilisés par `Recherche`) |

Bilan : **−147 lignes supprimées**, **161 lignes déplacées**.

### `database.py`

Suppression de `sauvegarder_template()`, `get_templates()` et de l'instruction `CREATE TABLE IF NOT EXISTS templates`. La table déjà créée chez les utilisateurs existants n'est pas détruite : elle cesse simplement d'être lue et écrite. Aucune migration destructive.

### `tests/`

Nouveau fichier `tests/test_navigation.py`. Voir section 6.

## 6. Le test qui ferme la brèche

Le défaut à l'origine de cette refonte est resté invisible deux mois faute de vérification. Le correctif durable est un test qui compare les deux sources de vérité :

- l'ensemble des pages **définies** — les littéraux des `if/elif page == "…"` ;
- l'ensemble des pages **listées** au menu — les options du `st.sidebar.radio`.

Le test échoue si les deux ensembles diffèrent, dans un sens comme dans l'autre : une page définie hors menu (le bug d'aujourd'hui) comme une entrée de menu sans page (un écran blanc).

L'analyse se fait sur l'arbre syntaxique du module via `ast`, sans exécuter Streamlit — le test reste rapide et sans effet de bord.

En complément, un second test à écrire — il n'en existe aucun aujourd'hui — utilisera `streamlit.testing.v1.AppTest` pour charger chaque page du menu et échouer sur toute exception. Ce harnais a été employé manuellement pendant la session du 2026-09-16 et fonctionne sur cette application ; il reste à le figer en test.

## 7. Point laissé ouvert — à trancher avant l'implémentation

Absorber `Scraping URLs` fait passer le bloc `Recherche` de **297 à ~400 lignes**, dans un fichier qui en compte déjà 1010. C'est le bloc le plus lourd de l'application, et il continue de grossir à chaque fonctionnalité.

L'extraction de chaque page dans un module dédié (`pages/recherche.py`, `pages/messages.py`, …) rendrait l'ensemble plus lisible et plus sûr à modifier. **Ce n'est pas inclus dans cette spec** : c'est un refactoring distinct, à décider séparément pour ne pas mêler déplacement de code et restructuration dans un même lot.

## 8. Hors périmètre

- Toute modification visuelle : palette, typographie, composants. `wefiit_theme.py` n'est touché **qu'à un seul endroit** — une règle CSS pour l'état actif du menu, conséquence directe de la décision sur les icônes (§3). Aucun token n'est modifié.
- Les filtres de recherche (écoles, entreprises, secteurs) livrés plus tôt ce jour. Ils vivent dans `construire_url_recherche` et ne sont pas touchés — y compris lors de la suppression de `Chasse`.
- Les fonctionnalités évoquées et non retenues pour l'instant : filtre par degré de relation, `pastCompany`, sélecteur géographique.

## 9. Risques

**Perte d'un parcours utilisé.** La suppression de `Chasse` retire un formulaire que Thomas utilise peut-être par habitude. Atténuation : `Recherche › Candidats` propose strictement tout ce que `Chasse` proposait, plus les écoles et les cabinets concurrents.

**Régression silencieuse au déplacement.** Les blocs déplacés dépendent de `st.session_state` (cookie, chemins utilisateur, scraper). Atténuation : `AppTest` charge chaque page après déplacement et échoue sur toute exception.

**Clés de widgets en conflit.** Passer `Scraping URLs` en onglet place ses widgets dans le même script que ceux de `Recherche`. Les clés existantes (`inviter_urls`, `btn_url_scraping`) sont déjà distinctes ; à revérifier à l'implémentation.

## 10. Suite

1. Relecture de cette spec par Thomas
2. Maquette interactive en artifact, itérée ensemble
3. Plan d'implémentation (`superpowers:writing-plans`), puis code en TDD
