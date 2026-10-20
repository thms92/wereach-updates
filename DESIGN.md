# Design — We.Reach

> Direction posée le 2026-10-18 (refonte de nuit, demande de Thomas :
> « un visuel bien moderne et dynamique », identité WEFIIT conservée).
> Mode : **Operate**. Les contrôles restent les contrôles Streamlit
> standard ; le monde visuel n'apporte que la typo, la palette, la densité
> et un geste signature.

## Idée

**Les invitations du jour.** Les 20 invitations quotidiennes conseillées
sont la ressource rare de l'outil (limite non bloquante). Elles sont dessinées comme une jauge de 20 crans
(`jauge_budget()`), présente en permanence dans la barre latérale et dans
chaque bloc « Invitations » où une action en consomme. Ailleurs, une puce
dit la même chose en mots : « N restantes sur 20 » (`texte_budget()`).
Une seule formulation partout : on compte ce qui reste, jamais ce qui est
utilisé. C'est le geste signature :
on le reconnaît partout, et il porte une information réelle.

## Coque

- **Barre latérale marine** (#172982 → teinte plus profonde #101D5E en
  bas, aplat, pas de dégradé décoratif sur le contenu). Texte blanc,
  item actif en pilule blanche translucide, wordmark en blanc + orange.
  La jauge du budget vit sous le menu.
- **Fond de travail** #F6F7FB (neutre légèrement froid), surfaces
  blanches. Une seule élévation par élément (ombre douce OU bordure).
- **En-tête de page** (`entete_page()`) : titre h1, une phrase de
  contexte, et à droite 1 à 3 puces d'état (session, quota, file).

## Palette (tokens `--wf-*`)

| Rôle | Valeur |
|---|---|
| Accent / marine | #172982 (hover #1F2F8F, profond #101D5E) |
| Accent vif (données, focus) | #3D5AFE |
| Orange (wordmark, budget consommé, mise en avant ponctuelle) | #F98F03 ; texte orange sur clair : #B45F00 |
| Succès / attention / danger | #15803D / #B45309 / #B91C1C (texte), teintes claires en fond |
| Texte / atténué | #14181C / #5B6472 (≥ 4.5:1 sur #F6F7FB et #F5F6F7) |

Graphiques : `PALETTE_GRAPHIQUES` (marine d'abord).

## Typographie

Inter seule. h1 1.75rem/800, h2 1.25rem/700, h3 1.05rem/700, corps
0.95rem, libellés 0.8rem/600. Chiffres tabulaires
(`font-variant-numeric: tabular-nums`) dans les métriques et tableaux.
Tracking ≥ -0.03em.

## Mouvement (« dynamique », mais au service de l'état)

- Entrée du contenu de page : fondu + montée de 8px, 220 ms, ease-out
  exponentiel, décalage 40 ms entre les cartes de métriques (une fois par
  rendu, pas de chorégraphie longue).
- Survol des cartes et boutons : élévation de 2px + ombre, 150 ms.
- Jauge du budget : remplissage animé des crans à l'affichage.
- Point « en direct » pulsé pour la session active et une tâche en cours.
- `prefers-reduced-motion: reduce` : aucune translation ni pulsation.

## Composants (`ui/composants.py`)

`bandeau_contexte`, `jauge_budget`, `texte_budget`, `carte_action`
(bloc « À faire », variante `vedette` pour les acceptations ; icônes
invitation, relance, message, alerte, ok, accepte, info, recherche, veille,
vide), `entonnoir`, `puce` (états), `point_direct`, `etat_vide` (avec
`etapes=` pour le premier lancement), `pluriel`. HTML statique + classes
`wf-*` définies dans `wefiit_theme.py`. Aucun émoji comme icône : icônes
Material (`:material/…:`) ou aucune.

## Actions irréversibles

Toute action qui part du compte LinkedIn (inviter, envoyer un message)
passe par un récapitulatif « Confirmer et lancer / Annuler »
(`ui/invitations.py::confirmation`), annulé dès qu'un champ change. Une
recherche sans invitation part directement.

## Interdits

Texte en dégradé, bordure gauche colorée > 1px sur cartes et alertes,
eyebrow au-dessus des titres, émojis-icônes, cartes imbriquées, modale
quand l'inline suffit.
