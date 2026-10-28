"""Rattache l'activité des comptes d'une application (base propre) aux comptes partagés des maths.

Pour chaque compte de l'ancienne base dont le nom d'utilisateur existe aussi dans la base des
maths, copie ses conversations, messages, réponses de quiz, lacunes et révisions de flashcards
dans le schéma de la matière (app_physique, app_chimie), sous l'identifiant du compte des maths.
Les comptes sans homonyme en maths ne sont pas copiés : ils sont listés (en nombre seulement).

À lancer depuis le backend de l'application concernée, avec son venv, APRÈS un premier démarrage
en mode partagé (qui crée les tables du schéma) :

    python ../../chatbot-chimie-burkina/deploy/rattacher_activite.py \
        .env ../../chatbot-chimie-burkina/deploy/out/chatphysique.comptes.env           # aperçu
    ... --executer                                                                       # copie

- L'ancienne base est lue en lecture seule ; rien n'y est supprimé.
- La copie est faite en une transaction avec le rôle limité de l'application, et peut être
  relancée sans doublon (mêmes identifiants, ON CONFLICT DO NOTHING).
- N'affiche aucun nom d'utilisateur ni contenu : seulement des nombres.
"""
import sys

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

# Ordre imposé par les clés étrangères (messages -> conversations).
TABLES = ["conversations", "messages", "remediation_answers", "struggles", "flashcard_reviews"]


def main() -> None:
    old_url = dotenv_values(sys.argv[1]).get("DATABASE_URL") or ""
    shared = dotenv_values(sys.argv[2])
    shared_url = shared.get("ACCOUNTS_DATABASE_URL") or ""
    execute = "--executer" in sys.argv[3:]
    if not old_url or not shared_url:
        sys.exit("DATABASE_URL (ancienne base) ou ACCOUNTS_DATABASE_URL (base partagée) manquante.")

    with psycopg.connect(shared_url, connect_timeout=15, row_factory=dict_row) as new:
        # Schéma de la matière : celui où le rôle de l'application peut créer des tables.
        schema = new.execute(
            """SELECT nspname FROM pg_namespace WHERE nspname IN ('app_chimie', 'app_physique')
               AND has_schema_privilege(nspname, 'CREATE')"""
        ).fetchone()
        if not schema:
            sys.exit("Aucun schéma app_chimie/app_physique accessible avec ce rôle.")
        schema = schema["nspname"]
        if new.execute("SELECT to_regclass(%s) AS t", (f"{schema}.conversations",)).fetchone()["t"] is None:
            sys.exit(f"Tables de {schema} absentes : démarre d'abord l'application en mode partagé.")
        shared_ids = {r["username_key"]: r["id"]
                      for r in new.execute("SELECT username_key, id FROM app.users").fetchall()}

        with psycopg.connect(old_url, connect_timeout=15, row_factory=dict_row,
                             options="-c default_transaction_read_only=on") as old:
            old_users = old.execute("SELECT id, username_key FROM app.users").fetchall()
            mapping = {u["id"]: shared_ids[u["username_key"]] for u in old_users if u["username_key"] in shared_ids}
            print(f"Schéma cible : {schema}")
            print(f"Comptes de l'ancienne base : {len(old_users)} ; avec homonyme en maths : {len(mapping)} ; "
                  f"sans homonyme (non copiés) : {len(old_users) - len(mapping)}")

            with new.transaction():
                for table in TABLES:
                    rows = old.execute(
                        sql.SQL("SELECT * FROM app.{} WHERE user_id = ANY(%s)").format(sql.Identifier(table)),
                        (list(mapping),),
                    ).fetchall()
                    copied = 0
                    for row in rows:
                        row = {k: Jsonb(v) if isinstance(v, (dict, list)) else v for k, v in row.items()}
                        row["user_id"] = mapping[row["user_id"]]
                        cols = list(row)
                        cur = new.execute(
                            sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                                sql.Identifier(schema), sql.Identifier(table),
                                sql.SQL(", ").join(map(sql.Identifier, cols)),
                                sql.SQL(", ").join(sql.Placeholder() * len(cols)),
                            ),
                            list(row.values()),
                        )
                        copied += cur.rowcount
                    print(f"  {table} : {len(rows)} ligne(s) dans l'ancienne base, {copied} copiée(s)")
                if not execute:
                    # Aperçu : la transaction est annulée, rien n'est conservé.
                    raise psycopg.Rollback()
    print("Copie effectuée." if execute else "Aperçu seulement (transaction annulée). Relance avec --executer.")


if __name__ == "__main__":
    main()
