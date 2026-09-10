#!/usr/bin/env python3
"""
download_gallery_photos.py — Olho de Deus

Baixa TODAS as fotos secundárias da galeria (individual_images) que ainda só
existem como img_url remoto — só a foto PRINCIPAL de cada indivíduo era
baixada localmente até agora (download_fbi_photos.py), então a galeria
inteira nunca tinha como ser classificada (CLIP) nem exibida offline.

Concorrente (ThreadPoolExecutor) — medido em 2026-09-10: o CDN do fbi.gov
pra essas imagens de galeria (caminho "seeking-info/...") é MUITO mais lento
e instável que o das fotos principais (chegou a 24s numa requisição sob
carga concorrente) — sequencial levaria várias horas pras ~7.500 fotos.
8 workers é o equilíbrio: throughput real sem martelar o servidor a ponto
de piorar a latência de todo mundo.

Mesma lógica de validação de download_fbi_photos.py (headers, magic bytes),
mas por linha de individual_images — usa o id numérico da linha como nome
de arquivo (evita colisão quando uma pessoa tem várias fotos).

Uso:
    poetry run python3 download_gallery_photos.py [--limit 100] [--workers 8]
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

from intelligence_db import DB, init_db

PHOTO_DIR = Path(__file__).resolve().parent / "data" / "gallery_photos"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "image/jpeg,image/png,*/*",
    "Referer": "https://www.fbi.gov/wanted",
}

JPEG_MAGIC = b"\xff\xd8"
PNG_MAGIC = b"\x89PNG"


def _is_real_image(content: bytes) -> bool:
    return content[:2] == JPEG_MAGIC or content[:4] == PNG_MAGIC


def _fetch_one(img_id: int, url: str) -> tuple[int, bytes | None]:
    """Roda numa thread do pool — só faz a requisição HTTP, sem tocar no DB
    (SQLite não é seguro pra escrita concorrente entre threads)."""
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        if _is_real_image(resp.content):
            return img_id, resp.content
    except Exception:
        pass
    return img_id, None


def download_gallery(limit: int | None = None, workers: int = 8):
    init_db()
    db = DB()
    cur = db.execute(
        "SELECT id, img_url FROM individual_images WHERE img_path IS NULL AND img_url IS NOT NULL"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[gallery] {len(rows)} fotos de galeria sem download local a processar ({workers} workers).")

    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    ok, failed = 0, 0
    db_lock = Lock()
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, row["id"], row["img_url"]): row["id"] for row in rows}
        for i, future in enumerate(as_completed(futures)):
            img_id, content = future.result()
            if content is None:
                failed += 1
            else:
                dest = PHOTO_DIR / f"{img_id}.jpg"
                dest.write_bytes(content)
                with db_lock:
                    db.execute(
                        "UPDATE individual_images SET img_path = ? WHERE id = ?",
                        (f"gallery_photos/{img_id}.jpg", img_id),
                    )
                ok += 1

            # Commit frequente (a cada 20, não 200) — descoberto rodando junto com
            # classify_gallery_images.py: em WAL mode, a transação fica aberta
            # (segurando o lock de escrita) até o commit; com 200 em lote e
            # ~45 img/min, isso passava dos 30s de busy_timeout e derrubava
            # qualquer outro script tentando escrever no mesmo banco.
            if (i + 1) % 20 == 0:
                with db_lock:
                    db.commit()
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  ... {i + 1}/{len(rows)} ({ok} ok, {failed} falharam) — {rate:.1f} img/s")

    db.commit()
    db.close()
    print(f"[gallery] concluído: {ok} baixadas, {failed} falharam.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    download_gallery(limit=args.limit, workers=args.workers)
