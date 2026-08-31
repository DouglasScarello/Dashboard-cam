#!/usr/bin/env python3
"""
Verificação de liveness pros streams HLS diretos (.m3u8), separado do
camera_liveness.py que só sabe validar YouTube via yt-dlp.

Achado real (2026-08-30): 2516 das 3587 câmeras (70%) não são YouTube —
são streams HLS diretos de sistemas de câmera de trânsito governamentais
reais (Delaware DOT, Maryland SHA, Virginia DOT, Caltrans, + alguns
internacionais como Indonésia/Portugal/Rússia). Nunca foram validadas de
verdade porque os scripts anteriores só sabem lidar com YouTube.

Método de checagem:
1. HTTP GET direto na URL .m3u8 com timeout curto.
2. Resposta 200 + conteúdo começa com "#EXTM3U" -> manifesto HLS válido.
3. Contém "#EXT-X-ENDLIST" -> é uma gravação que já terminou (VOD), não um
   loop ao vivo -> não serve como "câmera ao vivo", tratado como morto.
4. Qualquer erro (404, timeout, conexão recusada) -> morto.

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

Escreve no MESMO database/camera_liveness_state.json que o
camera_liveness.py usa — camera_grid_server.py já sabe ler esse arquivo
pra qualquer tipo de câmera, sem precisar de nenhuma mudança no backend.
"""

import argparse
import concurrent.futures
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
STATE_PATH = ROOT / "database" / "camera_liveness_state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [HLS-LIVENESS] %(message)s")
log = logging.getLogger("hls_liveness")

USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; verificacao de liveness de cameras publicas)"
TIMEOUT_SECONDS = 8


def is_hls_url(url: str) -> bool:
    return bool(url) and "youtube.com" not in url and "youtu.be" not in url


def _fetch_manifest(url: str) -> Optional[str]:
    """GET simples; devolve o corpo (texto) ou None em qualquer erro."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(url, resp.status, "não-200", None, None)
        return resp.read(8192).decode("utf-8", errors="ignore")


def check_one_hls(url: str, _depth: int = 0) -> Dict[str, Any]:
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
        return check_one_hls(sub_url, _depth=1)

    # Playlist de mídia (tem segmentos de verdade, ou é a sub-playlist que
    # acabamos de seguir) — chegou até aqui com #EXTM3U válido e sem
    # #EXT-X-ENDLIST, então é um loop ao vivo real.
    return {"status": "LIVE", "is_live": True, "error": None}


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def run(concurrency: int, limit: Optional[int]) -> Dict[str, Any]:
    cameras = load_json(CAMERAS_PATH, [])
    hls_cameras = [c for c in cameras if is_hls_url(c.get("url"))]
    if limit:
        hls_cameras = hls_cameras[:limit]

    state = load_json(STATE_PATH, {})
    now = datetime.now(timezone.utc).isoformat()

    def work(cam):
        r = check_one_hls(cam["url"])
        r["checked_at"] = now
        r["video_id_checked"] = None
        r["channel_url"] = None
        return cam["id"], r

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, hls_cameras):
            results[cam_id] = r

    live_count = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead_count = sum(1 for r in results.values() if r["status"] != "LIVE")
    log.info(f"Checados {len(results)} streams HLS diretos — LIVE: {live_count} ({live_count/max(1,len(results))*100:.1f}%) | MORTO/ENCERRADO: {dead_count}")

    # Mescla no state existente (que já tem os resultados de YouTube) —
    # nunca sobrescreve o arquivo inteiro, só as entradas HLS desta rodada.
    state.update(results)
    save_json(STATE_PATH, state)

    return {"checked": len(results), "live": live_count, "dead": dead_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=30, help="checagens simultâneas — streams diretos não têm bloqueio anti-bot tipo YouTube, pode ser mais agressivo")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
