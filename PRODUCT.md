# Product

<!-- impeccable:product-schema 1 -->

> Rédigé le 2026-10-18 sans entretien (Thomas absent, travail de nuit
> autorisé). Les faits marqués *(déduit)* viennent du code et de
> l'historique du projet, pas d'une réponse de Thomas : à confirmer.

## Platform

web

## Users

Une dizaine de consultants et recruteurs de WEFIIT (cabinet de conseil
Product / Data / IA), adresses @wefiit.com. Non techniques. Chacun utilise
We.Reach sur son propre Mac, avec son propre compte LinkedIn, pour :
- trouver des candidats (écoles, entreprises, secteurs) et les inviter ;
- trouver des contacts chez des clients ou prospects ;
- suivre chaque jour une liste d'entreprises cibles (Veille) et y repérer
  les personnes Product / Data / IA, avec leurs coordonnées.

## Product Purpose

Faire gagner du temps de prospection LinkedIn sans mettre en danger le
compte personnel de la personne. Succès : chaque matin, savoir quoi faire
(nouveaux contacts, acceptations à relancer, quota restant) et le faire en
quelques clics.

## Positioning

Un outil interne, local, qui travaille avec le compte LinkedIn de la
personne et respecte un budget quotidien strict (20 invitations par jour,
80 profils par passage) pour éviter toute restriction du compte.

## Operating Context

- Application Streamlit lancée en local (lanceur Mac), mise à jour
  automatique depuis GitHub. Utilisée sur écran d'ordinateur portable ou
  externe, rarement sur mobile *(déduit)*.
- Le parcours : profils trouvés → invités → acceptés → message envoyé.
- Une recherche ouvre une fenêtre Chrome pilotée ; elle peut durer
  plusieurs minutes.
- La session LinkedIn passe par le cookie `li_at`, collé une fois.

## Capabilities and Constraints

- Pages : Tableau de bord, Recherche (Candidats, Clients/Entreprises,
  Profils similaires), Messages, Historique, Journal. La Veille a été
  retirée le 2026-10-20.
- Limites bloquantes : 20 invitations et 60 pages LinkedIn par jour,
  affichées partout ; séances de 25 pages, 20 minutes de pause entre deux
  séances.
- Streamlit 1.58 : pas de composants JS sur mesure ; style par CSS injecté
  (`wefiit_theme.py`) et HTML statique.
- Aucune donnée personnelle réelle dans le dépôt.

## Brand Commitments

- Nom : We.Reach, wordmark avec accents orange (#F98F03) sur « . » et « ea ».
- Couleur de marque WEFIIT : bleu marine #172982. Police Inter.
- Thomas a demandé (2026-10-18) un visuel « bien moderne et dynamique ».
- Langue : français. Vouvoiement *(déduit : majoritaire dans les textes au 2026-10-18,
  16 « vous » contre 9 « tu »)*.

## Evidence on Hand

Aucune capture, aucun témoignage, aucune statistique d'usage à afficher.
Ne jamais inventer de chiffres ou de clients.

## Product Principles

1. Le compte LinkedIn de la personne passe avant tout : le budget du jour
   est visible partout où une action le consomme.
2. Dire quoi faire maintenant plutôt que montrer des graphiques.
3. Parler prospects, invitations et relances, jamais mécanique interne.
4. Chaque attente longue dit ce qui se passe et ce qui viendra après.

## Accessibility & Inclusion

WCAG AA : contraste 4.5:1 pour le texte, focus clavier visible,
`lang="fr"`, mouvement réduit respecté.
