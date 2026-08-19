from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from database import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestion du schéma SQLite OCR Pipe")
    parser.add_argument("command", choices=["migrate", "status"])
    parser.add_argument("--database", type=Path, default=Path("data/ocr_pipe.db"))
    args = parser.parse_args()

    if args.command == "migrate":
        run_migrations(args.database)
        print(f"Migrations appliquées sur {args.database}")
        return

    if not args.database.exists():
        print("Base absente")
        return
    with sqlite3.connect(args.database) as connection:
        rows = connection.execute(
            "SELECT version, applied_at, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    for version, applied_at, checksum in rows:
        print(f"{version}  {applied_at}  {checksum[:12] if checksum else 'sans-checksum'}")


if __name__ == "__main__":
    main()
