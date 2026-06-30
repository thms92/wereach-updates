# 📤 Guide de Partage - LinkedIn Scraper V2

## 🎯 Méthode Recommandée pour Mac

### Étape 1 : Créer le Package

Dans Terminal, naviguez vers le dossier et lancez :

```bash
cd "chemin/vers/mon dossier de scrapping perso"
./create_package.sh
```

Cela va créer un fichier ZIP avec tous les fichiers nécessaires.

### Étape 2 : Partager le ZIP

Vous avez plusieurs options :

#### Option A : AirDrop (Mac à Mac) 🍎
1. Localisez le fichier `LinkedIn-Scraper-V2_XXXXXXXX_XXXXXX.zip`
2. Clic droit > Partager > AirDrop
3. Sélectionnez le Mac de la personne
4. Envoyez !

#### Option B : Email 📧
1. Localisez le fichier ZIP
2. Attachez-le à un email
3. Envoyez à la personne

#### Option C : WeTransfer 🌐
1. Allez sur wetransfer.com
2. Uploadez le fichier ZIP
3. Copiez le lien de téléchargement
4. Envoyez le lien à la personne

#### Option D : Clé USB 💾
1. Copiez le fichier ZIP sur une clé USB
2. Donnez la clé USB à la personne

---

## 📝 Instructions pour la Personne qui Reçoit

Envoyez-lui ces instructions :

```
Bonjour,

Voici l'outil LinkedIn Scraper V2 que je t'ai préparé.

ÉTAPES D'INSTALLATION (Mac) :

1. Télécharge et décompresse le fichier ZIP

2. Ouvre Terminal (Applications > Utilitaires > Terminal)

3. Va dans le dossier décompressé :
   cd ~/Downloads/LinkedIn-Scraper-V2
   (ou glisse-dépose le dossier dans Terminal après avoir tapé "cd ")

4. Lance l'installation :
   ./install_mac.sh

5. Une fois l'installation terminée, lance l'application :
   ./launch_app.sh

6. L'application s'ouvre dans ton navigateur !

7. Pour récupérer ton cookie LinkedIn :
   - Connecte-toi à LinkedIn dans Chrome
   - Appuie sur Cmd+Option+I
   - Va dans Application > Cookies > linkedin.com
   - Cherche "li_at" et copie sa valeur
   - Colle-la dans l'interface

IMPORTANT :
- Ne partage jamais ton cookie li_at
- Limite-toi à 20-30 invitations par jour
- Respecte les bonnes pratiques (voir README.md)

Le fichier README.md contient toutes les instructions détaillées.

Bon scraping !
```

---

## ⚠️ Checklist Avant de Partager

Vérifiez que vous N'INCLUEZ PAS ces fichiers :

- [ ] `.secure_cookie` ❌
- [ ] `linkedin_scraper.db` ❌
- [ ] `scraper.log` ❌
- [ ] `debug_*.png` ❌
- [ ] `*.xlsx` ❌
- [ ] `__pycache__/` ❌

Le script `create_package.sh` exclut automatiquement ces fichiers.

---

## 🔧 En cas de Problème

Si la personne rencontre des problèmes :

### "Permission denied" lors de l'exécution du script

```bash
chmod +x install_mac.sh launch_app.sh
```

### "Python not found"

La personne doit installer Python :
https://www.python.org/downloads/

### "pip3: command not found"

Utiliser :
```bash
python3 -m pip install -r requirements.txt
```

### L'application ne se lance pas

Réinstaller les dépendances :
```bash
pip3 install -r requirements.txt --upgrade
python3 -m playwright install chromium
```

---

## 📊 Contenu du Package

Le ZIP contient :

### Code Python
- `app_advanced.py` - Interface Streamlit
- `scraper_v2.py` - Scraper principal
- `scraper_v2_sync.py` - Wrapper synchrone
- `config.py` - Configuration
- `database.py` - Gestion BDD
- `cookie_utils.py` - Gestion cookies
- `export_utils.py` - Export Excel
- `logger.py` - Logs

### Dossier utils/
- `dom_selectors.py` - Sélecteurs DOM
- `network_manager.py` - Gestion réseau
- `profile_extractor.py` - Extraction profils
- `__init__.py` - Init module

### Documentation
- `README.md` - Guide complet
- `INSTALLATION_MAC.md` - Guide d'installation Mac
- `requirements.txt` - Dépendances Python

### Scripts
- `install_mac.sh` - Script d'installation
- `launch_app.sh` - Script de lancement

---

## 💡 Conseils

1. **Testez d'abord** le package sur un autre Mac si possible

2. **Restez disponible** les premiers jours pour aider en cas de problème

3. **Rappelez les bonnes pratiques** :
   - Max 20-30 invitations/jour
   - Cibler des profils pertinents
   - Personnaliser les messages

4. **Expliquez les risques** :
   - Suspension de compte possible
   - Respecter les limites LinkedIn

---

## 🔄 Mise à Jour Future

Si vous modifiez l'outil et voulez partager la nouvelle version :

1. Relancez `./create_package.sh`
2. Envoyez le nouveau ZIP
3. La personne doit :
   - Sauvegarder son fichier `linkedin_scraper.db`
   - Remplacer les fichiers Python
   - Relancer `./install_mac.sh` si les dépendances ont changé

---

Bonne distribution ! 🚀
