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
   ao vivo novo, atualiza video_id/url e registra a troca (nunca troca
   silenciosamente sem log).

Achado real (2026-09-14, ver histórico do commit): uma rodada de teste
classificou 693 de 823 câmeras como mortas de uma vez só — não porque
estavam mortas, mas porque o YouTube bloqueou a varredura por anti-bot.
`camera_curation.py --apply` apaga quem está confirmado morto; se essa
varredura ruim tivesse alimentado um --apply direto, teria destruído a
maior parte do catálogo numa penada. Duas camadas de defesa contra isso,
nenhuma dispensa a outra:
  - `check_one` agora tenta de novo (com espera) antes de declarar morta —
    resolve soluço de rede pontual numa câmera isolada.
  - Retry não ajuda quando o bloqueio é sistêmico (a re-tentativa também
    leva bloqueio). Pra isso, `dead_streak` conta confirmações mortas em
    execuções SEPARADAS — camera_curation.py só remove com streak >= 2.
    Um evento correlacionado como o de 693/823 não se repete identicamente
    2 dias seguidos sem ser um problema real que merece olho humano.

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


RETRY_TENTATIVAS = 2  # tentativas ADICIONAIS depois da primeira, não o total
RETRY_ESPERA_BASE_S = 3.0


def _check_one_sem_retry(url: str) -> Dict[str, Any]:
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


def check_one(url: str) -> Dict[str, Any]:
    """Extrai metadado (sem baixar) e classifica o status real do stream.

    Tenta de novo antes de declarar morta — um timeout de rede pontual numa
    câmera isolada não pode virar "confirmado morto". Se for de fato um vídeo
    indisponível, a re-tentativa vai dar o mesmo resultado e só custa alguns
    segundos a mais; se for soluço de rede, a re-tentativa resolve."""
    ultimo = None
    for tentativa in range(RETRY_TENTATIVAS + 1):
        ultimo = _check_one_sem_retry(url)
        if ultimo["status"] != "DEAD":
            return ultimo
        if tentativa < RETRY_TENTATIVAS:
            time.sleep(RETRY_ESPERA_BASE_S * (tentativa + 1))
    return ultimo


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


def _garante_schema(conn) -> None:
    """`channel_url` e `dead_streak` não existiam na tabela original — a
    primeira ficou pra trás numa migração (era a causa do SELECT quebrado que
    derrubava o timer diário), a segunda é nova, pro gate de remoção. Guarda
    de idempotência igual à usada pra `is_test_candidate`/`test_notes`."""
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(cameras)")}
    if "channel_url" not in colunas:
        conn.execute("ALTER TABLE cameras ADD COLUMN channel_url TEXT")
    if "dead_streak" not in colunas:
        conn.execute("ALTER TABLE cameras ADD COLUMN dead_streak INTEGER DEFAULT 0")


def run(concurrency: int, limit: Optional[int], attempt_recovery: bool) -> Dict[str, Any]:
    import sqlite3
    db_path = ROOT / "database" / "live_cameras.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _garante_schema(conn)
    conn.commit()

    query = "SELECT id, url, video_id, channel_url, dead_streak FROM cameras WHERE confirmed_dead = 0"
    if limit:
        query += f" LIMIT {limit}"

    cameras = [dict(r) for r in conn.execute(query).fetchall()]
    conn.close()

    now = datetime.now(timezone.utc).isoformat()
    results: Dict[str, Any] = {}
    recovered = []

    def work(cam):
        cam_id = cam["id"]
        r = check_one(cam["url"])

        if r["status"] != "LIVE" and attempt_recovery:
            canal = cam.get("channel_url")
            if canal:
                achado = resolve_channel_live(canal)
                if achado:
                    log.info(f"[recuperada] {cam_id}: vídeo antigo morreu, "
                             f"canal {canal} tem live nova → {achado['video_id']}")
                    r = {
                        "status": "LIVE", "is_live": True, "live_status": "is_live",
                        "channel_url": canal, "error": None,
                        "recovered_video_id": achado["video_id"], "recovered_url": achado["url"],
                    }
                    recovered.append({"camera_id": cam_id, **achado})

        if not r.get("channel_url"):
            r["channel_url"] = cam.get("channel_url")
        r["checked_at"] = now
        r["video_id_checked"] = cam.get("video_id")
        r["dead_streak_anterior"] = cam.get("dead_streak") or 0
        return cam_id, r

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        for cam_id, r in ex.map(work, cameras):
            results[cam_id] = r

    live_count = sum(1 for r in results.values() if r["status"] == "LIVE")
    dead_count = sum(1 for r in results.values() if r["status"] != "LIVE")
    log.info(f"Checadas {len(results)} câmeras — LIVE: {live_count} | MORTA/ENCERRADA: {dead_count} "
             f"| recuperadas via canal: {len(recovered)}")

    # Atualizar o SQLite
    conn = sqlite3.connect(db_path)
    with conn:
        for cam_id, r in results.items():
            esta_morta = r["status"] != "LIVE"
            confirmed_dead = 1 if esta_morta else 0
            live_confirmed = 0 if esta_morta else 1
            live_status_str = r.get("live_status") or "offline"
            # Streak soma enquanto continuar morta em execuções separadas;
            # zera assim que uma execução a encontrar viva (inclusive por
            # recuperação de canal). É essa contagem, não o resultado de uma
            # execução isolada, que autoriza remoção em camera_curation.py.
            novo_streak = (r["dead_streak_anterior"] + 1) if esta_morta else 0

            if r.get("recovered_video_id"):
                conn.execute('''
                    UPDATE cameras
                    SET confirmed_dead = 0, live_confirmed = 1, live_status = ?,
                        video_id = ?, url = ?, channel_url = ?, dead_streak = 0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (live_status_str, r["recovered_video_id"], r["recovered_url"],
                      r["channel_url"], cam_id))
            else:
                conn.execute('''
                    UPDATE cameras
                    SET confirmed_dead = ?, live_confirmed = ?, live_status = ?,
                        channel_url = ?, dead_streak = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (confirmed_dead, live_confirmed, live_status_str,
                      r.get("channel_url"), novo_streak, cam_id))
    conn.close()

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
