# Veille entreprises — spec de conception

**Date :** 2026-10-15
**Statut :** en attente de relecture
**Décisions validées par :** Thomas, le 2026-10-15
**Périmètre de cette spec :** la **livraison 1**. Les livraisons 2 à 4 sont
situées (§3) pour que la livraison 1 ne les empêche pas, mais ne sont pas
conçues ici.


## Amendement du 2026-10-15 (décisions de Thomas, après relecture)

- **L'actualité entre dans la livraison 1** (elle était prévue en livraison 2).
  Source : flux RSS de Google News, gratuit, sans clé, sans coût LinkedIn.
  Requête : `"<nom>" (rachat OR acquisition OR fusion OR licenciement OR "plan
  social" OR restructuration OR "levée de fonds" OR lève OR nomme) when:1y`.
  Vérifié le 2026-10-15 : pour Decathlon, le rachat de 50 % de Sport 2000 et
  l'entrée au capital de Brompton ; pour une petite société (Thiga), rien —
  et sans ces mots-clés, des homonymes sans rapport. D'où deux filtres : la
  requête ne demande que ces événements, et un titre n'est gardé que s'il
  contient le nom de l'entreprise. Chaque titre est classé par mots-clés —
  *Rachat / fusion*, *Licenciements / restructuration*, *Levée de fonds*,
  *Nomination* — classement **approximatif**, affiché avec lien, source et
  date pour que la personne juge. Relue **une fois par jour pour toutes les
  entreprises suivies** (gratuite), indépendamment de la rotation LinkedIn.
  Aucune actualité → la fiche le dit, datée.
- **Le recrutement est hors périmètre** : « on s'en fiche » (Thomas).
- **En-tête « en un coup d'œil »** en tête de chaque fiche : taille, secteur,
  siège, effectif, dernière actualité marquante, nombre de contacts Product /
  Data / IA dont nouveaux. Pour lire une fiche en quelques secondes.
- Le récap « Nouveau aujourd'hui » inclut les nouvelles actualités.
- La livraison 2 se réduit donc au lancement automatique ; l'IA (résumés)
  reste en dernière livraison, optionnelle.

---

## 1. Le besoin

Thomas a vu une vidéo où Claude Code installe ScrapeGraphAI et un modèle local
(Ollama) pour produire, à partir d'une liste de sites, un fichier de leads :
*nom, dirigeant, poste, ville, email, téléphone, effectif, site, source*.

Son besoin va plus loin qu'un fichier ponctuel : **une veille quotidienne sur
des comptes cibles**. Chaque matin, pour chaque entreprise suivie, trouver tous
les contacts possibles sur des postes précis — Product, Data, IA — et tenir une
fiche entreprise : ses informations, son actualité, ses employés trouvés.

Usages déclarés : trouver des clients, débloquer des candidats, trier le
fichier.

## 2. Pourquoi pas la solution de la vidéo

| Contrainte | Vidéo (ScrapeGraphAI + Ollama) | We.Reach |
|---|---|---|
| Rien à installer chez les collègues | Ollama + un modèle de plusieurs Go par Mac | Arrive par la mise à jour automatique |
| Contacts Product/Data/IA | Ne sait pas lire LinkedIn connecté | Recherche LinkedIn déjà en service, avec la session de chacun |
| Fiabilité | Un petit modèle local devine en lisant des pages | Sources structurées d'abord (§5) |

On reprend l'**idée** — une fiche par entreprise, enrichie automatiquement,
chaque information avec sa source — pas l'outil.

## 3. Découpage en livraisons

1. **Comptes suivis, fiche entreprise, contacts, récap « Nouveau aujourd'hui »,
   lancement par bouton.** Objet de cette spec.
2. **Actualité** par le flux Google News (gratuit, sans clé), titres repérés
   par mots-clés : lève, recrute, nomme, rachète, plan social.
3. **Lancement automatique** à heure fixe (réveil programmé du Mac), avec
   rattrapage à la première ouverture de We.Reach dans la journée. Installé
   par la mise à jour, sans action des collègues.
4. **IA, si utile** : résumé de l'actualité, lecture des sites (coordonnées
   publiques, postes ouverts). Seule livraison qui demanderait une clé API
   (Claude, pas Ollama).

Aucune des livraisons 1 à 3 ne demande d'IA, de clé ni d'installation.

## 4. Décisions

| Question | Décision | Motif |
|---|---|---|
| Où vit la fonctionnalité | Dans We.Reach, distribuée par la mise à jour | Les collègues ne doivent rien installer |
| Volume | 20 à 50 entreprises par personne | Réponse de Thomas |
| Partage | **Chacun sa liste**, sur son Mac, avec son compte LinkedIn | Rien à synchroniser ; chaque compte porte son propre quota |
| Postes cherchés | Familles **Product, Data, IA**, les mêmes pour toute la liste, plus des intitulés libres | Réglage unique plutôt que par entreprise |
| Déclenchement (cible) | Heure fixe + rattrapage — **livraison 3** | Livraison 1 : bouton seulement |
| Résultat | Récap « Nouveau aujourd'hui » dans l'outil ; **aucune invitation automatique** | Irréversible, quota rare |
| Architecture | **Moteur de veille séparé de l'interface** (approche B) | Le bouton et le futur réveil appellent le même moteur ; la logique n'existe qu'une fois |
| Source des informations entreprise | Page LinkedIn « À propos », puis annuaire officiel recoupé | Structuré et fiable, sans IA |

## 5. Les sources

**Page LinkedIn de l'entreprise, section « À propos ».** Site web, taille,
secteur, siège, abonnés. Lue avec la session de l'utilisateur, comme les
profils. C'est elle qui **identifie** l'entreprise.

**Annuaire officiel — API Recherche d'entreprises** (`recherche-entreprises.api.gouv.fr`).
Gratuite, sans clé, publique. Dirigeants et fonctions, SIREN, activité (code
NAF), tranche d'effectif, date de création, siège. Vérifié le 2026-10-15 : la
recherche « thiga » renvoie en premier une exploitation agricole des Ardennes.
**L'annuaire n'est donc jamais interrogé seul** : un résultat n'est retenu que
s'il recoupe LinkedIn — commune du siège identique, ou domaine du site
cohérent. Plusieurs candidats compatibles ou aucun → « non rapprochée », rien
n'est deviné. Entreprises étrangères : absentes de l'annuaire, même mention.

**Recherche LinkedIn de personnes.** Celle de l'onglet Clients/Entreprises :
facette `currentCompany` (identifiant de l'entreprise, lu sur sa page LinkedIn
plutôt que deviné par le nom) et mots-clés des familles cochées, combinés en
OU. Dix profils par page de résultats.

## 6. Les écrans

Nouvelle entrée de menu **🏢 Veille** (sixième page), en trois parties.

**Nouveau aujourd'hui** — en tête de page. Depuis la dernière visite de la
page : nouveaux contacts groupés par entreprise et par famille (nom, intitulé,
degré, lien) ; changements de fiche (nouveau dirigeant, changement de taille).
Sélection → invitation, avec les garde-fous des Profils similaires : case
décochée par défaut, plafond d'invitations respecté, envoi seulement sur clic.
Un résumé du dernier passage : date, entreprises couvertes, arrêt éventuel et
sa cause.

**Mes entreprises.** Liste suivie : nom, dernier passage, contacts trouvés,
état de la fiche (identifiée / non identifiée / annuaire non rapproché).
Ajout depuis les sociétés de l'Historique, ou par collage du lien LinkedIn de
l'entreprise. Retrait. Bouton **« Lancer la veille »**, qui prévient qu'une
fenêtre Chrome va s'ouvrir et travailler.

**Fiche entreprise** — au clic. Ce que dit LinkedIn ; ce que dit l'annuaire ;
contacts par famille avec date de découverte ; pour chaque information, source
et date.

**Réglages de la veille** (volet) : familles cochées, intitulés libres, **part
du quota quotidien réservée à la veille** — 50 % par défaut, pour laisser de
la marge aux recherches manuelles.

## 7. Stockage

Dans la base SQLite existante de l'utilisateur (`profiles`, `invitations`,
`recherches` aujourd'hui). Ajouts, créés par `CREATE TABLE IF NOT EXISTS`
comme les tables actuelles — aucune migration destructive :

- **entreprises_suivies** : nom, lien LinkedIn, identifiant LinkedIn, date
  d'ajout, date du dernier passage, état d'identification, curseur de reprise
  de la recherche (dernière page parcourue par famille).
- **fiche_entreprise** : une ligne par information (champ, valeur, source,
  date) — l'historique des valeurs permet de signaler un changement.
- **contacts_veille** : lien entre un profil (table `profiles`, par URL
  canonique) et une entreprise suivie, famille de poste, date de découverte.
  Un profil déjà au fichier est relié, pas dupliqué, et ne compte pas comme
  « nouveau ».
- **passages_veille** : un enregistrement par passage (début, fin,
  entreprises couvertes, pages consommées, cause d'arrêt).

La date de dernière visite de la page Veille vit dans le dossier de config de
l'utilisateur, comme `derniere_version_vue.txt`.

## 8. Le moteur

Module autonome, sans Streamlit, appelable depuis l'application et en ligne de
commande (la livraison 3 l'appellera ainsi). Un passage :

1. **Verrou.** Si un passage ou une session LinkedIn de l'outil est déjà en
   cours pour cet utilisateur, refus avec message. Le verrou est aussi posé
   pendant le passage, et les recherches manuelles le respectent : deux
   sessions LinkedIn simultanées sur un même compte sont à proscrire.
2. **Budget.** Part du quota réservée (§6) moins ce qui a déjà été consommé
   aujourd'hui. Budget nul → arrêt immédiat, motivé.
3. **Lot.** Entreprises triées par date de dernier passage croissante
   (jamais passées en premier).
4. **Pour chaque entreprise**, jusqu'à épuisement du budget :
   a. page « À propos » — identification, fiche LinkedIn, identifiant ;
   b. annuaire officiel, recoupé (§5) ;
   c. recherche de personnes, à partir du curseur de reprise, quelques pages
      au plus par passage ; curseur mis à jour ;
   d. enregistrement ; date de dernier passage.
5. **Fin.** Enregistrement du passage et de sa cause d'arrêt.

Les délais humains, le warm-up et le moniteur HTTP existants s'appliquent :
la veille n'est pas plus rapide qu'un humain.

## 9. Échecs

| Situation | Comportement |
|---|---|
| Entreprise introuvable ou ambiguë sur LinkedIn | Fiche « non identifiée », lien demandé ; jamais de devinette |
| Annuaire : zéro ou plusieurs candidats compatibles, ou entreprise étrangère | Partie annuaire vide, « non rapprochée » ; le reste est gardé |
| Annuaire injoignable | Partie annuaire non mise à jour, la valeur précédente reste avec sa date |
| Cookie expiré | Arrêt du passage, cause affichée en tête du récap |
| Budget épuisé | Arrêt propre ; le récap dit combien d'entreprises ont été couvertes ; les autres passent en tête la fois suivante |
| Recherche sans résultat | Mentionné et daté dans la fiche (« aucun profil Data trouvé le 15/10 ») |
| Page « À propos » illisible (structure changée) | Avertissement explicite et HTML enregistré dans `logs/`, comme pour le panneau des Profils similaires |

Règle générale, héritée des Profils similaires : **aucune liste vide sans
explication, aucune donnée plausible mais fausse.**

## 10. Tests

- **Logique pure, sans navigateur ni réseau** : sélection du lot, calcul du
  budget, recoupement annuaire/LinkedIn (dont le cas « Thiga » : homonyme
  écarté), détection des nouveautés, curseur de reprise.
- **Extracteurs** : la page « À propos » lue par le vrai JavaScript dans un
  Chromium local sur une **fixture synthétique** fidèle à une capture réelle
  — même méthode que les Profils similaires. La capture réelle est faite à
  l'essai et ne va jamais dans le dépôt.
- **Annuaire** : réponses JSON enregistrées et rejouées ; aucun appel réseau
  dans les tests.
- **Interface** : AppTest, scraper remplacé par un espion (pattern existant).
- **Essai réel** avant toute publication, avec Thomas, sur 3 entreprises.

## 11. Hors périmètre (livraison 1)

- Actualité, lancement automatique, IA : livraisons 2 à 4.
- Liste partagée par l'équipe.
- Emails et téléphones nominatifs : non prévus. La collecte de coordonnées
  nominatives à des fins de prospection est encadrée par le RGPD ; à
  rediscuter explicitement si le besoin revient.
- Invitations automatiques.

## 12. Risques et inconnues

**Quota.** 20 à 50 entreprises, à quelques pages chacune, ne tiennent pas en
un seul matin dans la moitié de 80 pages. C'est voulu : veille tournante, une
entreprise revue tous les quelques jours. À mesurer à l'essai : pages réelles
par entreprise.

**Ce que le quota compte.** Le compteur actuel compte des profils scrapés.
Une page « À propos » ou une page de résultats de recherche n'en est pas un ;
il faudra décider à l'implémentation comment ces pages entrent dans le budget
— l'objectif est de ne pas solliciter LinkedIn davantage qu'aujourd'hui.

**Structure de la page « À propos ».** Inconnue à ce jour, à capturer à
l'essai — la leçon des Profils similaires (l'URL directe du panneau était
redirigée) s'applique : rien n'est tenu pour acquis avant d'avoir vu la page.

**Taille du fichier `app_advanced.py`.** Une sixième page alourdit encore un
fichier déjà gros ; la page Veille sera écrite dans son propre module.
