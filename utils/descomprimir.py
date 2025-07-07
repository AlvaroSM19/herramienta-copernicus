
import os
import tarfile
import zipfile
from datetime import datetime

raiz = r"C:\EUMETCast\received\hvs-2\Sentinel"

def extraer_y_eliminar_tar(ruta_tar, destino):
    try:
        with tarfile.open(ruta_tar, 'r') as tar:
            tar.extractall(path=destino)
        
        print(f"[{datetime.now()}] Extraído TAR: {ruta_tar}")
    except Exception as e:
        print(f"[{datetime.now()}] Error procesando TAR {ruta_tar}: {e}")

def extraer_y_eliminar_zip(ruta_zip, destino):
    try:
        with zipfile.ZipFile(ruta_zip, 'r') as zipf:
            zipf.extractall(path=destino)
        
        print(f"[{datetime.now()}] Extraído  ZIP: {ruta_zip}")
    except Exception as e:
        print(f"[{datetime.now()}] Error procesando ZIP {ruta_zip}: {e}")

def procesar_archivos():
    for dirpath, _, filenames in os.walk(raiz):
        for archivo in filenames:
            ruta_completa = os.path.join(dirpath, archivo)
            if archivo.endswith(".tar"):
                extraer_y_eliminar_tar(ruta_completa, dirpath)
            elif archivo.endswith(".zip"):
                extraer_y_eliminar_zip(ruta_completa, dirpath)

if __name__ == "__main__":
    procesar_archivos()
