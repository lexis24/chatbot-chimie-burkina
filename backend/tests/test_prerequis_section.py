"""Section « CE QUE TU DOIS DEJA SAVOIR » des manuels de chimie : le motif de recherche textuelle
(voir RAGSystem._prerequisite_section, utilisé par generate_prerequis) doit reconnaître la section
elle-même, mais pas les « Corrigés des prérequis » de fin de chapitre."""
import re

from rag_system import RAGSystem

PATTERN = re.compile(RAGSystem._PREREQ_SECTION_PATTERN, re.IGNORECASE)


def test_pattern_matches_the_section_heading_exercises_and_recap():
    assert PATTERN.search("CE QUE TU DOIS DEJA SAVOIR\nCes acquis de l'école primaire...")
    assert PATTERN.search("Ce que tu dois déjà savoir")
    assert PATTERN.search("1. Exerce-toi pour t'assurer que tu maîtrises les savoirs indispensables Exercice P1. Cite...")
    assert PATTERN.search("2. Rappel de ce qu'il faut savoir\nSavoirs et savoir-faire")


def test_pattern_ignores_the_end_of_chapter_answers_and_ordinary_content():
    assert not PATTERN.search("Corrigés des prérequis\nP1. L'état solide (une pierre, du bois)...")
    assert not PATTERN.search("La combustion du carbone produit du dioxyde de carbone.")
