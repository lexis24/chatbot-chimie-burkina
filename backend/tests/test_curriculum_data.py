"""Garde-fous sur curriculum_data.py : le programme de chimie reprend exactement les classes
et les intitulés de chapitres des manuels Hakili Lab, dans leur ordre. Ces tests protègent contre
une régression silencieuse (classe oubliée, liste vidée par erreur, chapitre renommé ou déplacé)
— l'ordre compte : le chapitre N d'un manuel est retrouvé à l'index N-1 (voir
document_processor.curriculum_chapter_from_number)."""
import json
import re
from pathlib import Path

from curriculum_data import CURRICULUM, get_chapters, get_classes
from document_processor import find_course_file

EXPECTED_CLASSES = ["4ème", "3ème", "2nde", "1ère", "Tle"]
EXPECTED_CHAPTER_COUNTS = {"4ème": 7, "3ème": 10, "2nde": 9, "1ère": 9, "Tle": 10}
DOCUMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
CLASS_FOLDERS = {"4ème": "4eme", "3ème": "3eme", "2nde": "2ndeC", "1ère": "1ereD", "Tle": "TleD"}


def test_expected_classes_in_school_order():
    assert get_classes() == EXPECTED_CLASSES


def test_every_class_has_its_full_chapter_list():
    for class_code in get_classes():
        chapters = get_chapters(class_code)
        assert len(chapters) == EXPECTED_CHAPTER_COUNTS[class_code], class_code
        assert len(chapters) == len(set(chapters)), f"{class_code} a des doublons de chapitre"


def test_every_class_has_a_display_name():
    for class_code in get_classes():
        assert CURRICULUM[class_code]["name"].strip()


def test_chapter_titles_follow_the_manuals():
    assert get_chapters("4ème")[0] == "La combustion avec ou sans flamme"
    assert get_chapters("3ème")[9] == "Les notions d'acide et de base"
    assert get_chapters("2nde")[2] == "La molécule et la mole de molécules"
    assert get_chapters("1ère")[5] == "Les réactions d'oxydoréduction en solution aqueuse"
    assert get_chapters("Tle")[-1] == "L'estérification, l'hydrolyse et la saponification"


def test_no_physics_chapter():
    """La physique a sa propre application : aucun de ses chapitres ne doit apparaître ici."""
    physics_words = ("lentille", "circuit", "force", "mouvement", "tension", "ombre", "lumière")
    for class_code in get_classes():
        for chapter in get_chapters(class_code):
            assert not any(w in chapter.lower() for w in physics_words), (class_code, chapter)


def test_each_chapter_has_its_course_pdf_with_matching_number():
    """Chaque chapitre a son PDF de cours dans data/documents/<classe>/, numéroté comme dans le
    programme : c'est ce qui garantit « Voir le cours » et le classement à l'ingestion."""
    for class_code, folder in CLASS_FOLDERS.items():
        numbers = sorted(
            int(re.match(r"Chimie_Chapitre_(\d+)_", p.name).group(1))
            for p in (DOCUMENTS_DIR / folder).glob("Chimie_Chapitre_*.pdf")
        )
        assert numbers == list(range(1, len(get_chapters(class_code)) + 1)), class_code


def test_every_chapter_finds_its_summary_and_flashcards():
    """« Résumé » et « Flashcards » : chaque chapitre retrouve SA fiche de révision et SON paquet
    de cartes (même numéro de chapitre, et intitulé du paquet = intitulé du programme)."""
    summaries_dir = DOCUMENTS_DIR.parent / "summaries"
    flashcards_dir = DOCUMENTS_DIR.parent / "flashcards"
    for class_code in get_classes():
        for number, chapter in enumerate(get_chapters(class_code), 1):
            fiche = find_course_file(str(summaries_dir), class_code, chapter)
            assert fiche and re.search(rf"Chimie_Chapitre_{number}_.*_FICHE_REVISION\.pdf$", Path(fiche).name), (class_code, chapter, fiche)
            paquet = find_course_file(str(flashcards_dir), class_code, chapter, extensions=(".json",))
            assert paquet, (class_code, chapter)
            data = json.loads(Path(paquet).read_text(encoding="utf-8"))
            assert data["chapitre"] == f"Chimie, Chapitre {number} : {chapter}", (class_code, chapter, paquet)
            assert data["cartes"], paquet


def test_course_lookup_returns_the_right_pdf_for_every_chapter():
    """« Voir le cours » (repli sans index vectoriel) : chaque chapitre retrouve SON PDF, y compris
    ceux dont le nom de fichier est abrégé (Tle : « ..._HCl_et_NaOH.pdf »)."""
    for class_code in get_classes():
        for number, chapter in enumerate(get_chapters(class_code), 1):
            result = find_course_file(str(DOCUMENTS_DIR), class_code, chapter)
            assert result is not None, (class_code, chapter)
            assert Path(result).name.startswith(f"Chimie_Chapitre_{number}_"), (class_code, chapter, result)
