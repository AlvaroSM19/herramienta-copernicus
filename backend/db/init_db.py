"""Inicializa (o actualiza) la base de datos a partir de schema.sql.

Ejecutar una sola vez:
    python -m backend.db.init_db
"""
from pathlib import Path

from core import db
from backend.config import DB_PATH, ROOT


def main() -> None:
    schema_path: Path = ROOT / "backend" / "db" / "schema.sql"
    db.init_db(DB_PATH, schema_path)


if __name__ == "__main__":
    main()
