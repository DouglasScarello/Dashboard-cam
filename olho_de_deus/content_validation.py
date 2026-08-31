#!/usr/bin/env python3
"""
Detecta "câmeras" que na verdade são TV/streams de terceiros, não câmeras
de monitoramento reais.

Problema real (achado 2026-08-30, relatado pelo usuário): cam_30
("Câmera de Monitoramento Curitiba / Foz do Iguaçu") é, na verdade, o
canal oficial do SBT transmitindo programação normal (título real: "SBT Ao
Vivo 2026-08-30 20:53", channel="SBT"). A curadoria anterior
(camera_liveness.py) só valida se o vídeo está "ao vivo" — nunca validou
se o CONTEÚDO é realmente uma câmera fixa. Esse é um problema pré-existente
no dataset original, não introduzido pela curadoria de liveness.

Heurísticas aplicadas (nenhuma sozinha é 100% — combinadas dão confiança
razoável; qualquer câmera flagada fica registrada em
`content_validation_report.json` pra revisão antes de decidir remover):

1. BLOCKLIST de canais de emissora de TV conhecida (nome exato do
   `channel`). Assinatura mais forte — um "SBT"/"Globo"/etc no campo
   channel não é uma prefeitura nem um streamer de webcam.
2. Data/hora no TÍTULO (ex: "SBT Ao Vivo 2026-08-30 20:53"). Câmeras fixas
   de monitoramento não geram um título novo por dia — isso é assinatura
   de transmissão editorial/jornalística.
3. Palavras-chave de programação editorial no título (ex: "ao vivo",
   "jornal", "novela", "podcast", "programa") combinadas com um canal que
   não é claramente uma prefeitura/orgão público (heurística mais fraca,
   só usada como sinal auxiliar, não decide sozinha).
"""

import argparse
import concurrent.futures
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yt_dlp

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
REPORT_PATH = ROOT / "database" / "content_validation_report.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CONTENT-CHECK] %(message)s")
log = logging.getLogger("content_validation")

YDL_OPTS = {
    "quiet": True, "no_warnings": True, "skip_download": True, "simulate": True,
    "noplaylist": True, "socket_timeout": 8, "extractor_retries": 0,
    "extractor_args": {"youtube": {"player_client": ["android"]}},
}

# Emissoras/redes de TV e rádio brasileiras (+ algumas internacionais) que
# jamais são uma câmera fixa de monitoramento — canal oficial transmitindo
# = programação editorial, não uma webcam de rua/praia/prefeitura.
BROADCASTER_BLOCKLIST = {
    "sbt", "rede globo", "globo", "globoplay", "record tv", "rede record",
    "band", "bandeirantes", "redetv", "rede tv", "cnn brasil", "jovem pan",
    "band news", "bandnews", "tv cultura", "gnt", "multishow", "sportv",
    "espn brasil", "cazé tv", "flow podcast", "podpah", "canal do vlad",
    "uol", "folha de s.paulo", "estadão", "veja", "cbn", "band play",
    "terra", "r7", "metropoles", "ig", "fox sports brasil",
}

DATE_IN_TITLE_RE = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]20\d{2})\b")
EDITORIAL_KEYWORDS_RE = re.compile(
    r"\b(jornal|novela|podcast|programa|talk show|entrevista|debate|plantão|telejornal)\b",
    re.IGNORECASE,
)


def classify(title: str, channel: str) -> Dict[str, Any]:
    title_l = (title or "").lower()
    channel_l = (channel or "").strip().lower()

    reasons = []
    if channel_l in BROADCASTER_BLOCKLIST:
        reasons.append(f"canal na blocklist de emissoras: '{channel}'")
    if DATE_IN_TITLE_RE.search(title or ""):
        reasons.append("título contém data (típico de transmissão editorial diária, não câmera fixa)")
    if EDITORIAL_KEYWORDS_RE.search(title or ""):
        reasons.append("título contém palavra-chave editorial (jornal/novela/podcast/programa/etc)")

    # Confiança: blocklist sozinha já é suficiente; as outras duas juntas
    # (sem blocklist) também são um sinal forte o bastante pra flagar.
    is_broadcaster = bool(
        channel_l in BROADCASTER_BLOCKLIST
        or (DATE_IN_TITLE_RE.search(title or "") and EDITORIAL_KEYWORDS_RE.search(title or ""))
    )
    return {"is_broadcaster": is_broadcaster, "reasons": reasons}


def check_content(url: str) -> Dict[str, Any]:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            title = info.get("title") or ""
            channel = info.get("channel") or ""
            classification = classify(title, channel)
            return {
                "title": title,
                "channel": channel,
                "channel_url": info.get("channel_url"),
                "error": None,
                **classification,
            }
        except Exception as e:
            return {"title": None, "channel": None, "channel_url": None,
                    "error": str(e)[:300], "is_broadcaster": False, "reasons": []}


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


def run(concurrency: int, limit: Optional[int], apply_removal: bool) -> Dict[str, Any]:
    full_cameras = load_json(CAMERAS_PATH, [])
    cameras = full_cameras[:limit] if limit else full_cameras

    def work(cam):
        return cam["id"], check_content(cam["url"])

    results: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, cameras):
            results[cam_id] = r

    flagged = {cid: r for cid, r in results.items() if r["is_broadcaster"]}
    log.info(f"Checadas {len(results)} câmeras — {len(flagged)} identificadas como TV/broadcaster, não câmera real.")
    for cid, r in flagged.items():
        cam = next((c for c in cameras if c["id"] == cid), {})
        log.warning(f"  {cid} ({cam.get('nome')}): channel='{r['channel']}' title='{r['title']}' — {'; '.join(r['reasons'])}")

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "total_checked": len(results),
        "flagged_count": len(flagged),
        "flagged": {
            cid: {
                "nome": next((c["nome"] for c in cameras if c["id"] == cid), None),
                **r,
            }
            for cid, r in flagged.items()
        },
    }
    save_json(REPORT_PATH, report)

    removed = []
    if apply_removal and flagged:
        remaining = [c for c in full_cameras if c["id"] not in flagged]
        removed = [{"id": cid, "nome": next((c["nome"] for c in cameras if c["id"] == cid), None)} for cid in flagged]
        save_json(CAMERAS_PATH, remaining)
        log.info(f"Removidas {len(removed)} entradas de {CAMERAS_PATH.name} ({len(full_cameras)} -> {len(remaining)}).")

    return {
        "checked": len(results),
        "flagged": len(flagged),
        "removed": len(removed),
        "report_path": str(REPORT_PATH),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None, help="checar só as N primeiras (teste)")
    parser.add_argument("--apply", action="store_true", help="remove de verdade as flagadas de live_cameras.json (sem isso, só gera o relatório)")
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit, apply_removal=args.apply)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
