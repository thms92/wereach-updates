#!/bin/bash

# Script d'installation automatique - LinkedIn Scraper Pro V2
# Exécuter avec: bash install.sh

echo "════════════════════════════════════════════════════════════"
echo "🚀 Installation LinkedIn Scraper Pro V2"
echo "════════════════════════════════════════════════════════════"
echo ""

# Aller dans le dossier du script
cd "$(dirname "$0")"

# 1. Vérifier Python
echo "📋 Étape 1/5 : Vérification de Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé."
    echo "   Installez-le depuis https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION détecté"
echo ""

# 2. Créer l'environnement virtuel
echo "📦 Étape 2/5 : Création de l'environnement virtuel..."
if [ -d "venv" ]; then
    echo "⚠️  L'environnement virtuel existe déjà"
    read -p "   Voulez-vous le recréer ? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
        echo "✅ Environnement virtuel recréé"
    else
        echo "⏭️  Utilisation de l'environnement existant"
    fi
else
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        echo "✅ Environnement virtuel créé"
    else
        echo "❌ Erreur lors de la création de l'environnement virtuel"
        echo "   Essayez manuellement: python3 -m venv venv"
        exit 1
    fi
fi
echo ""

# 3. Activer l'environnement virtuel
echo "⚡ Étape 3/5 : Activation de l'environnement virtuel..."
source venv/bin/activate
if [ $? -eq 0 ]; then
    echo "✅ Environnement activé"
else
    echo "❌ Erreur lors de l'activation"
    exit 1
fi
echo ""

# 4. Installer les dépendances Python
echo "📥 Étape 4/5 : Installation des dépendances Python..."
echo "   (Cela peut prendre 2-3 minutes...)"

pip install --upgrade pip -q

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
    if [ $? -eq 0 ]; then
        echo "✅ Dépendances Python installées"
    else
        echo "❌ Erreur lors de l'installation des dépendances"
        echo "   Essayez manuellement: pip install -r requirements.txt"
        exit 1
    fi
else
    echo "⚠️  requirements.txt non trouvé, installation manuelle..."
    pip install streamlit pandas playwright openpyxl plotly -q
    echo "✅ Dépendances de base installées"
fi
echo ""

# 5. Installer Playwright
echo "🌐 Étape 5/5 : Installation de Playwright (navigateur)..."
echo "   (Cela peut prendre 1-2 minutes...)"
playwright install chromium
if [ $? -eq 0 ]; then
    echo "✅ Playwright Chromium installé"
else
    echo "❌ Erreur lors de l'installation de Playwright"
    echo "   Essayez manuellement: playwright install chromium"
    exit 1
fi
echo ""

# Créer le dossier config
mkdir -p config

# Rendre le fichier .command exécutable
if [ -f "LinkedIn Scraper Pro Advanced.command" ]; then
    chmod +x "LinkedIn Scraper Pro Advanced.command"
    echo "✅ Fichier .command rendu exécutable"
fi

echo "════════════════════════════════════════════════════════════"
echo "✅ Installation terminée avec succès !"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "🎯 Prochaines étapes :"
echo ""
echo "   1. Double-cliquez sur 'LinkedIn Scraper Pro Advanced.command'"
echo "   OU"
echo "   2. Exécutez dans le terminal :"
echo "      source venv/bin/activate"
echo "      streamlit run app_advanced.py"
echo ""
echo "📚 Documentation :"
echo "   • INSTALLATION.md - Guide complet"
echo "   • SCRAPER_V2_GUIDE.md - Guide du Scraper V2"
echo "   • README.md - Vue d'ensemble"
echo ""
echo "🚀 Bon scraping !"
echo ""
