# Profils similaires — spec de conception

**Date :** 2026-10-14
**Statut :** en attente de relecture
**Décisions validées par :** Thomas, le 2026-10-14
**Version visée :** 1.5.0

---

## 1. Le besoin

« Tu as déjà placé quelqu'un de bien et tu veux retrouver le même profil
ailleurs — tu pars d'une réussite passée. »

Aujourd'hui ce parcours n'existe pas. Pour retrouver un profil comparable, il
faut regarder le profil de référence, en déduire soi-même les critères — école,
secteur, intitulé de poste —, puis les ressaisir dans l'onglet Candidats. On
traduit une intuition en filtres, et on perd en route tout ce qui ne se met pas
en filtre.

L'objectif est de partir directement de l'URL du profil réussi.

## 2. Objectif

Un onglet qui, à partir de l'URL d'un profil, produit une liste de profils
voisins, débarrassée de ceux qui ne servent à rien — déjà dans le réseau, déjà
dans la base, non invitables, encore dans l'entreprise de référence — puis la
fait passer dans la chaîne de récupération et d'invitation déjà en service.

## 3. Le mécanisme retenu

LinkedIn entretient lui-même, pour chaque profil, une liste de profils voisins :
le panneau **« Plus de profils pour vous »**. On l'avait cru directement
adressable :

```
https://www.linkedin.com/in/<vanity>/overlay/browsemap-recommendations/
```

> **Constaté à l'essai réel du 2026-10-14/15 :** LinkedIn redirige cette URL
> vers le profil lui-même. L'outil ouvre donc le profil et clique sur
> **« Tout afficher »** de la section ; s'il ne le trouve pas, il se rabat sur
> les ~5 profils de la section latérale, avec un avertissement. Le panneau
> rend au plus **20 profils par référence**, sans pagination : le défilement
> jusqu'à stabilisation n'a rien de plus à charger.

Chaque entrée du panneau porte le **nom**, le **degré de relation** (`1er`, `2e`,
`3e`), l'**intitulé** — cette ligne libre du type « Chief Analyst, Media &
Entertainment, OMDIA » —, un **lien vers le profil**, et un bouton **« Se
connecter »** ou **« Suivre »**.

### Ce que cette liste mesure vraiment

Pas une similarité d'attributs : une **co-consultation**. Les gens qui ont
regardé ce profil ont aussi regardé ceux-là.

C'est une bonne nouvelle pour de la prospection. La liste reflète ce que
d'autres recruteurs mettent dans le même panier — un signal que nous ne saurions
pas reconstruire, puisqu'il repose sur des millions de parcours de navigation
que LinkedIn seul observe.

### Pourquoi pas l'autre voie

L'alternative envisagée était d'extraire davantage du profil de référence —
école, parcours, secteur — pour en faire une recherche LinkedIn classique. Elle a
été écartée pour deux raisons : elle nous obligerait à scraper la section
Formation, de loin la partie la plus fragile du projet, et elle remplacerait un
signal que LinkedIn calcule bien par une approximation que nous calculerions mal.

## 4. Décisions

| Question | Décision | Motif |
|---|---|---|
| Source des profils voisins | Panneau browsemap de LinkedIn | Signal de co-consultation, inaccessible autrement |
| Extraction du profil de référence | **Limitée à l'entreprise actuelle** | Nécessaire au « ailleurs » (§6), et disponible sur la même page |
| Section Formation du profil | Non lue | Partie la plus fragile du scraping ; les filtres couvrent le besoin |
| Intitulé des suggestions | Gardé **brut**, non découpé | Texte écrit à la main, dans tous les formats ; un champ structuré faux est pire qu'un texte exact |
| Récursion (browsemap des trouvés) | **Non** | Multiplie les chargements de pages — le comportement qui fait repérer un compte — et la pertinence s'effondre dès le 2ᵉ niveau |
| Récupération des infos | Chaîne `run_url_scraper` existante | Déjà en service dans l'onglet Par URLs : poste et société lus sur la page de profil, plus fiables que l'intitulé |
| Invitation | Même chaîne, option `inviter` | Aucun code d'invitation nouveau |
| Découverte et action | **Deux étapes séparées** | Voir §5 : un point de relecture avant de dépenser du quota d'invitation |
| Emplacement | 4ᵉ onglet de `🔍 Recherche` | Même tâche que les trois autres : constituer une liste de profils à traiter |

### La conséquence architecturale

Cette fonctionnalité **ne scrape pas et n'invite pas**. Elle produit une liste
d'URLs, et la confie à la chaîne qui scrape et invite déjà. Le code nouveau se
réduit à : ouvrir une page, lire un panneau, filtrer une liste.

## 5. Le parcours

**Étape 1 — Trouver.** Tu colles l'URL d'un profil qui t'a donné satisfaction,
tu règles les filtres optionnels, tu lances. L'outil ouvre le panneau, le
déroule jusqu'en bas, en extrait les entrées, applique les exclusions, et
affiche le tableau de ce qui reste : nom, degré, intitulé, invitable ou non.
Sous le tableau, le compte de ce qui a été écarté et pourquoi.

**Étape 2 — Récupérer et inviter.** Un bouton reprend les URLs retenues et les
passe à la chaîne existante, avec la case « Envoyer des invitations » et le
champ message, comme dans l'onglet Par URLs. Tu obtiens le tableau habituel
— nom, poste, société — exportable en Excel et en CSV.

**Pourquoi deux étapes.** Les invitations sont une ressource rare : fortement
limitées sur un compte gratuit, et irréversibles. Un écran de relecture entre la
découverte et l'envoi te laisse voir ce que la liste a ramené avant que quoi que
ce soit ne parte. Une fonctionnalité exploratoire ne doit pas pouvoir consommer
un quota sans que tu aies regardé.

## 6. Les exclusions

### Toujours appliquées

**Le 1er degré.** Déjà dans ton réseau : rien à y faire. Le degré affiché par
LinkedIn est relatif au porteur du cookie, donc à toi — c'est exactement ce
qu'il faut. C'est aussi, au passage, le filtre par degré de relation qui était
jusqu'ici au backlog comme un chantier à part : il arrive gratuitement avec ce
panneau.

**Les profils déjà en base.** Via `profil_existe()`, sur l'URL normalisée. La
normalisation compte : LinkedIn sert les liens avec des paramètres de suivi
(`?miniProfileUrn=…`), et la même personne apparaîtrait deux fois.

### Au choix

Par défaut, rien n'est écarté d'autre que ce qui est déjà au fichier et le
1er degré (ci-dessus). Décision prise après l'essai réel : tout le reste se
règle à la main.

**Écarter une entreprise.** « Le même profil *ailleurs* » : celui qui travaille
encore dans la boîte où tu as placé ton candidat n'est pas forcément la cible.
Le champ « Entreprise à écarter » arrive **vide** après « Trouver ». L'entreprise
lue sur le profil de départ est seulement **proposée** à côté (« Entreprise du
profil de départ : X » et un bouton « Écarter X » qui remplit le champ), jamais
appliquée d'office. Quand elle n'a pas pu être lue, l'écran le dit et le champ
reste à saisir.

L'exclusion se fait sur l'intitulé, par recherche du nom de l'entreprise —
l'intitulé la mentionne la plupart du temps. Best effort assumé : qui ne met pas
son employeur dans son intitulé passera le filtre. Le tableau de l'étape 2
affichant la société lue sur la page de profil, tu les verras, et tu pourras les
écarter à ce moment-là.

**Ne garder que les invitables** (décoché par défaut). Une entrée qui ne propose que « Suivre » ne
pourra jamais recevoir d'invitation — compte restreint ou page suivie. Les garder
a du sens si tu veux juste constituer un fichier ; les écarter en a si tu veux
inviter.

**Filtrer sur un mot de l'intitulé.** « Product », « Data », « Finance ». Pour
resserrer quand la liste part dans une direction qui ne t'intéresse pas.

## 7. Changements par fichier

### `utils/browsemap.py` — nouveau

Toute la logique sans navigateur, donc testable au test unitaire :

- `normaliser_url(url)` — enlève les paramètres de suivi et le slash final,
  minuscule le vanity name. C'est la clé de comparaison avec la base.
- `vanity_depuis_url(url)` — extrait le vanity name, rend `None` si l'URL n'est
  pas un profil. Sert à valider la saisie et à construire l'URL du panneau.
- `url_panneau(url)` — l'URL de l'overlay à partir de l'URL du profil.
- `filtrer_suggestions(suggestions, deja_en_base, entreprise_reference, invitables_seulement, mot_intitule)` —
  rend `(retenues, ecartees)`, où chaque écartée porte son motif. Les motifs
  sont affichés à l'écran : une liste qui se vide doit dire pourquoi.

### `scraper_v2.py` — une méthode

`recolter_browsemap_async(cookie, url_reference, status_callback)` : ouvre le
profil de référence (l'URL du panneau n'est pas adressable, voir §3), clique sur
« Tout afficher », déroule jusqu'à ce que le nombre d'entrées cesse
d'augmenter, extrait en JavaScript, et lit au passage l'entreprise actuelle du
profil de référence.

Rend `(suggestions, entreprise_reference)`. `entreprise_reference` vaut `None`
si on n'a pas pu la lire — aucune entreprise n'est alors proposée à l'écran ; la saisie
manuelle (§6) reste possible.

Plus une méthode synchrone `recolter_browsemap(...)`, comme les autres, pour
l'appel depuis Streamlit.

### `app_advanced.py` — un onglet

`tab1, tab2, tab3 = st.tabs(...)` ligne 469 devient quatre onglets, avec
`👥 Profils similaires` en dernier. Les clés de widgets sont préfixées `sim_`
pour ne pas heurter celles de l'onglet Par URLs. Le résultat de l'étape 1 vit
dans `st.session_state` — il doit survivre au rerun que provoque l'étape 2.

### `database.py`

Inchangé. `profil_existe()` suffit.

### `tests/test_browsemap.py` — nouveau

Normalisation d'URL, extraction du vanity name, construction de l'URL du
panneau, et chaque exclusion de §6 — y compris les cas qui mordent : URL avec
paramètres de suivi, entreprise de référence inconnue, liste entièrement
écartée, panneau vide.

### `NOUVEAUTES.md` et `VERSION`

Section `## 1.5.0`, écrite pour l'équipe.

## 8. Ce que l'outil doit dire quand ça ne marche pas

Trois échecs distincts, trois messages distincts — le défaut que la 1.4.7 a
corrigé pour la recherche ne doit pas se reproduire ici sous une autre forme.

| Situation | Ce qui s'affiche |
|---|---|
| L'URL n'est pas un profil LinkedIn | Refus immédiat, avant tout chargement |
| Le panneau n'existe pas pour ce profil | « LinkedIn ne propose aucun profil voisin pour celui-ci » — c'est le cas d'un profil peu consulté |
| Le panneau a changé de structure | Avertissement explicite, et le HTML du panneau écrit dans `logs/` — comme le fait déjà `extraire_profils_page` |
| Tout a été écarté par les filtres | Le détail des motifs, pas un tableau vide |

Le troisième est celui qui compte : une extraction qui rend zéro doit crier, pas
rendre discrètement une liste vide qu'on prendrait pour un profil sans voisins.

## 9. Hors périmètre

- La récursion sur les profils trouvés (§4).
- Toute extraction du profil de référence au-delà de son entreprise actuelle.
- Le découpage de l'intitulé en poste et société.
- Les autres pistes du backlog : facette `pastCompany`, sélecteur géographique.
  Le filtre par degré, lui, cesse d'être au backlog : §6 le livre.

## 10. Risques et inconnues

**La taille de la liste est inconnue.** Personne n'a compté jusqu'où le panneau
se déroule. Dix entrées en font un complément de recherche ; cinquante en font
une source de prospection à part entière. Cela ne change pas l'architecture — le
premier essai réel tranchera. Si la liste est longue, c'est le quota
d'invitations qui deviendra la contrainte, pas la récolte.

**Le panneau peut être vide.** Il repose sur les consultations : un profil peu
regardé n'a rien à offrir. Traité en §8.

**La structure de l'overlay peut changer.** Risque inhérent à tout scraping,
moindre ici que pour la section Formation — c'est une page dédiée à une seule
chose — mais réel. Traité en §8.

**L'entreprise de référence n'est pas garantie lisible.** Le panneau est un
overlay : le profil est probablement rendu dessous, mais ce n'est pas vérifié.
Repli prévu en §7.

**Un chargement de page par profil à l'étape 2.** C'est le coût de la chaîne
existante, déjà payé quotidiennement par l'onglet Par URLs. Le risque est connu
et accepté, pas nouveau.

## 11. Suite

1. Relecture de cette spec par Thomas
2. Plan d'implémentation (`superpowers:writing-plans`)
3. Code en TDD, puis revue
