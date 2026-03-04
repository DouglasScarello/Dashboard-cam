#!/usr/bin/env python3
"""
extract_embeddings.py — Olho de Deus  [Fase 14: refatorado]

Ponto de entrada CLI para extração de embeddings biométricos.
Agora usa delta_embedder.py como backend (IndexIDMap, upsert incremental).

Mantido por compatibilidade com chamadas existentes (é chamado pelo
run_global_intelligence.py e por outros scripts).

Uso:
    poetry run python extract_embeddings.py
    poetry run python extract_embeddings.py --limit 1000
    poetry run python extract_embeddings.py --force-rebuild
"""
import argparse
from delta_embedder import run_delta

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olho de Deus — Extração Biométrica (Delta Mode)")
    parser.add_argument("--limit",         type=int, default=None, help="Máximo de registros a processar")
    parser.add_argument("--batch-size",    type=int, default=32,   help="Checkpoint interval (default: 32)")
    parser.add_argument("--force-rebuild", action="store_true",    help="Reconstrói o índice FAISS do zero")
    args = parser.parse_args()

    run_delta(
        limit=args.limit,
        batch_size=args.batch_size,
        force_rebuild=args.force_rebuild,
    )
