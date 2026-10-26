# Prof Karim — assistant de chimie (Burkina Faso)

Assistant IA de **chimie** pour les élèves du Burkina Faso, de la **4ème à la Terminale D**, construit sur
**Claude (Anthropic)** et une architecture **RAG** appuyée sur les manuels de la Collection Hakili Lab
(édition 2026). Application sœur de « Prof Amira » (mathématiques) et « Prof Aïcha » (physique), avec les mêmes
fonctionnalités.

## Ce que fait l'application

- **Questions de cours et d'exercices** : explications adaptées à la classe, ancrées en priorité sur les manuels
  indexés, avec mémoire de la conversation. Les questions qui ne relèvent pas de la chimie (physique, maths pures,
  autres matières...) sont poliment déclinées ; les outils mathématiques au service de la chimie sont acceptés.
- **Formules chimiques** écrites avec l'extension **mhchem** de KaTeX (`$\ce{CH4 + 2O2 -> CO2 + 2H2O}$`,
  `$\ce{Cu^2+}$`, `$\ce{H3O+}$`), rendues à l'écran, dans l'export PDF et converties en Unicode dans l'export Word.
- **Rigueur chimique** : équations équilibrées (éléments et charges), états physiques, quantités de matière, masses
  molaires, concentrations, tableau d'avancement en vrai tableau, unités et chiffres significatifs ; consignes de
  sécurité au laboratoire dès qu'une manipulation est évoquée.
- **Schémas de chimie** dessinés en SVG à partir d'une description JSON produite par Claude : montages de laboratoire
  (dosage, électrolyse, pile, chauffage à reflux, recueil de gaz, combustion, tube à essai), graphiques (courbes de
  dosage, avancement), échelles (pH, prédominance, classification des couples) et formules développées / Lewis.
- **Exercices** en 5 niveaux (du QCM d'application directe au type olympiades de chimie), indice, correction détaillée
  à la demande, avec schéma dans l'énoncé et dans la correction ; les QCM sont revérifiés par un second appel.
- **Prérequis** : diagnostic des notions antérieures, ancré sur la section « Ce que tu dois déjà savoir » de chaque
  chapitre du manuel (rappel de cours + exercices).
- **Flashcards** (1 608 cartes, répétition espacée pour les élèves connectés), **fiches de révision** PDF et
  **cours** PDF par chapitre.
- **Photo d'exercice** : l'élève envoie une photo ou un PDF, Claude guide la résolution.
- **Export PDF / Word** d'une session ou de tout l'historique ; comptes élèves, consentement, tableau de bord
  décideur (statistiques agrégées) ; application installable (PWA), thèmes clair et sombre (palette grenat).

## Programme couvert

45 chapitres de chimie, intitulés exactement comme dans les manuels (`backend/curriculum_data.py`) :
4ème (7), 3ème (10), 2nde C (9), 1ère D (9), Terminale D (10).

## Architecture

| Partie | Technologies |
|---|---|
| Backend `backend/` | FastAPI, Claude (`anthropic`), LlamaIndex, embeddings `paraphrase-multilingual-MiniLM-L12-v2` |
| Base de données | Postgres + pgvector (Neon) **dédiée à la chimie** : table vectorielle `chimie_burkina_embeddings` et données applicatives (schéma `app`) |
| Frontend `frontend/` | React 18 + Vite, Tailwind + daisyUI, Framer Motion, react-markdown + KaTeX (+ mhchem), schémas SVG maison (`components/figures/`), jsPDF/html2canvas et docx pour les exports |

Contenus pédagogiques :

| Dossier | Contenu | Utilisation |
|---|---|---|
| `backend/data/documents/<classe>/` | 45 chapitres PDF (`Chimie_Chapitre_N_….pdf`) | « Voir le cours » + index RAG |
| `backend/data/summaries/fiches_<classe>/` | 45 fiches de révision PDF | Résumé téléchargeable |
| `backend/data/flashcards/<classe>/` | 45 paquets JSON (`cartes` : `recto`/`verso`) | Flashcards |
| `sources_chimie/` (non versionné) | Livres complets, chapitres, fiches, flashcards, guides enseignant | Archive des documents fournis |

Dossiers de classe : `4eme`, `3eme`, `2ndeC`, `1ereD`, `TleD`. Le chapitre N d'un manuel correspond au N-ième chapitre
de sa classe dans `curriculum_data.py` : ce numéro sert de départage et de secours pour retrouver le bon fichier
(voir `document_processor.py`).

## Installation

Prérequis : **Python 3.11** (3.10 à 3.12), **Node.js 18+**, une clé API Anthropic, une base Neon avec l'extension
`vector` (`CREATE EXTENSION IF NOT EXISTS vector;`).

```powershell
# Backend
cd backend
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # puis renseigner les valeurs (voir ci-dessous)
.\venv\Scripts\python.exe seed_schools.py   # schéma "app" + référentiel d'établissements

# Frontend
cd ..\frontend
npm install
```

Variables indispensables dans `backend/.env` (jamais commité) :

```env
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://...neon.tech/neondb?sslmode=require   # connexion directe, sans "-pooler"
VECTOR_TABLE_NAME=chimie_burkina_embeddings
```

> Une variable d'environnement Windows `ANTHROPIC_API_KEY` déjà définie **prend le pas** sur celle du `.env`
> (python-dotenv ne remplace jamais une variable existante).

## Indexer les manuels

À relancer après tout ajout ou remplacement de PDF dans `data/documents/` (reconstruit entièrement la table
`chimie_burkina_embeddings`, sans toucher au reste de la base) :

```powershell
cd backend
[Console]::OutputEncoding = $OutputEncoding = [Text.UTF8Encoding]::new()
.\venv\Scripts\python.exe -u ingest_documents.py | Tee-Object -FilePath ingest.log
```

Chaque document est classé dans son chapitre par Claude à partir de son contenu, avec repli sur le numéro de
chapitre du nom de fichier. Durée : 10 à 30 minutes ; la dernière ligne doit indiquer `45 document(s) indexes`.
Ne pas lancer les tests backend pendant une indexation.

## Lancer l'application

```powershell
python run.py          # lance backend (port 8000) + frontend (port 5173) et ouvre le navigateur
```

ou séparément : `cd backend; .\venv\Scripts\python.exe -m uvicorn main:app --reload` puis
`cd frontend; npm run dev`, et ouvrir http://localhost:5173.

## Déploiement

Kit de déploiement Docker (un conteneur par application, accès de test par `http://IP:port`) : voir
[deploy/DEPLOIEMENT.md](deploy/DEPLOIEMENT.md). Le même kit sert à l'application de physique.

## Tests

```powershell
cd backend;  .\venv\Scripts\python.exe -m pytest      # utilise la DATABASE_URL du .env (comptes préfixés pytest_, supprimés en fin de test)
cd frontend; npx vitest run
```

## Principaux endpoints

| Endpoint | Rôle |
|---|---|
| `GET /api/classes`, `GET /api/classes/{code}/chapters` | Programme |
| `POST /api/chat`, `POST /api/chat/stream` | Question (réponse complète ou en streaming) |
| `POST /api/exercise`, `POST /api/exercise/solution` | Exercice structuré, puis sa correction (avec schéma éventuel) |
| `POST /api/prerequis` | Diagnostic des prérequis d'un chapitre |
| `POST /api/simplify` | Réexplication plus simple |
| `POST /api/exercise/photo` | Aide sur une photo/un PDF d'exercice |
| `GET /api/course/…`, `GET /api/summary/file/…`, `GET /api/flashcards/…` | Cours, fiche de révision, flashcards (le chapitre peut contenir « / », ex. « Les couples acide/base ») |
| `GET /api/health`, `GET /api/rag/status` | État du serveur, de Claude et de l'index |

## Dépannage

- **Le backend ne démarre pas / `PoolTimeout` / « failed to resolve host »** : diagnostiquer d'abord le réseau
  (DNS, port 443, port 5432) — certains réseaux bloquent le port 5432 (Postgres) ; tester avec un autre réseau
  (partage de connexion). Neon peut aussi mettre quelques secondes à se réveiller.
- **« Hors ligne » dans l'interface** : vérifier `http://127.0.0.1:8000/api/health`.
- **Réponses génériques de secours** : clé Anthropic absente ou invalide, ou modèle (`ANTHROPIC_MODEL`) retiré.
- **Accents déformés dans la console Windows** (`├®`) : affichage seulement ; corriger avec
  `[Console]::OutputEncoding = $OutputEncoding = [Text.UTF8Encoding]::new()`.
