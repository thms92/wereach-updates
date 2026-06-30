# 💼 LinkedIn Scraper V2

Outil professionnel de scraping LinkedIn avec envoi d'invitations automatisé.

## ⚠️ Avertissement Important

**Cet outil est à usage personnel uniquement.**

- ⚠️ Respectez les limites LinkedIn (max 100-200 invitations/semaine)
- ⚠️ Utilisation intensive = risque de suspension de compte
- ⚠️ Violation potentielle des conditions d'utilisation LinkedIn
- 🔒 Ne partagez JAMAIS votre cookie `li_at` avec personne

## 🚀 Installation sur Mac

### Prérequis

1. **Vérifier que Python est installé** (Python 3.10 minimum requis) :
   ```bash
   python3 --version
   ```
   
   Si Python n'est pas installé, téléchargez-le ici : https://www.python.org/downloads/

### Installation

1. **Ouvrir le Terminal** (Applications > Utilitaires > Terminal)

2. **Naviguer vers le dossier** :
   ```bash
   cd "chemin/vers/mon dossier de scrapping perso"
   ```

3. **Installer les dépendances Python** :
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Installer le navigateur Chromium pour Playwright** :
   ```bash
   python3 -m playwright install chromium
   ```

5. **Lancer l'application** :
   ```bash
   streamlit run app_advanced.py
   ```

6. **Ouvrir votre navigateur** à l'adresse affichée (généralement http://localhost:8501)

## 🔑 Récupérer votre Cookie LinkedIn

Le cookie `li_at` est nécessaire pour que l'outil puisse se connecter à LinkedIn.

### Méthode Chrome/Safari :

1. **Connectez-vous à LinkedIn** dans votre navigateur
2. **Ouvrez les DevTools** :
   - Chrome : `Cmd + Option + I`
   - Safari : `Cmd + Option + C` (activez d'abord le menu Développeur dans Préférences)
3. **Allez dans l'onglet "Application"** (Chrome) ou "Storage" (Safari)
4. **Cliquez sur "Cookies" > "https://www.linkedin.com"**
5. **Cherchez le cookie nommé `li_at`**
6. **Copiez sa valeur** (longue chaîne de caractères)
7. **Collez-le dans l'interface Streamlit**

### 🔒 Sécurité du Cookie

- ✅ Le cookie est stocké localement de manière sécurisée dans `.secure_cookie`
- ✅ Il n'est jamais envoyé ailleurs que sur LinkedIn
- ⚠️ Si quelqu'un obtient votre cookie, il peut accéder à votre compte LinkedIn
- 🔄 Changez votre mot de passe LinkedIn si vous pensez que le cookie est compromis

## 📊 Utilisation

### Onglet 1 : Candidats (Recherche par École)

1. **Entrez votre cookie** `li_at`
2. **Remplissez les paramètres** :
   - Mots-clés : "Product Manager", "CTO", etc.
   - Entreprise (optionnel) : "Google", "Apple", etc.
   - Nombre de profils : 5-50 recommandé
   - ✅ Île-de-France uniquement (optionnel)
3. **Sélectionnez UNE école** dans la liste
4. **Cochez "Envoyer des invitations"** si vous voulez inviter les profils
5. **Cliquez sur "Lancer le scraping"**

### Onglet 2 : Clients (Recherche par Entreprise)

1. **Même principe** mais sans filtre école
2. **Utilisez le filtre Entreprise** pour cibler une société spécifique
3. **Parfait pour prospection B2B**

### Onglet 3 : Templates

- Sauvegardez vos recherches favorites
- Réutilisez-les rapidement

### Onglet 4 : Dashboard

- Visualisez vos statistiques
- Suivez vos invitations envoyées
- Analysez vos résultats

## 🎯 Bonnes Pratiques

### Limites recommandées

- **Invitations par jour** : 20-30 maximum
- **Invitations par semaine** : 100-150 maximum
- **Délais entre profils** : 3-5 secondes (déjà configuré)
- **Pages par session** : 3-5 pages maximum

### Conseils

- ✅ Personnalisez vos messages d'invitation
- ✅ Ciblez des profils pertinents pour vous
- ✅ Ne spammez pas : qualité > quantité
- ✅ Faites des pauses entre les sessions
- ❌ N'envoyez pas 200 invitations d'un coup
- ❌ Ne laissez pas tourner l'outil H24

## 🐛 Résolution de Problèmes

### "Cookie invalide ou expiré"

→ Récupérez un nouveau cookie `li_at` (LinkedIn vous a déconnecté)

### "Impossible de charger la page"

→ Vérifiez votre connexion Internet
→ LinkedIn peut bloquer temporairement les requêtes (attendez 1h)

### "Aucun profil trouvé"

→ Vérifiez vos critères de recherche
→ Essayez des mots-clés différents

### L'application ne se lance pas

→ Vérifiez que toutes les dépendances sont installées :
```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

### Erreur "playwright not found"

→ Réinstallez playwright :
```bash
pip3 uninstall playwright
pip3 install playwright
python3 -m playwright install chromium
```

## 📁 Structure des Fichiers

```
mon dossier de scrapping perso/
├── app_advanced.py          # Interface principale
├── scraper_v2.py           # Scraper async
├── scraper_v2_sync.py      # Wrapper synchrone
├── config.py               # Configuration
├── database.py             # Base de données
├── cookie_utils.py         # Gestion cookies
├── export_utils.py         # Export Excel
├── logger.py               # Logs
├── requirements.txt        # Dépendances
├── .secure_cookie          # Cookie sauvegardé (créé automatiquement)
├── linkedin_scraper.db     # Base de données (créée automatiquement)
└── scraper.log            # Logs (créés automatiquement)
```

## 🔄 Mise à Jour

Si vous recevez une version mise à jour de l'outil :

1. **Sauvegardez vos données** :
   ```bash
   cp linkedin_scraper.db linkedin_scraper.db.backup
   cp .secure_cookie .secure_cookie.backup
   ```

2. **Remplacez les fichiers Python** (.py)

3. **Mettez à jour les dépendances** :
   ```bash
   pip3 install -r requirements.txt --upgrade
   ```

## 💡 Support

En cas de problème, vérifiez :
1. ✅ Python 3.10+ installé
2. ✅ Toutes les dépendances installées
3. ✅ Cookie `li_at` valide et récent
4. ✅ Connexion Internet stable
5. ✅ LinkedIn n'a pas bloqué temporairement votre compte

## 📜 Licence & Responsabilité

- Cet outil est fourni "tel quel" sans garantie
- L'utilisateur est seul responsable de l'utilisation de cet outil
- Respectez les conditions d'utilisation de LinkedIn
- Usage à vos propres risques

---

**Version** : 2.0  
**Dernière mise à jour** : Janvier 2026
