from pathlib import Path

# raíz del proyecto = carpeta que contiene *este* archivo
ROOT = Path(__file__).resolve().parents[1]

# Base de datos SQLite
DB_PATH = ROOT / "db" / "catalog.db"

# Directorio donde caen los NetCDF de EUMETCast (ajústalo según tu entorno)
# ⚠ Si tus NetCDF están en una ruta distinta, cámbialo aquí:
DATA_DIR = Path(r"C:\EUMETCast\received\hvs-2\Sentinel")
