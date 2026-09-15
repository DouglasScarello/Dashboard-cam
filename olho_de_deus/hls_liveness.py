#!/usr/bin/env python3
"""
Verificação de liveness pros streams HLS diretos (.m3u8), separado do
camera_liveness.py que só sabe validar YouTube via yt-dlp.

Achado real (2026-08-30): a maior parte do catálogo não é YouTube — são
streams HLS diretos de sistemas de câmera de trânsito governamentais reais
(Delaware DOT, Maryland SHA, Virginia DOT, Caltrans, Wowza de prefeituras,
+ internacionais). Nunca foram validadas de verdade porque os scripts
anteriores só sabiam lidar com YouTube.

Método de checagem:
1. HTTP GET direto na URL .m3u8 com timeout curto.
2. Resposta 200 + conteúdo começa com "#EXTM3U" -> manifesto HLS válido.
3. Contém "#EXT-X-ENDLIST" -> é uma gravação que já terminou (VOD), não um
   loop ao vivo -> não serve como "câmera ao vivo", tratado como morto.
4. Qualquer erro (404, timeout, conexão recusada) -> morto, mas só depois
   de tentar de novo (ver retry abaixo).

Achado real (2026-08-30, "efeito zumbi" reportado pelo usuário): algumas
câmeras passavam nessa checagem (manifesto principal responde 200 e é HLS
válido) mas ficavam com tela preta na prática — porque o manifesto
PRINCIPAL é só uma "master playlist" que aponta pra sub-playlists
("chunklists") por qualidade, e É A SUB-PLAYLIST que tem os segmentos de
vídeo reais. Confirmado num caso real: master playlist 200 OK, chunklist
referenciada dentro dela 404. Por isso agora, quando o manifesto é uma
master playlist (tem `#EXT-X-STREAM-INF`), o checker segue pra primeira
sub-playlist e só declara LIVE se ELA também for um manifesto HLS válido
— não confia só no nível superior.

Achado real (2026-09-15): este script escrevia em `database/
camera_liveness_state.json`, que `camera_grid_server.py` parou de refletir
de forma útil (arquivo ficou congelado, sem ninguém escrevendo, e a API
pública nunca tratava esses dados como atuais). Migrado pra escrever direto
nas mesmas colunas SQLite que `camera_liveness.py` usa, com a MESMA proteção
de retry+streak (ver `liveness_common.py`) — sem isso, repetiríamos aqui o
incidente de 693/823 câmeras marcadas mortas de uma vez por bloqueio de
rede, só que em ~2500-4700 câmeras HLS de uma vez.
"""

import argparse
import concurrent.futures
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from liveness_common import (
    DB_PATH,
    aplicar_resultados,
    buscar_candidatas,
    garante_schema_liveness,
)

USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; verificacao de liveness de cameras publicas)"
TIMEOUT_SECONDS = 8

# Mesma disciplina de retry usada em camera_liveness.py — um timeout/erro de
# rede pontual numa câmera isolada não pode virar "confirmado morto" numa
# checagem só. Não substitui o streak (que protege contra bloqueio
# SISTÊMICO); protege contra ruído pontual de uma câmera isolada.
RETRY_TENTATIVAS = 2
RETRY_ESPERA_BASE_S = 2.0


def is_hls_url(url: str) -> bool:
    return bool(url) and "youtube.com" not in url and "youtu.be" not in url


def _fetch_manifest(url: str) -> Optional[str]:
    """GET simples; devolve o corpo (texto) ou lança exceção em qualquer erro."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(url, resp.status, "não-200", None, None)
        return resp.read(8192).decode("utf-8", errors="ignore")


def _check_one_hls_sem_retry(url: str, _depth: int = 0) -> Dict[str, Any]:
    try:
        body = _fetch_manifest(url)
    except Exception as e:
        return {"status": "DEAD", "is_live": False, "error": f"{type(e).__name__}: {e}"[:300]}

    if not body or not body.lstrip().startswith("#EXTM3U"):
        return {"status": "DEAD", "is_live": False, "error": "resposta não é um manifesto HLS válido"}
    if "#EXT-X-ENDLIST" in body:
        return {"status": "ENDED_BUT_EXISTS", "is_live": False, "error": None}

    if "#EXT-X-STREAM-INF" in body and _depth == 0:
        # Master playlist — só aponta pra sub-playlists por qualidade, não
        # tem segmento nenhum aqui. "Efeito zumbi" real (2026-08-30): esse
        # nível responder 200 não prova nada, a câmera da rua já foi vista
        # com o manifesto principal OK e a sub-playlist real dando 404.
        first_variant = next((ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("#")), None)
        if not first_variant:
            return {"status": "DEAD", "is_live": False, "error": "master playlist sem nenhuma variante listada"}
        sub_url = urllib.parse.urljoin(url, first_variant)
        return _check_one_hls_sem_retry(sub_url, _depth=1)

    # Playlist de mídia (tem segmentos de verdade, ou é a sub-playlist que
    # acabamos de seguir) — chegou até aqui com #EXTM3U válido e sem
    # #EXT-X-ENDLIST, então é um loop ao vivo real.
    return {"status": "LIVE", "is_live": True, "error": None}


def check_one_hls(url: str) -> Dict[str, Any]:
    """Tenta de novo antes de declarar morta — mesmo raciocínio de
    camera_liveness.py::check_one: se for vídeo/stream de fato indisponível,
    a re-tentativa dá o mesmo resultado (custa só alguns segundos); se for
    soluço de rede, a re-tentativa resolve."""
    ultimo = None
    for tentativa in range(RETRY_TENTATIVAS + 1):
        ultimo = _check_one_hls_sem_retry(url)
        if ultimo["status"] != "DEAD":
            return ultimo
        if tentativa < RETRY_TENTATIVAS:
            time.sleep(RETRY_ESPERA_BASE_S * (tentativa + 1))
    return ultimo


def buscar_candidatas_hls(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Câmeras HLS diretas: `stream_format='M3U8'` explícito, OU
    `stream_format` vazio/legado cuja URL não é YouTube (achado 2026-09-15:
    2209 câmeras do catálogo têm `stream_format` vazio mas URL de Wowza/
    CDN direta — mesma família de `stream_format='M3U8'`, só sem o rótulo).
    Exclui explicitamente SNAPSHOT_JPEG e YOUTUBE, que têm checador
    próprio. Seleção de candidatas centralizada em
    `liveness_common.buscar_candidatas` (achado 2026-09-15, revisado: a
    condição antiga aqui era `confirmed_dead = 0`, que travava uma câmera
    fora da varredura já na 1ª falha — ver o docstring de lá)."""
    return buscar_candidatas(
        conn,
        excluir_stream_formats=["SNAPSHOT_JPEG", "YOUTUBE"],
        excluir_youtube_por_url=True,
        limit=limit,
    )


def run(concurrency: int, limit: Optional[int], dry_run: bool) -> Dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    garante_schema_liveness(conn)
    conn.commit()

    cameras = buscar_candidatas_hls(conn, limit)
    conn.close()

    def work(cam):
        r = check_one_hls(cam["url"])
        r["dead_streak_anterior"] = cam.get("dead_streak") or 0
        # live_status guarda o texto ORIGINAL (distingue "ended_but_exists"
        # de um 404 puro pra quem for depurar depois) — mas o campo "status"
        # que vai pra aplicar_resultados precisa virar DEAD explicitamente.
        # Achado (2026-09-15): sem essa normalização, "ENDED_BUT_EXISTS"
        # (stream que virou gravação encerrada) não é nem "LIVE" nem "DEAD"
        # pro vocabulário que aplicar_resultados entende — era descartado
        # como "sem voto" pra sempre, nunca confirmado morto, re-testado
        # em toda rodada futura sem nunca chegar a uma conclusão.
        r["live_status"] = "is_live" if r["status"] == "LIVE" else (r.get("status") or "offline").lower()
        r["status"] = "LIVE" if r["status"] == "LIVE" else "DEAD"
        return cam["id"], r

    results: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, cameras):
            results[cam_id] = r

    live_count = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead_count = sum(1 for r in results.values() if r["status"] != "LIVE")
    print(
        f"Checados {len(results)} streams HLS diretos — LIVE: {live_count} "
        f"({live_count/max(1,len(results))*100:.1f}%) | MORTO/ENCERRADO: {dead_count}"
    )

    if dry_run:
        print("[DRY-RUN] Nada foi escrito no banco. Amostra de mortos:")
        mortos = [(cid, r) for cid, r in results.items() if r["status"] != "LIVE"][:30]
        for cid, r in mortos:
            print(f"  {cid}: {r.get('error') or r['status']}")
        return {"checked": len(results), "live": live_count, "dead": dead_count, "dry_run": True}

    conn = sqlite3.connect(DB_PATH)
    with conn:
        aplicar_resultados(conn, results)
    conn.close()

    return {"checked": len(results), "live": live_count, "dead": dead_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=30, help="checagens simultâneas — streams diretos não têm bloqueio anti-bot tipo YouTube, pode ser mais agressivo")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="só relatório, não escreve no banco")
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit, dry_run=args.dry_run)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
