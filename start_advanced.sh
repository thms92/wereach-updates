#!/bin/bash

# LinkedIn Scraper Pro - Script de démarrage
# Ce script lance l'interface Streamlit améliorée

echo "🚀 Démarrage de LinkedIn Scraper Pro..."
echo ""

# Vérifier que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

# Activer l'environnement virtuel
if [ -d "venv" ]; then
    echo "🔧 Activation de l'environnement virtuel..."
    source venv/bin/activate
else
    echo "⚠️ Environnement virtuel non trouvé"
    exit 1
fi

# Vérifier que streamlit est installé
if ! python -c "import streamlit" &> /dev/null; then
    echo "📦 Installation des dépendances..."
    pip install -r requirements.txt

    echo "🌐 Installation de Playwright..."
    playwright install chromium
fi

# Créer le dossier config s'il n'existe pas
mkdir -p config

# Lancer Streamlit
echo "✅ Lancement de l'interface..."
echo ""
streamlit run app_advanced.py
