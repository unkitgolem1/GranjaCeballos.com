#!/usr/bin/env python3
"""Descarga SEPOMEX CSV y genera migración SQL solo para Yucatán (CP 97xxx)."""

import csv
import os
import urllib.request
from pathlib import Path

_CSV_URL = "https://raw.githubusercontent.com/redrbrt/sepomex-zip-codes/master/sepomex_abril-2016.csv"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "src" / "infrastructure" / "migrations"
_OUTPUT = _MIGRATIONS_DIR / "011_sepomex_yucatan.sql"


def _descargar_csv(path: Path) -> None:
    print(f"Descargando {_CSV_URL} ...")
    urllib.request.urlretrieve(_CSV_URL, path)
    print(f"  → {path} ({path.stat().st_size / 1024:.0f} KB)")


def _escapar(val: str) -> str:
    val = val.strip()
    if val.upper() == "NULL" or val == "":
        return ""
    return val.replace("'", "''")


def _generar() -> None:
    tmp = Path("/tmp/sepomex_full.csv")
    if not tmp.exists():
        _descargar_csv(tmp)

    with open(tmp, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["idEstado"] == "31"]

    print(f"Filtrados {len(rows)} registros de Yucatán")

    _MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    values: list[str] = []
    for r in rows:
        cp = r["cp"]
        colonia = _escapar(r["asentamiento"])
        municipio = _escapar(r["municipio"])
        ciudad = _escapar(r["ciudad"])
        tipo = _escapar(r["tipo"])
        zona = _escapar(r["zona"])
        values.append(
            f"  ('{cp}', '{colonia}', '{municipio}', 'Yucatán', '{ciudad}', '{tipo}', '{zona}')"
        )

    sql = f"""-- 011_sepomex_yucatan.sql
-- Códigos Postales de Yucatán — generado por scripts/generar_migracion_sepomex.py
-- Fuente: SEPOMEX (vía {_CSV_URL})
-- {len(rows)} registros, {len(set(r['cp'] for r in rows))} CPs únicos

CREATE TABLE IF NOT EXISTS codigos_postales (
    id            SERIAL       PRIMARY KEY,
    codigo_postal VARCHAR(5)   NOT NULL,
    colonia       VARCHAR(200) NOT NULL,
    municipio     VARCHAR(100) NOT NULL,
    estado        VARCHAR(50)  NOT NULL DEFAULT 'Yucatán',
    ciudad        VARCHAR(100) NOT NULL DEFAULT '',
    tipo_asenta   VARCHAR(50)  NOT NULL DEFAULT '',
    zona          VARCHAR(20)  NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cp_codigo ON codigos_postales(codigo_postal);

INSERT INTO codigos_postales (codigo_postal, colonia, municipio, estado, ciudad, tipo_asenta, zona)
VALUES
{','.join(values)};

"""

    with open(_OUTPUT, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"Migración generada: {_OUTPUT}")
    print(f"  → {len(values)} registros inserts")


if __name__ == "__main__":
    _generar()
