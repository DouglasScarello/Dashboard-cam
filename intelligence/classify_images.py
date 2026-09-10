#!/usr/bin/env python3
"""
classify_images.py — Olho de Deus

Descreve/classifica cada foto ANTES de gastar tempo com ArcFace/RetinaFace nela.
Usa CLIP (zero-shot, roda local, rápido até em CPU) pra responder: "o que essa
imagem realmente é?" — retrato único, cartaz com várias pessoas, esboço, foto
sem rosto (tatuagem/documento/veículo), etc.

Isso separa o problema em dois: "a imagem é utilizável pra reconhecimento
facial?" (decidido aqui, rápido) vs "qual é o embedding do rosto?" (decidido
depois, só nas imagens que valem a pena, pelo delta_embedder.py).

Uso:
    poetry run python3 classify_images.py [--limit 100]
"""
import argparse

import open_clip
import torch
from PIL import Image

from intelligence_db import DB, init_db

# Rótulos candidatos — o CLIP escolhe o mais provável pra cada imagem.
# A ORDEM não importa pro CLIP, mas os dois primeiros são os que o pipeline
# de reconhecimento facial considera "utilizáveis" (ver USABLE_LABELS abaixo).
LABELS = [
    "a clear photo of one single person's face",
    "a mugshot photo of one person",
    "a poster or collage showing multiple different people",
    "a sketch or artist's drawing of a face",
    "a photo of a tattoo, scar, or body part without a visible face",
    "a photo of a document, text, or logo",
    "a blurry, unclear, or very low quality photo",
    "a photo of a vehicle, building, or location without a person",
]

# Categorias que valem a pena mandar pro ArcFace/RetinaFace.
# "blurry" testado manualmente (2026-09-10): 16 de 17 imagens que o CLIP rotulou
# como "borrada/baixa qualidade" TINHAM rosto detectável de verdade pelo
# RetinaFace — CLIP não é confiável pra prever detectabilidade de rosto, só
# serve pra filtrar o que claramente NÃO é rosto (documento/veículo/tatuagem/
# esboço/cartaz). Deixar passar e o RetinaFace (com enforce_detection=True)
# já decide de verdade — ver NOITE_AUTONOMA_2026-09-10.md pro teste completo.
USABLE_LABELS = {LABELS[0], LABELS[1], "a blurry, unclear, or very low quality photo"}


def classify_all(limit: int | None = None, batch_size: int = 16):
    init_db()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[clip] Carregando modelo (device={device})...")
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
        "SELECT id, img_path FROM individuals "
        "WHERE img_path IS NOT NULL AND image_content_type IS NULL"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[clip] {len(rows)} imagens a classificar.")

    from pathlib import Path
    ROOT = Path(__file__).resolve().parent

    def resolve(img_path):
        for cand in [ROOT / "data" / img_path, ROOT.parent / img_path]:
            if cand.exists():
                return cand
        return None

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
                "UPDATE individuals SET image_content_type = ? WHERE id = ?",
                (label, row["id"]),
            )
            processed += 1

        db.commit()
        if processed % 100 < batch_size:
            print(f"  ... {processed}/{len(rows)}")

    db.close()

    print("\n" + "═" * 60)
    print(f"  🔎 Classificação CLIP concluída — {processed} imagens")
    print("═" * 60)
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        if n > 0:
            usable = " ✅ utilizável" if label in USABLE_LABELS else ""
            print(f"  {n:>5}  {label}{usable}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    classify_all(limit=args.limit)
