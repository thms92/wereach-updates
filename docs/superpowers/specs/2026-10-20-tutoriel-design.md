# Tutoriel guidé de We.Reach — conception

Date : 2026-10-20. Demandé par Thomas. Statut : à relire par Thomas.

## Intention

Un collègue qui découvre We.Reach, ou qui le retrouve après la refonte
1.6.0, doit comprendre **à quoi sert l'outil** et **comment s'en servir**,
écran par écran, sans lire de documentation. Le but de l'outil, tel qu'il
est présenté :

> We.Reach vous aide à trouver sur LinkedIn les bonnes personnes —
> candidats, contacts chez vos clients, profils Product, Data et IA de vos
> entreprises cibles —, à les inviter sans mettre votre compte en danger
> (20 invitations par jour au plus), puis à savoir qui a accepté pour leur
> écrire.

## Décisions de Thomas

- **Forme : des bulles sur les vrais éléments** (option C des maquettes).
  L'écran est assombri sauf l'élément expliqué ; une bulle à côté explique
  à quoi il sert et comment l'utiliser. Boutons **Précédent**,
  **Suivant**, **Passer le tutoriel**, repère « Étape n sur N ».
- **Quand :** au **premier lancement** d'un nouveau collègue, et **une
  fois** après la **prochaine mise à jour** (la version qui apporte le
  tutoriel) pour les collègues déjà installés. Tutoriel complet dans les
  deux cas ; il peut être passé à tout moment.
- **Pas de tutoriel aux mises à jour suivantes.**

## Choix de Claude (à vérifier par Thomas)

1. La visite **traverse les pages** dans l'ordre du parcours, pas dans
   l'ordre du menu ; « Suivant » ouvre la page de l'étape puis place la
   bulle.
2. Aux mises à jour suivantes, la fenêtre « Nouveautés » existante reste
   telle quelle (interprétation de « pas besoin sur les mises à jour
   d'après »).
3. Pour la version qui apporte le tutoriel, **le tutoriel remplace la
   fenêtre « Nouveautés »** : pas deux choses empilées au même démarrage.
   Sa première bulle dit que l'outil a été mis à jour.
4. Règle de déclenchement unique : le tutoriel démarre **tant que la
   mention « tutoriel vu » n'existe pas** pour la personne. Elle n'existe
   chez personne aujourd'hui : nouveau collègue et collègue mis à jour sont
   donc couverts par la même règle, et les mises à jour suivantes ne la
   suppriment pas.
5. « Passer » et « Terminer » mémorisent que le tutoriel a été vu (par
   personne, comme la version vue aujourd'hui). Il ne se relance plus seul.
6. Un bouton **« Revoir le tutoriel »** dans la barre latérale le relance
   à la demande.
7. Si l'élément d'une étape est introuvable à l'écran (page vide, donnée
   absente, mise en page changée), la bulle s'affiche **au centre** au lieu
   de pointer au mauvais endroit, et la visite continue.
8. Textes en vouvoiement, vocabulaire de l'outil, deux phrases au plus.
9. Bibliothèque : **driver.js** (libre, MIT, sans dépendance), copiée dans
   le projet — pas d'appel réseau à un CDN à chaque lancement.

## Les étapes (texte des bulles)

L'élément visé est indiqué entre crochets ; les repères sont les clés de
widget déjà en place (`st-key-…`), stables et utilisées par les tests.

0. **[centre] Bienvenue sur We.Reach** — « We.Reach vous aide à trouver
   les bonnes personnes sur LinkedIn, à les inviter sans risque pour votre
   compte, et à savoir qui a accepté. Deux minutes pour faire le tour ? »
   *Variante mise à jour :* « We.Reach a été mis à jour : nouvelle
   apparence, nouvelles pages. Deux minutes pour faire le tour ? »
1. **[menu latéral `nav_menu`] Le menu** — « Six pages, dans l'ordre où
   vous vous en servirez : votre journée commence au Tableau de bord. »
2. **[jauge de la barre latérale] Votre budget du jour** — « 20
   invitations par jour, pas plus : c'est ce qui protège votre compte
   LinkedIn. La jauge montre ce qu'il vous reste, partout dans l'outil. »
3. **[Tableau de bord, bloc « À faire »] Ce qui vous attend** — « Chaque
   matin, ouvrez le Tableau de bord : il vous dit qui a accepté, ce qui
   attend une réponse et ce que la veille a trouvé. »
4. **[Tableau de bord, « Parcours de vos prospects »] Votre parcours** —
   « Trouvés, invités, acceptés, contactés : vous voyez où en sont vos
   prospects, et votre taux d'acceptation. »
5. **[Recherche, carte de session ou bloc « Première connexion »] Votre
   session LinkedIn** — « À faire une seule fois : connectez votre session
   LinkedIn ici. Sans elle, aucune recherche ne peut partir. »
6. **[Recherche, onglets] Trois façons de chercher** — « Candidats par
   école, entreprise ou secteur ; contacts chez des clients ; ou profils
   proches d'un profil qui vous a plu. »
7. **[Recherche, bloc « Invitations » de Candidats] Inviter en toute
   sécurité** — « Activez les invitations si vous voulez inviter les
   profils trouvés. Avant tout envoi, un récapitulatif vous demande de
   confirmer. »
8. **[Veille, onglets] La veille de vos entreprises cibles** — « Suivez
   vos entreprises cibles : à chaque passage, We.Reach y repère les
   personnes Product, Data et IA. »
9. **[Veille, « Mes entreprises »] Ajouter une entreprise** — « Ajoutez
   une entreprise depuis votre fichier ou par le lien de sa page LinkedIn.
   Un clic sur une ligne ouvre sa fiche. »
10. **[Veille, bouton « Lancer la veille »] Lancer un passage** — « Lancez
    la veille : une fenêtre Chrome s'ouvre quelques minutes. Les nouveaux
    contacts apparaissent dans Nouveautés. »
11. **[Messages, étape 1 « Vérifier qui a accepté »] Relancer ceux qui ont
    accepté** — « Vérifiez qui a accepté vos invitations, puis écrivez-leur
    en une fois : sélectionnez, rédigez, confirmez. »
12. **[Historique, champ de recherche] Tout retrouver** — « Tous les
    profils trouvés sont ici : cherchez, filtrez par école ou par période,
    exportez en Excel. »
13. **[Journal] Ce que l'outil a fait** — « Le Journal raconte ce que
    We.Reach a fait. En cas de souci, « Signaler un problème » prépare un
    mail avec tout le nécessaire. »
14. **[bouton « Revoir le tutoriel »] C'est parti** — « Vous pouvez revoir
    ce tutoriel à tout moment ici. Bonne prospection ! » (bouton
    « Terminer »)

## Objectifs, non-objectifs, anti-objectifs

- **Objectifs :** compréhension du but et du parcours ; passable à tout
  moment ; ne gêne plus jamais après avoir été vu.
- **Non-objectifs :** aucune action réelle pendant la visite (rien ne
  cherche, n'invite, n'envoie) ; pas de tutoriel aux mises à jour
  suivantes ; pas de tutoriel interactif « faites-le vous-même ».
- **Anti-objectifs (échec même si ça marche) :** une bulle qui pointe le
  mauvais élément ; un tutoriel qui revient à chaque lancement ; un clic
  du tutoriel qui déclenche une recherche, une invitation ou un message ;
  un tutoriel qui bloque l'outil s'il plante (l'outil doit rester
  utilisable).

## Contraintes

- Streamlit 1.58. Le JavaScript passe par `st.html(...,
  unsafe_allow_javascript=True)`, filtré par DOMPurify : un `<script>`
  dont le texte contient « < » suivi d'une lettre ou d'un chiffre est
  supprimé **sans erreur** (constaté le 2026-10-18). Une bibliothèque
  minifiée doit donc être chargée par `<script src=…>` (fichier servi en
  statique), pas collée en ligne.
- Navigation : les pages sont des boutons de la barre latérale (clés
  `nav_---Dashboard`, `---Recherche`, `---Veille`, `---Messages`,
  `---Historique`, `---Logs`). Changer de page provoque un nouveau rendu :
  la visite doit reprendre à la bonne étape après ce rendu.
- La barre latérale est repliée sur petit écran : une étape qui la vise
  doit l'ouvrir, ou se rabattre au centre.
- Aucune donnée personnelle dans le dépôt ; thème et couleurs de
  `DESIGN.md` (bulle blanche, bouton principal marine, texte Inter).
- Respect de « mouvement réduit ».
- La mémoire « tutoriel vu » vit à côté de la mémoire de version
  existante (`utils/nouveautes.py`, dossier de configuration de la
  personne).

## Laissé au constructeur

Le mécanisme exact de reprise après changement de page, l'emplacement
du fichier statique, la manière de lire « tutoriel vu » côté Python, le
style précis de la bulle (dans les limites de `DESIGN.md`), et les tests.
