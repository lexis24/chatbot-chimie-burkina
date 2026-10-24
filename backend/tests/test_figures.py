"""Schémas de chimie (champ `figure` des exercices et des corrections, voir FIGURE_SCHEMAS dans
rag_system.py) : un schéma exploitable est conservé tel quel, un schéma vide, d'un type inconnu ou
d'un modèle de montage inconnu est écarté plutôt que servi au frontend (qui ne saurait pas le dessiner)."""
import json
import re

from rag_system import FIGURE_SCHEMAS, MONTAGE_MODELS, RAGSystem

MONTAGE = {"type": "montage", "modele": "dosage", "etiquettes": {"burette": "NaOH 0,10 mol/L", "becher": "HCl"}}


def test_valid_figure_keeps_each_chemistry_type():
    assert RAGSystem._valid_figure(MONTAGE) is MONTAGE
    assert RAGSystem._valid_figure({"type": "Montage", "modele": "Électrolyse"})
    assert RAGSystem._valid_figure({"type": "graphique", "series": [{"points": [[0, 0], [1, 1]]}]})
    assert RAGSystem._valid_figure({"type": "échelle", "zones": [{"de": 0, "a": 7, "label": "acide"}]})
    assert RAGSystem._valid_figure({"type": "echelle", "couples": [{"valeur": 0.34, "gauche": "Cu^{2+}", "droite": "Cu"}]})
    assert RAGSystem._valid_figure({"type": "molécule", "atomes": [{"id": "O", "symbole": "O", "position": [0, 0]}]})
    assert RAGSystem._valid_figure({"type": "Géométrie", "points": [{"id": "A", "x": 0, "y": 0}]})


def test_valid_figure_accepts_typeless_geometry():
    assert RAGSystem._valid_figure({"points": [{"id": "A", "x": 0, "y": 0}]})


def test_valid_figure_rejects_empty_unknown_or_malformed():
    assert RAGSystem._valid_figure({"type": "montage", "modele": "distillation"}) is None
    assert RAGSystem._valid_figure({"type": "montage"}) is None
    assert RAGSystem._valid_figure({"type": "molecule", "atomes": []}) is None
    assert RAGSystem._valid_figure({"type": "echelle"}) is None
    assert RAGSystem._valid_figure({"type": "circuit", "composants": [{"type": "pile"}]}) is None
    assert RAGSystem._valid_figure("figure") is None
    assert RAGSystem._valid_figure(None) is None


def test_parse_exercise_keeps_a_montage_figure():
    raw = json.dumps({"chapitre": "Le dosage d'oxydoréduction", "enonce": "Énoncé", "indices": ["Indice"], "figure": MONTAGE})
    parsed, chapter = RAGSystem._parse_exercise_json(raw, difficulty=2)
    assert parsed["figure"] == MONTAGE
    assert chapter == "Le dosage d'oxydoréduction"


def test_parse_exercise_drops_an_unusable_figure():
    raw = json.dumps({"enonce": "Énoncé", "indices": [], "figure": {"type": "montage", "modele": "inconnu"}})
    parsed, _ = RAGSystem._parse_exercise_json(raw, difficulty=3)
    assert parsed["figure"] is None


def test_parse_solution_keeps_a_valid_figure_and_drops_an_invalid_one():
    """La correction peut porter son propre schéma (courbe de dosage à tracer, montage légendé) :
    sans ce champ, le modèle « dessinait » le schéma en LaTeX (\\begin{array}), cassé à l'écran."""
    raw = json.dumps({"solution": "Voir le montage.", "reponse_finale": "10 mL", "figure": MONTAGE})
    assert RAGSystem._parse_exercise_solution_json(raw)["figure"] == MONTAGE
    raw = json.dumps({"solution": "Voir.", "reponse_finale": "", "figure": {"type": "graphique"}})
    assert RAGSystem._parse_exercise_solution_json(raw)["figure"] is None


def _schema_examples():
    examples = []
    for match in re.finditer(r'^\{"type"', FIGURE_SCHEMAS, flags=re.M):
        depth = 0
        for i in range(match.start(), len(FIGURE_SCHEMAS)):
            depth += FIGURE_SCHEMAS[i] == "{"
            depth -= FIGURE_SCHEMAS[i] == "}"
            if depth == 0:
                examples.append(json.loads(FIGURE_SCHEMAS[match.start():i + 1]))
                break
    return examples


def test_figure_schema_examples_are_valid_json_and_accepted():
    """Le modèle imite les exemples de FIGURE_SCHEMAS : chacun doit être du JSON valide et
    accepté par _valid_figure, sinon on lui apprendrait un format que l'application rejette."""
    examples = _schema_examples()
    assert {e["type"] for e in examples} == {"montage", "graphique", "echelle", "molecule", "geometrie"}
    assert all(RAGSystem._valid_figure(e) is not None for e in examples)


def test_montage_example_labels_belong_to_their_model():
    """Les étiquettes d'exemple doivent être des emplacements réellement dessinés par le modèle."""
    for example in _schema_examples():
        if example["type"] == "montage":
            assert set(example["etiquettes"]) <= set(MONTAGE_MODELS[example["modele"]])


def test_figure_as_text_is_compact_json():
    text = RAGSystem._figure_as_text(MONTAGE)
    assert text.startswith("Schéma de l'énoncé")
    assert '"type":"montage"' in text
    assert RAGSystem._figure_as_text(None) == ""
