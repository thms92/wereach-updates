# Prompt de redesign — à coller dans Claude (fonctionnalité Design / Artifacts)

Copie-colle le bloc ci-dessous dans une nouvelle conversation Claude (avec la création d'artifact/design activée). Il produira une maquette moderne **et** le CSS Streamlit prêt à intégrer.

---

Tu es un designer produit senior spécialisé en SaaS B2B. Je veux **redessiner l'interface** de mon application web interne « **LinkedIn Scraper Pro** ». C'est une app **Streamlit (Python)** utilisée par une petite équipe (≤10 personnes) pour prospecter sur LinkedIn : rechercher des profils, extraire poste/entreprise/école, envoyer des invitations, et gérer des campagnes.

## Ce que je veux
1. Un **design system** cohérent, moderne et professionnel (pas « startup flashy » : plutôt sobre, dense en infos, orienté outil de travail — style Linear / Notion / LinkedIn Sales Navigator).
2. Une **maquette HTML/CSS autonome** (un seul fichier, responsive, thème clair **et** sombre) montrant : l'écran de connexion, le Dashboard (métriques + graphiques), et une page de recherche avec tableau de résultats sélectionnables.
3. Le **CSS à injecter dans Streamlit** (`st.markdown("<style>…</style>", unsafe_allow_html=True)`) + une proposition de thème `.streamlit/config.toml` (couleurs primaire/fond/texte, police) pour appliquer ce design system à l'app réelle.

## Contraintes techniques (important)
- C'est du **Streamlit** : je ne peux styliser que via un thème `config.toml` + du CSS injecté (pas de refonte des composants). Donne-moi du CSS qui cible les classes/atttributs Streamlit stables (barre latérale, boutons, `stDataFrame`/`stDataEditor`, `stMetric`, onglets, `stTextInput`). Reste robuste aux changements de Streamlit (évite les classes hashées).
- Palette : à partir du bleu LinkedIn (`#0A66C2`) mais **atténué/pro**, avec une couleur d'accent secondaire et une échelle de gris propre. Bon contraste (WCAG AA), lisible en clair et sombre.
- Typo : une police système ou Google Font sobre (Inter / IBM Plex Sans).
- Composants à soigner : **cartes de métriques** (KPI), **tableaux denses** avec lignes zébrées + case à cocher de sélection, **badges de statut** (ex. « Invitation : Oui/En attente/Non »), **barre latérale de navigation** avec icônes, **boutons** (primaire/secondaire/danger), **états** (succès/alerte/erreur), **écran de connexion** centré.

## Pages de l'app à couvrir dans le design system
- **Connexion** (email + mot de passe, centré).
- **Dashboard** : 4 cartes KPI (Total profils, Invitations, Invitations aujourd'hui, Taux), + 2 graphiques (camembert par école, dernière recherche).
- **Recherche** : formulaire (mots-clés, entreprise, nombre, options) + tableau de résultats.
- **🎯 Chasse** : import d'une liste + tableau **avec cases à cocher** + actions groupées.
- **Historique** : grand tableau filtrable.
- **Configuration / Logs**.

## Livrables attendus (dans l'ordre)
1. Un court **guide de style** (palette avec codes hex, typographie, rayons, ombres, espacements).
2. La **maquette HTML/CSS** autonome (clair + sombre, responsive) — en artifact.
3. Le **bloc CSS Streamlit** + le **`config.toml`** prêts à copier dans mon app.

Commence par 3 questions max si un choix esthétique important te manque, sinon propose directement.
