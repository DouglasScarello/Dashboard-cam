#!/usr/bin/env python3
"""
download_fbi_photos.py — Olho de Deus

Baixa as fotos reais dos indivíduos já ingeridos via populate_db.py:load_fbi()
que ainda não têm img_path local (ou seja, nunca tiveram a foto baixada).
Não bate na API de novo — usa o img_url já salvo no banco na primeira ingestão.

Uso:
    poetry run python3 download_fbi_photos.py [--limit 100]
"""
import argparse
import time
from pathlib import Path

import requests

from intelligence_db import DB

PHOTO_DIR = Path(__file__).resolve().parent / "data" / "fbi_faces"

# www.fbi.gov bloqueia requests sem esses headers (WAF checa Accept/Referer, não só User-Agent).
# IMPORTANTE: não anunciar suporte a webp/avif no Accept — o CDN do fbi.gov serve WebP nesse
# caso (~29% das respostas, medido), e nem OpenCV nem DeepFace decodificam WebP, causando
# falha silenciosa (arquivo salvo com extensão .jpg mas ilegível).
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "image/jpeg,image/png,*/*",
    "Referer": "https://www.fbi.gov/wanted",
}

JPEG_MAGIC = b"\xff\xd8"
PNG_MAGIC = b"\x89PNG"


def _is_real_image(content: bytes) -> bool:
    """Confere magic bytes — protege contra WebP (Accept não deveria pedir, mas por garantia)
    e contra páginas HTML de erro devolvidas com HTTP 200 (link quebrado no CMS do fbi.gov)."""
    return content[:2] == JPEG_MAGIC or content[:4] == PNG_MAGIC


def download_photos(limit: int | None = None):
    db = DB()
    cur = db.execute(
        "SELECT id, img_url FROM individuals WHERE source = 'FBI' AND img_path IS NULL AND img_url IS NOT NULL"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[fbi-photos] {len(rows)} indivíduos sem foto local a processar.")

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    ok, failed = 0, 0
    for row in rows:
        uid, url = row["id"], row["img_url"]
        dest = PHOTO_DIR / f"{uid}.jpg"
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS)
            resp.raise_for_status()
            if not _is_real_image(resp.content):
                print(f"[fbi-photos] falhou {uid}: resposta não é JPEG/PNG real (provável WebP ou página HTML de erro)")
                failed += 1
                continue
            dest.write_bytes(resp.content)
            db.execute(
                "UPDATE individuals SET img_path = ? WHERE id = ?",
                (f"fbi_faces/{uid}.jpg", uid),
            )
            db.commit()
            ok += 1
        except Exception as e:
            print(f"[fbi-photos] falhou {uid}: {e}")
            failed += 1
        time.sleep(0.1)  # não martelar fbi.gov

    db.close()
    print(f"[fbi-photos] concluído: {ok} baixadas, {failed} falharam.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    download_photos(limit=args.limit)
