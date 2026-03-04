#!/usr/bin/env python3
"""
run_global_intelligence.py — Olho de Deus  [Fase 10: Parallel Ingestion Engine]

Orquestrador central ASYNC. Dispara todos os ingestores em paralelo via
asyncio.gather(return_exceptions=True), garantindo que a falha de uma
fonte não derrube as demais.

Tempo esperado: ~8 min (vs ~40 min sequencial na Fase 9)

Uso:
    poetry run python run_global_intelligence.py
    poetry run python run_global_intelligence.py --limit 100 --no-embed
    poetry run python run_global_intelligence.py --source fbi --source interpol
"""
import asyncio
import argparse
import logging
import sys
import time
import os
from pathlib import Path
from typing import Optional, List

import aiohttp
from tqdm.asyncio import tqdm as atqdm

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from intelligence_db import DB, init_db, stats as db_stats

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

# ─── Ingestores ──────────────────────────────────────────────────────────────
from fbi_ingestion          import FBIIngestor
from interpol_ingestion     import InterpolIngestor
from opensanctions_ingestion import OpenSanctionsIngestor
from bnmp_ingestion         import BNMPIngestor
from asia_ingestion         import AsiaIngestor
from us_local_ingestion     import USLocalIngestor

# ─── Catálogo de ingestores disponíveis ──────────────────────────────────────
INGESTOR_REGISTRY = {
    "fbi":        FBIIngestor,
    "interpol":   InterpolIngestor,
    "opensanctions": OpenSanctionsIngestor,
    "bnmp":       BNMPIngestor,
    "asia":       AsiaIngestor,
    "us_local":   USLocalIngestor,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


async def run_ingestor(
    name: str,
    cls,
    db: DB,
    session: aiohttp.ClientSession,
    limit: int,
) -> dict:
    """Executa um ingestor de forma isolada, capturando erros sem derrubar os outros."""
    ingestor = cls(db=db)
    t0 = time.monotonic()
    try:
        log.info(f"[{name.upper()}] ▶ Iniciando")
        result = await ingestor.run(session, limit=limit, limit_pages=max(1, limit // 20))
        elapsed = time.monotonic() - t0
        log.info(f"[{name.upper()}] ✓ Concluído em {elapsed:.1f}s — {ingestor.report()}")
        return {"source": name, "elapsed": elapsed, **result}
    except Exception as e:
        elapsed = time.monotonic() - t0
        log.error(f"[{name.upper()}] ✗ Falha crítica em {elapsed:.1f}s: {e}")
        return {"source": name, "elapsed": elapsed, "loaded": 0, "errors": 1}
    finally:
        ingestor.close()


async def pipeline(
    sources: Optional[List[str]] = None,
    limit: int = 50,
    no_embed: bool = False,
):
    # ─── Init ─────────────────────────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  🛰️  OLHO DE DEUS — Parallel Intelligence Sync  [Fase 10]")
    print("═" * 65)

    init_db()
    db = DB()

    active = {k: v for k, v in INGESTOR_REGISTRY.items()
              if not sources or k in sources}

    print(f"\n  Fontes ativas   : {', '.join(active.keys())}")
    print(f"  Limite por fonte: {limit} registros")
    print(f"  Paralelismo     : asyncio.gather (todos simultâneos)\n")

    t_start = time.monotonic()

    # ─── Disparo paralelo ─────────────────────────────────────────────────────
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            run_ingestor(name, cls, db, session, limit)
            for name, cls in active.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    db.close()

    # ─── Relatório final ──────────────────────────────────────────────────────
    t_total = time.monotonic() - t_start

    print("\n" + "═" * 65)
    print("  RELATÓRIO DE INGESTÃO")
    print("═" * 65)

    total_loaded = 0
    total_errors = 0
    for r in results:
        if isinstance(r, Exception):
            print(f"  ✗ EXCEÇÃO NÃO TRATADA: {r}")
            total_errors += 1
            continue
        status = "✓" if r.get("errors", 0) == 0 else "⚠"
        print(
            f"  {status} {r['source']:<20} "
            f"{r.get('loaded', 0):>5} carregados  "
            f"{r.get('errors', 0):>3} erros  "
            f"({r.get('elapsed', 0):.1f}s)"
        )
        total_loaded += r.get("loaded", 0)
        total_errors += r.get("errors", 0)

    print("─" * 65)
    print(f"  Total carregados : {total_loaded}")
    print(f"  Total erros      : {total_errors}")
    print(f"  Tempo total      : {t_total:.1f}s")

    # ─── Stats do banco ───────────────────────────────────────────────────────
    db2 = DB()
    s = db_stats(db2)
    db2.close()
    print("\n  BANCO DE INTELIGÊNCIA:")
    print(f"  🔴 Procurados     : {s.get('wanted', 0):>7}")
    print(f"  🟡 Desaparecidos  : {s.get('missing', 0):>7}")
    print(f"  📊 Total          : {s.get('total', 0):>7}")
    print(f"  🧬 Com biometria  : {s.get('with_biometrics', 0):>7}")
    print("═" * 65)

    # ─── Extração de embeddings ───────────────────────────────────────────────
    if not no_embed and total_loaded > 0:
        print("\n  🧬 Iniciando Delta Embedding Updater [Fase 14]...")
        try:
            from delta_embedder import run_delta
            embed_stats = run_delta(batch_size=32)
            print(
                f"  🧬 Embeddings: "
                f"+{embed_stats['processed']} novos | "
                f"{embed_stats['total_indexed']} total no FAISS"
            )
        except Exception as e:
            log.error(f"Erro no delta_embedder: {e}. Tente manualmente: python extract_embeddings.py")

    print("\n  ✅ Pipeline Fase 10+14 concluído.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Olho de Deus — Parallel Global Intelligence Sync"
    )
    parser.add_argument(
        "--source", action="append", dest="sources",
        choices=list(INGESTOR_REGISTRY.keys()),
        help="Executar apenas fonte(s) específica(s) (pode repetir)",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Limite de registros por fonte (default: 50)",
    )
    parser.add_argument(
        "--no-embed", action="store_true",
        help="Pular extração de embeddings ArcFace ao final",
    )
    args = parser.parse_args()

    asyncio.run(pipeline(
        sources=args.sources,
        limit=args.limit,
        no_embed=args.no_embed,
    ))


if __name__ == "__main__":
    main()
