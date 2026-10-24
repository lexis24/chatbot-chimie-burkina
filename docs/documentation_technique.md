# Documentation technique — Prof Karim (chimie, Burkina Faso)

Ce document décrit l'architecture réelle de l'application. L'installation et l'utilisation sont dans le
[README](../README.md).

## 1. Vue d'ensemble

```
Élève (navigateur, PWA)
   │  React + Vite : chat, exercices, prérequis, flashcards, cours, exports PDF/Word
   ▼
API FastAPI (backend/main.py)
   ├── RAGSystem (rag_system.py)
   │     ├── recherche vectorielle : LlamaIndex + PGVectorStore (table chimie_burkina_embeddings)
   │     └── génération : API Claude (prompts de chimie, schémas JSON, vérification des QCM)
   ├── database.py : comptes, conversations, messages, révisions de flashcards (schéma Postgres "app")
   └── fichiers statiques : data/documents (cours), data/summaries (fiches), data/flashcards (JSON)
   ▼
Postgres + pgvector (Neon) — base dédiée à la chimie
```

## 2. Backend

| Fichier | Rôle |
|---|---|
| `main.py` | Endpoints `/api/*`, validation (classes et chapitres du programme), authentification, consentement, persistance best-effort, service du frontend compilé ; messages d'erreur en français |
| `rag_system.py` | Recherche dans l'index, appels Claude (avec relance automatique si la réponse est tronquée), tous les prompts, analyse et validation des JSON d'exercices, de corrections et de prérequis, contenus de secours hors ligne |
| `curriculum_data.py` | Programme : 5 classes, 45 chapitres, intitulés et ordre exacts des manuels |
| `document_processor.py` | Extraction de texte (PDF/DOCX/TXT), correspondance classe/chapitre ↔ fichier (alias de dossiers, mots-clés, numéro de chapitre) |
| `ingest_documents.py` | Indexation : classement de chaque PDF par Claude (contenu), repli sur le numéro de chapitre, reconstruction de la table vectorielle |
| `database.py`, `auth.py`, `consent_text.py` | Données élèves, JWT, texte de consentement versionné |
| `config.py` | Paramètres (lus depuis `.env`) : modèle, budgets de tokens, `DATABASE_URL`, `VECTOR_TABLE_NAME`, dossiers de données |

### Prompts (rag_system.py)

Constantes partagées par les prompts :

- `OFF_TOPIC_INSTRUCTIONS` : portée limitée à la chimie (physique et maths déclinées, outils mathématiques au service
  de la chimie et questions de sécurité chimique acceptés).
- `FORMULA_FORMAT_INSTRUCTIONS` : formules, ions et équations en `\ce{...}` (mhchem) dans `$...$` ; autres grandeurs
  en LaTeX, unités en `\text{}` avec espace fine et virgule décimale `{,}`.
- `CHEMISTRY_RIGOR_INSTRUCTIONS` : équations équilibrées (éléments et charges), quantité de matière, masses molaires,
  calcul en trois temps, tableau d'avancement (à partir de la 2nde), nomenclature UICPA, niveau par classe (pas de
  mole avant la 2nde), consignes de sécurité et refus des modes opératoires dangereux.
- `FIGURE_SCHEMAS` / `FIGURE_FORMAT_INSTRUCTIONS` : formats JSON des schémas (voir §4) ; interdiction des schémas en
  ASCII et des pseudo-schémas LaTeX (`\begin{array}`).
- `NO_EMOJI_INSTRUCTIONS` : ton de manuel, tableaux Markdown (exemple : tableau d'avancement).

Exercices : 5 niveaux (`STAR_DIFFICULTY_LABELS`) — 1★ QCM, 2★ application d'une relation, 3★ notions combinées,
4★ situation d'intégration, 5★ olympiades (espèce inconnue à identifier, formule brute, réactif limitant caché,
ordre de grandeur, protocole...). L'énoncé et la correction sont générés par deux appels distincts ; les QCM
(exercices 1★ et prérequis) sont relus par un appel de vérification à température 0 (équilibrage, charges, unités).

Lecture des réponses JSON du modèle (`_loads_model_json`) : telle quelle, puis échappements LaTeX réparés
(`\ce` écrit avec un seul antislash), puis en tolérant de vrais sauts de ligne dans les chaînes (observé sur de longs
énoncés en Markdown).

Prérequis : les manuels n'ont pas de ligne « Prérequis : », mais chaque chapitre ouvre sur une section « CE QUE TU
DOIS DEJA SAVOIR » (exercices P1, P2... et tableau savoir-faire/rappel). `_prerequisite_section` la retrouve par
recherche **textuelle** dans la table vectorielle (filtre classe + chapitre, 45/45 chapitres) — la recherche
sémantique seule ne la retrouvait que pour 30 chapitres sur 45 et reste le repli. Le prompt reçoit aussi les
chapitres antérieurs (numérotés à partir de 1) et le programme des classes précédentes.

### Recherche des fichiers d'un chapitre

`find_course_file` cherche d'abord `<dossier>/<classe>/<chapitre>/`, puis parcourt les dossiers de classe
(`4eme`, `3eme`, `2ndeC`, `1ereD`, `TleD`, reconnus via `CLASS_ALIASES`) et note chaque fichier selon les mots-clés
de l'intitulé, avec un demi-point si son numéro `Chimie_Chapitre_N_` correspond au rang du chapitre dans le
programme. Un fichier dont le numéro désigne exactement le chapitre est accepté même s'il ne recoupe qu'une minorité
de mots-clés (noms abrégés : `…_2_Les_solutions_aqueuses_HCl_et_NaOH.pdf`). `/api/course` interroge d'abord l'index
vectoriel (filtre exact classe + chapitre posé à l'ingestion).

Les routes de fichiers par chapitre utilisent `{chapter:path}` : deux intitulés de Terminale contiennent une barre
oblique (« Les couples acide/base »), que l'encodage `%2F` ne protège pas.

## 3. Base de données

- **Table vectorielle** `data_chimie_burkina_embeddings` (préfixe `data_` ajouté par PGVectorStore) : passages de
  700 tokens (recouvrement 150) des 45 chapitres (3 804 passages), métadonnées `class`, `chapter`, `source`.
  Reconstruite à chaque exécution de `ingest_documents.py`.
- **Schéma `app`** : utilisateurs, établissements (`seed_schools.py`), conversations, messages (`MESSAGE_KINDS`),
  résultats de prérequis, signaux de difficulté, révisions de flashcards. Créé au démarrage (`database.init_db`).

## 4. Schémas de chimie

Claude décrit un schéma en JSON (bloc ```` ```figure ```` dans le chat, champ `figure` d'un exercice ou d'une
correction) ; le frontend le dessine en SVG.

| Type | Contenu |
|---|---|
| `montage` | Modèle prédéfini (`MONTAGE_MODELS`) : dosage (pH-mètre facultatif), electrolyse, pile, chauffage_reflux, recueil_gaz, combustion, tube_essai. Claude choisit le modèle et remplit les étiquettes ; le dessin place la verrerie et range les légendes en deux colonnes sans chevauchement |
| `graphique` | Axes gradués (grandeur + unité), séries de points ou courbes, repères (équivalence, demi-équivalence), annotations |
| `echelle` | Horizontale (zones de prédominance, échelle de pH, repères) ou verticale (`couples` : E° ou pKa, une espèce de chaque côté) |
| `molecule` | Atomes (ou groupes `CH3`) sur une grille, liaisons simples/doubles/triples, Cram (`avant`/`arriere`), doublets non liants, charges |
| `geometrie` | Construction géométrique simple (secours) |

- Backend : `FIGURE_SCHEMAS` (exemples testés par `tests/test_figures.py`), `RAGSystem._valid_figure`.
- Frontend : `components/ChemistryFigure.jsx` (aiguillage + barrière d'erreur), `components/figures/*`
  (`MontageFigure`, `GraphFigure`, `ScaleFigure`, `MoleculeFigure`, utilitaires `svg.jsx`), `lib/figureSpec.js`
  (logique pure testée). Étiquettes en texte simple (`H_2O`, `Cu^{2+}`, `pK_a`) ; un `\ce{}` écrit par erreur est
  converti. Police forcée en ligne sur le cadre (un schéma du chat est rendu dans un `<pre>`). Pointes de flèches en
  polygones pour un export PDF fidèle. L'export Word remplace un schéma par « [Schéma — voir dans l'application] ».

## 5. Frontend

| Élément | Rôle |
|---|---|
| `App.jsx` | État global, sessions invité (`localStorage`, clés `chatchimie-*`), exports ; un chapitre restauré qui n'appartient pas à la classe courante est oublié |
| `components/RichContent.jsx` | Rendu Markdown + KaTeX + mhchem (`katex/contrib/mhchem`) + schémas, partagé par tous les contenus |
| `components/ExerciseCard.jsx`, `RemediationQuiz.jsx`, `FlashcardsViewer.jsx`, `CourseViewer.jsx` | Exercices (schéma de l'énoncé et de la correction), prérequis, flashcards, lecteur PDF |
| `lib/pdf.js` | Export PDF : rendu foreignObject d'une copie fixée en haut à gauche (KaTeX et SVG dessinés par le navigateur), polices intégrées via `<svg><style>`, couleurs oklch normalisées, défilement remis à zéro pendant la capture, repli sur le rendu classique si la capture est blanche |
| `lib/docx.js`, `lib/docxModel.js` | Export Word ; conversion LaTeX → texte, y compris `\ce{}` (`SO₄²⁻`, `→`, `⇌`) |
| `tailwind.config.js` | Thèmes daisyUI `chatchimie-light` / `chatchimie-dark` (grenat `#9f1239`, ambre `#b45309`, accent `#d97706`) |

## 6. Tests

- Backend (`pytest`, 133 tests) : programme et couverture des PDF, fiches et flashcards (45 chapitres), correspondance
  des fichiers, schémas, section des prérequis, réparation des JSON d'exercices, API, base de données (comptes de test
  préfixés `pytest_`, supprimés en fin de test).
- Frontend (`vitest`, 64 tests) : schémas, conversion LaTeX/mhchem pour Word, validations, messages serveur.
