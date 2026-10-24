# Curriculum data for Burkina Faso - Chimie
# Source : manuels de Physique-Chimie de la Collection Hakili Lab (Édition 2026), de la 4ème à la
# Terminale D — partie chimie uniquement (la physique a sa propre application). Les intitulés
# reprennent EXACTEMENT ceux de la première page de chaque chapitre des manuels (« CHAPITRE N : ... »,
# vérifiés un par un contre les PDF de data/documents/ et le champ "chapitre" des flashcards), dans
# l'ordre des manuels : le chapitre N d'une classe est à l'index N-1 de sa liste. C'est ce qui permet
# à la recherche de cours et au classement automatique des documents (voir document_processor.py,
# ingest_documents.py) de fonctionner. La chimie n'est pas enseignée en 6ème/5ème.

CURRICULUM = {
    "4ème": {
        "name": "Quatrième",
        "chapters": [
            "La combustion avec ou sans flamme",
            "Les aspects pratiques des combustions",
            "L'utilisation des combustibles et les dangers",
            "Les atomes et les molécules",
            "La structure de l'atome",
            "La combustion du carbone",
            "La combustion du dihydrogène"
        ]
    },
    "3ème": {
        "name": "Troisième",
        "chapters": [
            "Les transformations électrochimiques du cuivre et de l'ion cuivre",
            "Les transformations chimiques du cuivre et de l'ion cuivre",
            "La pile électrochimique",
            "Les gaz",
            "L'électrolyse et la synthèse de l'eau",
            "Les alcanes et leur combustion",
            "L'oxydation du carbone, du soufre et du fer",
            "La réduction de l'oxyde ferrique et de l'oxyde cuivrique",
            "L'importance industrielle de la réduction des oxydes",
            "Les notions d'acide et de base"
        ]
    },
    "2nde": {
        "name": "Seconde C",
        "chapters": [
            "L'élément chimique",
            "L'atome et la mole d'atomes",
            "La molécule et la mole de molécules",
            "Les ions et la mole d'ions",
            "La réaction chimique",
            "La mise en solution des solides ioniques",
            "L'hydroxyde de sodium et sa solution",
            "Le chlorure d'hydrogène et sa solution",
            "Les acides et les bases"
        ]
    },
    "1ère": {
        "name": "Première D",
        "chapters": [
            "Les alcanes",
            "Les alcènes et les alcynes",
            "Les composés aromatiques",
            "Les composés organiques oxygénés",
            "La notion de stéréochimie",
            "Les réactions d'oxydoréduction en solution aqueuse",
            "Les potentiels d'oxydoréduction",
            "Le dosage d'oxydoréduction",
            "L'oxydoréduction par voie sèche"
        ]
    },
    "Tle": {
        "name": "Terminale D",
        "chapters": [
            "Les solutions aqueuses",
            "Les solutions aqueuses d'acide chlorhydrique et d'hydroxyde de sodium",
            "Les couples acide/base",
            "La classification des couples acide/base dans l'eau",
            "La réaction entre une solution d'acide chlorhydrique et une solution d'hydroxyde de sodium",
            "La réaction entre une solution d'acide faible et une solution de base forte",
            "Les alcools",
            "L'oxydation ménagée des composés organiques oxygénés",
            "Les amines, les amides et les acides alpha-aminés",
            "L'estérification, l'hydrolyse et la saponification"
        ]
    }
}

def get_classes():
    """Return list of all classes"""
    return list(CURRICULUM.keys())

def get_class_name(class_code):
    """Return full name of a class"""
    return CURRICULUM.get(class_code, {}).get("name", class_code)

def get_chapters(class_code):
    """Return list of chapters for a given class"""
    return CURRICULUM.get(class_code, {}).get("chapters", [])
