# Bilan de session — création de l'application de chimie

> Document de passation pour la prochaine session qui reprend ce dossier. Rédigé le 2026-10-24.

## Contexte

- Ce dépôt (`lexis24/chatbot-chimie-burkina`) part d'une copie de l'application de mathématiques (commit
  `0042d3a`), transformée en assistant de **chimie** « Prof Karim », avec les mêmes fonctionnalités. L'application
  de physique (`../chatbot-physique-burkina`, « Prof Aïcha ») a servi de modèle et n'a pas été modifiée.
- **Aucun déploiement** n'a été fait. Aucun serveur, aucune URL de production pour l'instant. Ne pas réutiliser les
  scripts, serveurs ou bases des applications de maths et de physique.
- Base de données : projet Neon **dédié** à la chimie (PostgreSQL 18, extension `vector` 0.8.6). `DATABASE_URL` est
  uniquement dans `backend/.env` (non versionné). Sur la machine de développement, une variable d'environnement
  Windows `ANTHROPIC_API_KEY` prend le pas sur le `.env`.

## Ce qui a été fait (étapes validées une à une)

1. **Identité** : nom « Prof Karim » (choisi parmi plusieurs propositions), palette grenat `#9f1239` / ambre `#b45309`,
   logo fiole (`FlaskConical`), icônes PWA régénérées, clés `localStorage` `chatchimie-*`, thèmes
   `chatchimie-light/dark`, fichiers exportés `chatchimie-*`, table vectorielle `chimie_burkina_embeddings`,
   `backend/.neon` supprimé, `sources_chimie/` ignoré par git.
2. **Programme** : `curriculum_data.py` = 45 chapitres (4ème 7, 3ème 10, 2nde C 9, 1ère D 9, Tle D 10), intitulés
   vérifiés un par un (ligne « CHAPITRE N : » de chaque PDF = champ « chapitre » des flashcards). `data/documents/` =
   45 PDF de chapitres. `document_processor.py` : départage par numéro de chapitre (repris de la physique) et
   acceptation des noms de fichiers abrégés dont le numéro correspond (`…_HCl_et_NaOH.pdf`).
3. **Prompts** (`rag_system.py`) : persona, portée chimie, formules en mhchem `\ce{}`, rigueur (équilibrage,
   quantité de matière, tableau d'avancement, unités), sécurité au laboratoire, olympiades de chimie, prérequis,
   contenus de secours hors ligne. Frontend : extension `katex/contrib/mhchem` ; export Word : conversion `\ce{}` →
   Unicode.
4. **Schémas** : `ChemistryFigure` (montage à modèles prédéfinis, graphique, échelle, molécule, géométrie), champ
   `figure` dans les exercices et les corrections ; testés avec de vraies réponses de Claude.
4bis. **Correctifs repris de la physique** : `pdf.js` (rendu foreignObject, polices intégrées, défilement),
   `MathContent` → `RichContent`, messages d'erreur en français, chapitre restauré oublié s'il n'est pas dans la
   classe, `run.py` sur `/api/classes`, `connect_timeout=10`.
5. **Contenus** : 45 fiches de révision PDF et 45 paquets de flashcards (1 608 cartes) importés tels quels ;
   indexation faite (45/45 PDF classés par leur contenu, 3 804 passages, aucun chapitre hors programme).
6. **Vérification** : 133 tests backend et 64 tests frontend verts ; parcours complet dans un vrai navigateur (Edge
   piloté par Playwright) ; README, documentation technique et ce bilan réécrits.

Documents bruts fournis (livres complets, guides enseignant, annexes) : `sources_chimie/`, ignoré par git.

## Problèmes trouvés et corrigés en cours de route

- **Barre oblique dans un intitulé** (« Les couples acide/base ») : 404 sur cours, résumé et flashcards de deux
  chapitres de Terminale — routes passées à `{chapter:path}`.
- **Réponse JSON d'exercice illisible** (une fois, non reproduite en 7 essais) : lecture plus tolérante
  (`_loads_model_json`, sauts de ligne non échappés acceptés).
- **Prérequis** : la recherche sémantique ne retrouvait la section « Ce que tu dois déjà savoir » que pour 30
  chapitres sur 45 → recherche textuelle sur ses marqueurs (45/45).
- Numérotation des chapitres antérieurs dans le prompt des prérequis (partait de 0).

## Points d'attention

- Réseau : certains réseaux bloquent le port 5432 (Postgres) ; l'application et les tests backend ne démarrent
  alors pas (`PoolTimeout`). Diagnostiquer DNS, port 443 et port 5432 avant de toucher au code.
- Ne pas lancer les tests backend pendant une indexation (ils initialisent l'index vectoriel au démarrage).
- Les montages sont des modèles fixes : un montage absent de la liste (distillation, hydrodistillation...) n'est pas
  dessinable — le modèle le décrit alors en phrases. Ajouter un modèle = `MONTAGE_MODELS` (backend) +
  `MontageFigure.jsx` + `figureSpec.js`.
- Les formules développées sont placées par Claude sur une grille : à surveiller sur les grosses molécules.

## À faire ensuite

- Déploiement : kit prêt dans `deploy/` (archive locale + `redeploy.sh` sur le serveur, secrets dans
  `~/<app>/container.env`), voir `deploy/DEPLOIEMENT.md` ; chimie sur le port 8002, physique sur le port 8003 du
  VPS 167.233.234.219, à valider après la vérification des ports libres.
- `DEPLOY.md` décrit un déploiement Railway + Vercel générique ; à relire avant usage.
