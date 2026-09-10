#!/usr/bin/env python3
"""
ocr_gallery_images.py — Olho de Deus

Mesmo OCR de ocr_documents.py, mas pra galeria inteira (individual_images)
em vez de só a foto principal — segue classify_gallery_images.py.

Uso:
    poetry run python3 ocr_gallery_images.py
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
        "SELECT id, img_path FROM individual_images WHERE image_content_type = ? AND ocr_text IS NULL",
        (DOCUMENT_LABEL,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[ocr-galeria] {len(rows)} documentos de galeria a processar.")
    if not rows:
        db.close()
        return

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    ok, empty = 0, 0
    for i, row in enumerate(rows):
        path = resolve(row["img_path"])
        if not path:
            continue
        try:
            results = reader.readtext(str(path), detail=0)
            text = " ".join(results).strip()
        except Exception as e:
            print(f"[ocr-galeria] falhou {row['id']}: {e}")
            continue

        if text:
            ok += 1
        else:
            empty += 1
        db.execute("UPDATE individual_images SET ocr_text = ? WHERE id = ?", (text or "", row["id"]))
        if (i + 1) % 10 == 0:
            db.commit()

    db.commit()
    db.close()
    print(f"[ocr-galeria] concluído: {ok} com texto extraído, {empty} sem texto legível.")


if __name__ == "__main__":
    run()
