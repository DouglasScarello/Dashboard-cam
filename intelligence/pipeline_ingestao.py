#!/usr/bin/env python3
"""
pipeline_ingestao.py — Olho de Deus

Orquestra a esteira completa de ingestão numa chamada só, na ordem certa
(antes disso eram 6 scripts manuais, fácil esquecer um passo ou rodar fora
de ordem):

    1. populate_db.py:load_fbi()      — busca lista do FBI (nomes/dados/URLs de foto)
    2. download_fbi_photos.py         — baixa as fotos de verdade
    3. classify_images.py             — CLIP: entende o que cada foto é
    4. ocr_documents.py               — extrai texto das fotos-documento
    5. clip_similarity_index.py       — indexa tatuagem/veículo por similaridade
    6. extract_embeddings.py          — ArcFace nos rostos de verdade (pula o resto)
    7. score_engine.py                — score de periculosidade de todo mundo
    8. health_check.py                — confirma que deu tudo certo no final

Uso:
    poetry run python3 pipeline_ingestao.py             # roda tudo
    poetry run python3 pipeline_ingestao.py --skip-fbi  # pula passo 1 (já ingerido)
"""
import argparse
import subprocess
import sys
from pathlib import Path

INTEL_DIR = Path(__file__).resolve().parent
OLHO_DIR = INTEL_DIR.parent / "olho_de_deus"
PYTHON = sys.executable  # mesmo interpretador que já está rodando este script


def run(label: str, cwd: Path, args: list[str]):
    print("\n" + "═" * 70)
    print(f"  ▶ {label}")
    print("═" * 70)
    result = subprocess.run([PYTHON] + args, cwd=str(cwd))
    if result.returncode != 0:
        print(f"\n[pipeline] '{label}' terminou com erro (código {result.returncode}) — parando aqui.")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fbi", action="store_true", help="pula a re-ingestão da lista do FBI")
    parser.add_argument("--skip-ocr", action="store_true")
    parser.add_argument("--skip-clip-similarity", action="store_true")
    args = parser.parse_args()

    if not args.skip_fbi:
        run("1/8 Ingestão FBI (lista + campos ricos)", INTEL_DIR,
            ["-c", "from populate_db import load_fbi; load_fbi(limit_pages=None)"])
    else:
        print("[pipeline] Pulando ingestão FBI (--skip-fbi).")

    run("2/8 Download de fotos reais", INTEL_DIR, ["download_fbi_photos.py"])
    run("3/8 Classificação de conteúdo (CLIP)", INTEL_DIR, ["classify_images.py"])

    if not args.skip_ocr:
        run("4/8 OCR nos documentos", INTEL_DIR, ["ocr_documents.py"])
    if not args.skip_clip_similarity:
        run("5/8 Índice de similaridade (tatuagem/veículo)", INTEL_DIR, ["clip_similarity_index.py", "--build"])

    run("6/8 Extração de embeddings faciais (ArcFace)", OLHO_DIR,
        ["extract_embeddings.py", "--force-rebuild"])
    run("7/8 Score de periculosidade", OLHO_DIR, ["score_engine.py"])
    run("8/8 Verificação final (health check)", OLHO_DIR, ["health_check.py"])

    print("\n[pipeline] Concluído. Ver relatório do health check acima.")


if __name__ == "__main__":
    main()
