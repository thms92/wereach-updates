# 🍎 Installation Rapide pour Mac

## Étape par Étape (Copier-Coller)

### 1️⃣ Vérifier Python

Ouvrir Terminal et taper :
```bash
python3 --version
```

Si vous voyez "Python 3.10" ou supérieur → OK ✅
Sinon → Installer Python depuis https://www.python.org/downloads/

### 2️⃣ Naviguer vers le dossier

```bash
cd ~/Desktop/"mon dossier de scrapping perso"
```

💡 **Astuce Mac** : Tapez `cd ` (avec un espace), puis glissez-déposez le dossier dans le Terminal, puis Entrée

### 3️⃣ Installer les dépendances

Copiez-collez cette commande :
```bash
pip3 install streamlit playwright pandas plotly openpyxl
```

Attendez que ça s'installe (1-2 minutes)

### 4️⃣ Installer Chromium

```bash
python3 -m playwright install chromium
```

Attendez (1-2 minutes)

### 5️⃣ Lancer l'application

```bash
streamlit run app_advanced.py
```

✅ L'application s'ouvre automatiquement dans votre navigateur !

Si ça ne s'ouvre pas automatiquement, allez sur : http://localhost:8501

## 🔑 Récupérer le Cookie LinkedIn (1ère utilisation)

1. Ouvrez Chrome et connectez-vous à LinkedIn
2. Appuyez sur `Cmd + Option + I` (DevTools)
3. Cliquez sur "Application" en haut
4. À gauche : Cookies > https://www.linkedin.com
5. Cherchez `li_at` dans la liste
6. Double-cliquez sur la valeur et copiez (Cmd+C)
7. Collez dans l'interface Streamlit

## 🎉 C'est tout !

Pour les prochaines fois, il suffit de :
1. Ouvrir Terminal
2. `cd` vers le dossier
3. `streamlit run app_advanced.py`

## ⚠️ En cas de problème

**"command not found: pip3"**
```bash
python3 -m pip install streamlit playwright pandas plotly openpyxl
```

**"command not found: streamlit"**
```bash
python3 -m streamlit run app_advanced.py
```

**L'app ne se lance pas**
```bash
# Réinstaller tout
pip3 install --upgrade pip
pip3 install -r requirements.txt
python3 -m playwright install chromium
```
