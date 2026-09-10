#!/usr/bin/env python3
"""
ocr_documents.py — Olho de Deus

Roda OCR (EasyOCR, já usado no pipeline de ALPR) nas imagens que o
classify_images.py identificou como documento/texto/logo — hoje descartadas
sem nenhum aproveitamento, mesmo podendo ter nome/número/texto relevante.

Uso:
    poetry run python3 ocr_documents.py
"""
from pathlib import Path

import easyocr

from intelligence_db import DB, init_db

DOCUMENT_LABEL = "a photo of a document, text, or logo"
ROOT = Path(__file__).resolve().parent


def resolve(img_path: str):
    for cand in [ROOT / "data" / img_path, ROOT.parent / img_path]:
        if cand.exists():
            return cand
    return None


def run():
    init_db()
    db = DB()
    cur = db.execute(
        "SELECT id, img_path FROM individuals WHERE image_content_type = ? AND ocr_text IS NULL",
        (DOCUMENT_LABEL,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[ocr] {len(rows)} documentos a processar.")
    if not rows:
        db.close()
        return

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    ok, empty = 0, 0
    for row in rows:
        path = resolve(row["img_path"])
        if not path:
            continue
        try:
            results = reader.readtext(str(path), detail=0)
            text = " ".join(results).strip()
        except Exception as e:
            print(f"[ocr] falhou {row['id']}: {e}")
            continue

        if text:
            ok += 1
            print(f"  [{row['id'][:8]}] {text[:100]}")
        else:
            empty += 1
        db.execute("UPDATE individuals SET ocr_text = ? WHERE id = ?", (text or "", row["id"]))
        db.commit()

    db.close()
    print(f"\n[ocr] concluído: {ok} com texto extraído, {empty} sem texto legível.")


if __name__ == "__main__":
    run()
