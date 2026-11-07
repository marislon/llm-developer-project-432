from pathlib import Path

import psycopg

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"

def get_migrations() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))

def read_migration(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def get_applied_migrations(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()

    return {row[0] for row in rows}

def ensure_migrations_table(conn: psycopg.Connection) -> None:
    sql = read_migration(
        MIGRATIONS_DIR / "000_schema_migrations.sql"
    )
    conn.execute(sql)

def apply_migration(
    conn: psycopg.Connection,
    path: Path,
) -> None:
    sql = read_migration(path)

    with conn.transaction():
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (path.name,),
        )
def run_migrations() -> None:
    with psycopg.connect(
        settings.database_url,
        autocommit=True,
    ) as conn:
        ensure_migrations_table(conn)

        applied = get_applied_migrations(conn)

        for path in get_migrations():
            if path.name == "000_schema_migrations.sql":
                continue

            if path.name in applied:
                print(f"SKIP: {path.name}")
                continue

            apply_migration(conn, path)
            print(f"APPLIED: {path.name}")

if __name__ == "__main__":
    run_migrations()
