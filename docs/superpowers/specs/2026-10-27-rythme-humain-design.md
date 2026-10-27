# Rythme humain et arrêt sur alerte LinkedIn — conception

Date : 2026-10-27. Demandé par Thomas. Statut : approuvé par Thomas le 2026-10-27 (sans limite d’horaire).

## Intention

Le 2026-10-26, le compte LinkedIn de Léa a reçu la page
`linkedin.com/checkpoint/challenge/…` : « Nous avons remarqué une activité
inhabituelle sur votre compte… votre compte avait accédé à un grand nombre
de données de profil… outil tiers ou extension ». C'est un avertissement,
pas encore une restriction. Un second avertissement mène en général à une
restriction du compte.

LinkedIn est l'outil de travail quotidien des consultants. Perdre un compte
coûte bien plus cher que d'aller moins vite. Thomas demande que l'outil se
comporte **comme une personne** pour ne plus provoquer ce message.

## Ce que dit le code aujourd'hui (constaté le 2026-10-27)

1. **Le compteur de profils ne voit qu'une partie des visites.**
   `DailyLimitsTracker.profiles_scraped` (`utils/human_behavior.py`) ne
   s'incrémente que pour les profils lus dans les résultats de recherche
   (`scraper_v2.py` ~l.1427), et le plafond (`can_scrape`, 80, tiré de
   `MAX_PROFILES_PER_RUN`) n'est vérifié que par `run_scraper_async`.
   Ouvrent des pages LinkedIn sans compter ni vérifier quoi que ce soit :
   - `run_url_scraper_async` : une page de profil par personne invitée depuis
     « Par critères » et « Profils similaires » (`goto` ~l.2121, puis
     `browse_page_naturally`) ;
   - `recolter_browsemap_async` : profil de départ et panneau « profils
     similaires » (~l.1895) ;
   - `verifier_acceptations_async` : jusqu'à 30 profils par clic (~l.945) ;
   - `envoyer_message` / `envoyer_messages_async` : une page par message
     (~l.812), jusqu'à 20 par envoi ;
   - `envoyer_invitation` : une page de profil (~l.606) ;
   - la résolution d'entreprise par navigation (~l.358, 372).
2. **La page d'alerte n'est pas reconnue.** `ResponseMonitor` ne lève
   `challenge_detected` que sur un statut 401/403 dont l'URL contient
   `challenge`/`checkpoint` ; la redirection de Léa est une page normale
   (statut 200). Les boucles ne testent que `login`/`authwall` dans
   `page.url`, et `check_safety` n'est appelé que par la recherche. L'outil
   peut donc continuer à charger des profils pendant une alerte.
3. **Limites actuelles** (`config.py`) : 80 profils par recherche,
   20 invitations par jour **conseillées, non bloquantes** (décision du
   2026-10-20), délais de 4 à 9 s entre profils, 30 vérifications et
   20 messages par clic.
4. Toutes les actions LinkedIn passent par `LinkedInScraperV2Sync`
   (`scraper_v2_sync.py`) sous le verrou `session_linkedin` : c'est le point
   d'entrée unique où contrôler l'autorisation d'agir.

## Buts

1. **Un budget unique de pages LinkedIn par jour et par personne**, qui
   compte **toute** page LinkedIn chargée par l'outil (recherche, profil,
   panneau, vérification, message, invitation, résolution d'entreprise) et
   **bloque** une fois atteint.
2. **Reconnaître une page d'alerte LinkedIn partout et arrêter l'action en
   cours** : fermer Chrome, ne plus charger aucune page. Pas de message ni
   de repos propres à l'outil : la personne voit la page de LinkedIn.
3. **Un rythme de personne** : séances courtes, pauses entre séances,
   irrégularité, pas de page inutile. **Pas de limite d'horaire** (décision
   de Thomas, 2026-10-27).
4. Les limites restent **visibles** : jauge, et raison d'un refus (budget du
   jour, pause).

## Non-buts et anti-buts

**Non-buts**
- Toute **dissimulation de l'automatisation** : fausse empreinte de
  navigateur, masquage de `navigator.webdriver` ou des marqueurs
  d'automatisation, rotation d'adresses IP ou de proxies pour échapper à la
  détection, résolution automatique de captcha ou de vérification
  d'identité. Décision de Claude, expliquée à Thomas le 2026-10-27 : c'est
  contourner un dispositif de sécurité, et c'est ce que LinkedIn sanctionne
  le plus durement. Le mode « camouflage » existant (`SCRAPER_STEALTH`)
  reste désactivé comme aujourd'hui ; on ne l'étend pas.
- Garantir qu'aucun avertissement ne reviendra : impossible, LinkedIn
  interdit l'automatisation. Le but est de réduire fortement le risque.
- Partager les compteurs entre collègues : chaque compte a son propre budget.

**Anti-buts** (échec même si « ça marche »)
- Une page LinkedIn chargée par l'outil **sans être comptée**.
- Continuer à charger des pages **après** une page d'alerte.
- Un refus **muet** de budget ou de pause : l'utilisateur doit
  savoir pourquoi l'outil refuse et quand il pourra agir.
- Bloquer l'outil au-delà de la journée, ou empêcher la personne d'utiliser
  LinkedIn elle-même.

## Décisions de Thomas

- Léa (et chacun) doit pouvoir **continuer à utiliser l'outil** : **pas de
  période de repos**, pas de reprise progressive, pas de blocage au-delà de
  la journée.
- **Pas de message d'alerte, de bandeau ni de bouton « avertissement »**
  dans l'outil : la personne voit déjà la page de LinkedIn (2026-10-27).
- Le but est **uniquement** la robustesse de l'outil et son côté humain, au
  maximum (2026-10-27).

## Le comportement voulu

### 1. Budget de pages par jour *(chiffres : choix de Claude, à régler)*

- Un compteur `pages_linkedin` par personne et par jour, dans le fichier de
  limites existant (`<config_dir>/daily_limits.json`), remis à zéro chaque
  jour (même logique que `DailyLimitsTracker`).
- **Toute** navigation de l'outil vers une page linkedin.com compte 1 :
  chargement de page, page de résultats suivante, ouverture de profil,
  ouverture du panneau « profils similaires ». Le warm-up (fil d'actualité)
  compte aussi. Les requêtes internes que LinkedIn fait lui-même pendant
  qu'une page est ouverte ne comptent pas.
- Plafond normal : **60 pages par jour**. À 100 %, toute nouvelle action
  LinkedIn est **refusée** avant d'ouvrir Chrome ; une action en cours
  s'arrête proprement à la page qui atteint le plafond et garde ce qu'elle a
  déjà fait.
- **Invitations : 20 par jour, bloquant** (retour sur la décision
  « conseillée » du 2026-10-20, demandé par la situation). Une invitation
  compte aussi dans les pages.
- Une **jauge « Pages LinkedIn du jour »** à côté de celle des invitations,
  dans la barre latérale.

### 2. Séances et pauses *(choix de Claude)*

- **Une séance = une action** (une recherche, une vérification, un envoi).
  Au plus **25 pages par séance**.
- **Pause obligatoire entre deux séances : 20 minutes**, avec le temps
  restant affiché (« Prochaine action possible à 14 h 35 »).
- Au plus **4 séances par jour**.
- **Aucune limite d'horaire ni de jour** (décision de Thomas, 2026-10-27).
- **Une seule vérification des acceptations par jour**, au plus
  **10 profils** ; envoi de messages : au plus **10 par séance**.
- Une recherche : au plus **25 profils** (au lieu de 80).

### 3. Rythme dans une séance *(choix de Claude)*

- Délai entre deux pages : tiré au hasard entre **8 et 20 secondes**, avec
  de temps en temps (environ 1 fois sur 6) une pause « lecture » de
  **30 à 90 secondes**.
- Après un chargement, attendre que la page soit affichée avant d'agir, puis
  un court défilement de lecture (le `browse_page_naturally` existant).
- **Pas de page inutile** : ne pas rouvrir un profil déjà ouvert dans la même
  séance ; ne pas ouvrir de profil quand l'information est déjà sur la page
  de résultats. Le constructeur cherche si l'invitation peut partir depuis la
  page de résultats sans ouvrir le profil ; c'est à valider en réel, et
  seulement si cela marche de façon fiable.
- Le warm-up (fil d'actualité) reste au début de chaque séance.

### 4. Reconnaître une alerte, partout

- Après **chaque** navigation, tester l'URL de la page **et** son contenu.
  Est une alerte :
  - une URL contenant `/checkpoint/`, `/challenge/`, `/authwall`,
    `/uas/login` ou `/login` ;
  - une page dont le texte contient « activité inhabituelle », « unusual
    activity », « restreint », « restricted », « vérifions qu'il s'agit bien
    de vous », « let's do a quick security check » (liste à compléter par le
    constructeur depuis les pages LinkedIn connues, en français et anglais) ;
  - un statut HTTP 429 sur une page linkedin.com, ou 3 réponses 999.
- Distinguer **session expirée** (login/authwall simple → message actuel
  « mettez à jour votre session ») et **alerte de sécurité** (tout le reste
  ci-dessus).
- Sur alerte : arrêter immédiatement la boucle, fermer Chrome, ne
  compter comme faites que les actions réellement faites, et terminer
  l'action comme une session interrompue (le libellé d'erreur existant
  suffit ; aucun texte nouveau, aucun état gardé pour les jours suivants).
- Le détecteur est **une seule fonction** appelée par toutes les boucles,
  pas une copie par boucle.

### 5. Ce que voit la personne

- Les jauges « Pages LinkedIn du jour » et « Invitations du jour ».
- Chaque refus dit pourquoi (budget du jour atteint, pause entre séances)
  et quand ce sera possible.
- Le Journal enregistre les refus et les arrêts sur page d'alerte.

## Précisions après relecture (2026-10-27, choix de Claude)

1. **Une tâche en deux temps = une seule séance.** « Par critères »
   (chercher puis inviter), « Profils similaires » (récolter puis inviter)
   et « Messages » (vérifier puis écrire) forment chacun **une** séance. Les
   deux appels partagent le plafond de 25 pages. La séance reste ouverte
   **30 minutes** après son premier appel pour laisser le temps de choisir ;
   la pause de 20 minutes démarre à la fin du dernier appel de la séance (ou
   à l'expiration des 30 minutes). Le suivi vit donc au niveau de la tâche,
   dans l'état persistant de la personne, pas dans un appel.
   **Coût d'une invitation** : l'ouverture du profil compte 1 page ; le clic
   sur « Se connecter » et la fenêtre d'envoi ne sont pas des navigations et
   ne comptent pas.
2. **Vérification des acceptations par listes, pas profil par profil.** Une
   vérification à 10 profils par jour ne suivrait jamais 20 invitations par
   jour. Le constructeur remplace la visite de chaque profil par la lecture de
   **la liste des invitations envoyées** (`/mynetwork/invitation-manager/sent/`)
   et/ou de **la liste des relations triées par ajout récent**
   (`/mynetwork/invite-connect/connections/`) : quelques pages pour tout le
   monde. Une personne passée de « envoyée » à « relation » est acceptée ;
   une personne qui a disparu des deux listes est classée « retirée ou
   refusée » (pas acceptée). À valider **en réel avec Thomas** avant toute
   publication ; si la lecture des listes n'est pas fiable, repli sur la
   méthode actuelle plafonnée à 10 profils par jour. Le critère « 1er degré »
   de la 1.9.0 reste la règle d'acceptation.
3. **Détecteur étroit.** Le contrôle par le **texte** ne s'applique qu'aux
   pages dont l'adresse n'est pas une page de travail normale (`/in/`,
   `/search/`, `/feed/`, `/mynetwork/`, `/company/`, `/school/`) : sur ces
   pages, seuls l'adresse et le statut HTTP comptent. Un faux positif ne
   coûte que l'arrêt de l'action en cours.
4. **« Tester la session »** charge le fil d'actualité : il compte 1 page et
   passe par le même détecteur. Le compteur étant un fichier, le processus
   séparé (`diagnostic_cookie.py`) l'incrémente avec la même classe.

## Ce qui ne doit pas casser

- Les 652 tests actuels, adaptés là où les limites changent.
- Le tableau de bord chiffré et la vérification des acceptations de la
  1.9.0 (branche non publiée) : la 1.9.0 ne doit pas partir sans ce
  chantier, parce que sa vérification ajoute des visites.
- Le tutoriel (si une jauge ou un bandeau change de place).
- Le verrou « une seule session LinkedIn à la fois ».

## Laissé au constructeur

- Où placer le compteur et le détecteur (le wrapper synchrone et
  `HumanBehavior` sont les candidats évidents), la forme de l'état
  persistant, les noms.
- Les textes des refus autres que le message d'alerte, dans le style des
  textes existants (vouvoiement, français courant).
- Tous les chiffres marqués « choix de Claude » sont des constantes de
  `config.py`, faciles à régler.
- La validation en réel (une séance avec Thomas) avant toute publication.
