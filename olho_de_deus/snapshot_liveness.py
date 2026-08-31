#!/usr/bin/env python3
"""
Verificação de liveness pras câmeras tipo "snapshot" (imagem JPEG única
que atualiza a cada request — ex: Ontario 511, câmeras Axis diretas),
diferente de hls_liveness.py (que valida manifesto .m3u8) e
camera_liveness.py (YouTube via yt-dlp).

Checagem: HTTP GET direto, confere status 200 + os primeiros bytes serem
mesmo um JPEG real (magic bytes FF D8 FF) — não confia só no status HTTP,
já que um servidor pode devolver 200 com uma página de erro em HTML.

Escreve no MESMO database/camera_liveness_state.json que as outras duas
checagens usam — camera_grid_server.py já lê esse arquivo de forma
genérica por câmera, sem precisar saber o tipo de fonte.
"""

import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
STATE_PATH = ROOT / "database" / "camera_liveness_state.json"

USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; verificacao de liveness de cameras publicas)"
TIMEOUT_SECONDS = 10
JPEG_MAGIC = b"\xff\xd8\xff"


def is_snapshot_camera(cam: Dict[str, Any]) -> bool:
    return cam.get("stream_format") == "SNAPSHOT_JPEG"


def check_one_snapshot(url: str) -> Dict[str, Any]:
    """Achado real (2026-08-31): alguns hosts (ex: weathercam.digitraffic.fi)
    aplicam rate-limit agressivo por IP — sob concorrência alta, várias
    câmeras genuinamente vivas voltam HTTP 429 ao mesmo tempo. Tratar 429
    como "morta" apagaria centenas de câmeras reais só por causa de
    etiqueta de rede, não porque a câmera parou de existir. Por isso 429
    vira um status PRÓPRIO (RATE_LIMITED) — nem confirma viva nem confirma
    morta; `run()` nunca deixa isso sobrescrever um LIVE anterior."""
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
    cameras = json.load(open(CAMERAS_PATH, "r", encoding="utf-8"))
    snap_cameras = [c for c in cameras if is_snapshot_camera(c)]
    if limit:
        snap_cameras = snap_cameras[:limit]

    state = load_json(STATE_PATH, {})
    now = datetime.now(timezone.utc).isoformat()

    def work(cam):
        r = check_one_snapshot(cam["url"])
        r["checked_at"] = now
        r["video_id_checked"] = None
        r["channel_url"] = None
        return cam["id"], r

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, snap_cameras):
            results[cam_id] = r

    rate_limited = sum(1 for r in results.values() if r["status"] == "RATE_LIMITED")
    live = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead = sum(1 for r in results.values() if r["status"] == "DEAD")
    print(
        f"Checadas {len(results)} câmeras snapshot — LIVE: {live} "
        f"({live/max(1,len(results))*100:.1f}%) | MORTAS: {dead} | "
        f"RATE-LIMITED (inconclusivo, estado anterior preservado): {rate_limited}"
    )

    # RATE_LIMITED nunca sobrescreve o estado anterior — é inconclusivo,
    # não prova nem vida nem morte. Só grava se ainda não havia nada pra
    # essa câmera (cold start honesto: fica UNKNOWN até uma checagem real).
    for cam_id, r in results.items():
        if r["status"] == "RATE_LIMITED" and cam_id in state:
            continue
        state[cam_id] = r
    save_json(STATE_PATH, state)
    return {"checked": len(results), "live": live, "dead": dead, "rate_limited": rate_limited}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
