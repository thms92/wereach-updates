# We.Reach — Guide d'installation (Mac)

We.Reach tourne **sur ton Mac**, avec **ta connexion** — c'est ce qui permet à
LinkedIn de fonctionner normalement. Installation = **une seule fois**, ~5 min.

---

## Étape 1 — Sortir le dossier du zip
Double-clic sur **`We.Reach.zip`** → tu obtiens un dossier **`We.Reach`**.
Mets-le où tu veux (ex. Bureau).

## Étape 2 — Autoriser le lanceur (une seule fois)
macOS bloque par principe **tout fichier venu d'internet**. Ce n'est pas un
problème de l'outil, et **ça ne se fait qu'une fois**.

1. **Clic droit** sur **`1 - Lancer We.Reach.command`** → **Ouvrir**.
   Si une fenêtre propose **Ouvrir** → clique dessus, c'est réglé → Étape 3.
2. Si l'alerte ne propose **que** *« Placer dans la corbeille »* / *« Terminé »*
   (macOS récent) :
   - clique **Terminé** (⚠️ surtout **pas** « Placer dans la corbeille ») ;
   - **Réglages Système** → **Confidentialité et sécurité** → descends tout en bas,
     section **Sécurité** ;
   - ligne « *« 1 - Lancer We.Reach.command » a été bloqué…* » → **Ouvrir quand même** ;
   - saisis le **mot de passe de ta session** ;
   - re-**double-clic** sur `1 - Lancer We.Reach.command` → **Ouvrir**.

## Étape 3 — Laisser installer (2 à 5 min, automatique)
Une fenêtre noire installe **tout** :
- **Python** si tu ne l'as pas → macOS demandera **le mot de passe de ta session**
  (normal, c'est pour installer Python) ;
- les composants + le navigateur.

Laisse faire, ne ferme rien. Ton **navigateur s'ouvre** sur We.Reach. 🎉

> Garde la fenêtre noire ouverte pendant que tu utilises l'outil.

---

## Mises à jour — automatiques
À chaque ouverture, We.Reach vérifie s'il existe une version plus récente et
l'installe tout seul (quelques secondes), **sans toucher à tes données**.
- Tu ne recevras **jamais** de nouveau zip à réinstaller.
- Tu n'auras **jamais** à refaire l'Étape 2.
- Ta version est affichée **en bas de la barre de gauche** : `We.Reach vX.Y.Z`.

## Utilisation
1. **Récupère ton cookie LinkedIn** (`li_at`) — tuto dans l'app (encadré
   « Comment récupérer mon cookie »), ou :
   - Connecte-toi sur **linkedin.com** (Chrome) → **F12** → onglet **Application**
     → **Cookies** → `https://www.linkedin.com` → ligne **`li_at`** → copie la valeur.
   - Ton cookie est **personnel** et **chiffré sur ton Mac** — ne le partage jamais.
2. Dans We.Reach → page **Recherche** → colle le cookie → **Enregistrer**.
3. **Candidats** : mots-clés + une **école** et/ou un **cabinet concurrent** → **Lancer**.
   Active « Envoyer des invitations » si tu veux inviter en même temps.
4. Plus tard → page **Messages** → **« Vérifier qui a accepté »** → coche → écris
   ton message → **Envoyer**.

## Bon à savoir
- **Sécurité** : max **20 invitations / jour** (limite volontaire pour protéger ton compte).
- Un **vrai Chrome s'ouvre** pendant le travail (c'est normal, ne le ferme pas).
- Pour **relancer** un autre jour : re-double-clic sur le même fichier (instantané).

## Souci ?
- Bloqué sur **`Email:`** dans la fenêtre noire → appuie juste sur **Entrée**.
- **« Ce site est inaccessible »** → attends 1 min (le 1er lancement est long), sinon relance.
- Autre → envoie une capture de la fenêtre noire à Thomas.

---

## (Pour Thomas) Publier une mise à jour
```bash
bash publish_update.sh patch "fix: description"
```
Bump la version, commit, push sur `main` du dépôt `thms92/wereach-updates`.
Tout le monde l'a au prochain lancement (délai ≤ 5 min : cache CDN de GitHub).
