"""Tests de document_processor.py : correspondance classe/chapitre <-> fichiers sur le disque.

Ce module a concentré plusieurs bugs subtils (alias de classe manquant pour les exports bruts,
correspondance de mots-clés qui ne coupait pas les mots car les libellés étaient déjà concaténés,
faux positifs sur des mots génériques, égalité de score entre deux chapitres dont les noms de
fichiers se recoupent, noms de fichiers abrégés). Ces tests figent le comportement attendu pour
éviter les régressions.
"""
from pathlib import Path

import pytest

from document_processor import (
    sanitize_folder_name,
    normalize_key,
    infer_class_from_path,
    find_course_file,
    chapter_number_from_filename,
    curriculum_chapter_from_number,
    _tokens,
)


def test_sanitize_folder_name_replaces_forbidden_characters():
    assert sanitize_folder_name("Les couples acide/base") == "Les couples acide-base"
    assert sanitize_folder_name("Sans caractère interdit") == "Sans caractère interdit"


def test_normalize_key_strips_accents_case_and_punctuation():
    assert normalize_key("L'élément chimique") == "lelementchimique"
    assert normalize_key("2nde") == "2nde"


def test_tokens_splits_words_and_drops_stopwords():
    # normalize_key concatène tout ("lelementchimique"), ce qui a longtemps cassé la
    # correspondance mot à mot : _tokens doit garder les mots séparés et retirer les mots vides.
    assert _tokens("La combustion du carbone") == ["combustion", "carbone"]
    assert _tokens("Les acides et les bases") == ["acide", "base"]


def test_tokens_naive_depluralization():
    assert _tokens("Composés aromatiques") == ["compose", "aromatique"]


@pytest.fixture
def fake_documents_dir(tmp_path: Path) -> Path:
    """Reproduit la structure réelle des documents : dossiers de classe nommés comme dans les
    exports (« 2ndeC » pour la classe « 2nde »), noms de fichiers sans accents qui ne reprennent
    pas toujours tous les mots de l'intitulé officiel."""
    root = tmp_path / "documents"

    twonde = root / "2ndeC"
    twonde.mkdir(parents=True)
    (twonde / "Chimie_Chapitre_1_L_element_chimique.pdf").write_bytes(b"%PDF-1.4 fake")
    (twonde / "Chimie_Chapitre_5_La_reaction_chimique.pdf").write_bytes(b"%PDF-1.4 fake")

    troisieme = root / "3eme"
    troisieme.mkdir(parents=True)
    # Seul fichier de 3ème, sans rapport avec « Les notions d'acide et de base » : une recherche
    # floue trop permissive le renverrait quand même faute de meilleur candidat.
    (troisieme / "Chimie_Chapitre_5_L_electrolyse_et_la_synthese_de_l_eau.pdf").write_bytes(b"%PDF-1.4 fake")

    terminale = root / "TleD"
    terminale.mkdir(parents=True)
    # Cas réels : « Les solutions aqueuses » est le début de l'intitulé du chapitre 2, et les
    # fichiers des chapitres 2 et 5 sont abrégés (« HCl_et_NaOH »).
    (terminale / "Chimie_Chapitre_1_Les_solutions_aqueuses.pdf").write_bytes(b"%PDF-1.4 fake")
    (terminale / "Chimie_Chapitre_2_Les_solutions_aqueuses_HCl_et_NaOH.pdf").write_bytes(b"%PDF-1.4 fake")
    (terminale / "Chimie_Chapitre_5_Reaction_entre_HCl_et_NaOH.pdf").write_bytes(b"%PDF-1.4 fake")
    (terminale / "Chimie_Chapitre_6_Reaction_acide_faible_base_forte.pdf").write_bytes(b"%PDF-1.4 fake")

    return root


def test_infer_class_from_path_handles_raw_export_alias(fake_documents_dir):
    path = fake_documents_dir / "2ndeC" / "Chimie_Chapitre_5_La_reaction_chimique.pdf"
    assert infer_class_from_path(path, fake_documents_dir) == "2nde"
    assert infer_class_from_path(Path("/x/TleD/a.pdf"), Path("/x")) == "Tle"
    assert infer_class_from_path(Path("/x/1ereD/a.pdf"), Path("/x")) == "1ère"


def test_find_course_file_matches_multiword_chapter(fake_documents_dir):
    result = find_course_file(str(fake_documents_dir), "2nde", "L'élément chimique")
    assert result is not None
    assert "L_element_chimique" in result


def test_find_course_file_rejects_unrelated_file(fake_documents_dir):
    """« Les notions d'acide et de base » (3ème) n'a pas de fichier : ne jamais renvoyer celui
    d'un autre chapitre de la classe."""
    result = find_course_file(str(fake_documents_dir), "3ème", "Les notions d'acide et de base")
    assert result is None


def test_find_course_file_breaks_ties_with_chapter_number(fake_documents_dir):
    """Régression : « Les solutions aqueuses » (chapitre 1 de Tle) recoupe autant de mots-clés avec
    le fichier du chapitre 2 qu'avec le sien ; le numéro de chapitre doit départager."""
    result = find_course_file(str(fake_documents_dir), "Tle", "Les solutions aqueuses")
    assert result is not None and "Chapitre_1_" in result


def test_find_course_file_accepts_abbreviated_file_name_with_matching_number(fake_documents_dir):
    """Régression : les fichiers abrégés (« HCl_et_NaOH ») ne recoupent qu'une minorité des
    mots-clés de leur intitulé ; leur numéro de chapitre suffit alors à les retenir."""
    result = find_course_file(
        str(fake_documents_dir), "Tle",
        "Les solutions aqueuses d'acide chlorhydrique et d'hydroxyde de sodium",
    )
    assert result is not None and "Chapitre_2_" in result
    result = find_course_file(
        str(fake_documents_dir), "Tle",
        "La réaction entre une solution d'acide chlorhydrique et une solution d'hydroxyde de sodium",
    )
    assert result is not None and "Chapitre_5_" in result


def test_find_course_file_returns_none_for_missing_content(fake_documents_dir):
    result = find_course_file(str(fake_documents_dir), "2nde", "Les acides et les bases")
    assert result is None


def test_find_course_file_official_convention_takes_priority(tmp_path):
    """Convention officielle : data_dir/<classe>/<chapitre>/fichier — doit être trouvé même sans
    recourir à la recherche floue."""
    folder = tmp_path / "4ème" / "Les gaz"
    folder.mkdir(parents=True)
    (folder / "cours.pdf").write_bytes(b"%PDF-1.4 fake")

    result = find_course_file(str(tmp_path), "4ème", "Les gaz")
    assert result == str(folder / "cours.pdf")


def test_chapter_number_from_filename_reads_every_naming_scheme():
    assert chapter_number_from_filename(Path("Chimie_Chapitre_4_Les_atomes_et_les_molecules.pdf")) == 4
    assert chapter_number_from_filename(Path("flashcards_TleD_Chimie_Chapitre_10_Esterification.json")) == 10
    assert chapter_number_from_filename(Path("Chimie_Chapitre_3_La_pile_electrochimique_FICHE_REVISION.pdf")) == 3
    assert chapter_number_from_filename(Path("Annexe_Questions_rapides.pdf")) is None


def test_curriculum_chapter_from_number_follows_manual_order():
    assert curriculum_chapter_from_number("4ème", Path("Chimie_Chapitre_1_x.pdf")) == "La combustion avec ou sans flamme"
    assert curriculum_chapter_from_number("Tle", Path("Chimie_Chapitre_10_x.pdf")) == "L'estérification, l'hydrolyse et la saponification"
    assert curriculum_chapter_from_number("4ème", Path("Chimie_Chapitre_8_x.pdf")) is None  # 7 chapitres en 4ème
    assert curriculum_chapter_from_number("4ème", Path("Annexe.pdf")) is None
