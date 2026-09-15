#!/usr/bin/env python3
"""
Verificação de liveness pras câmeras tipo "snapshot" (imagem JPEG única
que atualiza a cada request — ex: Ontario 511, câmeras Axis diretas),
diferente de hls_liveness.py (que valida manifesto .m3u8) e
camera_liveness.py (YouTube via yt-dlp).

Checagem: HTTP GET direto, confere status 200 + os primeiros bytes serem
mesmo um JPEG real (magic bytes FF D8 FF) — não confia só no status HTTP,
já que um servidor pode devolver 200 com uma página de erro em HTML.

Achado real (2026-09-15): este script escrevia em `database/
camera_liveness_state.json`, que `camera_grid_server.py` parou de refletir
de forma útil (arquivo congelado, ninguém escrevendo, API pública nunca via
isso como atual). Migrado pra escrever direto nas mesmas colunas SQLite que
camera_liveness.py usa, com retry (ver abaixo) + streak de confirmação (ver
`liveness_common.py`) — mesma proteção contra o incidente de 693/823
câmeras marcadas mortas de uma vez por bloqueio de rede, aqui aplicada às
~4600 câmeras SNAPSHOT_JPEG do catálogo.
"""

import argparse
import concurrent.futures
import json
import sqlite3
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from liveness_common import (
    DB_PATH,
    aplicar_resultados,
    garante_schema_liveness,
)

USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; verificacao de liveness de cameras publicas)"
TIMEOUT_SECONDS = 10
JPEG_MAGIC = b"\xff\xd8\xff"

# Mesma disciplina de retry de hls_liveness.py/camera_liveness.py — só pra
# DEAD, nunca pra RATE_LIMITED (que já é seu próprio sinal "sem voto";
# tentar de novo na hora só bateria no mesmo rate-limit de novo).
RETRY_TENTATIVAS = 2
RETRY_ESPERA_BASE_S = 2.0


def _check_one_snapshot_sem_retry(url: str) -> Dict[str, Any]:
    """Achado real (2026-08-31): alguns hosts (ex: weathercam.digitraffic.fi)
    aplicam rate-limit agressivo por IP — sob concorrência alta, várias
    câmeras genuinamente vivas voltam HTTP 429 ao mesmo tempo. Tratar 429
    como "morta" apagaria centenas de câmeras reais só por causa de
    etiqueta de rede, não porque a câmera parou de existir. Por isso 429
    vira um status PRÓPRIO (RATE_LIMITED) — nem confirma viva nem confirma
    morta; `aplicar_resultados` (liveness_common.py) nunca deixa isso
    sobrescrever um estado anterior."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return {"status": "DEAD", "is_live": False, "error": f"HTTP {resp.status}"}
            head = resp.read(16)
            if not head.startswith(JPEG_MAGIC):
                return {"status": "DEAD", "is_live": False, "error": "resposta não é um JPEG válido"}
            return {"status": "LIVE", "is_live": True, "error": None}
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"status": "RATE_LIMITED", "is_live": None, "error": "HTTP 429 — inconclusivo, não é prova de morte"}
        return {"status": "DEAD", "is_live": False, "error": f"HTTPError: {e.code}"}
    except Exception as e:
        return {"status": "DEAD", "is_live": False, "error": f"{type(e).__name__}: {e}"[:300]}


def check_one_snapshot(url: str) -> Dict[str, Any]:
    """Tenta de novo antes de declarar morta — mesmo raciocínio dos outros
    dois checadores: soluço de rede pontual não pode virar "confirmado
    morto" numa checagem só. RATE_LIMITED não é retentado aqui (ver acima)."""
    ultimo = None
    for tentativa in range(RETRY_TENTATIVAS + 1):
        ultimo = _check_one_snapshot_sem_retry(url)
        if ultimo["status"] != "DEAD":
            return ultimo
        if tentativa < RETRY_TENTATIVAS:
            time.sleep(RETRY_ESPERA_BASE_S * (tentativa + 1))
    return ultimo


def buscar_candidatas_snapshot(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    query = "SELECT id, url, dead_streak FROM cameras WHERE confirmed_dead = 0 AND stream_format = 'SNAPSHOT_JPEG' AND url IS NOT NULL AND url != ''"
    params: List[Any] = []
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def run(concurrency: int, limit: Optional[int], dry_run: bool) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    garante_schema_liveness(conn)
    conn.commit()

    cameras = buscar_candidatas_snapshot(conn, limit)
    conn.close()

    def work(cam):
        r = check_one_snapshot(cam["url"])
        r["dead_streak_anterior"] = cam.get("dead_streak") or 0
        if r["status"] == "LIVE":
            r["live_status"] = "is_live"
        elif r["status"] == "RATE_LIMITED":
            r["live_status"] = "rate_limited"
        else:
            r["live_status"] = "offline"
        return cam["id"], r

    results: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, cameras):
            results[cam_id] = r

    rate_limited = sum(1 for r in results.values() if r["status"] == "RATE_LIMITED")
    live = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead = sum(1 for r in results.values() if r["status"] == "DEAD")
    print(
        f"Checadas {len(results)} câmeras snapshot — LIVE: {live} "
        f"({live/max(1,len(results))*100:.1f}%) | MORTAS: {dead} | "
        f"RATE-LIMITED (inconclusivo, estado anterior preservado): {rate_limited}"
    )

    if dry_run:
        print("[DRY-RUN] Nada foi escrito no banco. Amostra de mortas:")
        for cid, r in list(results.items()):
            if r["status"] == "DEAD":
                print(f"  {cid}: {r.get('error')}")
        return {"checked": len(results), "live": live, "dead": dead, "rate_limited": rate_limited, "dry_run": True}

    conn = sqlite3.connect(DB_PATH)
    with conn:
        aplicar_resultados(conn, results)
    conn.close()

    return {"checked": len(results), "live": live, "dead": dead, "rate_limited": rate_limited}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="só relatório, não escreve no banco")
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit, dry_run=args.dry_run)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
