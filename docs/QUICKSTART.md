# 🚀 Guide de Démarrage Rapide

## Installation en 3 étapes

### 1️⃣ Installation des dépendances

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2️⃣ Lancement de l'application

**Option A - Script automatique (recommandé) :**
```bash
./start_advanced.sh
```

**Option B - Commande manuelle :**
```bash
streamlit run app_advanced.py
```

### 3️⃣ Récupération du cookie LinkedIn

1. Connectez-vous sur [LinkedIn](https://www.linkedin.com)
2. Ouvrez les outils développeur (F12)
3. Allez dans l'onglet **Application** > **Cookies** > `https://www.linkedin.com`
4. Cherchez le cookie nommé `li_at`
5. Copiez sa valeur (longue chaîne de caractères)

---

## 🎯 Première Utilisation

### Étape 1 : Ouvrir l'application

L'application s'ouvre automatiquement dans votre navigateur à l'adresse :
```
http://localhost:8501
```

### Étape 2 : Entrer le cookie

1. Allez dans la page **🔍 Recherche**
2. Collez votre cookie dans le champ "Cookie li_at"
3. Le cookie sera automatiquement chiffré et sauvegardé

### Étape 3 : Configurer une recherche

**Pour rechercher des candidats :**
1. Entrez un mot-clé (ex: "Product Manager")
2. Sélectionnez UNE école
3. Choisissez le nombre de profils
4. Cliquez sur "🔍 Lancer le scraping"

**Pour rechercher des clients :**
1. Allez dans l'onglet "🏢 Clients/Entreprises"
2. Entrez le mot-clé (ex: "CTO")
3. Optionnel : précisez une entreprise
4. Lancez la recherche

### Étape 4 : Consulter les résultats

Les résultats s'affichent immédiatement :
- 📊 Dashboard : statistiques globales
- 💾 Historique : tous les profils
- 📥 Export Excel : téléchargez les données

---

## 💡 Fonctionnalités Principales

### 📊 Dashboard
- Vue d'ensemble de vos statistiques
- Graphiques interactifs
- Alertes sur les limites

### 🔍 Recherche
- Scraping avec/sans invitations
- Messages personnalisés
- Délais aléatoires pour sécurité

### 📋 Templates
- Sauvegardez vos recherches fréquentes
- Réutilisez vos paramètres
- Gagnez du temps

### 💾 Historique
- Consultez tous vos profils
- Filtrez par école
- Exportez en Excel/CSV

### ⚙️ Configuration
- Visualisez les paramètres
- Gérez la base de données
- Consultez les écoles

---

## ⚠️ Limites Recommandées

Pour éviter les blocages LinkedIn :

- **Max 50 invitations / jour**
- **Max 200 profils / recherche**
- **Délais aléatoires activés** (2-4 secondes entre profils)
- **Pas de scraping 24/7** (utilisez modérément)

---

## 🆘 Problèmes Courants

### Le scraping ne démarre pas
- ✅ Vérifiez que le cookie est valide
- ✅ Reconnectez-vous sur LinkedIn
- ✅ Copiez un nouveau cookie

### Erreur "Cookie invalide"
- Le cookie a expiré (expire après ~1 an)
- Récupérez un nouveau cookie

### Playwright ne se lance pas
```bash
playwright install chromium
```

### Erreur d'import
```bash
pip install -r requirements.txt --upgrade
```

---

## 📈 Conseils d'Utilisation

### Pour les Candidats
1. Choisissez des mots-clés précis ("Product Manager Junior", "Data Scientist Paris")
2. Filtrez par une seule école à la fois
3. Utilisez les messages personnalisés pour augmenter le taux d'acceptation

### Pour les Clients
1. Ciblez les décideurs ("CEO", "CTO", "Head of")
2. Précisez l'entreprise ou le secteur
3. Personnalisez vos messages

### Optimisation
1. Créez des templates pour vos recherches récurrentes
2. Consultez régulièrement le dashboard
3. Exportez vos données en Excel pour analyse

---

## 🔐 Sécurité

### Données Protégées
- ✅ Cookie chiffré (AES-128)
- ✅ Base de données locale
- ✅ Aucune donnée envoyée à des serveurs externes

### Fichiers Sensibles
Ne JAMAIS partager :
- `config/cookie.txt`
- `config/secret.key`
- `profiles.db`

---

## 📞 Besoin d'Aide ?

Consultez la documentation complète :
- `README_AMELIORATIONS.md` - Liste complète des améliorations
- `scraper.log` - Logs détaillés en cas d'erreur

---

**Bon scraping ! 🎉**
