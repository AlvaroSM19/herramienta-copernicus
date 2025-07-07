-- backend/db/schema.sql

-- Esquema mínimo del catálogo (multi‐producto por archivo)

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT        NOT NULL,
    product_name    TEXT,
    datetime_start  TEXT,
    datetime_end    TEXT,
    satellite       TEXT,
    instrument      TEXT,
    product_type    TEXT NOT NULL,
    size_bytes      INTEGER,
    checksum        TEXT,
    UNIQUE (file_path, product_type)
);

-- Índices útiles
CREATE INDEX IF NOT EXISTS idx_products_dt  ON products (datetime_start);
CREATE INDEX IF NOT EXISTS idx_products_type ON products (product_type);

-- Índice espacial (bounding‐box) con RTree
CREATE VIRTUAL TABLE IF NOT EXISTS bbox_index
USING rtree(
    product_id,
    lat_min, lat_max,
    lon_min, lon_max
);
