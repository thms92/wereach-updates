#!/bin/bash
# Lanceur LinkedIn Scraper - macOS (double-clic)
cd "$(dirname "$0")"
clear
echo "============================================"
echo "   LinkedIn Scraper - Demarrage"
echo "============================================"
echo ""

# 1) Verifier que Docker tourne
echo "Verification de Docker..."
if ! docker info >/dev/null 2>&1; then
  echo ""
  echo "Docker ne tourne pas."
  echo "-> Ouvre l'application 'Docker Desktop', attends qu'elle demarre,"
  echo "   puis double-clique a nouveau sur ce fichier."
  echo ""
  read -p "Appuie sur Entree pour fermer..."
  exit 1
fi
echo "Docker OK"
echo ""

# 2) Demarrer l'app (la 1ere fois construit l'image : quelques minutes)
echo "Demarrage de l'application..."
echo "(La toute premiere fois peut prendre quelques minutes, c'est normal.)"
docker compose up -d --build

# 3) Attendre que l'app reponde
echo ""
echo "Attente du demarrage..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8501/_stcore/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# 4) Ouvrir le navigateur
echo "Pret ! Ouverture du navigateur..."
open http://localhost:8501
echo ""
echo "============================================"
echo " L'app est ouverte sur http://localhost:8501"
echo " Pour l'arreter : double-clique sur stop.command"
echo "============================================"
echo ""
read -p "Appuie sur Entree pour fermer cette fenetre..."
