import os
import re
import json
import base64
import unicodedata
from urllib.parse import urlparse
from typing import Optional
from llama_index.core import VectorStoreIndex, StorageContext, Document, Settings as LlamaSettings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from config import config
from curriculum_data import CURRICULUM
import anthropic

EMBED_DIM = 384  # sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Dossier explicite pour le cache du modèle d'embeddings — SANS ce `cache_folder` explicite,
# HuggingFaceEmbedding retombe sur llama_index.core.utils.get_cache_dir() (/tmp/llama_index),
# alors que le Dockerfile le pré-télécharge dans le cache HuggingFace par défaut (~/.cache/
# huggingface/hub) pour éviter tout accès réseau au démarrage (voir Dockerfile) : les deux
# chemins ne correspondaient pas, donc le conteneur re-téléchargeait (et échouait si le réseau
# sortant était bloqué/instable) à chaque démarrage au lieu d'utiliser le cache déjà présent
# dans l'image. Ce chemin doit rester identique à celui utilisé dans le Dockerfile.
EMBED_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hf_cache")


# Modèles de montages dessinés par le frontend (components/figures/MontageFigure.jsx) : le modèle de
# langage choisit le modèle et remplit les étiquettes, le dessin place lui-même le matériel — bien
# plus fiable que de lui faire positionner chaque pièce de verrerie par coordonnées.
MONTAGE_MODELS = {
    "dosage": ("burette", "becher", "agitateur", "sonde"),
    "electrolyse": ("generateur", "cathode", "anode", "gaz_cathode", "gaz_anode", "solution"),
    "pile": ("electrode_gauche", "solution_gauche", "electrode_droite", "solution_droite", "pont_salin", "appareil"),
    "chauffage_reflux": ("refrigerant", "eau_entree", "eau_sortie", "ballon", "chauffe_ballon"),
    "recueil_gaz": ("reactifs", "tube_degagement", "gaz", "cuve"),
    "combustion": ("gaz", "combustible", "cuillere", "liquide"),
    "tube_essai": ("ajout", "contenu", "observation"),
}

FIGURE_SCHEMAS = """SCHÉMAS DE CHIMIE — un schéma est un objet JSON dont le champ "type" vaut "montage", "graphique", \
"echelle", "molecule" ou "geometrie". Étiquettes en TEXTE SIMPLE, jamais de $ ni de \\ce dans le JSON : formules \
chimiques avec _ pour les indices et ^ pour les charges (H_2O, CO_2, Cu^{2+}, SO_4^{2-}, H_3O^+, CH_3COOH), lettres \
grecques et symboles directement en Unicode (λ, °C) — c'est la seule exception à la règle \\ce, propre au JSON des \
schémas. Étiquettes COURTES (20 caractères au plus). N'inclus une clé facultative que si elle sert au schéma.

1. "montage" — montage de laboratoire DÉJÀ DESSINÉ : choisis le "modele" et remplis seulement les étiquettes utiles \
(une étiquette absente garde son nom générique) :
{"type": "montage", "modele": "dosage", "etiquettes": {"burette": "NaOH 0,10 mol/L", "becher": "HCl + BBT", "sonde": "pH-mètre"}}
Modèles et étiquettes possibles :
- "dosage" : burette, becher, agitateur, sonde (sonde = pH-mètre, dessiné seulement si l'étiquette est donnée) ;
- "electrolyse" (électrolyseur à deux tubes retournés) : generateur, cathode, anode, gaz_cathode, gaz_anode, solution ;
- "pile" (deux demi-piles reliées par un pont salin) : electrode_gauche, solution_gauche, electrode_droite, \
solution_droite, pont_salin, appareil (appareil : "V", "A" ou "lampe" dans le champ "appareil" du schéma) ;
- "chauffage_reflux" : refrigerant, eau_entree, eau_sortie, ballon, chauffe_ballon ;
- "recueil_gaz" (recueil par déplacement d'eau) : reactifs, tube_degagement, gaz, cuve ;
- "combustion" (combustion dans un flacon) : gaz, combustible, cuillere, liquide (liquide, ex. eau de chaux, dessiné \
seulement si l'étiquette est donnée) ;
- "tube_essai" (test d'identification) : ajout, contenu, observation (observation dessinée seulement si donnée).

2. "graphique" — courbe ou mesures avec axes gradués (courbe de dosage, avancement, étalonnage) :
{"type": "graphique",
 "x": {"grandeur": "V_b", "unite": "mL", "min": 0, "max": 20, "pas": 5},
 "y": {"grandeur": "pH", "unite": "", "min": 0, "max": 14, "pas": 2},
 "series": [{"nom": "pH = f(V_b)", "points": [[0, 1.0], [5, 1.2], [9, 1.7], [10, 7.0], [11, 11.7], [15, 12.3], [20, 12.5]], "style": "ligne"}],
 "reperes": [{"axe": "x", "valeur": 10, "label": "V_bE = 10 mL"}],
 "annotations": [{"texte": "E", "position": [10.6, 7]}]}
TOUJOURS une grandeur ET son unité sur chaque axe (unité vide seulement pour le pH). "style" : points (mesures), \
ligne (courbe) ou points+ligne. Pour une courbe de dosage, donne une vingtaine de points calculés avec le saut \
de pH autour de l'équivalence. "reperes" = droite en pointillés (équivalence, demi-équivalence, valeur lue).

3. "echelle" — axe gradué avec zones ou couples :
- horizontale (échelle de pH, diagramme de prédominance) :
{"type": "echelle", "grandeur": "pH", "min": 0, "max": 14,
 "zones": [{"de": 0, "a": 4.8, "label": "CH_3COOH prédomine"}, {"de": 4.8, "a": 14, "label": "CH_3COO^- prédomine"}],
 "reperes": [{"valeur": 4.8, "label": "pK_a = 4,8"}]}
- verticale (classification des couples oxydant/réducteur ou acide/base) : "couples" avec la valeur (E° en V, ou \
pKa) et les deux espèces ; "gauche"/"droite" = titres des colonnes :
{"type": "echelle", "grandeur": "E° (V)", "gauche": "Oxydant", "droite": "Réducteur",
 "couples": [{"valeur": 0.34, "gauche": "Cu^{2+}", "droite": "Cu"}, {"valeur": -0.76, "gauche": "Zn^{2+}", "droite": "Zn"}]}

4. "molecule" — formule développée ou schéma de Lewis (atomes sur une grille, longueur de liaison 1) :
{"type": "molecule", "titre": "Éthanol",
 "atomes": [{"id": "C1", "symbole": "C", "position": [0, 0]}, {"id": "C2", "symbole": "C", "position": [1, 0]},
            {"id": "O", "symbole": "O", "position": [2, 0]}, {"id": "H1", "symbole": "H", "position": [3, 0]},
            {"id": "H2", "symbole": "H", "position": [-1, 0]}, {"id": "H3", "symbole": "H", "position": [0, 1]},
            {"id": "H4", "symbole": "H", "position": [0, -1]}, {"id": "H5", "symbole": "H", "position": [1, 1]},
            {"id": "H6", "symbole": "H", "position": [1, -1]}],
 "liaisons": [{"de": "C1", "vers": "C2"}, {"de": "C2", "vers": "O"}, {"de": "O", "vers": "H1"}, {"de": "C1", "vers": "H2"},
              {"de": "C1", "vers": "H3"}, {"de": "C1", "vers": "H4"}, {"de": "C2", "vers": "H5"}, {"de": "C2", "vers": "H6"}],
 "doublets": [{"atome": "O", "nombre": 2}]}
"ordre" d'une liaison : 1 (défaut), 2 ou 3. Représentation de Cram : "cram": "avant" (coin plein) ou "arriere" \
(coin hachuré), du premier atome vers le second. "doublets" = doublets non liants (schéma de Lewis seulement). \
"symbole" peut être un groupe (CH_3, OH, COOH) pour une formule semi-développée ; "charge" : "+" ou "-". \
Angles réalistes pour la géométrie (positions en zigzag pour une chaîne carbonée si utile).

5. "geometrie" — construction géométrique simple, si aucun type ci-dessus ne convient :
{"type": "geometrie", "points": [{"id": "A", "x": 0, "y": 0}, {"id": "B", "x": 4, "y": 0}],
 "segments": [{"from": "A", "to": "B"}], "labels": [{"text": "4 cm", "x": 2, "y": -0.4}]}
(clés facultatives : "angles" [{"vertex","from","to","right"}], "polygons", "circles" [{"center","radius"}])."""

FIGURE_FORMAT_INSTRUCTIONS = f"""SCHÉMAS — RÈGLE ABSOLUE, PRIORITAIRE SUR TOUT LE RESTE :
Dès qu'un schéma serait utile (montage expérimental, courbe de dosage ou d'avancement, échelle de pH ou de pKa, \
classification de couples, formule développée ou schéma de Lewis), tu DOIS le produire EXCLUSIVEMENT avec un bloc \
de code étiqueté `figure` contenant UN objet JSON valide, placé directement au bon endroit dans ta réponse :
```figure
{{"type": "montage", "modele": "electrolyse", "etiquettes": {{"gaz_cathode": "H_2", "gaz_anode": "O_2"}}}}
```
Une formule ou une équation chimique n'est PAS un schéma : elle s'écrit avec `\\ce{{...}}` (voir règle FORMULES). \
INTERDICTIONS STRICTES, sans AUCUNE exception, même si on te le demande explicitement : jamais de schéma en ASCII art \
(jamais de caractères `|`, `/`, `\\`, `-`, `_`, `+` alignés pour représenter de la verrerie, des liaisons ou des \
courbes), jamais un bloc de code sans l'étiquette `figure`, jamais un pseudo-schéma en LaTeX (`\\begin{{array}}`, \
suites de `\\text{{...}}` reliées par des tirets ou des flèches). Une molécule ou un montage esquissé avec des barres \
et des tirets est un ÉCHEC : utilise TOUJOURS le JSON à la place.

{FIGURE_SCHEMAS}"""

FORMULA_FORMAT_INSTRUCTIONS = """FORMULES CHIMIQUES, ÉQUATIONS ET UNITÉS EN LaTeX — RÈGLE ABSOLUE :
- Toute formule chimique, tout ion et toute équation s'écrit avec la commande `\\ce{...}` (extension mhchem), \
à l'intérieur de `$...$` (en ligne) ou `$$...$$` (isolée) : $\\ce{H2O}$, $\\ce{CO2}$, $\\ce{NaCl}$, $\\ce{Cu^2+}$, \
$\\ce{SO4^2-}$, $\\ce{H3O+}$, $\\ce{HO-}$, $\\ce{CH3-CH2-OH}$, $\\ce{CH3COOH}$. Équation-bilan : \
$\\ce{CH4 + 2O2 -> CO2 + 2H2O}$ ; équilibre : $\\ce{CH3COOH + H2O <=> CH3COO- + H3O+}$ ; états physiques : \
$\\ce{NaCl(s) -> Na+(aq) + Cl-(aq)}$ ; demi-équation électronique : $\\ce{Cu^2+ + 2e- -> Cu}$ ; couple : \
$\\ce{Cu^2+}/\\ce{Cu}$. N'écris JAMAIS une formule en texte brut (H2O, Cu2+, CO_2), ni en Unicode (H₂O, Cu²⁺), ni \
avec `\\mathrm` ou des indices `_` à la place de `\\ce{...}`.
- Toute autre relation, grandeur ou valeur numérique avec son unité s'écrit aussi en LaTeX : $n = \\dfrac{m}{M}$, \
$C = \\dfrac{n}{V}$, $\\mathrm{pH} = -\\log[\\ce{H3O+}]$, $K_a$, $\\mathrm{p}K_a$. L'unité s'écrit en romain avec \
`\\text{}`, séparée de la valeur par une espace fine `\\,`, et la virgule décimale s'écrit `{,}` : \
$18\\,\\text{g/mol}$, $0{,}10\\,\\text{mol/L}$, $24\\,\\text{L/mol}$, $25\\,^{\\circ}\\text{C}$, \
$6{,}02 \\times 10^{23}\\,\\text{mol}^{-1}$."""

CHEMISTRY_RIGOR_INSTRUCTIONS = """RIGUEUR EN CHIMIE — RÈGLE ABSOLUE :
- Une équation-bilan est TOUJOURS équilibrée : conservation des éléments ET des charges. Vérifie-la avant de \
l'écrire ; précise les états physiques ((s), (l), (g), (aq)) quand ils comptent pour le raisonnement.
- Quantité de matière (à partir de la 2nde) : $n = \\dfrac{m}{M}$, $n = C \\times V$, $n = \\dfrac{V}{V_m}$ pour un \
gaz. Utilise les masses molaires atomiques et le volume molaire donnés par l'énoncé ou par le CONTEXTE DOCUMENTAIRE ; \
à défaut, les valeurs usuelles (H : 1 ; C : 12 ; N : 14 ; O : 16 ; Na : 23 ; Cl : 35,5 ; Cu : 63,5 ; Fe : 56 ; en \
g/mol), en signalant que tu les choisis.
- Tout calcul se fait en trois temps : expression littérale, application numérique (valeurs ET unités), résultat \
avec son unité ; convertis d'abord dans les unités utiles (mL en L, g en kg si besoin...) en montrant la conversion. \
Un résultat numérique SANS unité est faux. À partir de la 2nde, respecte les chiffres significatifs.
- Pour une réaction à partir de la 2nde, raisonne avec un tableau d'avancement quand c'est utile (réactif limitant, \
avancement maximal, bilan de matière).
- Nomenclature officielle (UICPA, en français) : éthanol, acide éthanoïque, but-2-ène, 2-méthylpropane... ; en chimie \
organique, donne la formule semi-développée quand elle éclaire la réponse.
- Niveau : en 4ème/3ème, reste au modèle simple (atomes, molécules, ions, équations-bilans) sans parler de mole ; la \
mole, les concentrations et l'avancement apparaissent en 2nde ; pH, $K_a$ et $\\mathrm{p}K_a$ sont détaillés en Tle.
- SÉCURITÉ : quand une expérience est évoquée, rappelle les précautions du laboratoire scolaire (lunettes, gants, \
hotte ou pièce aérée, verser l'acide dans l'eau et jamais l'inverse, ne jamais goûter ni respirer directement un \
produit). Ne donne JAMAIS de mode opératoire pour fabriquer chez soi un produit dangereux (explosif, gaz toxique, \
mélange de produits ménagers comme eau de Javel + acide...) : explique plutôt pourquoi c'est dangereux."""

NO_EMOJI_INSTRUCTIONS = """TON ET MISE EN FORME — RÈGLE ABSOLUE : N'utilise JAMAIS d'emoji ni de pictogramme (aucun symbole \
du type ✅, ⚠️, 💡, 🎉, 👋, 💪, 🧪, 🚀, ✨, etc.), nulle part dans ta réponse, même pour marquer une réussite, un \
conseil ou un encouragement. Marque l'importance uniquement avec la mise en forme Markdown : **gras** pour les \
notions clés, `##`/`###` pour les titres, `>` pour une remarque importante. Écris comme un professeur ou un manuel \
scolaire soigné, jamais comme un assistant conversationnel générique.

TABLEAUX (tableau d'avancement, tableau de mesures, tests d'identification des ions...) : utilise TOUJOURS un vrai \
tableau Markdown (syntaxe standard avec des `|` pour séparer les colonnes ET une ligne `|---|---|` juste sous \
l'en-tête), jamais des tirets ou des espaces alignés à la main pour simuler des colonnes. Exemple pour un tableau \
d'avancement :
| État | Avancement | $n(\\ce{CH4})$ | $n(\\ce{O2})$ | $n(\\ce{CO2})$ | $n(\\ce{H2O})$ |
|---|---|---|---|---|---|
| Initial | $0$ | $n_1$ | $n_2$ | $0$ | $0$ |
| En cours | $x$ | $n_1 - x$ | $n_2 - 2x$ | $x$ | $2x$ |"""

OFF_TOPIC_INSTRUCTIONS = """PORTÉE — RÈGLE ABSOLUE : tu es un professeur de CHIMIE, rien d'autre. Si l'élève pose \
une question qui ne relève pas de la chimie (une autre matière scolaire — y compris la PHYSIQUE et les MATHÉMATIQUES, \
qui ont chacune leur propre assistant Hakili Lab —, la culture générale, l'actualité, des conseils personnels, de \
l'aide en programmation, écrire un texte/une histoire, etc.), décline poliment et brièvement : dis que tu es \
spécialisé en chimie et invite-le à reformuler une question de chimie. Ne réponds JAMAIS à la question hors-sujet \
elle-même, même partiellement, même « pour rendre service ». EXCEPTIONS à cette règle : les salutations, \
remerciements, et questions sur le fonctionnement de l'outil (« comment ça marche ? », « c'est quoi ce site ? ») ne \
sont pas concernées, réponds-y normalement et brièvement. Un outil mathématique utilisé POUR résoudre un problème de \
chimie (proportionnalité, pourcentages, puissances de dix, logarithme du pH...) fait partie de la chimie : aide \
l'élève sur ce calcul. Les questions de sécurité liées aux produits chimiques (intoxication au monoxyde de carbone, \
produits ménagers, brûlures par un acide) relèvent aussi de la chimie. Un exercice de chimie mis en contexte (savon au \
beurre de karité, charbon de bois, gaz butane, engrais, eau du forage...) reste une question de chimie : ce n'est PAS \
hors-sujet, ne le décline surtout pas."""

# Certains modèles récents (dont celui configuré ici) refusent qu'une conversation se termine
# par un tour "assistant" (pas de préremplissage) : la relance automatique en cas de réponse
# tronquée doit donc se terminer par ce message utilisateur plutôt que par le texte déjà généré.
CONTINUE_INSTRUCTION = ("Continue exactement là où tu t'es arrêté ci-dessus, sans rien répéter de ce qui "
                        "précède et sans rien ajouter avant (ni préambule, ni excuse) : je recolle ta "
                        "réponse précédente et cette suite bout à bout.")

# \b \f \r \t sont des échappements JSON valides à part entière, mais dans CE contexte (texte
# scientifique LaTeX) ce sont presque toujours le début d'une commande cassée (\frac, \times,
# \text, \to, \boxed, \begin...), jamais un vrai caractère de contrôle voulu — les
# exclure du jeu "sûr" pour qu'ils soient réparés. \n reste sûr (sauts de ligne très fréquents et
# légitimes dans les solutions), au prix d'un résidu rare (\neq/\nabla cassés seraient mal réparés).
_JSON_VALID_ESCAPE_CHARS = '"\\/nu'


def _repair_latex_json_escapes(text: str) -> str:
    """Double tout backslash qui ne fait pas déjà partie d'un échappement JSON jugé sûr ici (\\",
    \\\\, \\/, \\n, \\uXXXX). Répare les commandes LaTeX (\\vec, \\frac, \\det...) écrites en JSON
    avec un seul backslash au lieu de deux — un backslash simple suivi d'une lettre quelconque
    n'est pas un échappement JSON valide et fait échouer json.loads()."""
    return re.sub(r"\\(.)", lambda m: m.group(0) if m.group(1) in _JSON_VALID_ESCAPE_CHARS else "\\\\" + m.group(1),
                  text, flags=re.DOTALL)


def _loads_model_json(candidate: str):
    """json.loads d'un objet JSON écrit par le modèle, de plus en plus tolérant : tel quel, puis
    échappements LaTeX réparés (voir _repair_latex_json_escapes), puis en acceptant de vrais
    caractères de contrôle (saut de ligne, tabulation) non échappés dans les chaînes — observé sur
    de longs énoncés en Markdown, que json.loads refuse par défaut. None si rien ne passe."""
    repaired = _repair_latex_json_escapes(candidate)
    for text, strict in ((candidate, True), (repaired, True), (repaired, False)):
        try:
            return json.loads(text, strict=strict)
        except json.JSONDecodeError:
            continue
    return None

# Échelle de difficulté des exercices, en étoiles (1 à 5) : le niveau 4 correspond aux
# "situations d'intégration" du programme burkinabè (énoncé contextualisé, plusieurs notions),
# le niveau 5 sort volontairement du programme direct (type olympiades/concours) — voir
# generate_exercise, qui le traite à part (jamais ancré sur les documents de cours déposés :
# aucun contenu de ce type dedans, vérifié).
STAR_DIFFICULTY_LABELS = {
    1: "1 ÉTOILE — QCM D'APPLICATION DIRECTE (questions de cours)",
    2: "2 ÉTOILES — APPLICATION DIRECTE DES DÉFINITIONS, LOIS ET RELATIONS DU COURS (une équation à équilibrer, "
       "une relation à appliquer)",
    3: "3 ÉTOILES — NOTIONS COMBINÉES (plusieurs étapes enchaînées : équation, quantités de matière, bilan... "
       "proche d'une évaluation de classe)",
    4: "4 ÉTOILES — SITUATION D'INTÉGRATION (énoncé contextualisé complexe, plusieurs notions combinées, niveau examen)",
    5: "5 ÉTOILES — TYPE OLYMPIADES (problème de concours : astuce ou idée non standard, hors du cadre direct du "
       "programme, difficulté nettement au-dessus d'une situation d'intégration)",
}


class RAGSystem:
    def __init__(self):
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            cache_folder=EMBED_CACHE_DIR,
        )
        LlamaSettings.embed_model = self.embed_model

        # Configuration Anthropic Claude
        self.anthropic_api_key = config.ANTHROPIC_API_KEY
        self.anthropic_model = config.ANTHROPIC_MODEL
        self.anthropic_client = None
        # `claude-sonnet-5` rejette `temperature` ("deprecated for this model") — détecté au premier
        # appel (voir _create_message/_stream_claude) puis mémorisé ici pour éviter de retenter à
        # chaque appel un paramètre qu'on sait déjà refusé par le modèle configuré.
        self._temperature_supported = True
        if self.anthropic_api_key:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
                print(f"[OK] Anthropic Claude API configuree avec le modele {self.anthropic_model}")
            except Exception as e:
                print(f"[WARN] Erreur initialisation Anthropic: {e}")
        else:
            print("[WARN] ANTHROPIC_API_KEY manquante : le mode local degrade sera utilise.")

        # Embeddings stockés à part (Postgres + pgvector, ex. Neon), pas embarqués dans le
        # déploiement : voir DEPLOY.md::DATABASE_URL. `psql_url` parsée une fois ici, réutilisée
        # par from_params() (host/port/... séparés, pas juste connection_string) : c'est ce qui
        # laisse from_params() construire à la fois l'URL sync (psycopg2) ET async (asyncpg)
        # requises par PGVectorStore, sans les construire à la main.
        url = urlparse(config.DATABASE_URL)
        self._pg_params = dict(
            host=url.hostname,
            port=str(url.port or 5432),
            database=url.path.lstrip("/"),
            user=url.username,
            password=url.password,
        )
        self.table_name = config.VECTOR_TABLE_NAME
        self.index = None
        self.storage_context = None

    def _create_vector_store(self):
        return PGVectorStore.from_params(
            **self._pg_params,
            table_name=self.table_name,
            embed_dim=EMBED_DIM,
        )

    def _build_index(self, vector_store):
        self.storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.embed_model
        )

    def _reset_store(self):
        """Supprime la table d'embeddings pour la reconstruire de zéro (voir ingest_documents.py).
        PGVectorStore préfixe le nom de table donné par "data_" pour la vraie table SQL — vérifié
        empiriquement (pas documenté), ce préfixe est stable tant qu'on ne change pas de version
        du connecteur."""
        import psycopg
        with psycopg.connect(config.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "data_{self.table_name}"')
            conn.commit()

    def initialize_vector_store(self):
        try:
            vector_store = self._create_vector_store()
            self._build_index(vector_store)
            print("Vector store loaded successfully")
        except Exception as e:
            print(f"Existing vector store is incompatible, resetting it: {e}")
            self._reset_store()
            vector_store = self._create_vector_store()
            self._build_index(vector_store)
            print("Vector store initialized")

    def add_documents(self, documents, metadata=None):
        if metadata is None:
            metadata = {}

        docs = []
        for doc in documents:
            doc_metadata = metadata.copy()
            if isinstance(doc, dict):
                docs.append(Document(
                    text=doc.get("text", ""),
                    metadata=doc.get("metadata", doc_metadata)
                ))
            else:
                docs.append(Document(text=doc, metadata=doc_metadata))

        splitter = SentenceSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP
        )

        for doc in docs:
            nodes = splitter.get_nodes_from_documents([doc])
            self.index.insert_nodes(nodes)

        print(f"Added {len(docs)} documents to vector store")

    @staticmethod
    def _exact_filter(key: str, value: str) -> ExactMatchFilter:
        """Construit un ExactMatchFilter sûr pour du texte contenant une apostrophe (ex: chapitre
        "Racine carrée d'un nombre réel positif"). llama-index-vector-stores-postgres construit le
        WHERE en interpolant la valeur brute dans du SQL littéral (`f"'{filter_.value}'"`, voir
        _build_filter_clause dans postgres/base.py) sans l'échapper : une apostrophe non doublée y
        casse la requête (psycopg2.errors.SyntaxError), faisant silencieusement échouer le filtre
        exact et retomber sur des correspondances moins fiables (repli par nom de fichier, voire
        aucun résultat — "Voir le cours" 404 sur ces chapitres). Doubler l'apostrophe est l'échappement
        SQL standard d'un littéral, sans changer la valeur réellement comparée."""
        return ExactMatchFilter(key=key, value=value.replace("'", "''"))

    def _retrieve_with_filters(self, question, filters, top_k):
        metadata_filters = MetadataFilters(filters=filters) if filters else None
        retriever = self.index.as_retriever(
            similarity_top_k=top_k,
            filters=metadata_filters
        )
        return retriever.retrieve(question)

    def query(self, question, class_level=None, chapter=None, top_k=None):
        if top_k is None:
            top_k = config.TOP_K

        exact_filters = []
        if class_level:
            exact_filters.append(self._exact_filter("class", class_level))
        if chapter:
            exact_filters.append(self._exact_filter("chapter", chapter))

        nodes = self._retrieve_with_filters(question, exact_filters, top_k)
        if nodes or not (class_level and chapter):
            return nodes

        # Les documents importes depuis des exports ZIP/Drive n'ont pas toujours un
        # libelle de chapitre identique au curriculum. On garde alors la classe, mais
        # on relache le filtre chapitre pour ne pas ignorer les manuels disponibles.
        class_only_filters = [self._exact_filter("class", class_level)]
        return self._retrieve_with_filters(question, class_only_filters, top_k)

    def find_course_file_from_index(self, class_level: str, chapter: str) -> Optional[str]:
        """Cherche un document de cours via un filtre EXACT classe+chapitre dans l'index vectoriel,
        plutôt que par correspondance de noms de fichiers (voir document_processor.find_course_file).
        Fiable — contrairement à une recherche par similarité — car il s'agit d'une égalité stricte
        sur les métadonnées : ne peut renvoyer un document que si l'ingestion l'a explicitement classé
        sous ce couple (classe, chapitre) exact, ce qu'elle fait désormais en lisant le CONTENU des
        documents (voir ingest_documents.py::classify_chapter_from_content), pas leur nom de fichier."""
        try:
            nodes = self._retrieve_with_filters(
                chapter,
                [self._exact_filter("class", class_level), self._exact_filter("chapter", chapter)],
                top_k=1,
            )
        except Exception as e:
            print(f"[WARN] Recherche du cours dans l'index echouee: {e}")
            return None
        if not nodes:
            return None
        source = nodes[0].metadata.get("source")
        return source if source and os.path.isfile(source) else None

    def collection_count(self):
        try:
            import psycopg
            # Délai borné : /api/health appelle cette méthode à chaque fois, et ne doit jamais
            # rester bloqué sur une connexion lente ou un port 5432 filtré.
            with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT COUNT(*) FROM "data_{self.table_name}"')
                    return cur.fetchone()[0]
        except Exception as e:
            print(f"Postgres count failed: {e}")
            return 0

    # ========================================================================
    # APPEL CLAUDE (support multi-tours)
    # ========================================================================

    def _create_message(self, system_prompt: str, messages: list, max_tokens: int, temperature: float,
                         tools: list = None):
        """Un seul appel bas niveau à l'API Messages, avec repli si le modèle rejette `temperature`.

        `temperature` passe par `extra_body` plutôt qu'en paramètre nommé direct : le SDK anthropic
        (>=1.x) a retiré `temperature` de la signature typée de `create()`/`stream()`, ce qui lève un
        TypeError côté client avant même la requête HTTP — `extra_body` la transmet telle quelle à
        l'API, qui répond alors par un vrai BadRequestError si le modèle la refuse, rattrapable ici."""
        kwargs = {
            "model": self.anthropic_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if self._temperature_supported:
            kwargs["extra_body"] = {"temperature": temperature}
        try:
            return self.anthropic_client.messages.create(**kwargs)
        except anthropic.BadRequestError as e:
            # Certains modèles récents (ex: reasoning models) rejettent un temperature
            # personnalisé. On retente sans ce paramètre plutôt que de tout faire échouer.
            if "temperature" in str(e).lower():
                self._temperature_supported = False
                kwargs.pop("extra_body", None)
                return self.anthropic_client.messages.create(**kwargs)
            raise

    @staticmethod
    def _extract_text(response) -> str:
        text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                text += block.text
            elif isinstance(block, dict) and 'text' in block:
                text += block['text']
        return text

    def _call_claude(self, system_prompt: str, messages: list, max_tokens: int = 1024,
                      temperature: float = None, tools: list = None) -> str:
        """Appelle l'API Claude d'Anthropic avec un historique de messages et retourne le texte.

        Si la réponse est coupée par la limite de tokens (stop_reason == "max_tokens"), relance
        automatiquement la génération (en lui redonnant le texte déjà produit et en lui demandant
        de continuer directement à la suite) pour que l'élève reçoive toujours une réponse complète."""
        if not self.anthropic_client:
            print("[WARN] Anthropic client non initialise (cle API manquante ?)")
            return None

        temp = temperature if temperature is not None else config.ANTHROPIC_TEMPERATURE
        try:
            current_messages = list(messages)
            accumulated = ""
            for attempt in range(config.MAX_AUTO_CONTINUATIONS + 1):
                response = self._create_message(system_prompt, current_messages, max_tokens, temp, tools=tools)
                accumulated += self._extract_text(response)

                if response.stop_reason == "max_tokens" and attempt < config.MAX_AUTO_CONTINUATIONS:
                    if accumulated.strip():
                        # Reponse partielle : on demande de continuer directement a la suite.
                        current_messages = list(messages) + [
                            {"role": "assistant", "content": accumulated},
                            {"role": "user", "content": CONTINUE_INSTRUCTION},
                        ]
                    else:
                        # Le budget de tokens a ete integralement consomme par le raisonnement
                        # interne du modele (frequent sur les exercices complexes/schemas
                        # detailles), sans laisser une seule reponse textuelle : impossible de
                        # "continuer" un tour assistant vide (l'API le refuse), donc on relance la
                        # meme requete depuis le debut plutot que d'abandonner silencieusement.
                        current_messages = list(messages)
                    continue
                break

            return accumulated.strip() if accumulated.strip() else None

        except anthropic.APIError as e:
            print(f"[ERREUR] API Anthropic: {e}")
            return None
        except anthropic.RateLimitError as e:
            print(f"[ERREUR] Rate limit Anthropic: {e}")
            return None
        except Exception as e:
            print(f"[ERREUR] Anthropic: {e}")
            return None

    def _verify_qcm_batch(self, class_level: str, chapter: Optional[str], qcm_items: list) -> list:
        """Filet de sécurité contre une réponse marquée correcte à tort : les parseurs JSON
        (_parse_exercise_json, _parse_prerequis_json) ne valident QUE la forme d'un QCM généré
        (4 choix, un index entre 0 et 3), jamais si cet index pointe VRAIMENT vers la bonne
        réponse — un exercice de chimie qui affirme une mauvaise réponse avec la même assurance
        qu'une bonne est le pire scénario pour un tuteur (l'élève apprend l'erreur en confiance).

        Un second appel Claude, dédié UNIQUEMENT à la relecture (température 0, pas de rédaction
        de question), résout chaque question lui-même puis confirme ou corrige l'index — un seul
        appel pour tout le lot plutôt qu'un par question, pour ne pas multiplier la latence. En
        cas d'échec (API indisponible, JSON non parsable...), on sert le lot ORIGINAL tel quel :
        mieux vaut un exercice non revérifié qu'aucun exercice — ce n'est qu'un filet de sécurité
        additionnel, pas une condition pour servir une réponse."""
        if not qcm_items:
            return qcm_items

        try:
            payload = json.dumps(
                [
                    {"index": i, "question": it["question"], "choix": it["choix"],
                     "reponse_marquee": it["reponse_correcte_index"]}
                    for i, it in enumerate(qcm_items)
                ],
                ensure_ascii=False,
            )
            system_prompt = f"""Tu es un correcteur de chimie rigoureux, pas un rédacteur. On te \
soumet une liste de questions à choix multiples de niveau {class_level}{f" ({chapter})" if chapter else ""}, \
chacune avec l'index (0 à 3) actuellement marqué comme la bonne réponse. Pour CHAQUE question, résous-la \
intégralement par toi-même AVANT de comparer au marquage — ne te contente jamais de faire confiance à \
"reponse_marquee". Vérifie en particulier l'équilibrage des équations (éléments ET charges), les formules et les \
charges des ions, les masses molaires et l'unité de chaque choix : un choix numériquement juste mais avec une \
mauvaise unité, ou une équation mal équilibrée, est FAUX.

QUESTIONS :
{payload}

Réponds UNIQUEMENT avec un objet JSON (aucun texte avant/après, pas de bloc de code) : \
{{"verdicts": [{{"index": 0, "reponse_correcte_index": 0}}, ...]}} — un verdict par question, dans n'importe \
quel ordre (identifié par "index"), où "reponse_correcte_index" est TOUJOURS le bon index selon TA propre \
résolution, que le marquage initial soit juste ou faux."""

            response = self._call_claude(
                system_prompt, [{"role": "user", "content": "Vérifie ces questions."}],
                max_tokens=config.MAX_TOKENS_QCM_VERIFICATION, temperature=0,
            )
            if not response:
                return qcm_items

            text = response.strip()
            text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
            start, end = text.find("{"), text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return qcm_items
            data = json.loads(text[start:end + 1])

            verdicts = data.get("verdicts")
            if not isinstance(verdicts, list):
                return qcm_items

            corrected = list(qcm_items)
            for verdict in verdicts:
                if not isinstance(verdict, dict):
                    continue
                i = verdict.get("index")
                idx = verdict.get("reponse_correcte_index")
                if not isinstance(i, int) or not (0 <= i < len(corrected)):
                    continue
                if not isinstance(idx, int) or not (0 <= idx < len(corrected[i]["choix"])):
                    continue
                if idx != corrected[i]["reponse_correcte_index"]:
                    print(f"[INFO] Vérification QCM : correction {corrected[i]['reponse_correcte_index']} -> "
                          f"{idx} pour « {corrected[i]['question'][:60]}... »")
                    corrected[i] = {**corrected[i], "reponse_correcte_index": idx}
            return corrected
        except Exception as e:
            print(f"[WARN] Vérification QCM échouée, réponse originale conservée: {e}")
            return qcm_items

    def _stream_claude(self, system_prompt: str, messages: list, max_tokens: int = 1024,
                        temperature: float = None):
        """Version streaming de `_call_claude` : yield des fragments de texte au fur et à mesure,
        avec la même logique de continuation automatique si la réponse est tronquée."""
        if not self.anthropic_client:
            return

        temp = temperature if temperature is not None else config.ANTHROPIC_TEMPERATURE
        current_messages = list(messages)
        accumulated = ""

        for attempt in range(config.MAX_AUTO_CONTINUATIONS + 1):
            stop_reason = None

            # `messages.stream(...)` ne fait la requête HTTP qu'à l'entrée du context manager
            # (__enter__), donc le repli "sans temperature" doit être tenté à ce moment-là,
            # pas au moment de la simple construction de l'objet stream. Voir _create_message pour
            # pourquoi `temperature` passe par `extra_body` plutôt qu'en paramètre nommé direct.
            stream_kwargs = {
                "model": self.anthropic_model, "max_tokens": max_tokens,
                "system": system_prompt, "messages": current_messages,
            }
            if self._temperature_supported:
                stream_kwargs["extra_body"] = {"temperature": temp}
            stream_ctx = self.anthropic_client.messages.stream(**stream_kwargs)
            try:
                stream = stream_ctx.__enter__()
            except anthropic.BadRequestError as e:
                if "temperature" not in str(e).lower():
                    raise
                self._temperature_supported = False
                stream_kwargs.pop("extra_body", None)
                stream_ctx = self.anthropic_client.messages.stream(**stream_kwargs)
                stream = stream_ctx.__enter__()

            try:
                for text in stream.text_stream:
                    accumulated += text
                    yield text
                stop_reason = stream.get_final_message().stop_reason
            finally:
                stream_ctx.__exit__(None, None, None)

            if stop_reason == "max_tokens" and attempt < config.MAX_AUTO_CONTINUATIONS:
                if accumulated.strip():
                    current_messages = list(messages) + [
                        {"role": "assistant", "content": accumulated},
                        {"role": "user", "content": CONTINUE_INSTRUCTION},
                    ]
                else:
                    # Meme cas que dans _call_claude : rien de textuel produit du tout (budget
                    # entierement consomme par le raisonnement interne) — on relance depuis zero.
                    current_messages = list(messages)
                continue
            break

    @staticmethod
    def _build_history_messages(history: list, current_user_message: str) -> list:
        """Convertit l'historique frontend ([{role, content}, ...]) en messages Anthropic,
        tronque aux N derniers échanges et ajoute le message courant."""
        messages = []
        if history:
            max_messages = config.HISTORY_MAX_TURNS * 2
            trimmed = history[-max_messages:]
            for turn in trimmed:
                role = turn.get("role")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": current_user_message})
        return messages

    # ========================================================================
    # GÉNÉRATION DE RÉPONSES (chat)
    # ========================================================================

    def generate_response(self, question, class_level, chapter, history=None):
        """Génère une réponse pédagogique via Claude + RAG, avec mémoire de conversation."""
        try:
            context = ""
            sources = []

            try:
                nodes = self.query(question, class_level, chapter)
                if nodes:
                    context = "\n".join([node.get_content()[:500] for node in nodes])
                    sources = [node.metadata for node in nodes]
            except Exception as e:
                print(f"RAG retrieval failed: {e}")

            answer = self._generate_with_claude(question, context, class_level, chapter, history)

            return {
                "answer": answer,
                "sources": sources,
                "from_rag": len(sources) > 0
            }
        except Exception as e:
            print(f"Error generating response: {e}")
            return {
                "answer": f"Une erreur s'est produite. Erreur: {str(e)}",
                "sources": [],
                "from_rag": False,
                "error": str(e)
            }

    def _build_chat_prompt(self, question, context, class_level, chapter):
        """Construit (system_prompt, user_message) pour une question de chat.
        Partagé entre la génération classique et la génération en streaming."""

        classe_txt = class_level if class_level else \
            "non précisée par l'élève — déduis un niveau de langage raisonnable à partir de la question elle-même"
        chapitre_txt = chapter if chapter else \
            "non précisé par l'élève — identifie toi-même le thème de chimie concerné"

        if chapter:
            # Le chapitre sélectionné dans la barre latérale est un CONTEXTE, pas une contrainte :
            # une question hors-sujet mais toujours de chimie doit recevoir une vraie réponse,
            # pas une tentative forcée de rattachement à ce chapitre (source de réponses confuses
            # et lentes, le modèle passant du temps à chercher un lien qui n'existe pas).
            mission = (
                f"Aider un élève {f'de {class_level} ' if class_level else ''}à réellement comprendre ses "
                f"questions de chimie, pas seulement lui donner un résultat. Il suit actuellement le "
                f"chapitre « {chapter} », mais si sa question porte sur un tout autre sujet, réponds quand "
                "même complètement à SA question réelle, sans essayer de forcer artificiellement un lien "
                f"avec « {chapter} »."
            )
        elif class_level:
            mission = (
                f"Aider un élève de {class_level} à réellement comprendre sa question de chimie, "
                "pas seulement lui donner un résultat."
            )
        else:
            mission = (
                "Aider un élève du Burkina Faso à réellement comprendre sa question de chimie, "
                "pas seulement lui donner un résultat, même s'il n'a pas précisé sa classe ni son chapitre."
            )

        system_prompt = f"""Tu es « Prof Karim », un professeur de chimie expérimenté et bienveillant, \
expert du programme officiel du Burkina Faso (de la 4ème à la Terminale D).

MISSION
{mission}

{OFF_TOPIC_INSTRUCTIONS}

{FIGURE_FORMAT_INSTRUCTIONS}

{NO_EMOJI_INSTRUCTIONS}

RÈGLES À SUIVRE ABSOLUMENT :
1. Utilise en priorité le CONTEXTE DOCUMENTAIRE fourni ci-dessous (extraits de manuels officiels). S'il est vide ou \
insuffisant, réponds quand même avec tes connaissances solides en chimie (sauf si la question est hors-sujet, \
voir la règle de PORTÉE ci-dessus). NE DIS JAMAIS que tu ne peux pas répondre à une question de chimie.
2. N'invente jamais un fait, une source précise (page, numéro) que tu ne peux pas justifier avec le contexte fourni.
3. Adapte le niveau de langue et la profondeur des explications à la classe : {classe_txt} \
(vocabulaire simple, observations et expériences concrètes en 4ème/3ème ; quantités de matière et tableau \
d'avancement à partir de la 2nde ; formalisme rigoureux — $K_a$, $\\mathrm{{p}}K_a$, mécanismes de chimie organique \
du programme — en Terminale).
4. Structure TOUJOURS ta réponse en Markdown clair : titres courts avec ##, **gras** sur les notions clés, \
listes numérotées pour les étapes de résolution.
5. Applique strictement les règles FORMULES CHIMIQUES et RIGUEUR EN CHIMIE ci-dessous dans toute ta réponse.
6. Si l'élève demande d'expliquer une notion, une loi ou une réaction (question de cours), explique-la normalement : \
définition précise, équation-bilan quand il y a une réaction, signification de chaque grandeur avec son unité, puis \
un exemple chiffré complet et entièrement résolu. Quand c'est utile, décris l'expérience qui met la notion en \
évidence (matériel, observations, interprétation) avec ses précautions de sécurité. En revanche, si l'élève te soumet SON PROPRE exercice ou calcul à résoudre, \
NE DONNE PAS directement le résultat final : rappelle la méthode/formule à utiliser, détaille la première étape, \
donne une piste sur la suivante, puis invite-le à continuer et à te dire où il en est. Donne la résolution \
complète, étape par étape jusqu'au résultat, UNIQUEMENT si l'élève la demande explicitement (« donne-moi la \
solution », « corrige mon calcul », « je suis bloqué, montre-moi », « je ne trouve pas »), ou s'il te montre déjà \
sa propre tentative et te demande de la vérifier.
7. Illustre avec un exemple concret et réaliste du quotidien burkinabè (savon au beurre de karité, charbon de bois \
et foyers améliorés, gaz butane, eau de Javel, engrais, rouille des tôles, piles et batteries, eau du forage...) \
quand c'est pertinent pour la notion.
8. Termine ta réponse par une courte question de compréhension ou une invitation à s'entraîner \
(« Essaie maintenant avec... », « Est-ce plus clair ou veux-tu un autre exemple ? »).
9. Si un historique de conversation est fourni, reste parfaitement cohérent avec les échanges précédents.
10. Reste toujours encourageant et bienveillant, jamais condescendant.

{FORMULA_FORMAT_INSTRUCTIONS}

{CHEMISTRY_RIGOR_INSTRUCTIONS}

CONTEXTE DOCUMENTAIRE (programme officiel burkinabè, peut être vide) :
{context if context else "(Aucun document indexé pour ce chapitre — appuie-toi sur tes connaissances.)"}
"""

        user_message = f"""Chapitre : {chapitre_txt}
Classe : {classe_txt}

Question de l'élève : {question}"""

        return system_prompt, user_message

    def _generate_with_claude(self, question, context, class_level, chapter, history=None):
        """Utilise Claude pour générer une réponse pédagogique de qualité, avec contexte RAG et historique.
        class_level et chapter peuvent être vides : l'élève a le droit de poser une question sans les préciser."""

        system_prompt, user_message = self._build_chat_prompt(question, context, class_level, chapter)
        messages = self._build_history_messages(history, user_message)
        response = self._call_claude(system_prompt, messages, max_tokens=config.MAX_TOKENS_CHAT)
        if response:
            return response

        print("[WARN] Claude indisponible, utilisation du fallback local...")
        return self._generate_local_response(question, class_level, chapter, context)

    def generate_response_stream(self, question, class_level, chapter, history=None):
        """Génère la réponse en streaming : yield des dicts d'événements.
        {"delta": "..."} pour chaque fragment de texte, puis un événement final
        {"done": True, "sources": [...], "from_rag": bool} une fois la génération terminée."""
        context = ""
        sources = []

        try:
            nodes = self.query(question, class_level, chapter)
            if nodes:
                context = "\n".join([node.get_content()[:500] for node in nodes])
                sources = [node.metadata for node in nodes]
        except Exception as e:
            print(f"RAG retrieval failed: {e}")

        system_prompt, user_message = self._build_chat_prompt(question, context, class_level, chapter)
        messages = self._build_history_messages(history, user_message)

        got_any = False
        if self.anthropic_client:
            try:
                for chunk in self._stream_claude(system_prompt, messages, max_tokens=config.MAX_TOKENS_CHAT):
                    if chunk:
                        got_any = True
                        yield {"delta": chunk}
            except Exception as e:
                print(f"[ERREUR] streaming Claude: {e}")

        if not got_any:
            print("[WARN] Claude indisponible, utilisation du fallback local...")
            text = self._generate_local_response(question, class_level, chapter, context)
            yield {"delta": text}

        yield {"done": True, "sources": sources, "from_rag": len(sources) > 0}

    # ========================================================================
    # SIMPLIFICATION
    # ========================================================================

    def simplify_answer(self, question: str, original_answer: str, class_level: str, chapter: str = "") -> str:
        """Utilise Claude pour reformuler une réponse de façon nettement plus simple."""

        system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. \
Un élève de {class_level} n'a PAS compris ta première explication sur « {chapter or "ce chapitre"} ». \
Tu dois RÉEXPLIQUER, pas répéter.

RÈGLES :
- N'utilise PAS les mêmes phrases ni le même ordre que l'explication originale : change vraiment d'angle.
- Utilise des mots TRÈS SIMPLES, comme si tu parlais à un enfant de 10-12 ans, quelle que soit la classe réelle.
- Donne un exemple concret et imagé du quotidien au Burkina Faso (cuisine, feu de bois, savon, marché, etc.) ; \
une image simple aide souvent (les atomes comme des briques qu'on réassemble sans en perdre aucune).
- Sois chaleureux et rassurant : commence par une phrase du type « Pas de souci, on reprend autrement. »
- Découpe en 2 à 4 étapes très courtes, une idée par étape.
- Formules en LaTeX si nécessaire, mais garde-les minimales : formules chimiques avec `\\ce{{...}}` \
(ex : $\\ce{{H2O}}$), chaque valeur avec son unité (ex : $18\\,\\text{{g/mol}}$).
- Termine par une phrase d'encouragement.

{NO_EMOJI_INSTRUCTIONS}
"""

        user_message = f"""Question initiale de l'élève : {question or "(non précisée)"}

Explication originale à simplifier :
{original_answer[:1500]}

Réécris cette explication de façon beaucoup plus simple et différente dans la formulation :"""

        response = self._call_claude(system_prompt, [{"role": "user", "content": user_message}],
                                      max_tokens=config.MAX_TOKENS_SIMPLIFY)
        if response:
            return response

        return self._local_simplify(question, original_answer, class_level)

    # ========================================================================
    # PHOTO D'EXERCICE (vision Claude : explication + correction à partir d'une image)
    # ========================================================================

    def explain_exercise_photo(self, file_bytes: bytes, media_type: str, class_level: str = "",
                                chapter: str = "", user_prompt: str = "", history: list = None) -> str:
        """Analyse la photo (ou le PDF scanné) d'un exercice envoyé par l'élève et renvoie la
        méthode à suivre puis la correction détaillée. Claude lit le fichier directement (vision
        pour une image, lecture native pour un PDF) : plus fiable qu'un OCR classique pour des
        notations scientifiques (formules, équations, unités). `chapter` est le chapitre actuellement suivi dans la discussion,
        pas nécessairement celui de l'exercice photographié (l'élève peut envoyer une photo sans
        rapport avec la discussion en cours) : c'est un indice, jamais une contrainte."""
        classe_txt = f"un élève de {class_level}" if class_level else "un élève"
        chapitre_txt = (
            f" Il suit actuellement le chapitre « {chapter} », mais l'exercice photographié peut "
            "porter sur un tout autre sujet : identifie le VRAI sujet à partir du document, sans "
            f"te forcer à le rattacher à « {chapter} »."
            if chapter else ""
        )
        support_txt = "le PDF" if media_type == "application/pdf" else "la photo"
        is_followup = bool(history)
        followup_txt = (
            "\n8. Un historique de conversation est fourni ci-dessous : l'élève continue à te parler du "
            "MÊME exercice, déjà présenté plus haut dans l'échange (l'image jointe à ce message est "
            "TOUJOURS celle de cet exercice). Ne redemande pas de recopier l'énoncé ni de le renvoyer : "
            "réponds directement à sa nouvelle question, en te basant sur l'image et sur ce qui a déjà été dit."
            if is_followup else ""
        )

        system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso, expert du \
programme officiel (de la 4ème à la Terminale D). Un élève t'envoie {support_txt} d'un exercice de chimie \
(papier, manuscrit ou imprimé) et attend ton aide.

MISSION
1. Identifie précisément l'énoncé de l'exercice à partir du document fourni (recopie-le brièvement \
pour confirmer à l'élève que tu l'as bien lu, y compris s'il est manuscrit ou de mauvaise qualité).
2. Si le document est illisible, flou, ou ne contient pas d'exercice de chimie exploitable, dis-le \
clairement et demande un envoi plus net plutôt que d'inventer un énoncé.
3. Explique la méthode à suivre (quelle notion, quelle réaction, quelle relation, quelles conversions) pour cet \
exercice précis. Relève les données de l'énoncé avec leurs unités.
4. NE DONNE PAS directement la correction complète et le résultat final de cet exercice. Donne des pistes \
progressives : détaille la première étape à faire, ce qu'il faut calculer ou chercher, un point de vigilance \
fréquent sur ce type d'exercice (souvent une équation mal équilibrée, une charge d'ion oubliée ou une conversion \
de volume) — juste assez pour que l'élève puisse continuer seul. Termine en l'invitant à \
essayer et à te dire où il en est (son résultat, ou l'étape où il bloque).
5. EXCEPTION à la règle 4 : donne la correction complète, détaillée étape par étape jusqu'au résultat, si (a) \
l'élève le demande explicitement (« donne-moi la solution/correction/réponse », « je suis bloqué, montre-moi »), \
ou (b) il te montre sa propre tentative/son résultat et te demande de vérifier — dans ce cas corrige-le en \
détail, en indiquant précisément où est l'erreur s'il y en a une.
6. Si l'élève a ajouté une consigne ou une question précise avec son envoi, réponds D'ABORD à cette \
demande précise (ex: "seulement la question 2", "vérifie juste mon calcul") plutôt qu'à tout l'exercice — \
sauf si cette consigne est elle-même hors-sujet (voir la règle de PORTÉE ci-dessous), auquel cas décline-la \
et contente-toi d'aider sur l'exercice de chimie photographié.
7. Adapte le niveau de langue à {classe_txt}.{chapitre_txt}{followup_txt}

{OFF_TOPIC_INSTRUCTIONS}

{FIGURE_FORMAT_INSTRUCTIONS}

{NO_EMOJI_INSTRUCTIONS}

RÈGLES DE MISE EN FORME :
- Structure en Markdown clair : ## pour les titres courts, **gras** pour les notions clés.
- Applique les règles FORMULES CHIMIQUES et RIGUEUR EN CHIMIE ci-dessous.
- Termine par une courte question de compréhension ou une invitation à s'entraîner sur un exercice similaire.

{FORMULA_FORMAT_INSTRUCTIONS}

{CHEMISTRY_RIGOR_INSTRUCTIONS}
"""

        # PDF : bloc "document" (lu nativement par Claude, page par page). Image : bloc "image" (vision).
        file_block = (
            {"type": "document", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.b64encode(file_bytes).decode("ascii")}}
            if media_type == "application/pdf"
            else {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                               "data": base64.b64encode(file_bytes).decode("ascii")}}
        )
        if is_followup:
            instruction_txt = user_prompt.strip() if user_prompt and user_prompt.strip() else \
                "Continue à m'aider sur ce même exercice."
        else:
            instruction_txt = (
                f"Voici {support_txt} de mon exercice de chimie. {user_prompt.strip()}"
                if user_prompt and user_prompt.strip()
                else f"Voici {support_txt} de mon exercice de chimie. Aide-moi à le résoudre : "
                     "explique-moi la méthode et guide-moi pas à pas."
            )
        user_content = [
            file_block,
            {"type": "text", "text": instruction_txt},
        ]

        # Les échanges précédents sur ce même exercice (voir le paramètre `history`) : sans ça,
        # Claude ne verrait l'image qu'une seule fois et "l'oublierait" dès la question suivante,
        # incapable de répondre à un simple "résous la question a" sur la même photo.
        messages = []
        if history:
            max_messages = config.HISTORY_MAX_TURNS * 2
            for turn in history[-max_messages:]:
                role = turn.get("role")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_content})

        response = self._call_claude(
            system_prompt,
            messages,
            max_tokens=config.MAX_TOKENS_EXERCISE_PHOTO,
        )
        if response:
            return response

        return ("Je n'arrive pas à analyser ce fichier pour le moment. Réessaie avec une photo plus nette, "
                "bien cadrée sur l'exercice, ou recopie l'énoncé directement dans le chat.")

    # ========================================================================
    # PRÉREQUIS (QCM diagnostique sur les notions ANTÉRIEURES nécessaires à ce chapitre)
    # ========================================================================

    def generate_prerequis(self, class_level: str, chapter: str, history: list = None) -> list:
        """Identifie les notions prérequises indispensables pour aborder ce chapitre (vues dans des
        chapitres ANTÉRIEURS, pas le chapitre lui-même) et renvoie, pour chacune, un court RAPPEL de
        cours (ce que l'élève doit déjà savoir) suivi de 1 à 2 exercices diagnostiques — jamais l'inverse :
        l'élève doit pouvoir relire la notion avant de s'y confronter, pas deviner à l'aveugle puis
        recevoir une correction. Renvoie une liste de groupes {notion, rappel, exercices} (voir
        _parse_prerequis_json), PAS une liste plate de questions.
        Les manuels de chimie Hakili Lab n'ont pas de ligne « Prérequis : ... », mais chaque chapitre
        (vérifié sur les 45 PDF) ouvre sur une section « CE QUE TU DOIS DEJA SAVOIR » : exercices
        P1, P2... puis un tableau « savoir-faire (Pn) / rappel ». Le bloc de retrieval ci-dessous cible
        cette section plutôt que le contenu général du chapitre ; à défaut, le modèle déduit les
        prérequis du programme des chapitres antérieurs. Si l'élève a posé des questions récentes, elles pèsent sur QUELLES notions méritent
        2 exercices plutôt qu'un seul, pas sur le fait de tester le chapitre en cours (voir
        _local_prerequis pour le repli si Claude est indisponible)."""

        recent_questions = [
            turn.get("content", "").strip()
            for turn in (history or [])
            if turn.get("role") == "user" and turn.get("content", "").strip()
        ][-6:]

        if recent_questions:
            context_block = (
                "L'élève a récemment posé ces questions dans sa conversation (ordre chronologique) :\n"
                + "\n".join(f'- « {q} »' for q in recent_questions) +
                "\n\nCONSIGNE IMPORTANTE : si l'une de ces questions touche déjà une notion prérequise "
                "de ce chapitre, prévois 2 exercices diagnostiques pour celle-là plutôt qu'un seul "
                "(elle mérite d'être vérifiée plus en profondeur) ; un exercice suffit pour les autres."
            )
        else:
            context_block = ("L'élève n'a pas encore posé de question précise : répartis les exercices "
                              "de façon équilibrée entre les notions prérequises identifiées.")

        # Ce qui a DÉJÀ été vu : les chapitres antérieurs de cette classe (numérotés comme dans les
        # manuels, à partir de 1) et le programme de chimie des classes précédentes.
        previous_chapters_block = ""
        chapters_list = CURRICULUM.get(class_level, {}).get("chapters", [])
        if chapter in chapters_list:
            idx = chapters_list.index(chapter)
            if idx > 0:
                previous_chapters_block = "\n".join(f"Ch. {i} — {c}" for i, c in enumerate(chapters_list[:idx], 1))
        class_codes = list(CURRICULUM.keys())
        earlier_classes = class_codes[:class_codes.index(class_level)] if class_level in class_codes else []
        earlier_classes_block = "\n".join(
            f"{c} : " + " ; ".join(CURRICULUM[c]["chapters"]) for c in earlier_classes
        )
        previous_chapters_context = (
            f"\nCHAPITRES DÉJÀ VUS EN {class_level} AVANT CELUI-CI (numérotés comme dans les manuels) :\n"
            f"{previous_chapters_block}\n" if previous_chapters_block else ""
        ) + (
            f"\nPROGRAMME DE CHIMIE DES CLASSES PRÉCÉDENTES :\n{earlier_classes_block}\n" if earlier_classes_block else ""
        )

        # Ancrage documentaire : chaque chapitre des manuels de chimie ouvre sur une section « CE QUE
        # TU DOIS DEJA SAVOIR » (exercices P1, P2... et tableau savoir-faire/rappel, vérifié sur les
        # 45 PDF) — la requête cible cette section, contrairement à une recherche générique sur le nom
        # du chapitre qui ramènerait plutôt le contenu du chapitre lui-même.
        document_block = ""
        try:
            # Recherche TEXTUELLE de la section d'abord (marqueurs littéraux fiables, 45/45 chapitres
            # couverts) : la recherche sémantique seule ne la retrouvait que pour 30 chapitres sur
            # 45, le modèle d'embeddings la confondant avec le contenu général du chapitre.
            excerpts = self._prerequisite_section(class_level, chapter)
            if not excerpts:
                context_nodes = self._retrieve_with_filters(
                    "Ce que tu dois déjà savoir : exercices P1 P2 P3, rappel de ce qu'il faut savoir, "
                    "savoirs et savoir-faire indispensables, acquis des chapitres précédents",
                    [self._exact_filter("class", class_level), self._exact_filter("chapter", chapter)],
                    top_k=4,
                )
                excerpts = [n.get_content() for n in context_nodes]
            if excerpts:
                document_excerpts = "\n---\n".join(e[:1200] for e in excerpts)
                document_block = f"""
EXTRAITS DU MANUEL DE CE CHAPITRE — le manuel ouvre chaque chapitre sur une section « CE QUE TU DOIS DEJA \
SAVOIR » (exercices P1, P2... puis un tableau « savoir-faire (Pn) / rappel ») qui liste EXPLICITEMENT les acquis \
attendus. Si cette section apparaît ci-dessous, base-toi DESSUS EN PRIORITÉ (mêmes notions, sans recopier ses \
exercices) ; sinon, repère dans les extraits les notions que le chapitre UTILISE sans les réexpliquer :
{document_excerpts}
"""
        except Exception as e:
            print(f"[WARN] Recherche de contexte pour les prérequis echouee: {e}")

        system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. \
Un élève de {class_level} va commencer le chapitre « {chapter} ». AVANT qu'il ne s'y lance, tu vérifies \
qu'il maîtrise encore les notions prérequises — vues dans des chapitres ANTÉRIEURS, de cette année ou \
d'une année précédente — dont ce chapitre a besoin. Tu ne testes JAMAIS le contenu du chapitre « {chapter} » \
lui-même, seulement ce qui doit déjà être acquis avant de l'aborder. Un prérequis peut être une notion de chimie \
vue avant (atome, ion, formule, équation-bilan, mole...), une notion de physique utile (états de la matière, \
masse et volume) ou un outil mathématique indispensable (proportionnalité, pourcentages, puissances de dix, \
conversions d'unités).

{FORMULA_FORMAT_INSTRUCTIONS}

{CHEMISTRY_RIGOR_INSTRUCTIONS}
{previous_chapters_context}
{context_block}
{document_block}
STRUCTURE ATTENDUE, PAR NOTION (dans cet ORDRE, jamais l'inverse) :
1. Un RAPPEL DE COURS autonome sur la notion prérequise elle-même (définition, propriété ou méthode, \
+ un exemple chiffré rapide si utile) : l'élève doit pouvoir le lire et comprendre la notion SANS avoir \
encore vu les exercices. Ce n'est ni un indice ni une reformulation de l'exercice — c'est un vrai rappel \
de cours, comme une fiche de révision de 3 à 5 phrases.
2. ENSUITE seulement, 1 à 2 exercices diagnostiques à choix multiples pour vérifier que ce rappel est \
compris.

CONTRAINTES :
- Identifie 3 à 5 notions prérequises indispensables pour ce chapitre (reste concentré sur ce qui est \
vraiment nécessaire, pas un rappel exhaustif de toutes les années précédentes).
- Pour chaque notion, 1 exercice diagnostique — 2 exercices seulement pour une notion plus fondamentale \
ou plus fragile (voir consigne sur les questions récentes de l'élève ci-dessus). Au total, ne dépasse \
JAMAIS 7 exercices.
- Chaque exercice est COURT et ACCESSIBLE (application directe du rappel, sans piège ni astuce) : le but \
est de vérifier que la notion est acquise, pas de la retester en profondeur ni d'évaluer le chapitre à venir.
- Chaque exercice a EXACTEMENT 4 choix, une seule bonne réponse.
- Le champ "notion" reprend le nom court du PRÉREQUIS (2-5 mots, ex: "Formule d'un ion", "Équilibrer une \
équation", "Masse molaire") — jamais une notion du chapitre « {chapter} » lui-même.
- Pour chaque exercice, donne une "explication" courte confirmant la bonne réponse (1-2 phrases) — le \
rappel de cours a déjà enseigné la notion, cette explication ne fait que confirmer, pas réexpliquer en entier.
- Reste concis partout (rappel, exercice, explication) : pas de phrases superflues.
- Contexte réaliste et local burkinabè quand c'est pertinent.
- N'utilise AUCUN emoji.

FORMAT DE SORTIE — réponds UNIQUEMENT avec un objet JSON valide (aucun texte avant/après, pas de bloc de code) :
{{"notions": [{{"notion": "...", "rappel": "...", "exercices": [{{"question": "...", \
"choix": ["...", "...", "...", "..."], "reponse_correcte_index": 0, "explication": "..."}}, ...]}}, ...]}}
"""

        user_message = f"Prépare le diagnostic de prérequis avant le chapitre « {chapter} » pour un élève de {class_level}."

        response = self._call_claude(system_prompt, [{"role": "user", "content": user_message}],
                                      max_tokens=config.MAX_TOKENS_REMEDIATION)

        if response:
            questions = self._parse_prerequis_json(response)
            if questions:
                # Revérifie tous les exercices diagnostiques de toutes les notions en UN seul
                # appel (voir _verify_qcm_batch) plutôt qu'un par notion : on aplatit puis on
                # redistribue dans le même ordre.
                flat = [ex for notion in questions for ex in notion["exercices"]]
                verified = self._verify_qcm_batch(class_level, chapter, flat)
                i = 0
                for notion in questions:
                    n = len(notion["exercices"])
                    notion["exercices"] = verified[i:i + n]
                    i += n
                return questions

        print("[WARN] Claude indisponible ou reponse non structuree pour les prérequis, fallback local...")
        return self._local_prerequis(class_level, chapter)

    generate_remediation = generate_prerequis

    # Marqueurs de la section « CE QUE TU DOIS DEJA SAVOIR » des manuels de chimie (titre, exercices
    # « Exercice P1 », tableau « Rappel de ce qu'il faut savoir ») — pas les « Corrigés des
    # prérequis » de fin de chapitre, qui commencent par « P1. ».
    _PREREQ_SECTION_PATTERN = r"dois d.j. savoir|exercice p[0-9]|rappel de ce qu"

    def _prerequisite_section(self, class_level: str, chapter: str, limit: int = 3) -> list:
        """Passages indexés de la section « CE QUE TU DOIS DEJA SAVOIR » de ce chapitre, dans
        l'ordre du document (ordre d'insertion), ou [] si l'index n'en contient pas."""
        try:
            import psycopg
            with psycopg.connect(config.DATABASE_URL, connect_timeout=10) as conn, conn.cursor() as cur:
                cur.execute(
                    f'SELECT text FROM "data_{self.table_name}" '
                    "WHERE metadata_->>'class' = %s AND metadata_->>'chapter' = %s AND text ~* %s "
                    "ORDER BY id LIMIT %s",
                    (class_level, chapter, self._PREREQ_SECTION_PATTERN, limit),
                )
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"[WARN] Recherche de la section des prérequis echouee: {e}")
            return []

    @staticmethod
    def _parse_prerequis_json(raw_text: str):
        """Extrait et valide les groupes {notion, rappel, exercices} du diagnostic de prérequis
        renvoyé par Claude (voir FORMAT DE SORTIE dans generate_prerequis)."""
        text = raw_text.strip()
        text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        data = _loads_model_json(text[start:end + 1])
        if not isinstance(data, dict):
            return None

        raw_notions = data.get("notions")
        if not isinstance(raw_notions, list):
            return None

        notions = []
        for notion_item in raw_notions:
            if not isinstance(notion_item, dict):
                continue
            notion = str(notion_item.get("notion", "")).strip()
            rappel = str(notion_item.get("rappel", "")).strip()
            raw_exercices = notion_item.get("exercices")
            if not notion or not rappel or not isinstance(raw_exercices, list):
                continue

            exercices = []
            for item in raw_exercices:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                choix = item.get("choix")
                correct_index = item.get("reponse_correcte_index")
                if not question or not isinstance(choix, list) or len(choix) != 4:
                    continue
                if not isinstance(correct_index, int) or not (0 <= correct_index < 4):
                    continue
                exercices.append({
                    "question": question,
                    "choix": [str(c) for c in choix],
                    "reponse_correcte_index": correct_index,
                    "explication": str(item.get("explication", "")).strip(),
                })

            if exercices:
                notions.append({"notion": notion, "rappel": rappel, "exercices": exercices})

        return notions or None

    _parse_remediation_json = _parse_prerequis_json

    def _local_prerequis(self, class_level: str, chapter: str) -> list:
        """Fallback local pour le diagnostic de prérequis (utilisé uniquement si Claude est indisponible)."""
        return [{
            "notion": chapter or "Notion générale",
            "rappel": f"Le service Claude est momentanément indisponible : reviens plus tard pour un vrai "
                      f"diagnostic de prérequis sur « {chapter} ».",
            "exercices": [{
                "question": "Ceci est une version de secours, pas un vrai diagnostic.",
                "choix": ["Réessayer plus tard", "-", "-", "-"],
                "reponse_correcte_index": 0,
                "explication": "",
            }],
        }]

    _local_remediation = _local_prerequis

    # ========================================================================
    # ACCUEIL PERSONNALISÉ (élève connecté avec de l'historique)
    # ========================================================================

    def generate_welcome_message(self, username: str, weak_notions: list, struggles: list, topics: list) -> str:
        """Message d'accueil personnalisé pour un élève connecté ayant déjà de l'historique :
        mentionne 1-2 lacunes concrètes (notions ratées en remédiation, notions simplifiées)
        et suggère une action précise pour la prochaine session."""

        weak_text = "\n".join(
            f"- « {n['notion']} » (chapitre {n['chapter']}, {n['class_level']}) ratée {n['wrong_count']} fois en remédiation"
            for n in weak_notions
        ) or "Aucune lacune identifiée en remédiation pour l'instant."

        struggles_text = "\n".join(
            f"- A demandé une explication simplifiée sur « {s['question']} » (chapitre {s['chapter']}, {s['class_level']})"
            for s in struggles
        ) or "Aucune demande de simplification récente."

        topics_text = "\n".join(
            f"- {t['chapter']} ({t['class_level']}), {t['visits']} session(s)"
            for t in topics
        ) or "Aucun chapitre travaillé pour l'instant."

        system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. \
Un élève nommé {username} vient de se connecter à l'application. Tu as accès à son historique \
récent. Rédige un court message d'accueil personnalisé (DEUX PHRASES MAXIMUM, en Markdown léger) qui :
- Salue-le par son prénom/pseudo de façon chaleureuse et mentionne de façon concrète 1 lacune réelle \
tirée de son historique ci-dessous (pas de généralités).
- Termine par UNE suggestion précise et actionnable pour cette session (ex: reprendre tel chapitre, \
refaire un QCM de remédiation sur telle notion).
- Si l'historique ne montre AUCUNE lacune claire, félicite-le pour sa progression et propose \
d'avancer sur un nouveau chapitre plutôt que d'inventer un problème.

HISTORIQUE DE L'ÉLÈVE :
Notions ratées en remédiation :
{weak_text}

Notions ayant nécessité une simplification :
{struggles_text}

Chapitres travaillés récemment :
{topics_text}

{NO_EMOJI_INSTRUCTIONS}
Ne mets pas de titre Markdown (##), juste le message directement, comme si tu parlais à l'élève."""

        response = self._call_claude(system_prompt, [{"role": "user", "content": "Rédige le message d'accueil."}],
                                      max_tokens=500)
        if response:
            return response

        return self._local_welcome_message(username, weak_notions)

    @staticmethod
    def _local_welcome_message(username: str, weak_notions: list) -> str:
        """Fallback local pour l'accueil personnalisé (Claude indisponible)."""
        if weak_notions:
            notion = weak_notions[0]
            return (
                f"Content de te revoir, {username}. La dernière fois, « {notion['notion']} » "
                f"({notion['chapter']}) t'a donné du fil à retordre : ce serait une bonne idée d'y "
                f"revenir avant de continuer.\n\n"
                f"*(Le service Claude est momentanément indisponible, ceci est une version de secours.)*"
            )
        return (
            f"Content de te revoir, {username} ! Prêt à continuer là où tu t'es arrêté ?\n\n"
            f"*(Le service Claude est momentanément indisponible, ceci est une version de secours.)*"
        )

    # ========================================================================
    # GÉNÉRATION D'EXERCICES (structurés : énoncé / indices / solution)
    # ========================================================================

    @staticmethod
    def _recent_user_questions(history: list, limit: int = 4) -> list:
        """Dernières questions posées par l'élève dans la conversation (les plus utiles pour
        deviner un chapitre ou un niveau de difficulté implicites)."""
        if not history:
            return []
        return [t.get("content", "").strip() for t in history if t.get("role") == "user" and t.get("content")][-limit:]

    def _default_chapter(self, class_level: str) -> str:
        """Chapitre de repli quand aucun n'est précisé et que Claude n'en a pas proposé
        (ex: mode local sans API) : le premier chapitre du programme officiel de la classe."""
        chapters = CURRICULUM.get(class_level, {}).get("chapters", [])
        return chapters[0] if chapters else "Notions générales"

    @staticmethod
    def _infer_difficulty(history: list) -> int:
        """Estime un niveau de difficulté (1-4) quand l'élève n'a pas choisi lui-même, à partir
        de la sophistication de ses dernières questions. Défaut : 2 (application guidée)."""
        recent = RAGSystem._recent_user_questions(history)
        if not recent:
            return 2
        text = " ".join(recent).lower()
        advanced_markers = [
            "démontre", "démontrer", "justifie", "justifier", "établis", "établir l'expression",
            "tableau d'avancement", "avancement maximal", "réactif limitant", "quantité de matière",
            "concentration molaire", "dosage", "équivalence", "constante d'acidité", "pka", "solution tampon",
            "diagramme de prédominance", "demi-équation", "potentiel standard", "force électromotrice",
            "nombre d'oxydation", "stéréoisomère", "isomérie z", "carbone asymétrique", "estérification",
            "saponification", "oxydation ménagée", "rendement", "acide alpha-aminé",
        ]
        basic_markers = [
            "c'est quoi", "qu'est-ce que", "comment on fait", "définition", "exemple simple",
            "je ne comprends pas", "je comprends pas", "explique-moi", "explique moi",
        ]
        if any(marker in text for marker in advanced_markers):
            return 3
        if any(marker in text for marker in basic_markers):
            return 1
        return 2

    def generate_exercise(self, class_level, chapter, difficulty: int = None, history: list = None):
        """Génère un exercice structuré via Claude. Niveau 1★ : série de mini-questions QCM
        d'application directe. Niveaux 2-4★ : exercice ouvert (énoncé/indice/solution), la
        difficulté croissant jusqu'à une situation d'intégration en 4★.

        Le chapitre et la difficulté sont tous deux facultatifs : si l'élève ne les précise pas,
        Claude choisit lui-même un chapitre pertinent (à partir des dernières questions posées, ou
        un chapitre de base du programme sinon) et la difficulté est déduite du niveau apparent des
        questions récentes (moyenne par défaut)."""

        difficulty = difficulty if difficulty in (1, 2, 3, 4, 5) else self._infer_difficulty(history)
        difficulty_label = STAR_DIFFICULTY_LABELS[difficulty]

        auto_chapter = not chapter
        chapter_txt = chapter if chapter else "à choisir toi-même (voir consigne ci-dessous)"

        # Ancrage dans les documents fournis : priorité absolue à la matière déposée par l'équipe
        # pédagogique. Quand le chapitre est connu, le filtre doit être EXACT (pas le repli
        # classe-seule de self.query(), pensé pour le chat) : sinon, dès qu'aucun document ne
        # correspond vraiment, on récupérerait quand même des extraits d'un AUTRE chapitre de la
        # même classe et on croirait à tort avoir une source — l'exercice partirait alors sur un
        # sujet hors-programme sans jamais activer le repli recherche internet/génération libre.
        # Niveau 5 (olympiades) : jamais ancré sur les documents de cours déposés — ce sont des
        # manuels de programme standard, aucun contenu de type concours/olympiades dedans
        # (vérifié) ; les y ancrer donnerait au mieux un exercice 4★ recyclé, pas un vrai défi.
        context_nodes = []
        if difficulty != 5:
            try:
                if chapter:
                    context_nodes = self._retrieve_with_filters(
                        chapter,
                        [self._exact_filter("class", class_level), self._exact_filter("chapter", chapter)],
                        top_k=4,
                    )
                else:
                    recent = self._recent_user_questions(history, limit=1)
                    if recent:
                        context_nodes = self.query(recent[0], class_level=class_level, top_k=4)
            except Exception as e:
                print(f"[WARN] Recherche de contexte pour l'exercice echouee: {e}")

        web_search_tools = None
        if context_nodes:
            document_excerpts = "\n---\n".join(n.get_content()[:800] for n in context_nodes)
            context_instructions = f"""
DOCUMENTS DE COURS FOURNIS — base l'exercice EN PRIORITÉ sur ces extraits (mêmes notions, mêmes \
notations, même niveau de raisonnement) ; adapte les valeurs numériques et la mise en situation \
pour que l'exercice reste ORIGINAL plutôt qu'un copier-coller :
{document_excerpts}
"""
        elif difficulty == 5:
            context_instructions = """
Ce niveau sort volontairement du programme direct de la classe (voir la consigne OLYMPIADES \
ci-dessous) : ne te limite pas aux documents de cours. Compose un problème ORIGINAL à partir de \
tes connaissances des grands classiques de concours de chimie (olympiades nationales de chimie, \
problèmes préparatoires des olympiades internationales de chimie adaptés au niveau...) plutôt que de \
chercher à en citer un exact — l'objectif est un exercice inédit et bien calibré pour la classe, pas \
une citation d'archive.
"""
            # Pas d'outil de recherche web ici : un aller-retour de recherche consomme une bonne
            # partie du budget de tokens avant même de generer l'exercice, ce qui faisait souvent
            # revenir une reponse vide (voir MAX_TOKENS_EXERCISE_OLYMPIAD) sur ce niveau
            # spécifiquement — et une recherche n'apporte de toute façon pas grand-chose ici : aucune
            # vraie banque d'annales n'est indexée de façon exploitable, mieux vaut miser sur la
            # composition originale.
        else:
            context_instructions = """
Aucun document de cours fourni ne correspond à ce chapitre. Un outil de recherche internet est à \
ta disposition : utilise-le si une source fiable et récente (programme burkinabè de préférence) \
améliorerait la pertinence de l'exercice, sinon génère-le à partir de tes connaissances générales.
"""
            web_search_tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}]

        chapter_instructions = ""
        if auto_chapter:
            chapters_catalog = CURRICULUM.get(class_level, {}).get("chapters", [])
            catalog_txt = "\n".join(f"- {c}" for c in chapters_catalog) if chapters_catalog else "(programme non précisé)"
            recent_questions = self._recent_user_questions(history)
            history_txt = "\n".join(f"- {q}" for q in recent_questions) if recent_questions \
                else "(l'élève n'a pas encore posé de question)"
            chapter_instructions = f"""
L'ÉLÈVE N'A PAS CHOISI DE CHAPITRE — choisis-en un toi-même, en respectant cette règle :
- Si les dernières questions de l'élève ci-dessous pointent clairement vers un chapitre du programme, choisis-le.
- Sinon, choisis un chapitre de base adapté au niveau {class_level} (une notion fondamentale et incontournable).

Programme officiel de {class_level} :
{catalog_txt}

Dernières questions posées par l'élève :
{history_txt}

Indique EXACTEMENT l'intitulé retenu (repris tel quel dans la liste ci-dessus) dans le champ "chapitre" du JSON.
"""

        if difficulty == 1:
            system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. \
Tu génères une série de mini-questions à choix multiples ORIGINALES pour un élève de {class_level} sur le \
chapitre « {chapter_txt} », en application DIRECTE du cours (restitution immédiate, pas de raisonnement à \
plusieurs étapes).
{chapter_instructions}
{context_instructions}
CONTRAINTES :
- Fournis entre 3 et 4 mini-questions QCM, chacune sur une notion de base différente du chapitre.
- Chaque question a EXACTEMENT 4 choix, une seule bonne réponse.
- Contexte réaliste et local burkinabè quand c'est pertinent (cuisine au gaz ou au charbon, savon, engrais, eau du \
forage...).
- Une courte "explication" accompagne chaque question (pourquoi cette réponse est la bonne).
- Les distracteurs reprennent des erreurs typiques d'élèves : équation mal équilibrée, charge d'ion oubliée ou \
fausse, confusion atome/molécule/ion, oubli d'unité ou conversion oubliée.

{FORMULA_FORMAT_INSTRUCTIONS}

{NO_EMOJI_INSTRUCTIONS}

FORMAT DE SORTIE — réponds UNIQUEMENT avec un objet JSON valide (aucun texte avant/après, pas de bloc de code) :
{{"chapitre": "{chapter if chapter else '...'}", "enonce": "phrase d'introduction courte", "qcm": [{{"question": "...", \
"choix": ["...", "...", "...", "..."], "reponse_correcte_index": 0, "explication": "..."}}, ...]}}
"""
        else:
            olympiad_instructions = f"""
- CONSIGNE OLYMPIADES (niveau 5 uniquement) : ce n'est PAS un exercice de plus dans le programme de la classe — \
c'est un problème de concours de chimie, nettement plus dur qu'une "situation d'intégration" (niveau 4). Choisis \
UNE idée non standard et construis le problème AUTOUR d'elle (ne te contente pas de la nommer) : identifier une \
espèce inconnue à partir d'indices expérimentaux (tests caractéristiques, masses, volumes de gaz), retrouver une \
formule brute à partir de pourcentages massiques ou d'une combustion, raisonner sur la conservation des éléments \
ou des charges dans une suite de réactions, détecter le réactif limitant caché, estimer un ordre de grandeur \
(nombre de molécules, quantité de matière dans un objet courant), interpréter des résultats expérimentaux \
contradictoires, ou concevoir un protocole simple et sûr pour distinguer deux solutions. Les outils \
mathématiques restent ceux de la classe. \
INTERDIT : un exercice qui se résout en appliquant une formule du cours une ou deux fois, même avec des nombres \
compliqués — ce n'est qu'un niveau 4 déguisé, pas un niveau 5. Un élève sérieux de {class_level} doit pouvoir \
comprendre l'énoncé et les notions utilisées, mais PAS voir le chemin de résolution immédiatement : il doit \
chercher, essayer, se tromper avant de trouver l'angle d'attaque. L'indice unique pointe vers L'IDÉE CLÉ (quelle \
technique utiliser), jamais vers une étape de calcul. La solution doit expliquer POURQUOI cette idée fonctionne, \
pas seulement dérouler le calcul final.""" if difficulty == 5 else ""

            system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. \
Tu génères un exercice d'entraînement ORIGINAL pour un élève de {class_level} sur le chapitre « {chapter_txt} ».
{chapter_instructions}
{context_instructions}
CONTRAINTES :
- Niveau de difficulté : {difficulty_label}{olympiad_instructions}
- Contexte réaliste et local burkinabè (savon au beurre de karité, charbon de bois et foyers améliorés, gaz butane, \
engrais, eau du forage, rouille des tôles, piles et batteries, vinaigre et jus de citron...)
- Données numériques réalistes, chacune avec son unité ; donne dans l'énoncé les masses molaires atomiques, le \
volume molaire ou les constantes nécessaires (ex : $M(\\ce{{C}}) = 12\\,\\text{{g/mol}}$).
- Fournis exactement 1 indice qui guide SANS donner le résultat.
- NE RÉDIGE PAS de solution ni de réponse finale ici — uniquement l'énoncé et l'indice (la correction est générée \
séparément, à la demande de l'élève, voir generate_exercise_solution). Formule quand même l'énoncé de façon \
suffisamment précise et autonome pour qu'une solution complète et non ambiguë puisse en être déduite plus tard.
- OBLIGATOIRE si l'énoncé s'appuie sur un schéma (montage d'électrolyse, de pile, de dosage, de chauffage ou de \
recueil de gaz, courbe de dosage à exploiter, échelle de pKa ou de potentiels, formule développée à analyser...) : \
remplis le champ "figure" avec ce schéma (voir SCHÉMAS DE CHIMIE ci-dessous). Sinon mets "figure" à null. Le schéma \
de l'énoncé ne doit JAMAIS dévoiler la réponse (pas de gaz identifié s'il faut l'identifier, pas de volume équivalent \
dans un repère s'il faut le déterminer). N'essaie JAMAIS de dessiner avec des caractères ASCII (`|`, `/`, `\\`, `-`) \
dans "enonce" : uniquement le champ "figure" (ce champ est un mécanisme différent des blocs ```figure``` du chat : ici \
toujours un objet JSON dédié, jamais du texte).
{CHEMISTRY_RIGOR_INSTRUCTIONS}

{FORMULA_FORMAT_INSTRUCTIONS}

{NO_EMOJI_INSTRUCTIONS}

FORMAT DE SORTIE — réponds UNIQUEMENT avec un objet JSON valide (aucun texte avant/après, pas de bloc de code), \
exactement sous cette forme :
{{"chapitre": "{chapter if chapter else '...'}", "enonce": "...", "indices": ["..."], "figure": null}}

Si présente, la "figure" doit être un OBJET JSON (pas une chaîne de caractères échappée) suivant l'un des formats \
ci-dessous :
{FIGURE_SCHEMAS}
"""

        user_message = (
            f"Génère un exercice original et motivant sur « {chapter} » pour un élève de {class_level}."
            if chapter else
            f"Génère un exercice original et motivant pour un élève de {class_level} : choisis toi-même le "
            "chapitre le plus adapté, en suivant la consigne du système."
        )

        exercise_max_tokens = config.MAX_TOKENS_EXERCISE_OLYMPIAD if difficulty == 5 else config.MAX_TOKENS_EXERCISE
        response = self._call_claude(system_prompt, [{"role": "user", "content": user_message}],
                                      max_tokens=exercise_max_tokens, tools=web_search_tools)

        if response:
            parsed, claude_chapter = self._parse_exercise_json(response, difficulty)
            if parsed:
                resolved_chapter = chapter or claude_chapter or self._default_chapter(class_level)
                parsed["chapter"] = resolved_chapter
                parsed["class_level"] = class_level
                parsed["difficulty"] = difficulty
                if parsed["qcm"] is not None:
                    parsed["qcm"] = self._verify_qcm_batch(class_level, resolved_chapter, parsed["qcm"])
                return parsed
            print(f"[WARN] JSON exercice non parsable meme apres reparation ({len(response)} caracteres) : "
                  f"debut={response[:150]!r} fin={response[-150:]!r}")
        else:
            print("[WARN] _call_claude a renvoye une reponse vide pour l'exercice.")

        print("[WARN] Claude indisponible ou reponse non structuree pour l'exercice, fallback local...")
        return self._local_generate_exercise(class_level, chapter or self._default_chapter(class_level), difficulty)

    # Clés minimales qui rendent un schéma dessinable, par type (voir FIGURE_SCHEMAS et
    # frontend/src/lib/figureSpec.js) : un schéma sans aucun élément dessinable est ignoré plutôt
    # que servi vide. Sans "type", une figure avec des "points" est une figure géométrique. Le
    # montage, lui, se valide sur son "modele" (voir MONTAGE_MODELS), pas sur une liste.
    _FIGURE_REQUIRED_KEYS = {
        "graphique": ("series",),
        "echelle": ("zones", "reperes", "couples"),
        "molecule": ("atomes",),
        "geometrie": ("points",),
    }

    @staticmethod
    def _normalize_kind(value) -> str:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[\s'-]+", "_", text.strip().lower())

    @staticmethod
    def _valid_figure(figure) -> Optional[dict]:
        """Le schéma tel quel s'il est exploitable (type connu et au moins un élément dessinable,
        ou un modèle de montage connu), sinon None."""
        if not isinstance(figure, dict):
            return None
        kind = RAGSystem._normalize_kind(figure.get("type") or "geometrie")
        if kind == "montage":
            return figure if RAGSystem._normalize_kind(figure.get("modele")) in MONTAGE_MODELS else None
        required = RAGSystem._FIGURE_REQUIRED_KEYS.get(kind)
        if not required:
            return None
        if not any(isinstance(figure.get(k), list) and figure.get(k) for k in required):
            return None
        return figure

    @staticmethod
    def _figure_as_text(figure: Optional[dict]) -> str:
        """Résumé d'un schéma déjà généré (voir generate_exercise), pour que
        generate_exercise_solution puisse s'y référer sans avoir à le regénérer ni à le deviner :
        le JSON compact, lisible directement par le modèle quel que soit le type de schéma."""
        if not figure:
            return ""
        compact = json.dumps(figure, ensure_ascii=False, separators=(",", ":"))
        return f"Schéma de l'énoncé (JSON, pour information) : {compact[:2500]}"

    def generate_exercise_solution(self, class_level: str, chapter: str, difficulty: int,
                                    enonce: str, indices: Optional[list] = None,
                                    figure: Optional[dict] = None) -> dict:
        """Génère la correction (solution détaillée + réponse finale) d'un exercice DÉJÀ généré
        par generate_exercise, à la demande de l'élève (bouton "Voir la solution détaillée" côté
        frontend) — séparé de la génération de l'énoncé pour deux raisons : (1) la plupart des
        élèves qui génèrent un exercice ne demandent pas forcément la correction tout de suite,
        générer les deux d'un coup était donc souvent du travail perdu ; (2) réunir énoncé ET
        solution détaillée dans le même appel forçait à partager un seul budget de tokens entre
        les deux — sur un exercice de Terminale (raisonnement long, rédaction dense), la part
        "solution" pouvait à elle seule dépasser ce budget partagé, tronquant la réponse JSON et
        déclenchant un repli silencieux vers un exercice générique (symptôme observé : "l'exercice
        ne vient pas vraiment" en Terminale). Ici la solution a son propre budget dédié, donc plus
        de contention avec l'énoncé."""
        difficulty_label = STAR_DIFFICULTY_LABELS.get(difficulty, STAR_DIFFICULTY_LABELS[2])
        indice_txt = f"\nIndice déjà donné à l'élève : {indices[0]}" if indices else ""
        figure_txt = self._figure_as_text(figure)

        system_prompt = f"""Tu es « Prof Karim », professeur de chimie au Burkina Faso. Un élève de \
{class_level} a déjà reçu l'énoncé suivant (chapitre « {chapter} », niveau {difficulty_label}) et souhaite \
maintenant en voir la correction détaillée.

ÉNONCÉ DÉJÀ DONNÉ À L'ÉLÈVE (ne le répète pas, résous-le directement) :
{enonce}
{indice_txt}
{f"{chr(10)}{figure_txt}" if figure_txt else ""}

CONTRAINTES :
- Rédige une solution détaillée, étape par étape, cohérente avec CET énoncé précis (pas un autre) : équation-bilan \
équilibrée, données converties dans les unités utiles, expression littérale, application numérique, résultat avec \
son unité (et tableau d'avancement si la réaction le demande, à partir de la 2nde).
- Mets la réponse finale bien en évidence, séparément, TOUJOURS avec son unité quand c'est une grandeur.
- Si la correction demande de TRACER ou de COMPLÉTER un schéma (courbe de dosage, montage légendé, échelle de pKa, \
formule développée...), remplis le champ "figure" avec ce schéma (un objet JSON, formats ci-dessous) et réfère-toi à \
lui dans "solution" ; sinon mets "figure" à null. N'essaie JAMAIS de dessiner un schéma dans "solution" ou \
"reponse_finale" : ni caractères alignés, ni tableau LaTeX (`\\begin{{array}}`), ni suite de `\\text{{...}}` — \
uniquement le champ "figure". (Un tableau d'avancement, lui, est un vrai tableau Markdown dans "solution".)
{FORMULA_FORMAT_INSTRUCTIONS}

{CHEMISTRY_RIGOR_INSTRUCTIONS}

{NO_EMOJI_INSTRUCTIONS}

FORMAT DE SORTIE — réponds UNIQUEMENT avec un objet JSON valide (aucun texte avant/après, pas de bloc de code) :
{{"solution": "...", "reponse_finale": "...", "figure": null}}

Formats possibles pour "figure" :
{FIGURE_SCHEMAS}
"""
        user_message = "Rédige la correction détaillée de cet exercice."

        max_tokens = config.MAX_TOKENS_EXERCISE_OLYMPIAD if difficulty == 5 else config.MAX_TOKENS_EXERCISE
        response = self._call_claude(system_prompt, [{"role": "user", "content": user_message}], max_tokens=max_tokens)

        if response:
            parsed = self._parse_exercise_solution_json(response)
            if parsed:
                return parsed
            print(f"[WARN] JSON de correction non parsable ({len(response)} caracteres) : "
                  f"debut={response[:150]!r} fin={response[-150:]!r}")
        else:
            print("[WARN] _call_claude a renvoye une reponse vide pour la correction.")

        return {
            "solution": "Le service est momentanément indisponible : reviens plus tard pour voir la correction.",
            "reponse_finale": "",
            "figure": None,
        }

    @staticmethod
    def _parse_exercise_solution_json(raw_text: str) -> Optional[dict]:
        text = raw_text.strip()
        text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        data = _loads_model_json(text[start:end + 1])
        if not isinstance(data, dict):
            return None

        solution = str(data.get("solution", "")).strip()
        if not solution:
            return None
        return {
            "solution": solution,
            "reponse_finale": str(data.get("reponse_finale", "")).strip(),
            "figure": RAGSystem._valid_figure(data.get("figure")),
        }

    @staticmethod
    def _parse_exercise_json(raw_text: str, difficulty: int = 2):
        """Extrait et valide le JSON d'exercice renvoyé par Claude : forme QCM (liste `qcm`) en 1★,
        forme ouverte (`solution`/`indices`) en 2-4★. Tolère les fences markdown.
        Retourne un tuple (exercice, chapitre_choisi_par_claude) — le second élément n'est utile
        que lorsque l'élève n'avait pas précisé de chapitre lui-même."""
        text = raw_text.strip()
        text = re.sub(r"^```(json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text.strip()).strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, None

        # Échappement LaTeX cassé : ça arrive surtout dans le morceau "continué" d'une réponse
        # tronquée (voir _call_claude) — le modèle recommence alors à écrire \ce, \frac...
        # en JSON à échappement unique au lieu du double backslash JSON attendu (\\ce) ;
        # _loads_model_json tente une réparation ciblée avant d'abandonner.
        data = _loads_model_json(text[start:end + 1])
        if not isinstance(data, dict):
            return None, None

        enonce = str(data.get("enonce", "")).strip()
        if not enonce:
            return None, None

        claude_chapter = str(data.get("chapitre", "")).strip()

        if difficulty == 1:
            raw_qcm = data.get("qcm")
            if not isinstance(raw_qcm, list):
                return None, None
            qcm = []
            for item in raw_qcm:
                if not isinstance(item, dict):
                    continue
                question = str(item.get("question", "")).strip()
                choix = item.get("choix")
                correct_index = item.get("reponse_correcte_index")
                if not question or not isinstance(choix, list) or len(choix) != 4:
                    continue
                if not isinstance(correct_index, int) or not (0 <= correct_index < 4):
                    continue
                qcm.append({
                    "question": question,
                    "choix": [str(c) for c in choix],
                    "reponse_correcte_index": correct_index,
                    "explication": str(item.get("explication", "")).strip(),
                })
            if not qcm:
                return None, None
            return {"enonce": enonce, "indices": [], "solution": "", "reponse_finale": "", "figure": None,
                    "qcm": qcm}, claude_chapter

        indices = data.get("indices", [])
        if not isinstance(indices, list):
            indices = [str(indices)]

        figure = RAGSystem._valid_figure(data.get("figure"))

        # La solution est désormais générée séparément, à la demande (voir
        # generate_exercise_solution) : on ne l'exige plus ici (c'était la cause du bug
        # Terminale, la réponse combinée dépassant parfois le budget de tokens et laissant
        # "solution" vide, ce qui faisait rejeter tout l'exercice). On la récupère quand même
        # si le modèle en a fourni une, pour rester tolérant aux anciennes réponses.
        return {
            "enonce": enonce,
            "indices": [str(i) for i in indices][:1],
            "solution": str(data.get("solution", "")).strip(),
            "reponse_finale": str(data.get("reponse_finale", "")).strip(),
            "figure": figure,
            "qcm": None
        }, claude_chapter

    # ========================================================================
    # FALLBACKS LOCAUX (quand Claude est indisponible)
    # ========================================================================

    def _generate_local_response(self, question, class_level, chapter, context):
        """Fallback local pour les réponses (utilisé uniquement si Claude est indisponible)."""
        chapter_lower = chapter.lower()
        question_lower = question.lower()

        knowledge = self._get_knowledge(chapter_lower, question_lower, question, class_level, chapter)

        if knowledge:
            if context and context != "Aucun document spécifique disponible pour ce chapitre.":
                knowledge += f"\n\n**Extrait des documents :**\n{context[:500]}"
            return knowledge

        if context and context != "Aucun document spécifique disponible pour ce chapitre.":
            return f"""
**Question :** {question}

Voici les informations disponibles sur le chapitre "{chapter}" de {class_level}.

**Documents :**
{context[:800]}

*Conseil : Pour approfondir, consulte ton manuel ou demande à ton professeur.*
"""
        intro = (
            f'Le chapitre "{chapter}" fait partie du programme de {class_level} au Burkina Faso.'
            if class_level or chapter else
            "Voici ce que je peux te dire pour l'instant."
        )
        return f"""
**Question :** {question}

{intro}

**Pour t'aider :**
1. Relis les définitions dans ton cours
2. Fais des exercices d'application simples
3. Augmente progressivement la difficulté

*Je peux te donner des explications plus précises si tu reformules ta question, ou réessaie dans un instant \
(le service Claude est momentanément indisponible).*
"""

    def _get_knowledge(self, chapter_lower, question_lower, question, class_level, chapter):
        """Retourne le contenu de connaissance si le thème est détecté (secours hors-ligne uniquement)."""
        knowledge_base = {
            "alcane": f"""
**Question :** {question}

Les **alcanes** sont des hydrocarbures saturés : leurs molécules ne contiennent que des atomes de carbone et \
d'hydrogène, reliés uniquement par des liaisons simples.

**Formule générale :** $\\ce{{C_{{n}}H_{{2n+2}}}}$

**Exemples :** méthane $\\ce{{CH4}}$, éthane $\\ce{{C2H6}}$, propane $\\ce{{C3H8}}$, butane $\\ce{{C4H10}}$ (le gaz \
des bouteilles de cuisine).

**Combustion complète du butane :** $\\ce{{2C4H10 + 13O2 -> 8CO2 + 10H2O}}$

**Attention :** une combustion incomplète (manque d'air) produit du monoxyde de carbone $\\ce{{CO}}$, un gaz \
toxique et inodore : on cuisine toujours dans un endroit bien aéré.
""",
            "électrolyse": f"""
**Question :** {question}

L'**électrolyse de l'eau** décompose l'eau en dihydrogène et en dioxygène grâce au courant électrique (dans un \
électrolyseur, avec un peu d'hydroxyde de sodium pour rendre l'eau conductrice).

**Équation-bilan :** $\\ce{{2H2O -> 2H2 + O2}}$

- À la **cathode** (borne $-$) : il se dégage du dihydrogène $\\ce{{H2}}$ (il produit une petite détonation au \
contact d'une flamme).
- À l'**anode** (borne $+$) : il se dégage du dioxygène $\\ce{{O2}}$ (il ravive une bûchette incandescente).
- Le volume de dihydrogène obtenu est **le double** de celui du dioxygène.
""",
            "mole": f"""
**Question :** {question}

La **quantité de matière** $n$ d'un échantillon se mesure en moles ($\\text{{mol}}$). Une mole contient \
$N_A = 6{{,}}02 \\times 10^{{23}}$ entités (atomes, molécules ou ions).

**Relation :** $n = \\dfrac{{m}}{{M}}$
- $m$ : masse de l'échantillon, en grammes ($\\text{{g}}$)
- $M$ : masse molaire, en grammes par mole ($\\text{{g/mol}}$)

**Exemple :** $M(\\ce{{H2O}}) = 2 \\times 1 + 16 = 18\\,\\text{{g/mol}}$, donc $36\\,\\text{{g}}$ d'eau contiennent \
$n = \\dfrac{{36}}{{18}} = 2{{,}}0\\,\\text{{mol}}$ de molécules d'eau.
""",
            "acide": f"""
**Question :** {question}

Le **pH** indique si une solution aqueuse est acide, neutre ou basique (à $25\\,^{{\\circ}}\\text{{C}}$) :
- $\\mathrm{{pH}} < 7$ : solution **acide** (jus de citron, vinaigre) ;
- $\\mathrm{{pH}} = 7$ : solution **neutre** (eau pure) ;
- $\\mathrm{{pH}} > 7$ : solution **basique** (eau savonneuse, eau de chaux).

On le mesure avec du papier pH (valeur approchée) ou un pH-mètre (valeur précise).

**Neutralisation :** $\\ce{{H3O+ + HO- -> 2H2O}}$

**Sécurité :** pour diluer un acide, on verse toujours l'acide dans l'eau, jamais l'inverse.
""",
            "combustion": f"""
**Question :** {question}

Une **combustion** est une transformation chimique au cours de laquelle un **combustible** brûle en consommant un \
**comburant** (le dioxygène de l'air), avec dégagement de chaleur.

**Triangle du feu :** combustible + comburant + source de chaleur. Supprimer un des trois arrête le feu.

**Combustion du carbone :** $\\ce{{C + O2 -> CO2}}$ — le dioxyde de carbone formé trouble l'eau de chaux.

**Attention :** un brasero allumé dans une pièce fermée produit du monoxyde de carbone $\\ce{{CO}}$, gaz mortel.
""",
        }

        for key, value in knowledge_base.items():
            if key in chapter_lower or key in question_lower:
                return value
        return None

    def _local_simplify(self, question: str, original_answer: str, class_level: str) -> str:
        """Fallback simplification locale (utilisé uniquement si Claude est indisponible)."""
        key_points = []
        for line in original_answer.split('\n'):
            line = line.strip()
            if line and len(line) > 20 and not line.startswith('**') and not line.startswith('#'):
                line = line.replace('**', '').replace('*', '')
                key_points.append(line)

        text = '\n'.join(key_points[:4]) if key_points else original_answer[:300]
        return f"""
**Pas de panique, voici en plus simple :**

{text}

**Conseil :** En {class_level}, apprends bien la formule et fais plusieurs petits exercices d'application.

*(Le service Claude est momentanément indisponible, ceci est une version de secours.)*
"""

    def _local_generate_exercise(self, class_level, chapter, difficulty: int = 2):
        """Fallback exercice local structuré (utilisé uniquement si Claude est indisponible)."""
        if difficulty == 1:
            return {
                "enonce": f"Petit test de connaissances sur « {chapter} ».",
                "indices": [],
                "solution": "",
                "reponse_finale": "",
                "figure": None,
                "qcm": [{
                    "question": f"Quelle affirmation correspond à une notion du chapitre « {chapter} » ?",
                    "choix": [
                        "Une notion vue en cours sur ce chapitre",
                        "Une notion d'un autre chapitre",
                        "Une affirmation fausse",
                        "Une affirmation hors-programme",
                    ],
                    "reponse_correcte_index": 0,
                    "explication": "Le service Claude est momentanément indisponible : reviens plus tard "
                                   "pour un vrai QCM généré sur ce chapitre.",
                }],
                "chapter": chapter,
                "class_level": class_level,
                "difficulty": difficulty,
            }

        chapter_lower = chapter.lower()

        exercises = {
            "alcane": {
                "enonce": "À Koudougou, Moussa cuisine avec une bouteille de propane $\\ce{C3H8}$. Écris puis "
                           "équilibre l'équation-bilan de la combustion complète du propane dans le dioxygène.",
                "indices": [
                    "Une combustion complète d'un alcane ne produit que du dioxyde de carbone et de l'eau.",
                    "Équilibre d'abord le carbone, puis l'hydrogène, et termine par l'oxygène."
                ],
                "solution": "1) Réactifs : $\\ce{C3H8}$ et $\\ce{O2}$ ; produits : $\\ce{CO2}$ et $\\ce{H2O}$.\n"
                            "2) Carbone : 3 atomes, donc $\\ce{3CO2}$. Hydrogène : 8 atomes, donc $\\ce{4H2O}$.\n"
                            "3) Oxygène : $3 \\times 2 + 4 \\times 1 = 10$ atomes, donc $\\ce{5O2}$.",
                "reponse_finale": "$\\ce{C3H8 + 5O2 -> 3CO2 + 4H2O}$"
            },
            "combustion": {
                "enonce": "Dans le brasero de la cour, $12\\,\\text{g}$ de charbon de bois (considéré comme du carbone "
                           "pur) brûlent complètement en consommant $32\\,\\text{g}$ de dioxygène. Écris l'équation-bilan "
                           "de la réaction, puis calcule la masse de dioxyde de carbone formée.",
                "indices": [
                    "Au cours d'une transformation chimique, la masse totale se conserve.",
                    "La masse des produits est égale à la masse des réactifs consommés."
                ],
                "solution": "1) Équation-bilan : $\\ce{C + O2 -> CO2}$.\n"
                            "2) Conservation de la masse : $m(\\ce{CO2}) = m(\\ce{C}) + m(\\ce{O2}) = 12 + 32 = 44\\,\\text{g}$.",
                "reponse_finale": "$m(\\ce{CO2}) = 44\\,\\text{g}$"
            },
            "mole": {
                "enonce": "Awa remplit une bouteille avec $1{,}5\\,\\text{L}$ d'eau du forage, de masse $1{,}5\\,\\text{kg}$. "
                           "Calcule la quantité de matière de molécules d'eau qu'elle contient. Données : "
                           "$M(\\ce{H}) = 1\\,\\text{g/mol}$ ; $M(\\ce{O}) = 16\\,\\text{g/mol}$.",
                "indices": [
                    "Calcule d'abord la masse molaire de l'eau, puis convertis la masse en grammes.",
                    "Utilise ensuite la relation entre quantité de matière, masse et masse molaire."
                ],
                "solution": "1) $M(\\ce{H2O}) = 2 \\times 1 + 16 = 18\\,\\text{g/mol}$.\n"
                            "2) $m = 1{,}5\\,\\text{kg} = 1\\,500\\,\\text{g}$.\n"
                            "3) $n = \\dfrac{m}{M} = \\dfrac{1\\,500\\,\\text{g}}{18\\,\\text{g/mol}} \\approx 83\\,\\text{mol}$.",
                "reponse_finale": "$n(\\ce{H2O}) \\approx 83\\,\\text{mol}$, soit $8{,}3 \\times 10^{1}\\,\\text{mol}$."
            },
            "acide": {
                "enonce": "Avec du papier pH, Salif mesure le pH de trois liquides : le jus de citron "
                           "($\\mathrm{pH} = 2{,}5$), l'eau du forage ($\\mathrm{pH} = 7{,}0$) et une eau savonneuse "
                           "($\\mathrm{pH} = 10$). Classe chaque liquide : acide, neutre ou basique.",
                "indices": [
                    "Compare chaque valeur de pH à 7.",
                ],
                "solution": "1) Le jus de citron a un pH inférieur à 7 : il est acide.\n"
                            "2) L'eau du forage a un pH égal à 7 : elle est neutre.\n"
                            "3) L'eau savonneuse a un pH supérieur à 7 : elle est basique.",
                "reponse_finale": "Jus de citron : acide ; eau du forage : neutre ; eau savonneuse : basique."
            },
        }

        for key, value in exercises.items():
            if key in chapter_lower:
                return {
                    "enonce": value["enonce"],
                    "indices": value["indices"][:1],
                    "solution": value["solution"],
                    "reponse_finale": value["reponse_finale"],
                    "figure": value.get("figure"),
                    "qcm": None,
                    "chapter": chapter,
                    "class_level": class_level,
                    "difficulty": difficulty,
                }

        default_solution = "Applique la méthode vue en cours, étape par étape, en vérifiant chaque calcul."
        default_indices = ["Relis la définition principale du chapitre et repère la formule à appliquer."]
        return {
            "enonce": f"Entraîne-toi sur le chapitre « {chapter} » : reformule un problème vu en cours avec tes "
                      f"propres nombres, puis résous-le étape par étape.",
            "indices": default_indices,
            "solution": default_solution,
            "reponse_finale": "",
            "figure": None,
            "qcm": None,
            "chapter": chapter,
            "class_level": class_level,
            "difficulty": difficulty,
        }

