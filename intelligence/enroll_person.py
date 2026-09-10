#!/usr/bin/env python3
"""
enroll_person.py — Olho de Deus

Cadastra manualmente UMA pessoa na watchlist pessoal (category="watchlist",
source="manual") — diferente dos carregadores em massa (populate_db.py) que
ingerem bases públicas (FBI, OpenSanctions).

Reaproveita upsert_individual/insert_image já existentes; não muda o schema.

Uso:
    poetry run python3 enroll_person.py --name "Fulano" --photo /caminho/foto.jpg
    poetry run python3 enroll_person.py --name "Fulano" --photo foto1.jpg --photo foto2.jpg --relationship "familia"
"""
import argparse
import shutil
from pathlib import Path

from intelligence_db import DB, init_db, upsert_individual, insert_image, generate_deterministic_uid

ROOT = Path(__file__).resolve().parent
PHOTO_DIR = ROOT / "data" / "watchlist_photos"

# Nunca usar essas categorias aqui — são reservadas para os dados públicos do FBI
# (stats() e filtros de UI assumem que "wanted"/"missing" == FBI).
RESERVED_CATEGORIES = {"wanted", "missing"}


def enroll(name: str, photos: list[str], relationship: str | None = None, category: str = "watchlist"):
    if category in RESERVED_CATEGORIES:
        raise SystemExit(
            f"[erro] category='{category}' é reservada para dados públicos (FBI). "
            f"Use outro valor (ex: 'watchlist')."
        )
    if not photos:
        raise SystemExit("[erro] pelo menos uma --photo é obrigatória.")

    init_db()
    db = DB()
    uid = generate_deterministic_uid(name)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    primary_rel_path = None
    for i, src in enumerate(photos):
        src_path = Path(src).expanduser()
        if not src_path.exists():
            print(f"[aviso] foto não encontrada, pulando: {src_path}")
            continue
        ext = src_path.suffix or ".jpg"
        dest_name = f"{uid}.jpg" if i == 0 else f"{uid}_{i}{ext}"
        dest = PHOTO_DIR / dest_name
        shutil.copy(src_path, dest)
        rel_path = f"watchlist_photos/{dest_name}"  # resolvido por delta_embedder.resolve_img_path()
        if primary_rel_path is None:
            primary_rel_path = rel_path
        insert_image(db, uid, img_path=rel_path, is_primary=(primary_rel_path == rel_path))

    if not primary_rel_path:
        db.close()
        raise SystemExit("[erro] nenhuma foto válida foi copiada — cadastro abortado.")

    upsert_individual(db, {
        "id": uid,
        "name": name,
        "category": category,
        "source": "manual",
        "img_path": primary_rel_path,
        "description": relationship or "",
    })
    db.close()
    print(f"[ok] '{name}' cadastrado(a) com UID {uid} ({len(photos)} foto(s)).")
    print("[ok] rode 'poetry run python3 ../olho_de_deus/extract_embeddings.py' pra gerar o embedding.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cadastra uma pessoa na watchlist pessoal")
    parser.add_argument("--name", required=True)
    parser.add_argument("--photo", action="append", required=True, help="pode repetir --photo várias vezes")
    parser.add_argument("--relationship", default=None, help="ex: 'familia', 'funcionario' — vai pra description")
    parser.add_argument("--category", default="watchlist")
    args = parser.parse_args()
    enroll(args.name, args.photo, args.relationship, args.category)
