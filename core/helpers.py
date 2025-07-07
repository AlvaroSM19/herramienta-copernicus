"""Funciones de utilidad compartidas."""
from __future__ import annotations

import re
from typing import Tuple

import xarray as xr


def find_lat_lon(ds: xr.Dataset) -> Tuple[str, str]:
    """Devuelve los nombres de las variables de latitud y longitud.

    Reconoce:
    • standard_name == latitude / longitude
    • variables nav_lat / nav_lon
    • sufijos comunes: _lat, _lon, lat, lon, latitude, longitude (case-insensitive)
    """
    # 1) CF standard_name
    lat_name = lon_name = None
    for name in ds.variables:
        std = ds[name].attrs.get("standard_name", "").lower()
        if std in {"latitude", "grid_latitude"}:
            lat_name = name
        if std in {"longitude", "grid_longitude"}:
            lon_name = name
    if lat_name and lon_name:
        return lat_name, lon_name

    # 2) nav_lat / nav_lon
    if {"nav_lat", "nav_lon"}.issubset(ds.variables):
        return "nav_lat", "nav_lon"

    # 3) regex fallback
    lat = next(
        (n for n in ds.variables if re.search(r"(?:^|[_])lat(?:itude)?$", n, re.I)), None
    )
    lon = next(
        (n for n in ds.variables if re.search(r"(?:^|[_])lon(?:gitude)?$", n, re.I)), None
    )
    if lat and lon:
        return lat, lon

    raise ValueError("No se encontraron variables de lat/lon en el NetCDF")
