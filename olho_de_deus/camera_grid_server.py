#!/usr/bin/env python3
"""
Camera Grid API — Olho de Deus.

Serviço FastAPI independente (porta 8001) que expõe listagem de câmeras
públicas do YouTube e thumbnails/URLs de stream resolvidas sob demanda.

Este serviço é puramente "scene-level": lista câmeras, gera thumbnails e
resolve URLs de stream. Não realiza nenhum reconhecimento facial ou
correspondência com watchlists (isso é feito por outro serviço).
"""

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from youtube_stream import get_live_url

log = logging.getLogger("camera_grid_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [CAM-GRID] %(message)s")

ROOT = Path(__file__).resolve().parent.parent
LIVE_CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
OMNI_CAMS_PATH = ROOT / "database" / "omni_cams.json"

STREAM_URL_TTL = 240.0  # 4 minutos
THUMBNAIL_TTL = 5.0     # 5 segundos

# Cadência do worker de detecção de perigo (round-robin, uma câmera por vez)
DANGER_ROUND_ROBIN_DELAY = 1.5  # segundos entre câmeras
DANGER_ALERT_ACTIVE_TTL = 30.0  # segundos que um alerta permanece "ativo"

app = FastAPI(title="Olho de Deus — Camera Grid API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# Estado / caches em memória
# --------------------------------------------------------------------------

_cameras: List[Dict[str, Any]] = []
_cameras_by_id: Dict[str, Dict[str, Any]] = {}

# cache de URL de stream resolvida: camera_id -> {"url": str|None, "ts": float}
_stream_url_cache: Dict[str, Dict[str, Any]] = {}

# cache do JPEG codificado: camera_id -> {"bytes": bytes, "ts": float}
_thumbnail_cache: Dict[str, Dict[str, Any]] = {}

# um lock por camera_id para evitar capturas/resoluções duplicadas concorrentes
# RLock (reentrante): _capture_thumbnail_sync mantém o lock enquanto chama
# _resolve_stream_url_sync, que adquire o mesmo lock de novo na mesma thread —
# com um Lock comum isso trava para sempre (a thread espera por si mesma).
_camera_locks: Dict[str, threading.RLock] = {}
_camera_locks_guard = threading.Lock()


def _get_camera_lock(camera_id: str) -> threading.RLock:
    with _camera_locks_guard:
        lock = _camera_locks.get(camera_id)
        if lock is None:
            lock = threading.RLock()
            _camera_locks[camera_id] = lock
        return lock


# --------------------------------------------------------------------------
# Detecção de perigo em background (scene-level: armas / queda de pessoa —
# SEM reconhecimento facial, SEM correspondência de identidade).
#
# _alerts: camera_id -> {"camera_id", "type", "level", "detail", "ts"}
# Protegido por _alerts_lock, um lock DEDICADO e pequeno — nunca é o mesmo
# lock usado para I/O de câmera (_camera_locks). O lock aqui só é mantido
# durante a leitura/escrita do dict em memória, nunca durante captura de
# frame ou inferência do modelo, então GET /api/alerts nunca trava.
# --------------------------------------------------------------------------

_alerts: Dict[str, Dict[str, Any]] = {}
_alerts_lock = threading.Lock()


def _set_alert(camera_id: str, alert_type: str, level: int, detail: str) -> None:
    with _alerts_lock:
        _alerts[camera_id] = {
            "camera_id": camera_id,
            "type": alert_type,
            "level": level,
            "detail": detail,
            "ts": time.time(),
        }


def _get_active_alerts() -> List[Dict[str, Any]]:
    now = time.time()
    with _alerts_lock:
        stale_ids = [
            cid for cid, a in _alerts.items()
            if (now - a["ts"]) >= DANGER_ALERT_ACTIVE_TTL
        ]
        for cid in stale_ids:
            del _alerts[cid]
        return list(_alerts.values())


# --------------------------------------------------------------------------
# Carregamento da lista de câmeras
# --------------------------------------------------------------------------

def load_cameras() -> List[Dict[str, Any]]:
    """Carrega a lista de câmeras a partir de live_cameras.json (filtrando
    status == "LIVE"), com fallback para omni_cams.json (sem filtro)."""
    cameras: List[Dict[str, Any]] = []

    if LIVE_CAMERAS_PATH.exists():
        try:
            with open(LIVE_CAMERAS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cameras = [c for c in raw if c.get("status") == "LIVE"]
            log.info(
                f"Carregadas {len(cameras)} câmeras LIVE de {LIVE_CAMERAS_PATH.name} "
                f"(de {len(raw)} totais)."
            )
        except Exception as e:
            log.error(f"Falha ao ler {LIVE_CAMERAS_PATH}: {e}")
            cameras = []

    if not cameras and OMNI_CAMS_PATH.exists():
        try:
            with open(OMNI_CAMS_PATH, "r", encoding="utf-8") as f:
                cameras = json.load(f)
            log.info(
                f"Fallback: carregadas {len(cameras)} câmeras de {OMNI_CAMS_PATH.name} (sem filtro)."
            )
        except Exception as e:
            log.error(f"Falha ao ler {OMNI_CAMS_PATH}: {e}")
            cameras = []

    return cameras


def reload_cameras() -> None:
    global _cameras, _cameras_by_id
    cameras = load_cameras()
    _cameras = cameras
    _cameras_by_id = {str(c.get("id")): c for c in cameras}


# --------------------------------------------------------------------------
# Placeholder JPEG (câmera offline / falha de captura)
# --------------------------------------------------------------------------

def _generate_placeholder_jpeg(text: str = "OFFLINE", width: int = 640, height: int = 360) -> bytes:
    frame = np.full((height, width, 3), 40, dtype=np.uint8)  # cinza escuro
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.2
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)
    x = max((width - text_w) // 2, 0)
    y = max((height + text_h) // 2, 0)
    cv2.putText(frame, text, (x, y), font, font_scale, (180, 180, 180), thickness, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        # último recurso: jpeg mínimo válido gerado a partir de array preto
        ok, buf = cv2.imencode(".jpg", np.zeros((height, width, 3), dtype=np.uint8))
    return buf.tobytes()


_PLACEHOLDER_JPEG = _generate_placeholder_jpeg()


# --------------------------------------------------------------------------
# Resolução de URL de stream (com cache TTL + lock por câmera)
# --------------------------------------------------------------------------

def _resolve_stream_url_sync(camera_id: str, source_url: str) -> Optional[str]:
    """Função bloqueante: verifica cache, senão chama yt-dlp via get_live_url."""
    now = time.time()
    lock = _get_camera_lock(camera_id)
    with lock:
        cached = _stream_url_cache.get(camera_id)
        if cached is not None and (now - cached["ts"]) < STREAM_URL_TTL:
            return cached["url"]

        resolved: Optional[str] = None
        try:
            resolved = get_live_url(source_url)
        except Exception as e:
            log.error(f"Erro ao resolver stream para câmera {camera_id}: {e}")
            resolved = None

        _stream_url_cache[camera_id] = {"url": resolved, "ts": now}
        return resolved


async def resolve_stream_url(camera_id: str, source_url: str) -> Optional[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _resolve_stream_url_sync, camera_id, source_url)


# --------------------------------------------------------------------------
# Captura de frame (com cache TTL de 5s + lock por câmera)
# --------------------------------------------------------------------------

def _capture_thumbnail_sync(camera_id: str, source_url: str) -> bytes:
    """Função bloqueante: retorna JPEG bytes (cache, captura real, ou placeholder)."""
    now = time.time()
    lock = _get_camera_lock(camera_id)
    with lock:
        cached = _thumbnail_cache.get(camera_id)
        if cached is not None and (now - cached["ts"]) < THUMBNAIL_TTL:
            return cached["bytes"]

        stream_url = _resolve_stream_url_sync(camera_id, source_url)
        jpeg_bytes: bytes = _PLACEHOLDER_JPEG

        if stream_url:
            cap = None
            try:
                cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        ok, buf = cv2.imencode(".jpg", frame)
                        if ok:
                            jpeg_bytes = buf.tobytes()
            except Exception as e:
                log.error(f"Erro ao capturar frame da câmera {camera_id}: {e}")
            finally:
                if cap is not None:
                    cap.release()

        _thumbnail_cache[camera_id] = {"bytes": jpeg_bytes, "ts": now}
        return jpeg_bytes


async def capture_thumbnail(camera_id: str, source_url: str) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _capture_thumbnail_sync, camera_id, source_url)


# --------------------------------------------------------------------------
# Worker de detecção de perigo (thread única, round-robin por câmera)
#
# NÃO instanciamos um BehaviorPipeline por câmera (o __init__ dele carrega
# os modelos YOLO do disco — caro demais para repetir 33+ vezes). Em vez
# disso carregamos UMA única instância compartilhada (pose_model +
# weapon_model carregados uma vez) e, a cada iteração do round-robin,
# trocamos apenas camera_id/fall_counter/weapon_counter antes de chamar
# _analyze_pose/_analyze_weapons. Isso é seguro porque só uma câmera é
# analisada por vez, nesta única thread (sem concorrência entre câmeras),
# então não há necessidade de lock para os contadores em si — apenas
# guardamos o estado de cada câmera (contadores) num dict local à thread
# entre uma passada e outra do round-robin.
# --------------------------------------------------------------------------

_shared_behavior_pipeline = None  # instanciado dentro do próprio worker thread


def _danger_detection_worker() -> None:
    global _shared_behavior_pipeline

    try:
        from behavior_pipeline import BehaviorPipeline
    except Exception as e:
        log.error(f"Não foi possível importar BehaviorPipeline: {e}")
        return

    try:
        # camera_id/source_type aqui são placeholders — nunca chamamos
        # .run() nessa instância, só reaproveitamos os modelos carregados
        # e os métodos _analyze_pose/_analyze_weapons.
        _shared_behavior_pipeline = BehaviorPipeline(camera_id="__shared__", source_type="youtube")
    except Exception:
        log.exception("Falha ao carregar modelos de detecção de perigo — worker não iniciado.")
        return

    log.info("Worker de detecção de perigo (scene-level: armas/queda) iniciado.")

    # Estado (contadores de persistência) por câmera — vive só nesta thread.
    per_camera_state: Dict[str, Dict[str, int]] = {}

    while True:
        cams_snapshot = list(_cameras)
        if not cams_snapshot:
            time.sleep(5.0)
            continue

        for cam in cams_snapshot:
            cam_id = "unknown"
            try:
                cam_id = str(cam.get("id"))
                source_url = cam.get("url", "")

                # Reaproveita o cache de thumbnail (TTL de alguns segundos) em
                # vez de forçar uma nova captura — se já houve captura recente
                # para essa câmera, usamos os mesmos bytes.
                jpeg_bytes = _capture_thumbnail_sync(cam_id, source_url)
                if not jpeg_bytes or jpeg_bytes is _PLACEHOLDER_JPEG:
                    time.sleep(DANGER_ROUND_ROBIN_DELAY)
                    continue

                arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is None:
                    time.sleep(DANGER_ROUND_ROBIN_DELAY)
                    continue

                state = per_camera_state.setdefault(cam_id, {"fall": 0, "weapon": 0})

                # Troca o "contexto" da instância compartilhada para esta câmera.
                _shared_behavior_pipeline.camera_id = cam_id
                _shared_behavior_pipeline.fall_counter = state["fall"]
                _shared_behavior_pipeline.weapon_counter = state["weapon"]

                fell = False
                weaponed = False
                try:
                    fell = bool(_shared_behavior_pipeline._analyze_pose(frame))
                except Exception:
                    log.exception(f"Erro na análise de queda (câmera {cam_id})")
                try:
                    weaponed = bool(_shared_behavior_pipeline._analyze_weapons(frame))
                except Exception:
                    log.exception(f"Erro na análise de armas (câmera {cam_id})")

                # Persiste os contadores atualizados de volta no estado da câmera.
                state["fall"] = _shared_behavior_pipeline.fall_counter
                state["weapon"] = _shared_behavior_pipeline.weapon_counter

                if weaponed:
                    _set_alert(
                        cam_id, "WEAPON", 10,
                        "Possível ameaça armada (arma/objeto perigoso) detectada em cena.",
                    )
                elif fell:
                    level = 10 if state["fall"] > 15 else 6
                    _set_alert(
                        cam_id, "FALL", level,
                        "Possível pessoa caída detectada em cena.",
                    )
            except Exception:
                log.exception(f"Erro no worker de detecção de perigo (câmera {cam_id})")

            time.sleep(DANGER_ROUND_ROBIN_DELAY)


def start_danger_detection_worker() -> None:
    thread = threading.Thread(target=_danger_detection_worker, daemon=True)
    thread.start()


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    reload_cameras()
    start_danger_detection_worker()


@app.get("/api/health")
async def health():
    return {"status": "ONLINE", "cameras_loaded": len(_cameras)}


@app.get("/api/cameras")
async def list_cameras():
    result = []
    for cam in _cameras:
        cam_id = str(cam.get("id"))
        result.append(
            {
                "id": cam_id,
                "nome": cam.get("nome", ""),
                "local": cam.get("local", ""),
                "setor": cam.get("setor", ""),
                "thumbnail_url": f"/api/cameras/{cam_id}/thumbnail.jpg",
                "url": cam.get("url", ""),
            }
        )
    return result


@app.get("/api/cameras/{camera_id}/thumbnail.jpg")
async def camera_thumbnail(camera_id: str):
    cam = _cameras_by_id.get(camera_id)
    if cam is None:
        return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

    source_url = cam.get("url", "")
    jpeg_bytes = await capture_thumbnail(camera_id, source_url)
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@app.get("/api/alerts")
async def get_alerts():
    """Alertas de perigo ATIVOS (scene-level: arma/queda), últimos 30s.

    Só lê um dict em memória protegido por um lock pequeno e dedicado —
    nunca bloqueia em I/O de câmera ou inferência de modelo, então esta
    rota nunca trava/hangs.
    """
    return _get_active_alerts()


@app.get("/api/cameras/{camera_id}/live_url")
async def camera_live_url(camera_id: str):
    cam = _cameras_by_id.get(camera_id)
    if cam is None:
        return {"url": None}

    source_url = cam.get("url", "")
    resolved = await resolve_stream_url(camera_id, source_url)
    return {"url": resolved}


if __name__ == "__main__":
    reload_cameras()
    start_danger_detection_worker()
    uvicorn.run(app, host="0.0.0.0", port=8001)
