# Nouveautés de We.Reach

Ce fichier est lu par l'application : chaque section `## <version>` est
annoncée aux utilisateurs au premier lancement suivant la mise à jour.
Écrire pour eux, pas pour un développeur — ce qui change à l'écran, pas
ce qui change dans le code.

## 1.4.9

**L'annonce d'une mise à jour apparaît toute seule.**
Jusqu'ici elle ne pouvait surgir qu'au moment où vous cliquiez quelque part :
en laissant We.Reach ouvert sans y toucher, on pouvait ne jamais être
prévenu. L'outil surveille désormais en arrière-plan et vous avertit dans les
cinq minutes, sans rien faire.

## 1.4.8

**Un bouton « Vérifier les mises à jour » dans le panneau de gauche.**
We.Reach ne regarde le dépôt qu'une fois toutes les dix minutes, pour ne pas
le solliciter sans cesse. Si on vous annonce qu'une version vient de sortir,
ce bouton la cherche immédiatement.

## 1.4.7

**Une école sans identifiant ne ruine plus toute la recherche.**
Il suffisait d'une seule pour que le filtre « écoles » cesse d'en être un et
devienne une simple recherche de mots dans les profils : sélectionner
quarante écoles ne renvoyait alors aucun résultat. Celles qui posent problème
sont maintenant écartées, nommées à l'écran, et la recherche part avec les
autres.

**Plus aucune limite sur le nombre d'écoles ni de secteurs.**
Vous pouvez tous les sélectionner. Le plafond de dix n'avait pas lieu d'être.

**Vos parenthèses sont réparées toutes seules.**
Une parenthèse oubliée dans les mots-clés rendait la requête invalide, et
LinkedIn répondait « Aucun résultat » sans rien expliquer.

## 1.4.6

**We.Reach vous prévient quand une mise à jour existe.**
Un bandeau apparaît en haut de l'écran avec un bouton « Mettre à jour
maintenant » : un clic, et l'outil redémarre à jour. Jusqu'ici la mise à jour
ne s'installait qu'au démarrage — qui ne fermait jamais l'application pouvait
rester des semaines sur une ancienne version sans le savoir.

## 1.4.5

**Le panneau de gauche s'allège.**
Les réglages techniques — proxy, paramètres de scraping, réinitialisation de
la base — n'y figurent plus. Ils ne servaient pas à l'usage quotidien, et
l'un d'eux effaçait tout votre historique d'un simple clic.

## 1.4.4

**Le bouton « Préparer le mail » fonctionne vraiment.**
Il annonçait que votre messagerie s'ouvrait, et rien ne se passait : macOS
peut avoir confié les liens mail à un navigateur, qui les avale en silence.
We.Reach le détecte et ouvre Mail. Si vous avez choisi Outlook, c'est Outlook
qui s'ouvre — on contourne un navigateur, pas votre choix.

## 1.4.3

**Le signalement ouvre votre logiciel de messagerie, plus le navigateur.**
Le bouton « Préparer le mail » passait par un lien web, que Chrome ou Arc
détournaient volontiers vers un webmail. Il ouvre maintenant directement
Mail — ou le logiciel de messagerie que vous avez défini par défaut.

## 1.4.2

**Vous pouvez lancer une recherche sans poser de filtre.**
L'onglet Candidats exigeait au moins une école, une entreprise ou un secteur.
Des mots-clés seuls suffisent désormais — comme c'était déjà le cas dans
l'onglet Clients/Entreprises. Seule une recherche entièrement vide reste
refusée : sans le moindre critère, LinkedIn renverrait des profils au hasard
et votre quota d'invitations y passerait.

## 1.4.1

**Relancer We.Reach alors qu'il est déjà ouvert ne pose plus de problème.**
Un second double-clic pouvait afficher une erreur incompréhensible, puis
ouvrir une deuxième fenêtre qui montrait encore l'ancienne version. L'outil
ferme désormais la session précédente avant de repartir, proprement.

## 1.4.0

**Signaler un problème ne demande plus de capture d'écran.**
Si l'outil refuse de démarrer, la fenêtre d'erreur propose désormais
d'envoyer un rapport : un mail s'ouvre déjà rédigé, avec tout ce qui sert au
diagnostic. Vous n'avez qu'à cliquer sur Envoyer. Un volet « Signaler un
problème » existe aussi dans le panneau de gauche, pour les soucis
rencontrés en cours d'utilisation. Vous voyez toujours ce qui part, et votre
cookie LinkedIn n'y figure jamais.

## 1.3.0

**We.Reach fonctionne où que vous rangiez son dossier.**
Jusqu'ici il ne démarrait de façon fiable que depuis Téléchargements : posé
sur le Bureau ou dans Documents, iCloud en déplaçait des morceaux pour gagner
de la place et l'outil cassait. Vos données sont désormais rangées à part,
hors de portée d'iCloud. Vous pouvez mettre le dossier où bon vous semble.

**Retélécharger l'outil ne vous fait plus rien perdre.**
Avant, un nouveau dossier repartait vide : cookie à ressaisir, historique
envolé. Maintenant il retrouve tout automatiquement.

## 1.2.3

**L'outil se répare tout seul après une mise à jour de votre Mac.**
Jusqu'ici, une montée de version de macOS pouvait casser l'installation : la
fenêtre noire affichait « python: command not found » et la seule issue était
de tout réinstaller. Désormais We.Reach s'en aperçoit au démarrage, se
reconstruit en deux ou trois minutes, et repart. Vous n'avez rien à faire.

## 1.2.2

**Le menu de gauche a été mis au propre.**
Libellés alignés, espacement resserré, et la page sur laquelle vous vous
trouvez est désormais mise en valeur lisiblement.

## 1.2.1

**Le blocage de macOS au lancement ne reviendra plus.**
Si macOS vous a déjà refusé d'ouvrir We.Reach — l'alerte qui ne propose que
« Placer dans la corbeille » et « Terminé » —, et surtout s'il vous l'a
refusé une deuxième fois alors que vous l'aviez déjà autorisé, c'est réglé.
L'autorisation que vous donnez une fois est désormais définitive, y compris
après une mise à jour de votre Mac.

## 1.2.0

**Vous pouvez combiner plusieurs écoles et plusieurs entreprises.**
Sélectionnez Dauphine *et* ESCP, tapez « Capgemini, Accenture » dans le champ
entreprises : vous obtenez les profils passés par l'une de ces écoles **et**
travaillant dans l'une de ces entreprises.

**Nouveau filtre par secteur d'activité.**
43 secteurs, du conseil à l'édition de logiciels en passant par la banque, le
luxe ou l'industrie. Il se cumule avec les écoles et les entreprises.

**Le menu passe à cinq entrées.**
« Scraping URLs » est devenu l'onglet **Par URLs** dans Recherche, et
« Configuration » le volet **⚙️ Réglages** dans le panneau de gauche.

**La page « Chasse » disparaît.**
Recherche › Candidats fait tout ce qu'elle faisait, avec en plus les écoles et
les cabinets concurrents. Une différence si vous y aviez vos habitudes : Chasse
laissait demander 200 profils d'un coup, Recherche s'arrête à 80 — c'est la
limite de sécurité de l'outil, que Chasse contournait.

**L'application vous annonce désormais ce qui change.**
À chaque mise à jour, une fenêtre récapitule les nouveautés au premier
lancement — une seule fois, et seulement si vous utilisiez déjà l'outil.
