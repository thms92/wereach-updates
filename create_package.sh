#!/bin/bash

echo "📦 Création du package LinkedIn Scraper V2"
echo "=========================================="
echo ""

# Nom du package
PACKAGE_NAME="LinkedIn-Scraper-V2"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ZIP_NAME="${PACKAGE_NAME}_${TIMESTAMP}.zip"

# Créer un dossier temporaire
echo "1️⃣ Création du dossier temporaire..."
rm -rf /tmp/$PACKAGE_NAME
mkdir -p /tmp/$PACKAGE_NAME
mkdir -p /tmp/$PACKAGE_NAME/utils

# Copier les fichiers Python essentiels
echo "2️⃣ Copie des fichiers Python..."
cp app_advanced.py /tmp/$PACKAGE_NAME/
cp scraper_v2.py /tmp/$PACKAGE_NAME/
cp scraper_v2_sync.py /tmp/$PACKAGE_NAME/
cp config.py /tmp/$PACKAGE_NAME/
cp database.py /tmp/$PACKAGE_NAME/
cp cookie_utils.py /tmp/$PACKAGE_NAME/
cp export_utils.py /tmp/$PACKAGE_NAME/
cp logger.py /tmp/$PACKAGE_NAME/

# Copier le dossier utils
echo "3️⃣ Copie du dossier utils..."
cp utils/__init__.py /tmp/$PACKAGE_NAME/utils/
cp utils/dom_selectors.py /tmp/$PACKAGE_NAME/utils/
cp utils/network_manager.py /tmp/$PACKAGE_NAME/utils/
cp utils/profile_extractor.py /tmp/$PACKAGE_NAME/utils/

# Copier les fichiers de documentation
echo "4️⃣ Copie de la documentation..."
cp requirements.txt /tmp/$PACKAGE_NAME/
cp README.md /tmp/$PACKAGE_NAME/
cp INSTALLATION_MAC.md /tmp/$PACKAGE_NAME/
cp LISTE_FICHIERS_A_PARTAGER.txt /tmp/$PACKAGE_NAME/

# Copier les scripts d'installation
echo "5️⃣ Copie des scripts..."
cp install_mac.sh /tmp/$PACKAGE_NAME/
cp launch_app.sh /tmp/$PACKAGE_NAME/

# Rendre les scripts exécutables
chmod +x /tmp/$PACKAGE_NAME/install_mac.sh
chmod +x /tmp/$PACKAGE_NAME/launch_app.sh

# Créer le ZIP
echo "6️⃣ Création de l'archive ZIP..."
cd /tmp
zip -r "$ZIP_NAME" "$PACKAGE_NAME" > /dev/null

# Déplacer le ZIP dans le dossier d'origine
mv "/tmp/$ZIP_NAME" "$OLDPWD/"

# Nettoyer
rm -rf /tmp/$PACKAGE_NAME

echo ""
echo "✅ Package créé avec succès !"
echo ""
echo "📦 Fichier : $ZIP_NAME"
echo "📍 Emplacement : $(pwd)/$ZIP_NAME"
echo ""
echo "Vous pouvez maintenant partager ce fichier ZIP !"
echo ""
