#!/usr/bin/env python3
"""
clip_similarity_index.py — Olho de Deus

Índice de busca por similaridade visual (CLIP + FAISS) pra categorias que NÃO
são rosto — tatuagem/cicatriz e veículo — identificadas pelo classify_images.py.
Não é reconhecimento facial: é "essa tatuagem/carro se parece com qual dos que
já vimos", útil quando o rosto não é visível na câmera.

Uso:
    poetry run python3 clip_similarity_index.py --build   # (re)constrói o índice
    poetry run python3 clip_similarity_index.py --search <caminho_da_imagem>
"""
import argparse
import json
from pathlib import Path

import faiss
import numpy as np
import open_clip
import torch
from PIL import Image

from intelligence_db import DB, init_db

ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "data" / "clip_visual_db.faiss"
META_PATH = ROOT / "data" / "clip_visual_metadata.json"

# Categorias não-faciais que fazem sentido buscar por similaridade visual —
# ver LABELS em classify_images.py.
INDEXABLE_LABELS = {
    "a photo of a tattoo, scar, or body part without a visible face",
    "a photo of a vehicle, building, or location without a person",
}

_model = None
_preprocess = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    global _model, _preprocess
    if _model is None:
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32-quickgelu", pretrained="openai"
        )
        _model.eval().to(_device)
    return _model, _preprocess


def _embed_image(path: Path) -> np.ndarray:
    model, preprocess = _load_model()
    img = preprocess(Image.open(path).convert("RGB")).unsqueeze(0).to(_device)
    with torch.no_grad():
        feat = model.encode_image(img)
        feat /= feat.norm(dim=-1, keepdim=True)
    return feat.cpu().numpy().astype("float32")[0]


def resolve(img_path: str):
    for cand in [ROOT / "data" / img_path, ROOT.parent / img_path]:
        if cand.exists():
            return cand
    return None


def build():
    init_db()
    db = DB()
    placeholders = ",".join("?" for _ in INDEXABLE_LABELS)
    cur = db.execute(
        f"SELECT id, name, img_path, image_content_type FROM individuals "
        f"WHERE image_content_type IN ({placeholders}) AND img_path IS NOT NULL",
        tuple(INDEXABLE_LABELS),
    )
    rows = [dict(r) for r in cur.fetchall()]
    db.close()
    print(f"[clip-sim] {len(rows)} imagens (tatuagem/veículo) a indexar.")

    vecs, meta = [], []
    for row in rows:
        path = resolve(row["img_path"])
        if not path:
            continue
        try:
            emb = _embed_image(path)
        except Exception as e:
            print(f"[clip-sim] falhou {row['id']}: {e}")
            continue
        vecs.append(emb)
        meta.append({"uid": row["id"], "title": row["name"], "category": row["image_content_type"]})

    if not vecs:
        print("[clip-sim] nada pra indexar.")
        return

    index = faiss.IndexFlatIP(vecs[0].shape[0])  # embeddings já normalizados -> produto interno = cosseno
    index.add(np.array(vecs, dtype="float32"))
    faiss.write_index(index, str(INDEX_PATH))
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"[clip-sim] índice salvo com {index.ntotal} vetores → {INDEX_PATH}")


def search(query_path: str, top_k: int = 5):
    if not INDEX_PATH.exists():
        print("[clip-sim] índice não existe ainda — rode com --build primeiro.")
        return
    index = faiss.read_index(str(INDEX_PATH))
    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    emb = _embed_image(Path(query_path)).reshape(1, -1)
    scores, ids = index.search(emb, top_k)
    print(f"\nTop {top_k} mais parecidos com {query_path}:")
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0:
            continue
        m = meta[idx]
        print(f"  {score:.3f}  {m['title']}  ({m['category']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--search", type=str, default=None, help="caminho de imagem pra buscar parecidos")
    args = parser.parse_args()

    if args.build:
        build()
    elif args.search:
        search(args.search)
    else:
        parser.print_help()
