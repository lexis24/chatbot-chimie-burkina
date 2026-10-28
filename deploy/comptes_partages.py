"""Prépare la base des maths pour servir de base de comptes commune (chimie et physique).

À exécuter UNE fois, en local, depuis chatbot-chimie-burkina/backend avec son venv :

    python ../deploy/comptes_partages.py ../../comptes_maths.env              # aperçu, aucune écriture
    python ../deploy/comptes_partages.py ../../comptes_maths.env --executer   # exécution

Ce que fait --executer, dans une seule transaction (tout ou rien) :
  - crée deux rôles de connexion, chatchimie_app et chatphysique_app, avec un mot de passe aléatoire ;
  - crée les schémas app_chimie et app_physique, où chaque application créera ses propres tables
    d'activité (conversations, messages, quiz, flashcards) à son démarrage ;
  - donne à chaque rôle, sur les comptes partagés app.users et app.schools : lecture, création,
    mise à jour — jamais de suppression ;
  - ne donne aucun accès aux tables d'activité des maths (app.conversations, app.messages...) ni à
    l'index vectoriel des maths, ni au schéma de l'autre matière.

Aucune table existante n'est modifiée. Les adresses de connexion des deux rôles sont écrites dans
deploy/out/<app>.comptes.env (ignoré par git), jamais affichées.
"""
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from dotenv import dotenv_values
from psycopg import sql

APPS = {"chatchimie": "app_chimie", "chatphysique": "app_physique"}
OUT = Path(__file__).resolve().parent / "out"


def statements(role: str, schema: str, password: str) -> list[sql.Composed]:
    r, s = sql.Identifier(role), sql.Identifier(schema)
    return [
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(r, sql.Literal(password)),
        sql.SQL("CREATE SCHEMA {}").format(s),
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(s, r),
        sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(r),
        sql.SQL("GRANT SELECT, INSERT, UPDATE ON app.users, app.schools TO {}").format(r),
        # Nécessaire pour que les tables d'activité de la matière pointent vers app.users.
        sql.SQL("GRANT REFERENCES ON app.users TO {}").format(r),
    ]


def masked(stmt: sql.Composed, conn) -> str:
    text = stmt.as_string(conn)
    return text.split(" PASSWORD ")[0] + " PASSWORD '********'" if " PASSWORD " in text else text


def role_url(admin_url: str, role: str, password: str) -> str:
    parts = urlsplit(admin_url)
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=f"{role}:{quote(password, safe='')}@{host}"))


def main() -> None:
    admin_url = dotenv_values(sys.argv[1]).get("MATHS_DATABASE_URL") or ""
    execute = "--executer" in sys.argv[2:]
    if not admin_url:
        sys.exit(f"MATHS_DATABASE_URL absente de {sys.argv[1]}")

    passwords = {app: secrets.token_urlsafe(32) for app in APPS}
    options = "" if execute else "-c default_transaction_read_only=on"  # aperçu : écriture impossible
    with psycopg.connect(admin_url, connect_timeout=15, options=options) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('app.users') IS NOT NULL")
        if not cur.fetchone()[0]:
            sys.exit("app.users introuvable : ce n'est pas la base des maths. Rien n'a été fait.")
        cur.execute("""SELECT (SELECT count(*) FROM pg_roles WHERE rolname = ANY(%s))
                            + (SELECT count(*) FROM pg_namespace WHERE nspname = ANY(%s))""",
                    ([f"{a}_app" for a in APPS], list(APPS.values())))
        if cur.fetchone()[0]:
            sys.exit("Rôles ou schémas déjà présents : script déjà exécuté ? Rien n'a été fait.")

        plan = [(app, stmt) for app, schema in APPS.items()
                for stmt in statements(f"{app}_app", schema, passwords[app])]
        print("Instructions SQL" + (" exécutées :" if execute else " prévues (aperçu, rien n'est exécuté) :"))
        for _, stmt in plan:
            print("  " + masked(stmt, conn) + ";")
        if not execute:
            conn.rollback()
            print("\nRelance avec --executer pour appliquer.")
            return
        for _, stmt in plan:
            cur.execute(stmt)
    # Transaction validée à la sortie du bloc « with » ; on n'écrit les adresses qu'après.

    OUT.mkdir(exist_ok=True)
    for app in APPS:
        path = OUT / f"{app}.comptes.env"
        path.write_text(f"ACCOUNTS_DATABASE_URL={role_url(admin_url, f'{app}_app', passwords[app])}\n",
                        encoding="ascii")
        print(f"Adresse de connexion de {app}_app écrite dans {path} (à ajouter au container.env du serveur).")


if __name__ == "__main__":
    main()
