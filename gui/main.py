#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CopernicusTool GUI (versión multiventana)
=====================================

Aplicación de escritorio en PySide 6 para explorar, filtrar y visualizar
archivos NetCDF de los satélites Sentinel (por ejemplo Sentinel-5P/TROPOMI).

Incluye:
- Apertura simultánea de varias visualizaciones independientes.
"""

# ----------------------------------------------------------------------
#  Importaciones estándar
# ----------------------------------------------------------------------
from __future__ import annotations
from config import CITY_COORDS
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# ----------------------------------------------------------------------
#  Librerías de terceros
# ----------------------------------------------------------------------
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import numpy as np
import requests
import sqlite3
from dateutil import parser
from geopy.distance import geodesic
from netCDF4 import Dataset, Group
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableView,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)

# ----------------------------------------------------------------------
#  Utilidades / Configuración del proyecto
# ----------------------------------------------------------------------
from config import VARIABLES_ALIAS, SATELLITE_ALIAS
from backend.config import DB_PATH
from gui.report_dialog import ReportDialog

MAX_PIXELS = 5_000_000              # submuestreo para evitar imágenes gigantes
API_URL   = "http://localhost:8000" # endpoint de la API interna FastAPI

INTERNAL_BY_HUMAN = {
    alias.lower(): internal
    for internal, alias in VARIABLES_ALIAS.items()
}
CATEGORIES_HUMAN = sorted(VARIABLES_ALIAS.values())

# ======================================================================
#  Funciones auxiliares generales
# ======================================================================

def reset_database() -> tuple[bool, str]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("DELETE FROM products")
        cur.execute("DELETE FROM bbox_index")
        conn.commit()
        conn.close()
        return True, "Base de datos reiniciada correctamente."
    except Exception as e:
        return False, str(e)

def iso_to_human(iso_str: str) -> str:
    try:
        dt_obj = parser.isoparse(iso_str)
        return dt_obj.strftime("%d %b %Y, %H:%M:%S")
    except Exception:
        return iso_str

# ----------------------------------------------------------------------
#  Funciones auxiliares para NetCDF
# ----------------------------------------------------------------------

def walk_groups(grp: Group):
    yield grp
    for g in grp.groups.values():
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
    aliases  = ("lat", "latitude") if coord == "lat" else ("lon", "longitude")
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

def _fit_1d(lon, lat, n: int) -> Tuple[np.ndarray, np.ndarray]:
    if lon.size == n and lat.size == n:
        return lon.ravel(), lat.ravel()
    return lon.ravel()[:n], lat.ravel()[:n]

# ----------------------------------------------------------------------
#  Estimar resolución espacial (mejorado, robusto)
# ----------------------------------------------------------------------

def _angular_to_km(dlat_deg: float,
                   dlon_deg: float,
                   ref_lat_deg: float) -> tuple[float, float]:
    km_per_deg = 111.32
    dlat_km = abs(dlat_deg) * km_per_deg
    dlon_km = abs(dlon_deg) * km_per_deg * np.cos(np.deg2rad(ref_lat_deg))
    return dlat_km, dlon_km

def _estimate_resolution(lat_arr: np.ndarray, lon_arr: np.ndarray) -> tuple[float, float] | None:
    lat = np.ma.asarray(lat_arr).squeeze()
    lon = np.ma.asarray(lon_arr).squeeze()
    if lat.ndim == lon.ndim == 1 and lat.size > 1 and lon.size > 1:
        dlat_med = np.median(np.diff(lat))
        dlon_med = np.median(np.diff(lon))
        ref_lat  = np.median(lat)
        return _angular_to_km(dlat_med, dlon_med, ref_lat)
    if lat.ndim == lon.ndim == 2 and lat.shape == lon.shape:
        n_lines, n_pixels = lat.shape
        points = [
            (0, 0),
            (n_lines // 2, n_pixels // 2),
            (n_lines - 2, n_pixels // 2),
            (n_lines // 2, n_pixels - 2),
        ]
        dx = []
        dy = []
        for i, j in points:
            if j < n_pixels - 1:
                p1 = (lat[i, j], lon[i, j])
                p2 = (lat[i, j+1], lon[i, j+1])
                try:
                    dx.append(geodesic(p1, p2).km)
                except Exception:
                    pass
            if i < n_lines - 1:
                p1 = (lat[i, j], lon[i, j])
                p2 = (lat[i+1, j], lon[i+1, j])
                try:
                    dy.append(geodesic(p1, p2).km)
                except Exception:
                    pass
        dx_med = float(np.mean(dx)) if dx else None
        dy_med = float(np.mean(dy)) if dy else None
        if dx_med is not None and dy_med is not None:
            return (dy_med, dx_med)
    return None

# ======================================================================
#  Modelo Qt para QTableView
# ======================================================================

class ItemModel(QAbstractTableModel):
    headers = ["id", "product_name", "datetime_start", "satellite", "product_type"]

    def __init__(self, data: List[dict]) -> None:
        super().__init__()
        self._data = data

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)
    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)
    def data(self, index, role):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        key = self.headers[index.column()]
        raw = self._data[index.row()].get(key, "")
        if key == "datetime_start" and isinstance(raw, str):
            return iso_to_human(raw)
        if key == "satellite" and isinstance(raw, str):
            return SATELLITE_ALIAS.get(raw.lower(), raw).title()
        if key == "product_type" and isinstance(raw, str):
            return VARIABLES_ALIAS.get(raw, raw)
        return str(raw)
    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            hdr = self.headers[section]
            if hdr == "datetime_start":
                return "Date"
            if hdr == "product_type":
                return "Category"
            return hdr.replace("_", " ").title()
        return None
    def set_data(self, data: List[dict]) -> None:
        self.beginResetModel()
        self._data = data
        self.endResetModel()
    def item_at(self, row: int) -> dict:
        return self._data[row]

# ======================================================================
#  Thread trabajador que lee el NetCDF
# ======================================================================

class PlotWorker(QObject):
    finished = Signal()
    error    = Signal(str)
    draw     = Signal(object, object, object, object, str)

    def __init__(self, ruta_nc: str, variable: str):
        super().__init__()
        self.ruta_nc = ruta_nc
        self.variable = variable

    def run(self):
        try:
            with Dataset(self.ruta_nc) as nc:
                var = _to_masked(find_var(nc, self.variable))
                if var.ndim > 2:
                    var = var[0]
                lat_arr = _to_masked(coord_arr(nc, "lat"))
                lon_arr = _to_masked(coord_arr(nc, "lon"))
            if var.size > MAX_PIXELS:
                factor   = int(np.sqrt(var.size / MAX_PIXELS)) + 1
                var      = var[::factor, ::factor]
                lat_arr  = (lat_arr[::factor, ::factor] if lat_arr.ndim == 2
                            else lat_arr[::factor])
                lon_arr  = (lon_arr[::factor, ::factor] if lon_arr.ndim == 2
                            else lon_arr[::factor])
            self.draw.emit(var, lat_arr, lon_arr, None, self.variable)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# ======================================================================
#  Ventana de visualización individual
# ======================================================================

class VisualizerWindow(QDialog):
    def __init__(
        self,
        nc_path: str,
        variable: str,
        category: str,
        satellite: str,
        parent: Optional[QWidget] = None,
        zoom_extent: Optional[list[float]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{satellite}  |  {category}")
        self.resize(900, 600)
        self.zoom_extent = zoom_extent

        layout      = QVBoxLayout(self)
        self._fig   = plt.figure(figsize=(8, 5))
        self._cavas = FigureCanvas(self._fig)
        self._tb    = NavigationToolbar(self._cavas, self)

        layout.addWidget(self._tb)
        layout.addWidget(self._cavas)

        self.worker = PlotWorker(nc_path, variable)
        self.thread = QThread()

        self.worker.moveToThread(self.thread)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self._on_error)
        self.worker.draw.connect(self._draw_plot)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Error al leer NetCDF", msg)
        self.thread.quit()

    def _draw_plot(self, var, lat_arr, lon_arr, _, variable):
        self._fig.clear()
        ax = self._fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.coastlines(resolution="10m")
        ax.add_feature(cfeature.BORDERS, linestyle=":")
        ax.add_feature(cfeature.LAND, facecolor="lightgray")
        ax.gridlines(draw_labels=True, linewidth=0.4, alpha=0.5)

        if var.ndim == 2:
            if lat_arr.ndim == lon_arr.ndim == 1:
                lon2, lat2 = np.meshgrid(lon_arr, lat_arr)
            else:
                lon2, lat2 = lon_arr, lat_arr
            if var.shape != lat2.shape:
                if var.shape == lon2.shape:
                    var = var.T
                else:
                    lon1, lat1 = _fit_1d(lon_arr, lat_arr, var.size)
                    point_size = 300 if self.zoom_extent else 4
                    sc = ax.scatter(
                        lon1, lat1,
                        c=var.ravel(),
                        s=point_size,
                        cmap="viridis",
                        transform=ccrs.PlateCarree(),
                    )
                    self._finish(ax, sc, lon_arr, lat_arr, variable, var)
                    if self.zoom_extent:
                        ax.set_extent(self.zoom_extent, crs=ccrs.PlateCarree())
                    self._cavas.draw()
                    return
            sc = ax.pcolormesh(
                lon2, lat2, var,
                shading="auto",
                cmap="viridis",
                transform=ccrs.PlateCarree(),
            )
        else:
            lon1, lat1 = _fit_1d(lon_arr, lat_arr, var.size)
            sc = ax.scatter(
                lon1, lat1,
                c=var.ravel(),
                s=4,
                cmap="viridis",
                transform=ccrs.PlateCarree(),
            )
        self._finish(ax, sc, lon_arr, lat_arr, variable, var)
        if self.zoom_extent:
            ax.set_extent(self.zoom_extent, crs=ccrs.PlateCarree())
        self._cavas.draw()

    def _finish(self, ax, mappable, lon, lat, title: str, var) -> None:
        res_attr = getattr(var, "spatial_resolution", None)
        if not res_attr:
            try:
                res_attr = getattr(var.group().parent, "spatial_resolution", None)
            except Exception:
                res_attr = None
        if res_attr:
            res_str = f"Resolución nominal: {res_attr}"
        else:
            res_est = _estimate_resolution(lat, lon)
            if res_est is None:
                res_str = "Resolución: desconocida (No hay datos suficientes)."
            else:
                dlat_km, dlon_km = res_est
                res_str = (f"Resolución ≈ {dlat_km:.2f} × {dlon_km:.2f} km "
                           f"→ {(dlat_km * dlon_km):.2f} km²")
        if mappable is not None:
            self._fig.colorbar(
                mappable,
                ax=ax,
                label=title.replace("_", " ").title()
            )
        ax.set_title(f"{title.replace('_', ' ').title()}\n{res_str}")
        plt.tight_layout()

# ======================================================================
#  Ventana de visualización múltiple
# ======================================================================

class MultiVisualizerWindow(QDialog):
    def __init__(self,
                 products: list[dict],
                 variable,
                 category,
                 satellites,
                 parent=None,
                 zoom_extent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Visualización múltiple: {category}")
        self.resize(900, 600)

        layout     = QVBoxLayout(self)
        self._fig  = plt.figure(figsize=(8, 5))
        self._cavs = FigureCanvas(self._fig)
        self._tb   = NavigationToolbar(self._cavs, self)

        layout.addWidget(self._tb)
        layout.addWidget(self._cavs)

        self.visualize_all(products, variable, zoom_extent)

    def visualize_all(self, products, variable, zoom_extent):
        self._fig.clear()
        ax = self._fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.coastlines(resolution="10m")
        ax.add_feature(cfeature.BORDERS, linestyle=":")
        ax.add_feature(cfeature.LAND, facecolor="lightgray")
        ax.gridlines(draw_labels=True, linewidth=0.4, alpha=0.5)
        mappable = None

        all_vals = []
        for prod in products:
            nc_path = prod.get("file_path", "")
            try:
                with Dataset(nc_path) as nc:
                    var = _to_masked(find_var(nc, variable))
                    var = np.squeeze(var)
                    all_vals.append(var.compressed())
            except Exception:
                pass

        if not all_vals:
            QMessageBox.warning(self, "Sin datos",
                                "No se pueden leer datos de los productos seleccionados.")
            return

        all_vals_flat = np.concatenate(all_vals)
        vmin = float(np.nanmin(all_vals_flat))
        vmax = float(np.nanmax(all_vals_flat))

        for prod in products:
            nc_path = prod.get("file_path", "")
            try:
                with Dataset(nc_path) as nc:
                    var = _to_masked(find_var(nc, variable))
                    var = np.squeeze(var)

                    lat_arr = _to_masked(coord_arr(nc, "lat"))
                    lon_arr = _to_masked(coord_arr(nc, "lon"))
                    lat_arr = np.squeeze(lat_arr)
                    lon_arr = np.squeeze(lon_arr)

                    if lat_arr.ndim == lon_arr.ndim == 1:
                        if (var.ndim == 2 and var.shape == (lat_arr.size, lon_arr.size)):
                            lon2, lat2 = np.meshgrid(lon_arr, lat_arr)
                            mappable = ax.pcolormesh(
                                lon2, lat2, var,
                                shading="auto",
                                cmap="viridis",
                                vmin=vmin, vmax=vmax,
                                transform=ccrs.PlateCarree(),
                            )
                        elif (var.ndim == 1 and var.size == lat_arr.size == lon_arr.size):
                            mappable = ax.scatter(
                                lon_arr, lat_arr,
                                c=var,
                                cmap="viridis",
                                s=3,
                                vmin=vmin, vmax=vmax,
                                transform=ccrs.PlateCarree(),
                            )
                    elif lat_arr.ndim == lon_arr.ndim == 2:
                        mappable = ax.pcolormesh(
                            lon_arr, lat_arr, var,
                            shading="auto",
                            cmap="viridis",
                            vmin=vmin, vmax=vmax,
                            transform=ccrs.PlateCarree(),
                        )
            except Exception as e:
                print(f"Error visualizando {nc_path}: {e}")

        if zoom_extent:
            ax.set_extent(zoom_extent, crs=ccrs.PlateCarree())

        if mappable is not None:
            self._fig.colorbar(
                mappable,
                ax=ax,
                label=variable.replace("_", " ").title()
            )
        ax.set_title(f"Productos seleccionados superpuestos ({len(products)})")
        self._cavs.draw()

# ======================================================================
#  IngestThread
# ======================================================================

class IngestThread(QThread):
    finished_ingest = Signal()
    error_ingest    = Signal(str)

    def __init__(self, workers: Optional[int] = None) -> None:
        super().__init__()
        self.workers = workers

    def run(self) -> None:
        try:
            from backend.scanner.ingest import ingest
            ingest(workers=self.workers)
            self.finished_ingest.emit()
        except Exception as e:
            self.error_ingest.emit(str(e))

# ======================================================================
#  Ventana principal de la aplicación
# ======================================================================

class Main(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Herramienta de visualización Copernicus")
        self.resize(1_000, 600)

        # Lista para guardar ventanas abiertas
        self._ventanas_abiertas = []

        central      = QWidget()
        main_layout  = QVBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        filtro_frame  = QWidget()
        filtro_layout = QHBoxLayout()
        filtro_frame.setLayout(filtro_layout)
        main_layout.addWidget(filtro_frame)

        filtro_layout.addWidget(QLabel("Inicio:"))
        self.start = QDateEdit()
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd")
        self.start.setDate(dt.date.today() - dt.timedelta(days=30))
        filtro_layout.addWidget(self.start)

        filtro_layout.addWidget(QLabel("Fin:"))
        self.end = QDateEdit()
        self.end.setCalendarPopup(True)
        self.end.setDisplayFormat("yyyy-MM-dd")
        self.end.setDate(dt.date.today())
        filtro_layout.addWidget(self.end)

        filtro_layout.addWidget(QLabel("Categoría:"))
        self.cmb_category = QComboBox()
        self.cmb_category.addItem("")
        added = set()
        for alias in VARIABLES_ALIAS.values():
            if alias.lower() not in added:
                self.cmb_category.addItem(alias)
                added.add(alias.lower())
        filtro_layout.addWidget(self.cmb_category)

        filtro_layout.addWidget(QLabel("Máx. resultados:"))
        self.spn_limit = QSpinBox()
        self.spn_limit.setRange(0, 10_000)
        self.spn_limit.setValue(500)
        filtro_layout.addWidget(self.spn_limit)

        self.search = QPushButton("Buscar")
        self.search.clicked.connect(self.query)
        filtro_layout.addWidget(self.search)

        self.clear_btn = QPushButton("Limpiar filtros")
        self.clear_btn.clicked.connect(self.clear_filters)
        filtro_layout.addWidget(self.clear_btn)

        filtro_layout.addWidget(QLabel("Área:"))
        self.cmb_area = QComboBox()
        self.cmb_area.addItems([
            "Global", "Solo Asturias", "Solo España", "Solo Europa"
        ])
        filtro_layout.addWidget(self.cmb_area)

        self.update_btn = QPushButton("Actualizar BD")
        self.update_btn.clicked.connect(self.update_db)
        filtro_layout.addWidget(self.update_btn)

        self.reset_btn = QPushButton("Resetear BD")
        self.reset_btn.clicked.connect(self.reset_db)
        filtro_layout.addWidget(self.reset_btn)

        self.btn_report = QPushButton("Generar Reporte")
        self.btn_report.clicked.connect(self._on_generate_report)
        main_layout.addWidget(self.btn_report)

        self.btn_downloader = QPushButton("Lanzar Downloader")
        self.btn_downloader.clicked.connect(self.lanzar_downloader)
        main_layout.addWidget(self.btn_downloader)

        self.btn_api = QPushButton("Lanzar API")
        self.btn_api.clicked.connect(self.lanzar_api)
        main_layout.addWidget(self.btn_api)

        self.table = QTableView()
        self.model = ItemModel([])
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self.btn_vis = QPushButton("Visualizar")
        self.btn_vis.setEnabled(False)
        self.btn_vis.clicked.connect(self._on_visualize)
        main_layout.addWidget(self.btn_vis)

        self.btn_vis_multi = QPushButton("Visualizar seleccionados")
        self.btn_vis_multi.setEnabled(False)
        self.btn_vis_multi.clicked.connect(self._on_visualize_multi)
        main_layout.addWidget(self.btn_vis_multi)

        self.btn_vis_ast = QPushButton("Visualizar Asturias")
        self.btn_vis_ast.setEnabled(False)
        self.btn_vis_ast.clicked.connect(self._on_visualize_asturias)
        main_layout.addWidget(self.btn_vis_ast)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.ingest_thread: Optional[IngestThread] = None

    def _on_generate_report(self):
        dlg = ReportDialog(self)
        dlg.show()
        self._ventanas_abiertas.append(dlg)
        dlg.destroyed.connect(lambda: self._ventanas_abiertas.remove(dlg))

    def reset_db(self):
        confirm = QMessageBox.question(
            self, "Confirmar reseteo",
            "¿Estás seguro de que quieres borrar todo el contenido de la base de datos?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            ok, msg = reset_database()
            if ok:
                QMessageBox.information(self, "BD reiniciada", msg)
                self.clear_filters()
            else:
                QMessageBox.critical(self, "Error", msg)

    def _on_selection_changed(self):
        has_sel = self.table.selectionModel().hasSelection()
        self.btn_vis.setEnabled(has_sel)
        self.btn_vis_ast.setEnabled(has_sel)
        self.btn_vis_multi.setEnabled(has_sel
                                      and len(self.table.selectionModel().selectedRows()) > 1)

    def lanzar_downloader(self):
        script_path = os.path.join(os.getcwd(), "downloader", "eumet_gui.py")
        if not os.path.exists(script_path):
            QMessageBox.warning(self, "Downloader no encontrado",
                                f"No se encuentra {script_path}")
            return
        if sys.platform == "win32":
            subprocess.Popen([
                sys.executable, "-m", "downloader.eumet_gui"
            ], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([sys.executable, "-m", "downloader.eumet_gui"])

    def lanzar_api(self):
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "backend.api.main:app",
                     "--port", "8000"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "backend.api.main:app",
                     "--port", "8000"]
                )
        except Exception as e:
            QMessageBox.warning(self, "Error al lanzar API", str(e))

    def query(self):
        params: dict[str, str | int] = {}

        if (limit_val := self.spn_limit.value()) > 0:
            params["limit"] = limit_val

        start_date = dt.datetime.combine(self.start.date().toPython(), dt.time.min).isoformat()
        end_date   = dt.datetime.combine(self.end.date().toPython(),   dt.time.max).isoformat()
        params["start"] = start_date
        params["end"]   = end_date

        cat_text = self.cmb_category.currentText().strip()
        if cat_text:
            for k, v in VARIABLES_ALIAS.items():
                if v.lower() == cat_text.lower():
                    params["product_type"] = k
                    break
            else:
                QMessageBox.warning(self, "Categoría no válida",
                                    f"La categoría '{cat_text}' no coincide con ninguna conocida.")
                return

        match self.cmb_area.currentText():
            case "Solo Asturias":
                params["bbox"] = "42.9,-7.3,44.1,-4.7"
            case "Solo España":
                params["bbox"] = "36.0,-9.5,43.8,3.3"
            case "Solo Europa":
                params["bbox"] = "34.0,-25.0,71.0,45.0"

        try:
            resp = requests.get(f"{API_URL}/items", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("Respuesta inesperada de la API")
            self.model.set_data(data)
            self.status.showMessage(f"× {len(data)} resultado(s)", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Error en la API", str(exc))
            self.status.showMessage("Error al recuperar datos", 5000)

    def clear_filters(self):
        self.start.setDate(dt.date.today() - dt.timedelta(days=30))
        self.end.setDate(dt.date.today())
        self.cmb_category.setCurrentIndex(0)
        self.spn_limit.setValue(0)
        self.cmb_area.setCurrentIndex(0)
        try:
            resp = requests.get(f"{API_URL}/items", params={}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError("Respuesta inesperada de la API")
            self.model.set_data(data)
            self.status.showMessage(f"× {len(data)} resultado(s) (todos)", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Error en la API", str(exc))
            self.status.showMessage("Error al recuperar datos", 5000)

    def update_db(self):
        self.update_btn.setEnabled(False)
        self.status.showMessage("Actualizando base de datos...", 5000)
        self.ingest_thread = IngestThread(workers=None)
        self.ingest_thread.finished_ingest.connect(self._on_ingest_finished)
        self.ingest_thread.error_ingest.connect(self._on_ingest_error)
        self.ingest_thread.start()

    def _on_ingest_finished(self):
        QMessageBox.information(self, "BD Actualizada",
                                "La base de datos se ha actualizado correctamente.")
        self.clear_filters()
        self.update_btn.setEnabled(True)
        self.status.clearMessage()
        if self.ingest_thread:
            self.ingest_thread.quit()
            self.ingest_thread.wait()
            self.ingest_thread = None

    def _on_ingest_error(self, err: str):
        QMessageBox.critical(self, "Error al actualizar BD", err)
        self.update_btn.setEnabled(True)
        self.status.clearMessage()
        if self.ingest_thread:
            self.ingest_thread.quit()
            self.ingest_thread.wait()
            self.ingest_thread = None

    # ------------------ Cambios para multiventana ---------------------

    def _abrir_ventana(self, ventana):
        ventana.show()
        self._ventanas_abiertas.append(ventana)
        ventana.destroyed.connect(lambda: self._ventanas_abiertas.remove(ventana))

    # Visualización individual
    def _on_visualize(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row  = sel[0].row()
        item = self.model.item_at(row)

        nc_path  = item.get("file_path", "")
        raw_sat  = item.get("satellite", "")
        raw_ptype= item.get("product_type", "")

        sat_legible = SATELLITE_ALIAS.get(raw_sat.lower(), raw_sat).title()

        if not Path(nc_path).exists():
            QMessageBox.critical(self, "Archivo no encontrado",
                                 f"El archivo asociado a este producto ha sido eliminado:\n{nc_path}"
                                 "\n\nSe eliminará de la base de datos.")
            try:
                conn = sqlite3.connect(DB_PATH)
                cur  = conn.cursor()
                cur.execute("DELETE FROM products WHERE id = ?", (item["id"],))
                cur.execute("DELETE FROM bbox_index WHERE product_id = ?", (item["id"],))
                conn.commit()
                conn.close()
            except Exception as e:
                QMessageBox.critical(self, "Error al eliminar de la BD", str(e))
            self.query()
            return

        try:
            with Dataset(nc_path) as nc:
                _ = find_var(nc, raw_ptype)
        except Exception as exc:
            QMessageBox.critical(self, "Error NetCDF",
                                 f"No se pudo localizar la variable '{raw_ptype}' en el archivo.\n{exc}")
            return

        category_legible = VARIABLES_ALIAS.get(raw_ptype, raw_ptype)

        viz = VisualizerWindow(
            nc_path, raw_ptype,
            category_legible, sat_legible,
            parent=None
        )
        self._abrir_ventana(viz)

    # Visualización múltiple
    def _on_visualize_multi(self):
        sel_rows = self.table.selectionModel().selectedRows()
        if not sel_rows:
            return
        products = [self.model.item_at(row.row()) for row in sel_rows]
        variable   = products[-1].get("product_type", "")
        satellites = ", ".join([p.get("satellite", "") for p in products])
        category   = VARIABLES_ALIAS.get(variable, variable)
        products_same_var = [p for p in products
                             if p.get("product_type", "") == variable]
        if not products_same_var:
            QMessageBox.warning(self, "Selección",
                                "No hay productos seleccionados con la misma variable.")
            return
        viz = MultiVisualizerWindow(
            products_same_var, variable,
            category, satellites,
            parent=None
        )
        self._abrir_ventana(viz)

    # Visualización Asturias (zoom)
    def _on_visualize_asturias(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        row  = sel[0].row()
        item = self.model.item_at(row)

        nc_path  = item.get("file_path", "")
        raw_sat  = item.get("satellite", "")
        raw_ptype= item.get("product_type", "")

        sat_legible = SATELLITE_ALIAS.get(raw_sat.lower(), raw_sat).title()

        if not Path(nc_path).exists():
            QMessageBox.critical(self, "Archivo no encontrado",
                                 f"El archivo asociado a este producto ha sido eliminado:\n{nc_path}"
                                 "\n\nSe eliminará de la base de datos.")
            try:
                conn = sqlite3.connect(DB_PATH)
                cur  = conn.cursor()
                cur.execute("DELETE FROM products WHERE id = ?", (item["id"],))
                cur.execute("DELETE FROM bbox_index WHERE product_id = ?", (item["id"],))
                conn.commit()
                conn.close()
            except Exception as e:
                QMessageBox.critical(self, "Error al eliminar de la BD", str(e))
            self.query()
            return

        try:
            with Dataset(nc_path) as nc:
                _ = find_var(nc, raw_ptype)
        except Exception as exc:
            QMessageBox.critical(self, "Error NetCDF",
                                 f"No se pudo localizar la variable '{raw_ptype}' en el archivo.\n{exc}")
            return

        category_legible = VARIABLES_ALIAS.get(raw_ptype, raw_ptype)

        viz = VisualizerWindow(
            nc_path, raw_ptype,
            category_legible, sat_legible,
            parent=None,
            zoom_extent=[-7.3, -4.7, 42.9, 44.1]
        )
        self._abrir_ventana(viz)

# ======================================================================
#  Punto de entrada
# ======================================================================

def main() -> None:
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
