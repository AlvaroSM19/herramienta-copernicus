"""Servicio REST que expone el catálogo SQLite mediante FastAPI.

Arranque rápido (raíz del proyecto, venv activo):
    uvicorn backend.api.main:app --reload --port 8000
"""
from __future__ import annotations

from typing import List, Optional

import sqlite3
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from backend.config import DB_PATH
from core.db import get_conn

app = FastAPI(title="CopernicusTool API", version="0.4.0")

# ----------------------------  Modelos  ---------------------------- #
class Item(BaseModel):
    id: int
    file_path: str
    product_name: str
    datetime_start: Optional[str]
    datetime_end: Optional[str]
    satellite: Optional[str]
    instrument: Optional[str]
    product_type: Optional[str]
    size_bytes: int

    # bounding-box (pueden ser null)
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    lon_min: Optional[float] = None
    lon_max: Optional[float] = None


# -------------------------  Dependencias  -------------------------- #
def get_cursor() -> sqlite3.Cursor:
    conn = get_conn(DB_PATH)
    try:
        yield conn.cursor()
    finally:
        conn.close()


# ---------------------------  Helpers  ----------------------------- #
def _parse_bbox(bbox: str):
    """Convierte 'latmin,lonmin,latmax,lonmax' en 4 floats."""
    try:
        lat_min, lon_min, lat_max, lon_max = map(float, bbox.split(","))
        return lat_min, lat_max, lon_min, lon_max
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="bbox debe ser latmin,lonmin,latmax,lonmax",
        ) from err


# ---------------------------  Endpoints  --------------------------- #
@app.get("/items", response_model=List[Item])
def list_items(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    start: Optional[str] = Query(None, description="ISO-8601 start date"),
    end: Optional[str] = Query(None, description="ISO-8601 end date"),
    satellite: Optional[str] = None,
    product_type: Optional[str] = None,
    bbox: Optional[str] = Query(None, description="latmin,lonmin,latmax,lonmax"),
    cur: sqlite3.Cursor = Depends(get_cursor),
):
    """Devuelve la lista de productos filtrados y paginados."""
    where, params = [], []

    if start:
        where.append("p.datetime_start >= ?")
        params.append(start)
    if end:
        where.append("p.datetime_end <= ?")
        params.append(end)
    if satellite:
        where.append("p.satellite = ?")
        params.append(satellite)
    if product_type:
        where.append("p.product_type = ?")
        params.append(product_type)

    if bbox:
        lat_min, lat_max, lon_min, lon_max = _parse_bbox(bbox)
        subq = (
            "SELECT product_id FROM bbox_index "
            "WHERE lat_min <= ? AND lat_max >= ? "
            "AND lon_min <= ? AND lon_max >= ?"
        )
        where.append(f"p.id IN ({subq})")
        params.extend([lat_max, lat_min, lon_max, lon_min])

    where_clause = "WHERE " + " AND ".join(where) if where else ""
    sql = f"""
        SELECT p.id, p.file_path, p.product_name, p.datetime_start, p.datetime_end,
               p.satellite, p.instrument, p.product_type, p.size_bytes,
               b.lat_min, b.lat_max, b.lon_min, b.lon_max
        FROM products AS p
        LEFT JOIN bbox_index AS b ON b.product_id = p.id
        {where_clause}
        ORDER BY p.datetime_start DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = cur.execute(sql, params).fetchall()
    return [Item(**row).dict() for row in rows]


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int, cur: sqlite3.Cursor = Depends(get_cursor)):
    """Devuelve metadatos completos de un producto."""
    sql = """
        SELECT p.id, p.file_path, p.product_name, p.datetime_start, p.datetime_end,
               p.satellite, p.instrument, p.product_type, p.size_bytes,
               b.lat_min, b.lat_max, b.lon_min, b.lon_max
        FROM products AS p
        LEFT JOIN bbox_index AS b ON b.product_id = p.id
        WHERE p.id = ?
    """
    row = cur.execute(sql, (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="item not found")
    return Item(**row).dict()
