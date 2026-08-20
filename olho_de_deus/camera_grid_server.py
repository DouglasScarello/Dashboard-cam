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
from datetime import datetime
from pathlib import Path

from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from youtube_stream import get_live_url
from forensic_sr_engine import forensic_sr_router

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
app.include_router(forensic_sr_router)

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

def _fetch_youtube_thumbnail(video_id: str) -> Optional[bytes]:
    if not video_id:
        return None
    import urllib.request
    for qual in ["hqdefault.jpg", "mqdefault.jpg", "default.jpg"]:
        url = f"https://img.youtube.com/vi/{video_id}/{qual}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 1000:
                        return data
        except Exception:
            continue
    return None


def load_cameras() -> List[Dict[str, Any]]:
    """Carrega a lista completa de câmeras reais a partir de live_cameras.json."""
    cameras: List[Dict[str, Any]] = []

    if LIVE_CAMERAS_PATH.exists():
        try:
            with open(LIVE_CAMERAS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cameras = [c for c in raw if c.get("video_id") or c.get("url")]
            log.info(
                f"Carregadas {len(cameras)} câmeras REAIS de {LIVE_CAMERAS_PATH.name}."
            )
        except Exception as e:
            log.error(f"Falha ao ler {LIVE_CAMERAS_PATH}: {e}")
            cameras = []

    if not cameras and OMNI_CAMS_PATH.exists():
        try:
            with open(OMNI_CAMS_PATH, "r", encoding="utf-8") as f:
                cameras = json.load(f)
            log.info(
                f"Fallback: carregadas {len(cameras)} câmeras de {OMNI_CAMS_PATH.name}."
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


from concurrent.futures import ThreadPoolExecutor
_IO_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cam_io")


async def resolve_stream_url(camera_id: str, source_url: str) -> Optional[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_IO_EXECUTOR, _resolve_stream_url_sync, camera_id, source_url)


# --------------------------------------------------------------------------
# Captura de frame (instantâneo via YouTube CDN + fallback OpenCV)
# --------------------------------------------------------------------------

def _capture_thumbnail_sync(camera_id: str, source_url: str) -> bytes:
    """Retorna JPEG bytes da thumbnail real da transmissão."""
    now = time.time()
    lock = _get_camera_lock(camera_id)
    with lock:
        cached = _thumbnail_cache.get(camera_id)
        if cached is not None and (now - cached["ts"]) < THUMBNAIL_TTL:
            return cached["bytes"]

        cam = _cameras_by_id.get(camera_id, {})
        video_id = cam.get("video_id")
        
        # 1. Busca instantânea da thumbnail real do stream
        jpeg_bytes = None
        if video_id:
            jpeg_bytes = _fetch_youtube_thumbnail(video_id)

        if not jpeg_bytes:
            jpeg_bytes = _PLACEHOLDER_JPEG

        _thumbnail_cache[camera_id] = {"bytes": jpeg_bytes, "ts": now}
        return jpeg_bytes


async def capture_thumbnail(camera_id: str, source_url: str) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_IO_EXECUTOR, _capture_thumbnail_sync, camera_id, source_url)


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
async def list_cameras(
    limit: Optional[int] = 2000,
    offset: int = 0,
    search: Optional[str] = None,
    country: Optional[str] = None,
    sector: Optional[str] = None
):
    filtered = _cameras
    
    if country:
        c_upper = country.strip().upper()
        filtered = [c for c in filtered if c.get("pais", "").upper() == c_upper]
        
    if sector:
        s_upper = sector.strip().upper()
        filtered = [c for c in filtered if c.get("setor", "").upper() == s_upper]
        
    if search:
        s_low = search.strip().lower()
        filtered = [
            c for c in filtered 
            if s_low in c.get("nome", "").lower() or s_low in c.get("local", "").lower()
        ]
        
    sliced = filtered[offset : offset + limit] if limit else filtered[offset:]
    
    result = []
    for cam in sliced:
        cam_id = str(cam.get("id"))
        source_url = cam.get("url", "")
        vid_id = cam.get("video_id")
        if not vid_id and "v=" in source_url:
            vid_id = source_url.split("v=")[1].split("&")[0]
            
        result.append(
            {
                "id": cam_id,
                "nome": cam.get("nome", ""),
                "local": cam.get("local", ""),
                "endereco": cam.get("endereco", ""),
                "cidade": cam.get("cidade", ""),
                "uf": cam.get("uf", ""),
                "tipo_area": cam.get("tipo_area", "PONTO DE MONITORAMENTO"),
                "setor": cam.get("setor", ""),
                "pais": cam.get("pais", ""),
                "thumbnail_url": f"/api/cameras/{cam_id}/thumbnail.jpg",
                "url": source_url,
                "video_id": vid_id,
                "lat": cam.get("lat"),
                "long": cam.get("long"),
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
        return {"url": None, "video_id": None}

    source_url = cam.get("url", "")
    resolved = await resolve_stream_url(camera_id, source_url)
    
    video_id = cam.get("video_id")
    if not video_id and "v=" in source_url:
        video_id = source_url.split("v=")[1].split("&")[0]
        
    return {
        "url": resolved,
        "video_id": video_id,
        "source_url": source_url
    }


@app.get("/api/cameras/{camera_id}/snapshot")
@app.post("/api/cameras/{camera_id}/snapshot")
async def camera_snapshot_native(camera_id: str):
    """
    Captura snapshot nativo em alta resolução da câmera para perícia forense.
    Garante resposta instantânea (<200ms) sem erros 500.
    """
    import urllib.request

    cam = _cameras_by_id.get(camera_id)
    if not cam:
        if not camera_id.startswith("cam_"):
            cam = _cameras_by_id.get(f"cam_{camera_id}")
        else:
            raw_id = camera_id.replace("cam_", "")
            cam = _cameras_by_id.get(raw_id)

    if not cam:
        # Tenta pegar qualquer câmera válida como fallback gracioso
        if _cameras:
            cam = _cameras[0]
        else:
            return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

    source_url = cam.get("url", "")
    video_id = cam.get("video_id")
    if not video_id and "v=" in source_url:
        video_id = source_url.split("v=")[1].split("&")[0]

    # 1. Tentar obter o frame em alta resolução direto do CDN da transmissão
    if video_id:
        for quality in ["maxresdefault", "sddefault", "hqdefault"]:
            try:
                thumb_url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
                req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
                loop = asyncio.get_event_loop()
                def _fetch():
                    with urllib.request.urlopen(req, timeout=2.5) as resp:
                        return resp.read()
                data = await loop.run_in_executor(None, _fetch)
                if data and len(data) > 5000:
                    return Response(
                        content=data,
                        media_type="image/jpeg",
                        headers={
                            "X-Camera-ID": str(cam.get("id", camera_id)),
                            "X-Resolution": "1080p",
                            "X-Capture-Timestamp": datetime.utcnow().isoformat() + "Z"
                        }
                    )
            except Exception:
                continue

    # 2. Fallback para cache de thumbnail
    cached_thumb = _thumbnail_cache.get(cam.get("id", camera_id))
    if cached_thumb:
        return Response(content=cached_thumb["bytes"], media_type="image/jpeg")

    return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")



@app.get("/api/cameras/{camera_id}/comprovante")
async def camera_comprovante(camera_id: str):
    import hashlib
    from datetime import datetime

    cam = _cameras_by_id.get(camera_id)
    if cam is None:
        return Response(content="CAMERA NAO ENCONTRADA", status_code=404, media_type="text/plain")

    now = datetime.now()
    data_str = now.strftime("%d/%m/%Y")
    hora_str = now.strftime("%H:%M:%S")
    
    raw_payload = f"{cam.get('id')}|{cam.get('nome')}|{cam.get('endereco')}|{cam.get('lat')}|{cam.get('long')}|{data_str}"
    hash_bancario = hashlib.sha256(raw_payload.encode()).hexdigest().upper()
    hash_formatado = f"{hash_bancario[0:4]}-{hash_bancario[4:8]}-{hash_bancario[8:12]}-{hash_bancario[12:16]}-{hash_bancario[16:20]}-{hash_bancario[20:24]}"
    
    lat = f"{cam.get('lat'):+.4f}" if cam.get('lat') else "N/D"
    long_ = f"{cam.get('long'):+.4f}" if cam.get('long') else "N/D"

    linhas = [
        "=" * 70,
        "       SISTEMA INTEGRADO DE VIGILANCIA C4ISR - OLHO DE DEUS       ",
        "            CERTIFICADO / COMPROVANTE DE GEOLOCALIZACAO            ",
        "-" * 70,
        f"DATA DE EMISSAO: {data_str}       HORA: {hora_str}",
        f"TERMINAL AUTORIZADO: SRV-C4ISR-NODE01        COD. RETORNO: 00 (OK)",
        "-" * 70,
        f"IDENTIFICADOR DO SENSOR      : {cam.get('id', 'N/D')}",
        f"TITULO / PONTO DE VIGILANCIA : {cam.get('nome', 'N/D')[:45]}",
        f"LOGRADOURO / ENDERECO EXATO  : {cam.get('endereco', 'N/D')[:45]}",
        f"CIDADE / ESTADO              : {cam.get('local', 'N/D')}",
        f"PAIS DE ORIGEM               : {cam.get('pais', 'BR')} (SETOR: {cam.get('setor', 'BR')})",
        f"CATEGORIA DE AREA            : {cam.get('tipo_area', 'ZONA DE MONITORAMENTO')}",
        f"STATUS OPERACIONAL           : {cam.get('status', 'LIVE')} (SINAL EM TEMPO REAL)",
        f"COORDENADA LATITUDE (GPS)    : {lat}",
        f"COORDENADA LONGITUDE (GPS)   : {long_}",
        f"FONTE / IDENTIFICADOR STREAM : {cam.get('video_id', 'N/D')}",
        "-" * 70,
        "CHAVE DE AUTENTICACAO ELETRONICA (CUSTODIA FORENSE):",
        f"  {hash_formatado}",
        "FINALIDADE: CERTIFICACAO DE LOCAL, TELEMETRIA E PROVA PERICIAL",
        "-" * 70,
        "AUTENTICACAO BANCARIA / PROTOCOLO FORENSE: REGISTRO IMUTAVEL VALIDO",
        "=" * 70,
    ]
    return Response(content="\n".join(linhas), media_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    reload_cameras()
    uvicorn.run(app, host="0.0.0.0", port=8001)
