from __future__ import annotations

import sqlite3
import hashlib
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            checksum TEXT
        )""")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(schema_migrations)")}
        if "checksum" not in columns:
            connection.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT")
        applied = {row[0]: row[1] for row in connection.execute(
            "SELECT version, checksum FROM schema_migrations"
        )}
        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = migration_path.stem.split("_", 1)[0]
            sql = migration_path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if version in applied:
                if applied[version] and applied[version] != checksum:
                    raise RuntimeError(f"La migration {version} a été modifiée après application.")
                if not applied[version]:
                    connection.execute(
                        "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
                        (checksum, version),
                    )
                continue
            safe_version = version.replace("'", "''")
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql +
                f"\nINSERT INTO schema_migrations (version, checksum) VALUES ('{safe_version}', '{checksum}');\n"
                "COMMIT;"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
