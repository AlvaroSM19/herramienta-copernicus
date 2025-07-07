"""Utilidades mínimas para trabajar con SQLite."""
from pathlib import Path
import sqlite3


def init_db(db_path: Path, schema_path: Path) -> None:
    """Crea (o actualiza) la base de datos usando el esquema dado."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.close()
    print(f"✅ Base inicializada en {db_path}")


def get_conn(db_path: Path) -> sqlite3.Connection:
    """Devuelve conexión SQLite con row_factory=sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
