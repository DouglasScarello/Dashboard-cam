#!/usr/bin/env python3
"""
classify_gallery_images.py — Olho de Deus

Mesma classificação CLIP de classify_images.py, mas pra galeria inteira
(individual_images) em vez de só a foto principal de cada indivíduo.
Até 2026-09-10 uma pessoa podia ter uma foto de rosto E uma de tatuagem
na galeria e não havia como saber qual era qual sem abrir a imagem —
pedido do usuário: "coloque as infos certas... fica mais fácil de
colocar no front".

Reaproveita os mesmos LABELS/USABLE_LABELS de classify_images.py (mesmo
critério do que é "utilizável pra reconhecimento facial").

Uso:
    poetry run python3 classify_gallery_images.py [--limit 100]
"""
import argparse
from pathlib import Path

import open_clip
import torch
from PIL import Image

from classify_images import LABELS, USABLE_LABELS
from intelligence_db import DB, init_db

ROOT = Path(__file__).resolve().parent


def resolve(img_path: str):
    for cand in [ROOT / "data" / img_path, ROOT.parent / img_path]:
        if cand.exists():
            return cand
    return None


def classify_gallery(limit: int | None = None, batch_size: int = 16):
    init_db()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[clip-galeria] Carregando modelo (device={device})...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32-quickgelu", pretrained="openai"
    )
    tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")
    model.eval().to(device)

    with torch.no_grad():
        text_tokens = tokenizer(LABELS).to(device)
        text_features = model.encode_text(text_tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)

    db = DB()
    cur = db.execute(
        "SELECT id, img_path FROM individual_images "
        "WHERE img_path IS NOT NULL AND image_content_type IS NULL"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[clip-galeria] {len(rows)} fotos de galeria a classificar.")

    counts = {label: 0 for label in LABELS}
    counts["falha_ao_abrir"] = 0
    processed = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        imgs, valid_rows = [], []
        for row in batch:
            path = resolve(row["img_path"])
            if not path:
                counts["falha_ao_abrir"] += 1
                continue
            try:
                img = preprocess(Image.open(path).convert("RGB"))
                imgs.append(img)
                valid_rows.append(row)
            except Exception:
                counts["falha_ao_abrir"] += 1

        if not imgs:
            continue

        with torch.no_grad():
            image_input = torch.stack(imgs).to(device)
            image_features = model.encode_image(image_input)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            similarity = (100.0 * image_features @ text_features.T).softmax(dim=-1)

        for row, sims in zip(valid_rows, similarity):
            best_idx = int(sims.argmax())
            label = LABELS[best_idx]
            counts[label] += 1
            db.execute(
                "UPDATE individual_images SET image_content_type = ? WHERE id = ?",
                (label, row["id"]),
            )
            processed += 1

        db.commit()
        if processed % 200 < batch_size:
            print(f"  ... {processed}/{len(rows)}")

    db.close()

    print("\n" + "═" * 60)
    print(f"  🔎 Classificação CLIP da galeria concluída — {processed} imagens")
    print("═" * 60)
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        if n > 0:
            usable = " ✅ utilizável (rosto)" if label in USABLE_LABELS else ""
            print(f"  {n:>5}  {label}{usable}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    classify_gallery(limit=args.limit)
