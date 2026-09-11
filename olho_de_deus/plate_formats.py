#!/usr/bin/env python3
"""
plate_formats.py — Olho de Deus

Ponte entre database/plate_formats.db (pesquisado em 2026-09-11, ver
build_plate_formats_db.py) e o motor de ALPR (forensic_sr_engine.py) — dado
o país de uma câmera, devolve o idioma de OCR certo e a regex de validação
certa, em vez do motor assumir sempre formato brasileiro.

Uso:
    from plate_formats import get_format
    fmt = get_format("JP")
    fmt.ocr_langs      # ['en', 'ja']
    fmt.regex          # re.compile(...) ou None
"""
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "plate_formats.db"

# Fallback pra país sem linha no banco — não trava, só não valida formato
# nem tenta idioma especial (assume alfabeto latino, inglês).
_FALLBACK = {
    "country_code": "XX",
    "country_name_pt": "Desconhecido",
    "layout": "single_line",
    "regex": None,
    "ocr_langs": ["en"],
}


@dataclass
class PlateFormat:
    country_code: str
    country_name_pt: str
    layout: str
    script: str
    pattern_desc_pt: str
    regex: Optional[re.Pattern]
    example: Optional[str]
    ocr_langs: List[str]
    color_scheme_pt: Optional[str]
    confidence: str
    tested_in_project: bool


def _row_to_format(row: dict) -> PlateFormat:
    return PlateFormat(
        country_code=row["country_code"],
        country_name_pt=row["country_name_pt"],
        layout=row["layout"],
        script=row["script"],
        pattern_desc_pt=row["pattern_desc_pt"],
        regex=re.compile(row["regex"]) if row.get("regex") else None,
        example=row.get("example"),
        ocr_langs=(row.get("ocr_langs") or "en").split(","),
        color_scheme_pt=row.get("color_scheme_pt"),
        confidence=row.get("confidence", "desconhecido"),
        tested_in_project=bool(row.get("tested_in_project", 0)),
    )


def get_format(country_code: Optional[str]) -> PlateFormat:
    """Busca o formato de placa pro país dado. Sem correspondência (país fora
    do banco, ou None/'' vindo de câmera sem país cadastrado) devolve um
    fallback genérico — nunca lança exceção, o chamador sempre recebe algo
    utilizável."""
    if country_code:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM plate_formats WHERE country_code = ?", (country_code.upper(),)
            ).fetchone()
            conn.close()
            if row:
                return _row_to_format(dict(row))
        except sqlite3.Error:
            pass
    return _row_to_format(_FALLBACK)


def list_supported_countries() -> List[str]:
    """Lista os country_code com formato cadastrado — útil pra logs/debug."""
    try:
        conn = sqlite3.connect(DB_PATH)
        codes = [r[0] for r in conn.execute("SELECT country_code FROM plate_formats ORDER BY country_code")]
        conn.close()
        return codes
    except sqlite3.Error:
        return []


if __name__ == "__main__":
    for code in list_supported_countries():
        fmt = get_format(code)
        print(f"{fmt.country_code} ({fmt.country_name_pt}): langs={fmt.ocr_langs} "
              f"regex={'sim' if fmt.regex else 'não'} testado={fmt.tested_in_project}")
