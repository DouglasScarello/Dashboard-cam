#!/usr/bin/env python3
"""
Verificação de liveness das câmeras (lives de terceiros no YouTube).

Problema real: `database/live_cameras.json` guarda um video_id fixo por
câmera, mas são lives de terceiros (prefeituras, pessoas comuns) — quando o
streamer encerra e reinicia a transmissão, o video_id muda ou simplesmente
some. Sem checagem, o dashboard mostra como "ativa" uma câmera que já morreu
há horas, e o usuário só descobre ao clicar (tela "Vídeo indisponível").

O que este módulo faz:
1. Checa cada camera.url via yt-dlp (extração só de metadado, sem baixar
   vídeo) e grava o resultado em `database/camera_liveness_state.json`.
2. Enquanto uma câmera está viva, guarda o `channel_url` dela — é a única
   forma de tentar recuperar automaticamente se o vídeo específico morrer
   depois (YouTube redireciona <channel>/live pro stream ativo do canal).
3. Se uma câmera está marcada morta mas já temos o channel_url de uma
   checagem anterior, tenta resolver <channel_url>/live; se achar um vídeo
   ao vivo novo, atualiza video_id/url em live_cameras.json e registra a
   troca (nunca troca silenciosamente sem log).

Intervalo real de rotatividade das lives: NÃO é conhecido a priori — a
estimativa do usuário foi "~6h" mas isso precisa ser observado, não
assumido. Cada rodada desta checagem grava `checked_at`; rodando este
script periodicamente (ver `--help` pra intervalo sugerido) e comparando
`checked_at`/`status` ao longo do tempo dá o dado real de quanto tempo cada
stream fica no ar antes de cair — não adivinhar esse número.
"""

import argparse
import concurrent.futures
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yt_dlp

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
STATE_PATH = ROOT / "database" / "camera_liveness_state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [LIVENESS] %(message)s")
log = logging.getLogger("camera_liveness")

YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "simulate": True,
    "noplaylist": True,
    "socket_timeout": 8,
    "extractor_retries": 0,
    # Client "web" (padrão do yt-dlp) leva bloqueio "Sign in to confirm
    # you're not a bot" em varreduras de centenas de vídeos seguidos — já
    # aconteceu aqui (rodada de teste: 693/823 vieram falso-DEAD só por
    # isso). O client "android" não passa por esse checkpoint anti-bot.
    "extractor_args": {"youtube": {"player_client": ["android"]}},
}


def check_one(url: str) -> Dict[str, Any]:
    """Extrai metadado (sem baixar) e classifica o status real do stream."""
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            is_live = bool(info.get("is_live"))
            return {
                "status": "LIVE" if is_live else "ENDED_BUT_EXISTS",
                "is_live": is_live,
                "live_status": info.get("live_status"),
                "channel_url": info.get("channel_url"),
                "error": None,
            }
        except Exception as e:
            msg = str(e)
            # yt-dlp distingue "gravação indisponível" (stream antigo morreu,
            # sem replay) de "vídeo indisponível" (removido/privado) — ambos
            # significam, pra nós, "não dá pra abrir agora".
            return {
                "status": "DEAD",
                "is_live": False,
                "live_status": None,
                "channel_url": None,
                "error": msg[:300],
            }


def resolve_channel_live(channel_url: str) -> Optional[Dict[str, str]]:
    """Tenta achar o stream ATUAL de um canal (<channel>/live). Só é chamado
    quando o video_id salvo já morreu e temos o canal de uma checagem
    anterior — é a única forma real de recuperação automática."""
    live_url = channel_url.rstrip("/") + "/live"
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        try:
            info = ydl.extract_info(live_url, download=False)
            if info.get("is_live") and info.get("id"):
                return {"video_id": info["id"], "url": f"https://www.youtube.com/watch?v={info['id']}"}
        except Exception:
            pass
    return None


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


def run(concurrency: int, limit: Optional[int], attempt_recovery: bool) -> Dict[str, Any]:
    # Full_cameras é sempre a lista COMPLETA do disco — nunca truncada.
    # `cameras` (possivelmente limitada por --limit, só para teste) é o
    # subconjunto que de fato checamos nesta rodada. A gravação de volta em
    # CAMERAS_PATH sempre parte de full_cameras, senão um teste com --limit
    # sobrescreveria o arquivo inteiro com só o subconjunto testado (bug já
    # aconteceu uma vez aqui: apagou 783 de 823 câmeras — restaurado via git).
    full_cameras = load_json(CAMERAS_PATH, [])
    cameras = full_cameras[:limit] if limit else full_cameras

    prev_state = load_json(STATE_PATH, {})
    now = datetime.now(timezone.utc).isoformat()

    results: Dict[str, Any] = {}
    recovered = []

    def work(cam):
        cam_id = cam["id"]
        r = check_one(cam["url"])
        # Preserva o último channel_url conhecido se a checagem atual não
        # trouxe um novo (ex: quando o vídeo já morreu, não há metadado).
        if not r["channel_url"]:
            r["channel_url"] = prev_state.get(cam_id, {}).get("channel_url")
        r["checked_at"] = now
        r["video_id_checked"] = cam.get("video_id")
        return cam_id, r

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, cameras):
            results[cam_id] = r

    live_count = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead_count = sum(1 for r in results.values() if r["status"] != "LIVE")
    log.info(f"Checadas {len(results)} câmeras — LIVE: {live_count} | MORTA/ENCERRADA: {dead_count}")

    if attempt_recovery:
        # Acha canais "agregadores" — um channel_url usado por MAIS DE UMA
        # câmera distinta. Achado real (2026-08-30): canal do SkylineWebcams
        # hospeda dezenas de vídeos de câmeras diferentes; recuperar via
        # <canal>/live resolve pro ÚNICO vídeo em destaque do canal, então
        # todas as câmeras "mortas" daquele canal viravam cópias umas das
        # outras — 11 câmeras diferentes colapsaram na mesma live por causa
        # disso antes desta checagem existir. Canal agregador nunca é usado
        # pra recuperação: não dá pra saber qual vídeo específico do canal
        # correspondia à câmera original.
        channel_to_cams: Dict[str, set] = {}
        for cid, r in results.items():
            ch = r.get("channel_url")
            if ch:
                channel_to_cams.setdefault(ch, set()).add(cid)
        for cid, entry in prev_state.items():
            ch = entry.get("channel_url")
            if ch:
                channel_to_cams.setdefault(ch, set()).add(cid)
        aggregator_channels = {ch for ch, cids in channel_to_cams.items() if len(cids) > 1}
        if aggregator_channels:
            log.info(f"{len(aggregator_channels)} canal(is) agregador(es) detectado(s) — recuperação desativada pra eles.")

        # Atualiza in-place dentro de full_cameras (lista completa), nunca
        # dentro do subconjunto `cameras` — ver comentário acima.
        full_by_id = {c["id"]: c for c in full_cameras}
        for cam_id, r in results.items():
            if r.get("channel_url") in aggregator_channels:
                continue
            if r["status"] == "LIVE" or not r.get("channel_url"):
                continue
            new = resolve_channel_live(r["channel_url"])
            if new and new["video_id"] != r.get("video_id_checked") and cam_id in full_by_id:
                old_video_id = full_by_id[cam_id].get("video_id")
                full_by_id[cam_id]["video_id"] = new["video_id"]
                full_by_id[cam_id]["url"] = new["url"]
                results[cam_id]["status"] = "LIVE"
                results[cam_id]["is_live"] = True
                results[cam_id]["recovered_from"] = old_video_id
                recovered.append({"id": cam_id, "old_video_id": old_video_id, "new_video_id": new["video_id"]})
                log.info(f"Recuperada {cam_id}: {old_video_id} -> {new['video_id']} (mesmo canal)")

        if recovered:
            # Grava a lista COMPLETA (full_cameras já atualizada in-place via
            # full_by_id, que compartilha os mesmos dicts), nunca o subconjunto.
            assert len(full_cameras) == len(full_by_id), "sanity check: recuperação nunca pode mudar o total de câmeras"
            save_json(CAMERAS_PATH, full_cameras)

    save_json(STATE_PATH, results)
    return {
        "checked": len(results),
        "live": live_count,
        "dead": dead_count,
        "recovered": recovered,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--concurrency", type=int, default=10, help="checagens simultâneas (padrão 10 — moderado pra não levar rate-limit do YouTube)")
    parser.add_argument("--limit", type=int, default=None, help="checar só as N primeiras câmeras (pra teste)")
    parser.add_argument("--no-recovery", action="store_true", help="só checar status, não tentar recuperar via <canal>/live")
    args = parser.parse_args()

    t0 = time.time()
    summary = run(concurrency=args.concurrency, limit=args.limit, attempt_recovery=not args.no_recovery)
    summary["elapsed_seconds"] = round(time.time() - t0, 1)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
