import sqlite3
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np
import tqdm
import xxhash
import xarray as xr
from netCDF4 import Dataset
from dateutil import parser
import re
from backend.config import DATA_DIR, DB_PATH
from core.helpers import find_lat_lon
from config import VARIABLES_ALIAS

MAX_SIZE_MB = 700

_HAS_DASK = False
try:
    import dask  # noqa: F401
    _HAS_DASK = True
except ModuleNotFoundError:
    pass

# Lista de nombres de archivos que no se deben procesar
BLACKLIST = [
    "geodetic_in",  
    "FRP_SWIR500m",
    "time_cordinates",
    "geo:"
    "trsp",
    "w_aer",
    "tie_geo_coordinates",
    "tie_meteo",
    "wqsf",
    "tsm_nn",

]
    
def extract_times_from_filename(nc_path: Path) -> Tuple[str, str]:
    name = nc_path.stem
    match = re.search(r"(\d{8}T\d{6})_(\d{8}T\d{6})", name)
    if match:
        try:
            dt1 = parser.isoparse(match.group(1)).strftime("%Y-%m-%dT%H:%M:%S")
            dt2 = parser.isoparse(match.group(2)).strftime("%Y-%m-%dT%H:%M:%S")
            return dt1, dt2
        except Exception:
            return "", ""
    return "", ""

def walk_all_variables(nc_group):
    names = set()
    for var in nc_group.variables:
        names.add(var)
    for subgroup in getattr(nc_group, "groups", {}).values():
        names |= walk_all_variables(subgroup)
    return names

def normalize_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        dt = parser.isoparse(value)
    except Exception:
        try:
            dt = parser.parse(value)
        except Exception:
            return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def extract_bbox_fallback(nc: Dataset) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    def find_coord_array(grp, coord_names):
        for name in coord_names:
            if name in grp.variables:
                return grp.variables[name][:]
        for subgrp in getattr(grp, "groups", {}).values():
            result = find_coord_array(subgrp, coord_names)
            if result is not None:
                return result
        return None

    lat_names = ["lat", "latitude", "LATITUDE", "LAT"]
    lon_names = ["lon", "longitude", "LONGITUDE", "LON"]

    lat_arr = find_coord_array(nc, lat_names)
    lon_arr = find_coord_array(nc, lon_names)

    if lat_arr is not None and lon_arr is not None:
        return float(np.nanmin(lat_arr)), float(np.nanmax(lat_arr)), float(np.nanmin(lon_arr)), float(np.nanmax(lon_arr))

    return None, None, None, None

def extract_metadata(nc_path: Path) -> Tuple[List[Tuple], List[Tuple]] | Tuple[Exception, None]:
    if nc_path.stat().st_size > MAX_SIZE_MB * 1024 * 1024:
        print(f"[extract_metadata] ⚠ Archivo demasiado grande: {nc_path.name} ({nc_path.stat().st_size / (1024*1024):.2f} MB)")
        return [], []

    try:
        metas: List[Tuple] = []
        bboxes: List[Tuple] = []

        try:
            ds_xr = xr.open_dataset(nc_path, decode_times=False, mask_and_scale=False)
            try:
                lat_name, lon_name = find_lat_lon(ds_xr)
                lat_arr = ds_xr[lat_name].values
                lon_arr = ds_xr[lon_name].values
            except ValueError:
                corner_lat_vars = sorted([v for v in ds_xr.variables if "pixel_corner_latitude_Corner" in v])
                corner_lon_vars = sorted([v for v in ds_xr.variables if "pixel_corner_longitude_Corner" in v])
                if len(corner_lat_vars) == 4 and len(corner_lon_vars) == 4:
                    lat_corners = np.array([ds_xr[v].values for v in corner_lat_vars])
                    lon_corners = np.array([ds_xr[v].values for v in corner_lon_vars])
                    lat_arr = np.nanmean(lat_corners, axis=0)
                    lon_arr = np.nanmean(lon_corners, axis=0)
                else:
                    raise ValueError("Ni coordenadas CF ni variables de esquinas encontradas")
            lat_min = float(np.nanmin(lat_arr))
            lat_max = float(np.nanmax(lat_arr))
            lon_min = float(np.nanmin(lon_arr))
            lon_max = float(np.nanmax(lon_arr))
            ds_xr.close()
        except Exception:
            with Dataset(nc_path) as nc:
                lat_min, lat_max, lon_min, lon_max = extract_bbox_fallback(nc)

        size_bytes = nc_path.stat().st_size
        with open(nc_path, "rb") as fbin:
            checksum = xxhash.xxh64_hexdigest(fbin.read(8192))

        with Dataset(nc_path) as nc:
            vars_in_nc = walk_all_variables(nc)
            matched_vars = [v for v in vars_in_nc if v in VARIABLES_ALIAS]

            raw_start = getattr(nc, "start_time", "") or ""
            raw_end = getattr(nc, "stop_time", "")

            datetime_start = normalize_datetime(raw_start)
            datetime_end = normalize_datetime(raw_end)

            if not datetime_start or not datetime_end:
                dt1, dt2 = extract_times_from_filename(nc_path)
                datetime_start = datetime_start or dt1
                datetime_end = datetime_end or dt2

            satellite = getattr(nc, "platform", "") or getattr(nc, "source", "").split(" ")[0]
            instrument = getattr(nc, "instrument", "")

            if not matched_vars:
                return [], []

            for vname in matched_vars:
                alias_legible = VARIABLES_ALIAS[vname]
                product_name = f"{alias_legible} – {vname}"
                meta = (
                    str(nc_path),
                    product_name,
                    datetime_start,
                    datetime_end,
                    satellite,
                    instrument,
                    vname,
                    size_bytes,
                    checksum,
                )
                metas.append(meta)
                bboxes.append((lat_min, lat_max, lon_min, lon_max))

        return metas, bboxes

    except Exception as exc:
        return exc, None

def ingest(workers: Optional[int] = None):
    print("\n=== Llamando a ingest() ===")
    print(f"DATA_DIR = {DATA_DIR}")
    print(f"DB_PATH  = {DB_PATH}")
    print(f"¿Existe DATA_DIR? {DATA_DIR.exists()}")
    all_nc = [
        p for p in DATA_DIR.rglob("*.nc")
        if p.stem not in BLACKLIST
    ]
    print(f"¿# archivos .nc? {len(all_nc)}\n")

    if not all_nc:
        print(f"(No se encontraron NetCDF en {DATA_DIR})")
        return

    print(f"◼ Escaneando {len(all_nc):,} archivos con {workers or 'N'} procesos… "
          f"(dask {'ON' if _HAS_DASK else 'OFF'})\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    ins_product = (
        "INSERT OR IGNORE INTO products "
        "(file_path, product_name, datetime_start, datetime_end, satellite, instrument, product_type, size_bytes, checksum) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    ins_bbox = (
        "INSERT OR IGNORE INTO bbox_index "
        "(product_id, lat_min, lat_max, lon_min, lon_max) VALUES (?, ?, ?, ?, ?)"
    )

    batch_meta = deque()
    batch_bbox = deque()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_metadata, p): p for p in all_nc}

        for fut in tqdm.tqdm(as_completed(futures), total=len(futures), unit="file"):
            result = fut.result()
            if isinstance(result[0], Exception):
                print(f"⚠ {futures[fut].name}: {result[0]}")
                continue

            metas, bboxes = result
            for meta, bbox in zip(metas, bboxes):
                batch_meta.append(meta)
                batch_bbox.append(bbox)

            if len(batch_meta) >= 500:
                _flush(cur, ins_product, ins_bbox, batch_meta, batch_bbox)

    _flush(cur, ins_product, ins_bbox, batch_meta, batch_bbox)
    conn.commit()
    conn.close()
    print("✓ Ingesta completada\n")

def _flush(cur, ins_product: str, ins_bbox: str, metas: deque, bboxes: deque):
    while metas:
        meta = metas.popleft()
        cur.execute(ins_product, meta)
        cur.execute(
            "SELECT id FROM products WHERE file_path = ? AND product_type = ?",
            (meta[0], meta[6]),
        )
        row = cur.fetchone()
        if row is None:
            continue
        prod_id = row[0]
        lat_min, lat_max, lon_min, lon_max = bboxes.popleft()
        cur.execute(ins_bbox, (prod_id, lat_min, lat_max, lon_min, lon_max))

if __name__ == "__main__":
    import sys
    workers_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    ingest(workers_arg)
