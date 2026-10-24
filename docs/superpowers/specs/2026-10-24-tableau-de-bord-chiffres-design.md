# Tableau de bord chiffré de We.Reach — conception

Date : 2026-10-24. Demandé par Thomas. Statut : approuvé par Thomas le
2026-10-24, après relecture.

## Intention

Les consultants veulent des **chiffres utiles tirés de l'outil** : combien
ils invitent, combien acceptent, et où (écoles, entreprises, postes). Le
tableau de bord actuel « n'est pas rempli de bonne info » (Thomas) : un
parcours cumulé depuis toujours, une dernière recherche, une répartition
par école repliée.

Le tableau de bord devient donc un **suivi chiffré personnel, purement
consultatif**, que chacun filtre comme il veut.

## Décisions de Thomas

- **Chacun son tableau**, calculé sur sa propre base, sur son Mac. Pas de
  vue d'équipe, rien de partagé.
- **Consultatif seulement** : l'outil montre, il ne recommande rien.
- **Filtres** : période, avec un découpage **semaine par semaine** ; les
  **30 derniers jours** ; une **plage personnalisée** ; plus des filtres par
  école, entreprise et poste.
- **Disposition A** de la maquette : tout sur une page, de haut en bas.
  Filtres, chiffres clés, évolution par semaine, puis les tableaux par
  école, par entreprise et par poste, à la suite.
- **Emplacement : le Tableau de bord lui-même**. Pas de nouvelle entrée de
  menu. Le bloc « Parcours de vos prospects » est remplacé.
- **Acceptations** : le bouton « Vérifier qui a accepté » de la page
  Messages reste tel quel. Pas de vérification automatique.

## Buts, non-buts, anti-buts

**Buts**
- Des chiffres **justes** sur les invitations, les acceptations et les
  messages, pour une période choisie.
- Le détail par école, par entreprise et par poste, filtrable.

**Non-buts**
- Vue d'équipe, comparaison entre collègues.
- Recommandations (« ciblez plutôt telle école »).
- Lecture des réponses aux messages, relances.
- Vérification automatique des acceptations.
- Export Excel des chiffres (non demandé).

**Anti-buts** (ce qui en ferait un échec, même si ça « marche »)
- **Un chiffre faux sans que rien ne le signale.** C'est le risque principal,
  voir les préalables.
- Un pourcentage trompeur calculé sur 1 ou 2 personnes (« 100 % »).
- Casser le tutoriel guidé, ou faire disparaître la seule alerte qui dit
  « des personnes ont accepté, écrivez-leur ».

## Préalables : rendre les données justes

Constaté en lisant le code le 2026-10-24. Les quatre corrections sont à
faire **avant** la page, chacune avec son test. Thomas les a approuvées le
2026-10-24.

1. **Les invitations du chemin actuel ne sont pas enregistrées.** Depuis la
   version 1.8.0, « Par critères » cherche sans inviter, puis invite la
   sélection par `bloc_recuperer_inviter` → `run_url_scraper_async`. Même
   chose pour « Profils similaires ». Ce chemin envoie l'invitation et la
   décompte du budget du jour (`scraper_v2.py`, autour de la ligne 2109),
   mais n'appelle jamais `db.ajouter_invitation`. Seul l'ancien chemin le
   fait (`scraper_v2.py:1370`). Conséquences actuelles : pas de carte
   « invitations en attente », bouton « Vérifier qui a accepté » grisé,
   parcours et taux faux.
   → Enregistrer l'invitation dans ce chemin, comme dans l'autre. Si
   l'extraction du profil a échoué, il faut quand même un profil (au moins
   l'URL et le nom affiché) pour rattacher l'invitation.
2. **Le second passage efface l'école du profil.** Dans
   `run_url_scraper_async`, `ajouter_profil(..., ecole='')` met à jour un
   profil déjà connu, et la requête `UPDATE` de `ajouter_profil` réécrit
   `ecole` (et `localisation`, `nb_connexions`) avec la valeur vide. Un
   profil trouvé par « Par critères » (école renseignée) perd donc son école
   au moment où on l'invite. Le tableau par école serait vide pour tous les
   invités.
   → Ne jamais remplacer une valeur connue par une valeur vide lors d'une
   mise à jour. *(Choix de Claude)* La règle vaut pour **toutes** les
   colonnes réécrites (`nom`, `poste`, `entreprise`, `ecole`,
   `localisation`, `nb_connexions`). Une valeur non vide différente remplace
   l'ancienne, comme aujourd'hui, **sauf l'école** : un profil garde la
   première école qui l'a trouvé, pour que ses invitations ne changent pas
   de ligne dans le tableau par école.

**Limite à accepter** : les invitations envoyées avant la correction ne
seront jamais dans les chiffres. *(Choix de Claude)* La fenêtre « Nouveautés »
de la version qui apporte la page le dit en une phrase.

3. **La vérification ne regarde que les 30 invitations les plus anciennes.**
   `page_messages.py:136` passe `max_check=30`, et la liste est triée de la
   plus ancienne à la plus récente (`database.py:224`). Les personnes qui
   n'acceptent jamais restent en tête : les invitations récentes peuvent
   n'être jamais vérifiées. **Décision de Thomas (2026-10-24) : les deux
   remèdes.**
   - Chaque invitation garde la date de sa dernière vérification (nouvelle
     colonne, migration douce comme `date_message`). La vérification prend
     d'abord les invitations jamais vérifiées, puis celles vérifiées le moins
     récemment. Le plafond de 30 par passage reste. *(Choix de Claude)* Parmi
     les jamais vérifiées, les plus récentes d'abord. Une invitation est
     marquée vérifiée seulement si sa page a été lue, pas en cas d'erreur ou
     de session expirée.
   - Sous les chiffres clés : « N invitations de la période n'ont jamais été
     vérifiées », affiché seulement si N > 0.
   - Le bouton et la page Messages gardent leur forme. Seuls l'ordre et
     l'enregistrement changent.
4. **De fausses acceptations.** La vérification compte comme acceptée toute
   personne dont le profil affiche un bouton « Message »
   (`scraper_v2.py:~920`). Or le code dit lui-même (`scraper_v2.py:51-52`)
   que LinkedIn affiche ce bouton à des 2e et 3e degré au profil ouvert.
   **Décision de Thomas (2026-10-24) : corriger avant la page.** Ne compter
   comme acceptée qu'une **relation de 1er degré** lue sur la page du profil.
   L'outil sait déjà lire un degré « 1er / 2e / 3e » ailleurs
   (`utils/dom_selectors.py`, autour des lignes 440 et 1010, et
   `utils/profile_extractor.py:50`) : partir de là. Si le degré est
   illisible, la personne n'est **pas** comptée comme acceptée (elle reste en
   attente). Le sélecteur sera validé **en réel sur LinkedIn** avant la
   livraison, comme les invitations l'ont été. *(Choix de Claude)* Les
   acceptations déjà enregistrées ne sont pas re-vérifiées.

## Décisions de la relecture (2026-10-24)

- **Compter par date d'envoi** : approuvé par Thomas (« go » sur la
  proposition). Chaque invitation et son acceptation comptent dans la
  semaine où l'invitation est partie. Le graphique par semaine répond au
  « semaine par semaine » ; pas de sélecteur de semaine précise.
- **Branche** : partir de `feature/budget-sans-veille` (1.8.4), approuvé.

## La page, de haut en bas

Maquette validée : version A de
`.superpowers/brainstorm/59935-1792837209/content/mes-chiffres-disposition.html`
(locale, non versionnée). Le contenu ci-dessous fait foi là où il en diffère.

0. **En tête, gardés de l'actuel** *(choix de Claude)* : le bandeau (session
   LinkedIn, budget du jour) et le bloc « À faire », en plus compact. Raison :
   c'est la seule alerte « N personnes ont accepté → Ouvrir Messages » de
   l'outil, et le tutoriel y pointe. Le bloc « Dernière recherche » et la
   « Répartition par école » repliée sont retirés : le second est remplacé
   par le tableau par école, le premier n'apporte pas de chiffre.
1. **Filtres**, sur une ligne :
   - période : « 7 jours », « 30 jours » (par défaut *(choix de Claude)*),
     « Plage personnalisée » (deux dates) ;
   - école, entreprise, poste : listes à choix multiples, vides = tout.
   - Tous les filtres se cumulent et s'appliquent à toute la page (chiffres
     clés, graphique, tableaux).
2. **Chiffres clés** (tuiles) :
   - **Invitations** envoyées sur la période ;
   - **Acceptées** parmi ces invitations ;
   - **Taux d'acceptation**, toujours avec le nombre réel dessous
     (« 61 sur 184 ») ;
   - **Messages envoyés** à ces personnes ;
   - **En attente** : invitées sur la période, pas encore acceptées.
     *(Choix de Claude : remplace le « délai moyen » de la maquette, voir
     plus bas.)*
   - Sous les tuiles, une ligne : « Acceptations vérifiées pour la dernière
     fois le jj/mm à hh:mm, depuis la page Messages. » Ou « jamais
     vérifiées ».
3. **Évolution semaine par semaine** : barres groupées invitations /
   acceptations, une paire par semaine (lundi à dimanche, numérotée « S42 »
   ou datée, au choix du constructeur). Pour une période de 7 jours, une ou
   deux semaines seulement : c'est acceptable.
4. **Trois tableaux**, l'un sous l'autre : **par école**, **par entreprise**,
   **par poste**. Colonnes : invités, acceptés, taux. Triés par nombre
   d'invités décroissant.

## Règles de calcul *(choix de Claude, à vérifier par Thomas)*

- **Une période regroupe les invitations ENVOYÉES dans la période** (date
  d'envoi). Acceptées, messages, en attente et taux portent sur ces mêmes
  invitations, même si l'acceptation est arrivée après la période. Sinon le
  taux peut dépasser 100 % et ne veut plus rien dire. Conséquence connue :
  sur les jours les plus récents, le taux paraît bas parce que les gens
  n'ont pas encore eu le temps de répondre.
- **Une personne compte une fois** : on compte des profils distincts, comme
  `compter_parcours` aujourd'hui (une personne invitée deux fois = 1).
- **Seuil** : sous **5 invitations**, une ligne de tableau ou une tuile
  affiche « trop peu (n) » au lieu d'un pourcentage. Les nombres bruts
  restent affichés.
- **Pas de « délai moyen avant acceptation »** : `date_acceptation` est la
  date du clic sur « Vérifier qui a accepté », pas celle de l'acceptation sur
  LinkedIn. Le chiffre serait faux.
- **Pas de comparaison à la période précédente** (les « +12 % » de la
  maquette) dans cette version : avec 20 invitations par jour au plus, les
  écarts seraient surtout du bruit. À rajouter plus tard si Thomas le
  demande.
- **Fuseau** : SQLite enregistre en UTC (`CURRENT_TIMESTAMP`). Les bornes
  de période et les semaines se calculent en heure locale (même logique que
  `date_locale`).
- **École** : c'est l'école **ciblée par la recherche** qui a trouvé le
  profil, pas forcément celle de la personne. Les libellés composites
  (« Dauphine / ESCP ») comptent pour chaque école, comme `repartir_par_ecole`
  le fait déjà. Un profil sans école (trouvé par « Profils similaires », ou
  ancien) va dans une ligne « Non renseignée ».
- **Entreprise et poste** : la valeur enregistrée sur le profil, nettoyée
  des espaces et regroupée sans tenir compte des majuscules. Vide =
  « Non renseigné(e) ».
- **Poste** : les intitulés LinkedIn sont très variés. On affiche les 15
  postes les plus invités, puis une ligne « Autres ». Pas de regroupement
  intelligent (« PM » = « Product Manager ») dans cette version.

## Date de la dernière vérification

Aujourd'hui, rien ne l'enregistre. *(Choix de Claude)* Le bouton « Vérifier
qui a accepté » écrit l'horodatage de chaque vérification **terminée**
(même sans nouvelle acceptation) dans le dossier de configuration de la
personne (`user_paths.config_dir`), à côté du compteur du budget. Une
vérification refusée parce que la session LinkedIn est occupée n'écrit rien.

## Ce qui ne doit pas casser

- **Tutoriel** (`utils/tutoriel.py`) : l'étape « Votre parcours » cible
  `ol.wf-entonnoir, .wf-vide` sur le tableau de bord. Elle doit viser le
  nouveau bloc (les chiffres clés), avec un texte à jour. L'étape « Ce qui
  vous attend » vise les cartes « À faire », qui restent.
- **Tests existants** du tableau de bord (`tests/test_refonte_tableau_de_bord.py`,
  `tests/test_pages_smoke.py`, `tests/test_phase4_*`) : à adapter là où ils
  vérifient le parcours retiré, pas à supprimer en bloc.
- **État vide** : base sans invitation → un état vide qui dit comment remplir
  la page (lancer une recherche, inviter), pas un mur de zéros.
- **Bases anciennes** sans colonne `date_message` : 0 message, pas d'erreur
  (comme `compter_parcours`).
- Le thème (`wefiit_theme.py`, `PALETTE_GRAPHIQUES`, Inter), le vouvoiement
  et le français courant de `PRODUCT.md`.

## Laissé au constructeur

- Le découpage du code : fonctions de calcul pures et testées sans
  Streamlit (comme `actions_du_jour`), séparées de l'affichage.
- Le composant Streamlit de chaque filtre, la forme exacte des tuiles et du
  graphique (Plotly est déjà utilisé), dans le style existant.
- Le nom du fichier où est stockée la date de vérification.
- L'ordre des commits, la montée de version et la note « Nouveautés »,
  selon les habitudes du dépôt.
- Le travail se fait en TDD, sur une branche dédiée, avec l'accord de Thomas
  avant chaque modification (règle du projet). Point de départ : la branche
  de travail actuelle (`feature/budget-sans-veille`, version 1.8.4), car
  `main` est loin derrière. À confirmer avec Thomas.
