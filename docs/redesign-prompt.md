# Prompt de redesign — WeFiiT Reach (à coller dans Claude, mode Artifacts/Design)

Copie-colle tout le bloc ci-dessous dans une nouvelle conversation Claude avec la création d'Artifacts activée.

---

Tu es un **designer produit senior** (SaaS B2B, design systems). Je veux **redessiner entièrement** l'interface de mon application web interne de prospection LinkedIn. C'est une app **Streamlit (Python)** utilisée par une petite équipe (≤ 10 personnes) pour rechercher des profils LinkedIn, extraire poste/entreprise/école, envoyer des invitations et gérer des campagnes.

## Marque
- **Nom du produit** : **WeFiiT Reach** (outil de prospection LinkedIn de WeFiiT).
- Tagline possible : « Prospection LinkedIn, simplifiée ».
- Le logo peut être un simple wordmark « WeFiiT Reach » avec un point d'accent coloré (ex. le « i » ou un point teal).

## Direction artistique (très important)
- **Propre, moderne, épuré** — peu de couleur, réservée aux éléments importants (CTA, badges de statut, métriques clés). Le reste en neutres.
- **Références** : **BoondManager** (SaaS, tableaux de données clairs et sobres), **Apple** (blanc, respiration, typographie soignée, sensation premium/simple), et la **palette de wefiit.com**.
- **Formes** : coins **arrondis** (rayons généreux, ~10–16px), beaucoup d'**espace**, transitions **fluides**, **ombres douces** et subtiles. Rien de chargé.

## Palette (inspirée de wefiit.com — donne les hex exacts)
- **Neutres** : blancs / off-white et une échelle de gris propre pour les fonds, bordures et textes (thème clair par défaut).
- **Accent principal** : un **teal / cyan** vif (comme wefiit) — uniquement pour CTA, liens, focus, éléments actifs.
- **Sombre profond** : un **charcoal / navy** (~#111418) pour le thème sombre et certains contrastes.
- **Statuts** : vert (succès / « Oui »), ambre (« En attente »), rouge (erreur / « Non »).
- Contraste **WCAG AA**. Fournis **thème clair ET thème sombre**.

## Typographie
- Sans-serif contemporaine (**Inter** ou équivalent type SF Pro). Titres larges et nets, corps de texte léger et lisible. Hiérarchie claire par la taille et le poids.

## Écrans à concevoir (dans le design system)
1. **Connexion** : écran centré, email + mot de passe, wordmark, très épuré (esprit Apple).
2. **Dashboard** (écran d'arrivée) :
   - un **sélecteur de période** (Semaine / Mois / Trimestre / Tout) en haut ;
   - **4 cartes KPI** (Total profils, Invitations envoyées, Invitations aujourd'hui, Taux d'acceptation) ;
   - **2 graphiques** (évolution dans le temps + répartition, ex. par école/entreprise).
3. **Recherche** avec **3 onglets** : **Candidats**, **Clients/Entreprises**, **File d'attente** — formulaire (mots-clés, entreprise, nombre, options, case « Envoyer des invitations ») + **tableau de résultats** dense mais aéré.
4. **Historique** : grand tableau filtrable/triable.
5. **Logs** : console de journal lisible (monospace léger).

## Composants à soigner
- **Barre latérale de navigation** (icônes + libellés, item actif en accent), avec en bas l'utilisateur connecté + déconnexion.
- **Cartes KPI** (grand chiffre, libellé, petite variation/tendance).
- **Tableaux** : lignes aérées, en-têtes discrets, **case à cocher de sélection**, **badges de statut** (« Oui » vert, « En attente » ambre, « Non » rouge), colonnes Nom/Poste/Entreprise/URL.
- **Boutons** : primaire (accent teal), secondaire (neutre), danger. États hover/focus/disabled.
- **Onglets**, **champs de formulaire**, **toasts** succès/alerte/erreur.

## Contrainte technique (déterminante)
C'est du **Streamlit** : je ne peux styliser que via (a) un **thème `.streamlit/config.toml`** (primaryColor, backgroundColor, secondaryBackgroundColor, textColor, font) et (b) du **CSS injecté** avec `st.markdown("<style>…</style>", unsafe_allow_html=True)`. Le CSS doit cibler des sélecteurs Streamlit robustes (barre latérale, `stButton`, `stMetric`, `stDataFrame`/`stDataEditor`, `stTabs`, `stTextInput`, en-tête) et **éviter les classes hachées** instables. Pas de refonte des composants React.

## Livrables (dans cet ordre)
1. **Guide de style** court : palette (hex), typo, rayons, ombres, espacements.
2. **Maquette HTML/CSS autonome** (un seul fichier, responsive, **thème clair + sombre**) montrant : Connexion, Dashboard, et l'onglet Recherche avec tableau de résultats — en **artifact**.
3. Le **bloc CSS Streamlit** + le **`.streamlit/config.toml`** prêts à copier dans mon app, cohérents avec la maquette.

Pose-moi au maximum 3 questions si un choix esthétique majeur te manque ; sinon propose directement.

---

**Après** : une fois la maquette validée, récupère le bloc CSS + `config.toml` et redonne-les à ton assistant (moi) pour intégration dans l'app Streamlit.
