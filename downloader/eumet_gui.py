import sys
import threading
import os
import shutil
import tarfile
import zipfile
from datetime import datetime, timedelta, time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QComboBox, QPushButton,
    QDateTimeEdit, QLineEdit, QVBoxLayout, QHBoxLayout, QWidget,
    QFileDialog, QTextEdit
)
from PyQt6.QtCore import Qt

import eumdac

from config import BBOX_PREDEFINIDAS, colecciones, consumer_key, consumer_secret

credentials = (consumer_key, consumer_secret)

MAX_SIZE = 200 * 1024 * 1024  # 200 MB

class DownloaderThread(threading.Thread):
    def __init__(self, parent, product_id, dtstart, dtend, bbox, output_dir):
        super().__init__()
        self.parent = parent
        self.product_id = product_id
        self.dtstart = dtstart
        self.dtend = dtend
        self.bbox = bbox
        self.output_dir = output_dir

    def run(self):
        self.parent.append_log(f"\nBuscando productos en: {self.product_id}")
        try:
            token = eumdac.AccessToken(credentials)
            datastore = eumdac.DataStore(token)
            collection = datastore.get_collection(self.product_id)
            products = collection.search(bbox=self.bbox, dtstart=self.dtstart, dtend=self.dtend)
            n = 0
            for product in products:
                size_bytes = getattr(product, "size", None)
                if size_bytes is None:
                    self.parent.append_log(
                        f"Omitido (tamaño desconocido): {getattr(product, 'name', str(product))}")
                    continue
                if size_bytes > MAX_SIZE:
                    self.parent.append_log(
                        f"Omitido (> {size_bytes/(1024*1024):.1f} MB): {getattr(product, 'name', str(product))}")
                    continue
                with product.open() as fsrc:
                    file_path = os.path.join(self.output_dir, fsrc.name)
                    if os.path.exists(file_path):
                        self.parent.append_log(f"Ya descargado: {fsrc.name}")
                        continue
                    with open(file_path, mode='wb') as fdst:
                        shutil.copyfileobj(fsrc, fdst)
                    self.parent.append_log(f'Descargado: {fsrc.name}')
                    n += 1
            if n == 0:
                self.parent.append_log("No hay productos nuevos para descargar en este rango.")
            self.parent.append_log("\nDescarga finalizada.\n")
        except Exception as e:
            self.parent.append_log(f"Error: {e}")

class DescompresionThread(threading.Thread):
    def __init__(self, parent, raiz):
        super().__init__()
        self.parent = parent
        self.raiz = raiz

    def run(self):
        n_tar, n_zip = 0, 0
        for dirpath, _, filenames in os.walk(self.raiz):
            for archivo in filenames:
                if archivo.endswith('.done'):
                    continue
                ruta_completa = os.path.join(dirpath, archivo)
                # ----- TAR -----
                if archivo.endswith(".tar"):
                    try:
                        size_bytes = os.path.getsize(ruta_completa)
                        if size_bytes > MAX_SIZE:
                            self.parent.append_log(f"[{datetime.now()}] TAR demasiado grande ({size_bytes/(1024*1024):.1f} MB): {ruta_completa}. Eliminando sin descomprimir.")
                            os.remove(ruta_completa)
                            continue
                        with tarfile.open(ruta_completa, 'r') as tar:
                            tar.extractall(path=dirpath)
                        self.parent.append_log(f"[{datetime.now()}] Extraído TAR: {ruta_completa}")
                        # .done VACÍO
                        done_path = ruta_completa + ".done"
                        with open(done_path, "w") as f:
                            f.write("")
                        os.remove(ruta_completa)
                        n_tar += 1
                    except Exception as e:
                        self.parent.append_log(f"[{datetime.now()}] Error TAR {ruta_completa}: {e}")
                # ----- ZIP -----
                elif archivo.endswith(".zip"):
                    try:
                        size_bytes = os.path.getsize(ruta_completa)
                        if size_bytes > MAX_SIZE:
                            self.parent.append_log(f"[{datetime.now()}] ZIP demasiado grande ({size_bytes/(1024*1024):.1f} MB): {ruta_completa}. Eliminando sin descomprimir.")
                            os.remove(ruta_completa)
                            continue
                        with zipfile.ZipFile(ruta_completa, 'r') as zipf:
                            zipf.extractall(path=dirpath)
                        self.parent.append_log(f"[{datetime.now()}] Extraído ZIP: {ruta_completa}")
                        # .done VACÍO
                        done_path = ruta_completa + ".done"
                        with open(done_path, "w") as f:
                            f.write("")
                        os.remove(ruta_completa)
                        n_zip += 1
                    except Exception as e:
                        self.parent.append_log(f"[{datetime.now()}] Error ZIP {ruta_completa}: {e}")
        if n_tar == 0 and n_zip == 0:
            self.parent.append_log("No se encontraron archivos .tar ni .zip para descomprimir.")
        else:
            self.parent.append_log(f"Descompresión finalizada. {n_tar} TAR y {n_zip} ZIP extraídos.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EUMETSAT Downloader")
        self.setMinimumWidth(550)
        self.scan_active = False

        layout = QVBoxLayout()

        # Zona predefinida y bbox
        self.zone_label = QLabel("Zona:")
        self.zone_combo = QComboBox()
        for z in BBOX_PREDEFINIDAS.keys():
            self.zone_combo.addItem(z)
        self.zone_combo.currentTextChanged.connect(self.set_bbox_from_zone)

        self.bbox_label = QLabel("Bounding box (W, S, E, N):")
        self.bbox_edit = QLineEdit(BBOX_PREDEFINIDAS["España peninsular"])
        self.bbox_edit.setEnabled(False)  # Solo editable si "Personalizada"

        layout.addWidget(self.zone_label)
        layout.addWidget(self.zone_combo)
        layout.addWidget(self.bbox_label)
        layout.addWidget(self.bbox_edit)

        # Producto individual
        self.product_label = QLabel("Producto (descarga individual):")
        self.product_combo = QComboBox()
        for k in colecciones.keys():
            self.product_combo.addItem(k)
        layout.addWidget(self.product_label)
        layout.addWidget(self.product_combo)

        # Fechas
        self.start_label = QLabel("Fecha inicio:")
        self.start_edit = QDateTimeEdit(datetime.utcnow() - timedelta(days=1))
        self.start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_edit.setCalendarPopup(True)

        self.end_label = QLabel("Fecha fin:")
        self.end_edit = QDateTimeEdit(datetime.utcnow())
        self.end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_edit.setCalendarPopup(True)

        layout.addWidget(self.start_label)
        layout.addWidget(self.start_edit)
        layout.addWidget(self.end_label)
        layout.addWidget(self.end_edit)

        # Carpeta salida
        self.dir_label = QLabel("Carpeta descarga:")
        self.dir_edit = QLineEdit(r"C:\EUMETCast\received\hvs-2\Sentinel\Download")
        self.dir_btn = QPushButton("Elegir carpeta")
        self.dir_btn.clicked.connect(self.choose_folder)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.dir_label)
        hlayout.addWidget(self.dir_edit)
        hlayout.addWidget(self.dir_btn)
        layout.addLayout(hlayout)

        # Botón descargar individual
        self.download_btn = QPushButton("Descargar (individual)")
        self.download_btn.clicked.connect(self.download)
        layout.addWidget(self.download_btn)

        # Escaneo continuo (todos los productos)
        self.start_scan_btn = QPushButton("Iniciar escaneo continuo (todos los productos)")
        self.start_scan_btn.clicked.connect(self.start_scan)
        layout.addWidget(self.start_scan_btn)

        self.stop_scan_btn = QPushButton("Parar escaneo")
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        self.stop_scan_btn.setEnabled(False)
        layout.addWidget(self.stop_scan_btn)

        # Botón de descompresión (hilo)
        self.unzip_btn = QPushButton("Descomprimir archivos (.tar y .zip)")
        self.unzip_btn.clicked.connect(self.lanzar_descompresion)
        layout.addWidget(self.unzip_btn)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def set_bbox_from_zone(self, zone):
        bbox = BBOX_PREDEFINIDAS[zone]
        self.bbox_edit.setText(bbox)
        self.bbox_edit.setEnabled(zone == "Personalizada")

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", self.dir_edit.text())
        if folder:
            self.dir_edit.setText(folder)

    def append_log(self, text):
        self.log.append(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def download(self):
        product_name = self.product_combo.currentText()
        product_id = colecciones[product_name]
        dtstart = self.start_edit.dateTime().toPyDateTime()
        dtend = self.end_edit.dateTime().toPyDateTime()
        bbox = self.bbox_edit.text().strip()
        output_dir = self.dir_edit.text()
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        self.append_log(f"Inicio descarga: {product_name}\n{dtstart} a {dtend}\nBBox: {bbox}\nDestino: {output_dir}")
        thread = DownloaderThread(self, product_id, dtstart, dtend, bbox, output_dir)
        thread.start()

    def lanzar_descompresion(self):
        raiz = self.dir_edit.text()
        thread = DescompresionThread(self, raiz)
        thread.start()

    def start_scan(self):
        self.scan_active = True
        self.start_scan_btn.setEnabled(False)
        self.stop_scan_btn.setEnabled(True)
        self.append_log("¡Escaneo automático iniciado para TODOS los productos!")
        self._scan_thread = threading.Thread(target=self.scan_loop, daemon=True)
        self._scan_thread.start()

    def stop_scan(self):
        self.scan_active = False
        self.start_scan_btn.setEnabled(True)
        self.stop_scan_btn.setEnabled(False)
        self.append_log("Escaneo automático detenido.")

    def scan_loop(self):
        INTERVALO = 15 * 60  # 15 minutos
        bbox = self.bbox_edit.text().strip()
        output_dir = self.dir_edit.text()
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        while self.scan_active:
            ahora = datetime.utcnow()
            inicio = datetime.combine(ahora.date(), time.min)
            fin = ahora
            self.append_log(f"\n--- ESCANEO: {ahora.strftime('%Y-%m-%d %H:%M:%S')} UTC ---")
            try:
                token = eumdac.AccessToken(credentials)
                datastore = eumdac.DataStore(token)
                for nombre, coll_id in colecciones.items():
                    self.append_log(f">>> Buscando en colección: {nombre} ({coll_id})")
                    try:
                        collection = datastore.get_collection(coll_id)
                        products = collection.search(bbox=bbox, dtstart=inicio, dtend=fin)
                        descargados = 0
                        for product in products:
                            size_bytes = getattr(product, "size", None)
                            if size_bytes is not None and size_bytes > MAX_SIZE:
                                self.append_log(
                                    f"Omitido (> {size_bytes/(1024*1024):.1f} MB): {getattr(product, 'name', str(product))}")
                                continue
                            with product.open() as fsrc:
                                file_path = os.path.join(output_dir, fsrc.name)
                                if os.path.exists(file_path):
                                    self.append_log(f"Ya descargado: {fsrc.name}")
                                    continue
                                with open(file_path, mode='wb') as fdst:
                                    shutil.copyfileobj(fsrc, fdst)
                                self.append_log(f'Descargado: {fsrc.name}')
                                descargados += 1
                        if descargados == 0:
                            self.append_log("No hay productos nuevos en esta colección.")
                    except Exception as e:
                        self.append_log(f"Error accediendo a la colección {coll_id}: {e}")
                self.append_log("--- DESCARGA FINALIZADA ---")
            except Exception as e:
                self.append_log(f"Error general en el escaneo: {e}")

            for _ in range(INTERVALO):
                if not self.scan_active:
                    break
                threading.Event().wait(1)
        self.append_log("Escaneo finalizado.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
