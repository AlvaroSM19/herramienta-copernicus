import sys
import datetime as dt
import os
import sqlite3
import numpy as np
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QDateEdit, QMessageBox, QLineEdit, QProgressBar, QFileDialog, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.dates import DateFormatter
from netCDF4 import Dataset, Group
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from backend.config import DB_PATH
from config import VARIABLES_ALIAS
import imageio.v3 as iio
from config import CITY_COORDS


def walk_groups(grp: Group):
    yield grp
    for g in getattr(grp, "groups", {}).values():
        yield from walk_groups(g)

def find_var(grp: Group, name: str):
    tgt = name.lower()
    for g in walk_groups(grp):
        for vname, var in g.variables.items():
            if vname.lower() == tgt:
                return var
    raise KeyError(f"Variable '{name}' no encontrada en el NetCDF")

def coord_arr(grp: Group, coord: str):
    want_std = "latitude" if coord == "lat" else "longitude"
    aliases = ("lat", "latitude") if coord == "lat" else ("lon", "longitude")
    for g in walk_groups(grp):
        for vname, v in g.variables.items():
            if getattr(v, "standard_name", "").lower() == want_std:
                return v[:]
        for a in aliases + tuple(a.upper() for a in aliases):
            if a in g.variables:
                return g.variables[a][:]
    raise RuntimeError(f"Coordenada '{coord}' no encontrada")

def _to_masked(var):
    data = var[:].astype("float64")
    fill_val = getattr(var, "_FillValue", None)
    miss_val = getattr(var, "missing_value", None)
    if fill_val is not None:
        data = np.ma.masked_equal(data, float(fill_val))
    if miss_val is not None:
        data = np.ma.masked_equal(data, float(miss_val))
    data = np.ma.masked_where(np.abs(data) > 1e20, data)
    data = np.ma.masked_invalid(data)
    return data

def _fit_1d(lon, lat, n: int):
    # Si todo es 1D, y tamaños iguales a n, OK
    if lon.size == n and lat.size == n:
        return lon.ravel(), lat.ravel()
    # Por si acaso, recorta
    return lon.ravel()[:n], lat.ravel()[:n]

MAX_DIST_KM = 5
EARTH_RADIUS_KM = 6371
MAX_THREADS = 4

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))

def process_file(path, datestr, var_key, lat0, lon0):
    try:
        with Dataset(path) as nc:
            var = _to_masked(find_var(nc, var_key))
            lat_arr = _to_masked(coord_arr(nc, "lat"))
            lon_arr = _to_masked(coord_arr(nc, "lon"))
            if lat_arr.ndim == 1 and lon_arr.ndim == 1:
                lat2d, lon2d = np.meshgrid(lat_arr, lon_arr, indexing="ij")
            else:
                lat2d, lon2d = lat_arr, lon_arr

            dist_km = haversine(lat2d, lon2d, lat0, lon0)
            min_dist = np.min(dist_km)
            if min_dist > MAX_DIST_KM:
                return None

            var_data = np.squeeze(var)
            dist_km = np.squeeze(dist_km)
            if var_data.shape != dist_km.shape:
                matched = False
                for v in [var_data, var_data.T]:
                    for d in [dist_km, dist_km.T]:
                        if v.shape == d.shape:
                            var_data = v
                            dist_km = d
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    return None

            mask = dist_km <= MAX_DIST_KM
            masked_values = var_data[mask]
            if np.ma.count(masked_values) == 0:
                return None
            val = float(np.ma.mean(masked_values))
            dt_val = dt.datetime.fromisoformat(datestr)
            return (dt_val, val, path)
    except Exception as ex:
        print(f"[process_file] Error en archivo {path}: {ex}")
        return None

class ReportWorker(QThread):
    done = Signal(list, list, list, str)
    progress = Signal(int)
    def __init__(self, var_key, dt_start, dt_end, lat0, lon0, ciudad, files_rows):
        super().__init__()
        self.var_key = var_key
        self.dt_start = dt_start
        self.dt_end = dt_end
        self.lat0 = lat0
        self.lon0 = lon0
        self.ciudad = ciudad
        self.files_rows = files_rows
    def run(self):
        results = []
        total = len(self.files_rows)
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            futures = [
                executor.submit(process_file, path, datestr, self.var_key, self.lat0, self.lon0)
                for path, datestr in self.files_rows
            ]
            for i, fut in enumerate(as_completed(futures)):
                res = fut.result()
                if res:
                    results.append(res)
                self.progress.emit(int((i + 1) * 100 / total) if total else 100)
        results.sort()  # Por fecha
        if results:
            fechas, valores, paths = zip(*results)
        else:
            fechas, valores, paths = [], [], []
        self.done.emit(list(fechas), list(valores), list(paths), self.ciudad)

class ReportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generador de Reporte Temporal (paralelo)")
        self.resize(1000, 950)
        layout = QVBoxLayout(self)
        control_layout = QHBoxLayout()
        layout.addLayout(control_layout)

        control_layout.addWidget(QLabel("Variable:"))
        self.cmb_variable = QComboBox()
        for k, v in VARIABLES_ALIAS.items():
            self.cmb_variable.addItem(v, userData=k)
        control_layout.addWidget(self.cmb_variable)

        control_layout.addWidget(QLabel("Inicio:"))
        self.date_start = QDateEdit()
        self.date_start.setDate(dt.date.today() - dt.timedelta(days=30))
        self.date_start.setCalendarPopup(True)
        control_layout.addWidget(self.date_start)

        control_layout.addWidget(QLabel("Fin:"))
        self.date_end = QDateEdit()
        self.date_end.setDate(dt.date.today())
        self.date_end.setCalendarPopup(True)
        control_layout.addWidget(self.date_end)

        control_layout.addWidget(QLabel("Ciudad:"))
        self.cmb_city = QComboBox()
        for city in CITY_COORDS:
            self.cmb_city.addItem(city)
        control_layout.addWidget(self.cmb_city)

        self.lat_input = QLineEdit()
        self.lat_input.setPlaceholderText("Lat")
        self.lat_input.setFixedWidth(80)
        control_layout.addWidget(self.lat_input)

        self.lon_input = QLineEdit()
        self.lon_input.setPlaceholderText("Lon")
        self.lon_input.setFixedWidth(80)
        control_layout.addWidget(self.lon_input)

        self.btn_generate = QPushButton("Generar Reporte")
        self.btn_generate.clicked.connect(self.generate_report)
        control_layout.addWidget(self.btn_generate)

        self.btn_anim = QPushButton("Descargar animación")
        self.btn_anim.setEnabled(False)
        self.btn_anim.clicked.connect(self.save_animation)
        control_layout.addWidget(self.btn_anim)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.canvas = FigureCanvas(plt.Figure(figsize=(6, 4)))
        layout.addWidget(self.canvas)
        self.ax = self.canvas.figure.subplots()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(QLabel("Log de proceso"))
        layout.addWidget(self.log_text)

        self.anim_paths = []
        self.anim_dates = []
        self.var_key = None
        self.anim_lat0 = None
        self.anim_lon0 = None
        self.worker = None

    def log(self, msg):
        now = dt.datetime.now().strftime("%H:%M:%S")
        text = f"[{now}] {msg}"
        print(text)
        self.log_text.append(text)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def generate_report(self):
        var_key = self.cmb_variable.currentData()
        start_date = self.date_start.date().toPython()
        end_date = self.date_end.date().toPython()
        city = self.cmb_city.currentText()
        lat0, lon0 = CITY_COORDS.get(city, (None, None))
        if city == "Personalizado":
            try:
                lat0 = float(self.lat_input.text())
                lon0 = float(self.lon_input.text())
            except ValueError:
                QMessageBox.warning(self, "Error", "Coordenadas inválidas para 'Personalizado'.")
                self.log("Error: Coordenadas personalizadas inválidas.")
                return
        if lat0 is None or lon0 is None:
            QMessageBox.warning(self, "Error", f"No se encontró la ciudad {city}.")
            self.log(f"Error: Ciudad no encontrada: {city}")
            return
        delta_deg = MAX_DIST_KM / 111
        min_lat = lat0 - delta_deg
        max_lat = lat0 + delta_deg
        min_lon = lon0 - delta_deg
        max_lon = lon0 + delta_deg
        dt_start = dt.datetime.combine(start_date, dt.time(0, 0))
        dt_end = dt.datetime.combine(end_date, dt.time(23, 59))
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT p.file_path, p.datetime_start
            FROM products p
            JOIN bbox_index b ON b.product_id = p.id
            WHERE p.product_type = ?
            AND p.datetime_start BETWEEN ? AND ?
            AND b.lat_max >= ? AND b.lat_min <= ?
            AND b.lon_max >= ? AND b.lon_min <= ?
            ORDER BY p.datetime_start ASC
        """, (
            var_key,
            dt_start.isoformat(),
            dt_end.isoformat(),
            min_lat, max_lat,
            min_lon, max_lon
        ))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            QMessageBox.information(self, "Sin datos", "No se encontraron productos en el rango y zona indicados.")
            self.log("No se encontraron productos para los filtros indicados.")
            return
        self.ax.clear()
        self.ax.set_title("Cargando...")
        self.canvas.draw()
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.btn_generate.setEnabled(False)
        self.btn_anim.setEnabled(False)
        self.var_key = var_key
        self.anim_lat0 = lat0
        self.anim_lon0 = lon0
        self.log(f"Iniciando reporte de {len(rows)} productos")
        self.worker = ReportWorker(var_key, dt_start, dt_end, lat0, lon0, city, rows)
        self.worker.done.connect(self._on_worker_done)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.start()

    @Slot(list, list, list, str)
    def _on_worker_done(self, dates, values, paths, city):
        self.progress.setVisible(False)
        self.btn_generate.setEnabled(True)
        if not dates:
            QMessageBox.warning(self, "Advertencia", "No se pudieron procesar archivos válidos. Verifique el log para más detalles.")
            self.btn_anim.setEnabled(False)
            self.log("No se pudieron procesar archivos válidos.")
            return
        self.ax.clear()
        self.ax.plot(dates, values, marker='o')
        self.ax.set_title(f"Evolución en {city} de {VARIABLES_ALIAS.get(self.cmb_variable.currentData(), self.cmb_variable.currentText())}")
        self.ax.set_xlabel("Fecha")
        self.ax.set_ylabel("Valor promedio en zona")
        self.ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
        self.ax.tick_params(axis='x', rotation=45)
        self.canvas.draw()
        self.anim_paths = paths
        self.anim_dates = dates
        self.btn_anim.setEnabled(True)
        self.log("Reporte generado correctamente.")

    def _plot_product_robust(self, ax, path, var_key, vmin, vmax, bbox, fecha):
        # Lógica equivalente a VisualizerWindow._draw_plot()
        with Dataset(path) as nc:
            var = _to_masked(find_var(nc, var_key))
            lat_arr = _to_masked(coord_arr(nc, "lat"))
            lon_arr = _to_masked(coord_arr(nc, "lon"))
            var = np.squeeze(var)
            lat_arr = np.squeeze(lat_arr)
            lon_arr = np.squeeze(lon_arr)
            # Hay muchos posibles casos:
            if var.ndim == 2:
                # Caso habitual
                if lat_arr.ndim == lon_arr.ndim == 1:
                    lon2, lat2 = np.meshgrid(lon_arr, lat_arr)
                elif lat_arr.ndim == lon_arr.ndim == 2:
                    lon2, lat2 = lon_arr, lat_arr
                else:
                    raise ValueError("Dimensiones incompatibles")
                # Si forma no cuadra, prueba trasponer
                if var.shape != lat2.shape:
                    if var.shape == lon2.shape:
                        var = var.T
                    else:
                        # Fallback: scatter plano
                        lon1, lat1 = _fit_1d(lon_arr, lat_arr, var.size)
                        sc = ax.scatter(
                            lon1, lat1,
                            c=var.ravel(),
                            s=3,
                            cmap="viridis",
                            vmin=vmin, vmax=vmax,
                            transform=ccrs.PlateCarree(),
                        )
                        return sc
                return ax.pcolormesh(
                    lon2, lat2, var,
                    shading="auto",
                    cmap="viridis",
                    vmin=vmin, vmax=vmax,
                    transform=ccrs.PlateCarree(),
                )
            # Si var es 1D, intenta scatter
            lon1, lat1 = _fit_1d(lon_arr, lat_arr, var.size)
            sc = ax.scatter(
                lon1, lat1,
                c=var.ravel(),
                s=3,
                cmap="viridis",
                vmin=vmin, vmax=vmax,
                transform=ccrs.PlateCarree(),
            )
            return sc

    def save_animation(self):
        
        if not self.anim_paths:
            QMessageBox.warning(self, "Animación", "No hay productos para animar.")
            self.log("No hay productos para animar.")
            return

        var_key = self.var_key
        lat0, lon0 = self.anim_lat0, self.anim_lon0
        delta = 5.0
        bbox = [lon0 - delta, lon0 + delta, lat0 - delta, lat0 + delta]  # [W, E, S, N]
        productos_validos = []
        fechas_validas = []
        vmin, vmax = None, None
        self.log("Calculando rango de color global...")
        for path, fecha in zip(self.anim_paths, self.anim_dates):
            try:
                with Dataset(path) as nc:
                    var = _to_masked(find_var(nc, var_key))
                    if var is None or np.ma.count(var) == 0:
                        self.log(f"Archivo vacío o inválido: {path}")
                        continue
                    dmin = float(np.nanmin(var))
                    dmax = float(np.nanmax(var))
                    if vmin is None or dmin < vmin:
                        vmin = dmin
                    if vmax is None or dmax > vmax:
                        vmax = dmax
                    productos_validos.append(path)
                    fechas_validas.append(fecha)
            except Exception as ex:
                self.log(f"Error leyendo {path}: {ex}")
                continue

        if not productos_validos or vmin is None or vmax is None or vmin == vmax:
            QMessageBox.warning(self, "Animación", "No se encontraron productos válidos para la animación o el rango de colores es inválido.")
            self.log("No se encontraron productos válidos para la animación.")
            return

        fname, _ = QFileDialog.getSaveFileName(self, "Guardar animación", "", "Video MP4 (*.mp4)")
        if not fname:
            self.log("Usuario canceló la selección de archivo.")
            return

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        import tempfile

        tmpdir = tempfile.mkdtemp(prefix="animframes_")
        self.log(f"Generando frames PNG temporales en directorio temporal: {tmpdir}")

        frame_files = []
        for idx, (path, fecha) in enumerate(zip(productos_validos, fechas_validas)):
            try:
                fig = plt.figure(figsize=(8,7))
                ax = fig.add_subplot(1,1,1, projection=ccrs.PlateCarree())
                ax.set_extent(bbox, crs=ccrs.PlateCarree())
                ax.add_feature(cfeature.COASTLINE)
                ax.add_feature(cfeature.BORDERS, linestyle=':')
                ax.add_feature(cfeature.LAND, facecolor='lightgray')
                mappable = self._plot_product_robust(ax, path, var_key, vmin, vmax, bbox, fecha)
                if mappable is not None:
                    cbar = fig.colorbar(mappable, ax=ax, orientation="vertical", pad=0.01, aspect=30)
                ax.set_title(f"{VARIABLES_ALIAS.get(var_key,var_key)} - {fecha.strftime('%Y-%m-%d %H:%M')}")
                outname = os.path.join(tmpdir, f"frame_{idx:04d}.png")
                fig.savefig(outname, dpi=100, bbox_inches="tight")
                plt.close(fig)
                frame_files.append(outname)
            except Exception as ex:
                self.log(f"Error generando frame {idx}: {ex}")

        if not frame_files:
            QMessageBox.warning(self, "Animación", "No se pudo generar ningún frame de la animación.")
            self.log("No se pudo generar ningún frame.")
            return

        self.log("Montando vídeo con imageio...")
        try:
            # Lee todos los frames y asegúrate de que todos tengan el mismo tamaño
            images = [iio.imread(f) for f in frame_files]
            # Si los tamaños no coinciden, redimensiona al menor
            min_shape = min((im.shape[0], im.shape[1]) for im in images)
            images = [im[:min_shape[0], :min_shape[1], ...] for im in images]
            iio.imwrite(fname, images, fps=1, codec="libx264", quality=8)  # Puedes ajustar el fps si quieres
            self.log("Vídeo generado correctamente con imageio.")
            QMessageBox.information(self, "Animación", f"Animación guardada correctamente en:\n{fname}")
        except Exception as e:
            self.log(f"Error con imageio: {e}")
            QMessageBox.warning(self, "Error", f"No se pudo guardar la animación con imageio:\n{e}")

        # Limpieza
        try:
            for f in frame_files:
                os.remove(f)
            os.rmdir(tmpdir)
            self.log("Frames temporales eliminados.")
        except Exception as ex:
            self.log(f"No se pudo limpiar temp: {ex}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = ReportDialog()
    dlg.show()
    sys.exit(app.exec())
