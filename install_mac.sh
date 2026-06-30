#!/bin/bash

echo "🍎 Installation LinkedIn Scraper V2 pour Mac"
echo "============================================"
echo ""

# Vérifier Python
echo "1️⃣ Vérification de Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "✅ Python $PYTHON_VERSION trouvé"
else
    echo "❌ Python 3 non trouvé"
    echo "→ Installez Python depuis https://www.python.org/downloads/"
    exit 1
fi

# Installer les dépendances
echo ""
echo "2️⃣ Installation des dépendances Python..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dépendances installées"
else
    echo "❌ Erreur lors de l'installation des dépendances"
    exit 1
fi

# Installer Chromium
echo ""
echo "3️⃣ Installation de Chromium pour Playwright..."
python3 -m playwright install chromium

if [ $? -eq 0 ]; then
    echo "✅ Chromium installé"
else
    echo "❌ Erreur lors de l'installation de Chromium"
    exit 1
fi

echo ""
echo "🎉 Installation terminée avec succès !"
echo ""
echo "Pour lancer l'application :"
echo "  streamlit run app_advanced.py"
echo ""
echo "Ou utilisez le script de lancement :"
echo "  ./launch_app.sh"
echo ""
