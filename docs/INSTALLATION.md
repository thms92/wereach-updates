# 🚀 Guide d'Installation - LinkedIn Scraper Pro V2

## 📋 Prérequis

- **Python 3.8+** installé sur votre Mac
- **Terminal** ou **Ligne de commande**

---

## ⚡ Installation Rapide (3 minutes)

### **Étape 1 : Ouvrir le Terminal**

1. Appuyez sur `Cmd + Espace`
2. Tapez "Terminal" et appuyez sur `Entrée`

---

### **Étape 2 : Aller dans le dossier du projet**

```bash
cd "/chemin/vers/mon dossier de scrapping perso"
```

**💡 Astuce :** Vous pouvez glisser-déposer le dossier dans le Terminal pour obtenir le chemin automatiquement !

---

### **Étape 3 : Créer l'environnement virtuel**

```bash
python3 -m venv venv
```

**Résultat attendu :** Un dossier `venv/` est créé (vous le verrez dans votre dossier)

---

### **Étape 4 : Activer l'environnement virtuel**

```bash
source venv/bin/activate
```

**Résultat attendu :** Vous verrez `(venv)` au début de votre ligne de commande :
```
(venv) username@MacBook mon dossier de scrapping perso %
```

---

### **Étape 5 : Installer les dépendances**

```bash
pip install -r requirements.txt
```

**Durée :** ~2 minutes

**Résultat attendu :**
```
Successfully installed streamlit-1.x.x playwright-1.x.x pandas-2.x.x ...
```

---

### **Étape 6 : Installer Playwright (navigateur)**

```bash
playwright install chromium
```

**Durée :** ~1 minute

**Résultat attendu :**
```
Chromium 123.0.6312.4 downloaded
```

---

### **Étape 7 : Lancer l'application** 🎉

**Option A - Via le fichier .command (recommandé)**
```bash
# Rendre le fichier exécutable
chmod +x "LinkedIn Scraper Pro Advanced.command"

# Double-cliquez ensuite sur le fichier dans le Finder
```

**Option B - Via le terminal**
```bash
streamlit run app_advanced.py
```

**Résultat attendu :**
- Votre navigateur s'ouvre automatiquement sur `http://localhost:8501`
- Vous voyez l'interface LinkedIn Scraper Pro

---

## ✅ Vérification de l'installation

Si tout fonctionne, vous devriez voir dans la sidebar :

```
⚙️ Version du Scraper
☐ 🚀 Utiliser Scraper V2 (Beta)
```

---

## 🐛 Résolution de Problèmes

### **Erreur : "python3: command not found"**

**Solution :** Installer Python 3

1. Aller sur https://www.python.org/downloads/
2. Télécharger Python 3.11 ou plus récent
3. Installer et réessayer

---

### **Erreur : "Permission denied" sur le .command**

**Solution :**
```bash
chmod +x "LinkedIn Scraper Pro Advanced.command"
```

---

### **Erreur lors de pip install**

**Solution 1 - Mettre à jour pip :**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Solution 2 - Installer manuellement :**
```bash
pip install streamlit pandas playwright openpyxl
playwright install chromium
```

---

### **L'application se lance mais erreur "Module 'utils' not found"**

**Solution :** Vérifier que le dossier utils existe
```bash
ls -la utils/
```

Si le dossier n'existe pas, contactez le support.

---

## 🎯 Prochaines Étapes

Une fois l'installation terminée :

1. **Tester V1** (version classique)
   - Décochez "Utiliser Scraper V2"
   - Lancez un scraping de test (5 profils)

2. **Tester V2** (nouvelle version)
   - Cochez "Utiliser Scraper V2"
   - Lancez le même scraping
   - Comparez les résultats

3. **Lire la documentation**
   - Ouvrez `SCRAPER_V2_GUIDE.md` pour les détails sur V2

---

## 📞 Support

**En cas de problème :**

1. Vérifiez les logs : `scraper.log`
2. Prenez une capture d'écran de l'erreur
3. Notez la version Python : `python3 --version`

---

## 🎉 C'est tout !

Votre LinkedIn Scraper Pro V2 est prêt à l'emploi !

**Bon scraping ! 🚀**
