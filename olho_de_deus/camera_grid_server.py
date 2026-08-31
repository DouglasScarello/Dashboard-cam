import db_manager
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
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from youtube_stream import get_live_url
from forensic_sr_engine import forensic_sr_router

log = logging.getLogger("camera_grid_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [CAM-GRID] %(message)s")

ROOT = Path(__file__).resolve().parent.parent
LIVE_CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
OMNI_CAMS_PATH = ROOT / "database" / "omni_cams.json"
LIVENESS_STATE_PATH = ROOT / "database" / "camera_liveness_state.json"

# Um "LIVE" checado há mais tempo que isso é tratado como desconhecido, não
# como vivo — evita confiar indefinidamente numa checagem antiga enquanto o
# intervalo real de rotatividade das lives (ver camera_liveness.py) ainda
# não foi medido empiricamente. 30 min é um valor conservador de partida.
LIVENESS_STALE_AFTER_SECONDS = 30 * 60

STREAM_URL_TTL = 240.0  # 4 minutos
# Captura real via ffmpeg leva alguns segundos (resolve stream + decodifica
# 1 frame) — 5s como antes faria recapturar quase a cada request. 30s é um
# equilíbrio razoável entre "atual" e não sobrecarregar o yt-dlp/ffmpeg.
THUMBNAIL_TTL = 30.0

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

_liveness_state: Dict[str, Any] = {}
_liveness_mtime: float = 0.0


def _reload_liveness_state_if_changed() -> None:
    """Recarrega database/camera_liveness_state.json só se o arquivo mudou
    desde a última leitura — permite rodar `camera_liveness.py` por fora
    (manual ou cron) e o servidor pega o resultado sem precisar reiniciar."""
    global _liveness_state, _liveness_mtime
    try:
        mtime = LIVENESS_STATE_PATH.stat().st_mtime
    except FileNotFoundError:
        return
    if mtime == _liveness_mtime:
        return
    try:
        with open(LIVENESS_STATE_PATH, "r", encoding="utf-8") as f:
            _liveness_state = json.load(f)
        _liveness_mtime = mtime
        log.info(f"Estado de liveness recarregado ({len(_liveness_state)} câmeras checadas).")
    except Exception as e:
        log.error(f"Falha ao ler {LIVENESS_STATE_PATH.name}: {e}")


def get_camera_liveness(cam_id: str, cam: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Retorna {live_confirmed, confirmed_dead, live_status, checked_at}.

    Duas perguntas diferentes, de propósito:
    - `live_confirmed`: temos evidência POSITIVA recente de que está ao vivo.
    - `confirmed_dead`: temos evidência NEGATIVA recente (checagem real
      disse que não está ao vivo). É este campo que o frontend usa pra
      bloquear a abertura — nunca abrir o que sabemos que está morto.

    Override manual: setar `"manual_dead_override": true` direto no objeto
    da câmera em live_cameras.json mata ela na hora, sem esperar o próximo
    scan do camera_liveness.py. Só isso tem efeito de verdade — escrever
    `"confirmed_dead": true` direto no JSON NÃO funciona, porque esse campo
    da resposta da API é sempre recalculado aqui, nunca lido do disco (bug
    já confundiu alguém: editou o JSON, reiniciou o servidor, achou que
    tinha resolvido, mas por coincidência a câmera já estava morta pelo
    scan de qualquer forma).

    Sem checagem nenhuma ainda (cold start, ou checagem velha demais) os
    dois ficam False — não travamos a UI inteira só porque a varredura
    ainda não rodou; só bloqueamos quando há prova real de que morreu."""
    if cam and cam.get("manual_dead_override"):
        return {"live_confirmed": False, "confirmed_dead": True, "live_status": "MANUAL_OVERRIDE", "checked_at": None}

    entry = _liveness_state.get(cam_id)
    if not entry:
        return {"live_confirmed": False, "confirmed_dead": False, "live_status": "UNKNOWN", "checked_at": None}

    checked_at = entry.get("checked_at")
    is_stale = True
    if checked_at:
        try:
            checked_dt = datetime.fromisoformat(checked_at)
            age = (datetime.now(timezone.utc) - checked_dt).total_seconds()
            is_stale = age > LIVENESS_STALE_AFTER_SECONDS
        except Exception:
            is_stale = True

    if is_stale:
        return {"live_confirmed": False, "confirmed_dead": False, "live_status": "UNKNOWN", "checked_at": checked_at}

    status = entry.get("status", "UNKNOWN")
    return {
        "live_confirmed": status == "LIVE",
        "confirmed_dead": status in ("DEAD", "ENDED_BUT_EXISTS"),
        "live_status": status,
        "checked_at": checked_at,
    }

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

def _is_direct_stream_url(url: str) -> bool:
    """True pra URL já tocável direto (HLS .m3u8 de servidor real tipo
    Wowza/streamlock/DOT) — não precisa (e não pode) passar pelo resolvedor
    orientado a YouTube."""
    return bool(url) and "youtube.com" not in url and "youtu.be" not in url


def _capture_real_frame_jpeg(camera_id: str, source_url: str, timeout_s: float = 15.0) -> Optional[bytes]:
    """Frame REAL da transmissão ao vivo agora — não a thumbnail estática do
    YouTube (que pode ser de qualquer momento passado, ou nem existir pra
    uma live).

    Achados reais (2026-08-30): (1) câmeras HLS diretas (Wowza/streamlock/
    DOT — hoje 100% do catálogo, já que as câmeras do YouTube foram todas
    removidas) sempre falhavam aqui porque a URL passava pelo resolvedor
    `_resolve_stream_url_sync`/`get_live_url`, que só sabe extrair vídeo do
    YouTube — pra uma URL Wowza isso sempre retornava None. (2) mesmo
    quando o ffmpeg tinha sucesso, o retorno estava quebrado
    (`{"cameras": ...}.stdout` — dict não tem esse atributo, um resto de
    copy-paste de outro trecho de código), então a captura NUNCA
    funcionava, nem pra câmera nenhuma."""
    if _is_direct_stream_url(source_url):
        stream_url = source_url
    else:
        stream_url = _resolve_stream_url_sync(camera_id, source_url)
    if not stream_url:
        return None
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", stream_url, "-frames:v", "1", "-q:v", "3", "-f", "image2", "pipe:1"],
            capture_output=True, timeout=timeout_s,
        )
        if result.returncode == 0 and len(result.stdout) > 2000:
            return result.stdout
        if result.returncode != 0:
            log.warning(f"ffmpeg falhou pra câmera {camera_id}: {result.stderr[-300:].decode('utf-8', errors='ignore')}")
    except Exception as e:
        log.warning(f"Falha ao capturar frame real da câmera {camera_id}: {e}")
    return None


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
    # A função original lia do disco, agora vamos apenas re-alimentar o spatial_index se necessário, 
    # mas o grid server não precisa mais armazenar em memória!
    pass

def reload_cameras() -> None:
    # Não faz mais nada porque agora lemos direto do SQLite
    pass


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
    """Retorna JPEG bytes de um frame REAL e atual da transmissão — não a
    thumbnail estática do YouTube (que pode ser de qualquer momento, ou
    inexistente pra uma live). Achado de auditoria: tanto esta função
    quanto o endpoint `/snapshot` só buscavam a imagem estática do YouTube
    antes desta correção — o usuário reportou "quero um print real de
    agora, não thumbnail do YouTube"."""
    now = time.time()
    lock = _get_camera_lock(camera_id)
    with lock:
        cached = _thumbnail_cache.get(camera_id)
        if cached is not None and (now - cached["ts"]) < THUMBNAIL_TTL:
            return cached["bytes"]

        cam = db_manager.get_camera_by_id(camera_id) or {}
        video_id = cam.get("video_id")

        # 1. Frame real via ffmpeg do stream ao vivo (pode levar alguns
        # segundos — por isso o cache com TTL mais longo agora).
        jpeg_bytes = _capture_real_frame_jpeg(camera_id, source_url)

        # 2. Fallback: thumbnail estática do YouTube (câmera pode estar
        # offline — melhor mostrar algo do que travar a UI).
        if not jpeg_bytes and video_id:
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
        cams_snapshot = db_manager.get_cameras(limit=10000, status='ONLINE', geo='WITH_GEO')['cameras'] # Apenas um subset para demo, ideal seria iterar banco
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
    return {"status": "ONLINE", "cameras_loaded": "DB"}


@app.get("/api/cameras")
async def list_cameras(
    limit: Optional[int] = 2000,
    offset: int = 0,
    search: Optional[str] = None,
    country: Optional[str] = None,
    area: Optional[str] = None,
    status: Optional[str] = "ALL",
    geo: Optional[str] = "ALL",
    source: Optional[str] = None
):
    _reload_liveness_state_if_changed()

    # Achado real (2026-08-31): filtrar ONLINE/OFFLINE direto no SQL usava
    # a coluna `confirmed_dead` do banco, que é só um resíduo do JSON de
    # origem e não reflete `get_camera_liveness()` (a fonte de verdade
    # real, calculada a partir de camera_liveness_state.json +
    # manual_dead_override). Isso podia esconder do usuário câmeras
    # genuinamente vivas cujo campo antigo no JSON estava desatualizado.
    # Agora: filtros de metadado (país/área/geo/busca) continuam no SQL
    # (são atributos estáticos, seguros de filtrar ali), mas
    # ONLINE/OFFLINE e a paginação final acontecem em Python, depois de
    # calcular a liveness de verdade pra cada câmera candidata.
    candidates = db_manager.get_cameras_by_filters(country=country, area=area, geo=geo, search=search, source=source)

    enriched = []
    for cam in candidates:
        cam_id = str(cam.get("id"))
        source_url = cam.get("url", "")
        vid_id = cam.get("video_id")
        if not vid_id and source_url and cam.get("stream_format") != "SNAPSHOT_JPEG" and "youtube.com" in source_url and "v=" in source_url:
            vid_id = source_url.split("v=")[1].split("&")[0]

        liveness = get_camera_liveness(cam_id, cam)

        if status == "ONLINE" and liveness["confirmed_dead"]:
            continue
        if status == "OFFLINE" and not liveness["confirmed_dead"]:
            continue

        enriched.append(
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
                # SNAPSHOT_JPEG (Ontario 511, NZTA, ...) = imagem única que
                # atualiza a cada request, não stream HLS contínuo — o
                # frontend precisa saber disso pra não tentar abrir a URL
                # como manifesto .m3u8 no player de vídeo.
                "stream_format": cam.get("stream_format"),
                "live_confirmed": liveness["live_confirmed"],
                "confirmed_dead": liveness["confirmed_dead"],
                "live_status": liveness["live_status"],
                "live_checked_at": liveness["checked_at"],
            }
        )

    total = len(enriched)
    if limit is not None:
        result = enriched[offset:offset + limit]
    else:
        result = enriched[offset:]
    return {"cameras": result, "total": total}

@app.get("/api/cameras/map")
async def list_cameras_map(north: float, south: float, east: float, west: float, limit: int = 1000):
    _reload_liveness_state_if_changed()
    cams = db_manager.get_cameras_in_bbox(north, south, east, west, limit)
    result = []
    for cam in cams:
        cam_id = str(cam.get("id"))
        # Achado real (2026-08-31): esse endpoint tinha 2 bugs — (1)
        # `db_result["total"]` referenciava uma variável que não existe
        # nesta função (NameError em toda chamada), e (2) `confirmed_dead`
        # vinha direto da coluna crua do banco em vez de
        # `get_camera_liveness()`, então o mapa não recebia override
        # manual nem respeitava a janela de "checagem velha demais".
        liveness = get_camera_liveness(cam_id, cam)
        result.append({
            "id": cam_id,
            "nome": cam.get("nome", ""),
            "lat": cam.get("lat"),
            "long": cam.get("long"),
            "tipo_area": cam.get("tipo_area", ""),
            "thumbnail_url": f"/api/cameras/{cam_id}/thumbnail.jpg",
            "video_id": cam.get("video_id"),
            "url": cam.get("url"),
            "stream_format": cam.get("stream_format"),
            "confirmed_dead": liveness["confirmed_dead"],
            "live_confirmed": liveness["live_confirmed"],
        })
    return {"cameras": result, "total": len(result)}


@app.get("/api/cameras/{camera_id}")
async def get_camera_detail(camera_id: str):
    """Busca UMA câmera por id, com liveness computada — usado pelo
    deep-link de alertas: como a listagem principal agora pagina do lado
    do servidor (`displayLimit`), a câmera de um alerta quase nunca está
    no lote já carregado no frontend. Sem isso, o deep-link simplesmente
    não achava a câmera (achado real 2026-08-31)."""
    _reload_liveness_state_if_changed()
    cam = db_manager.get_camera_by_id(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Câmera não encontrada")

    source_url = cam.get("url", "")
    vid_id = cam.get("video_id")
    if not vid_id and source_url and cam.get("stream_format") != "SNAPSHOT_JPEG" and "youtube.com" in source_url and "v=" in source_url:
        vid_id = source_url.split("v=")[1].split("&")[0]

    liveness = get_camera_liveness(camera_id, cam)
    return {
        "id": camera_id,
        "nome": cam.get("nome", ""),
        "local": cam.get("local", ""),
        "endereco": cam.get("endereco", ""),
        "cidade": cam.get("cidade", ""),
        "uf": cam.get("uf", ""),
        "tipo_area": cam.get("tipo_area", "PONTO DE MONITORAMENTO"),
        "setor": cam.get("setor", ""),
        "pais": cam.get("pais", ""),
        "thumbnail_url": f"/api/cameras/{camera_id}/thumbnail.jpg",
        "url": source_url,
        "video_id": vid_id,
        "lat": cam.get("lat"),
        "long": cam.get("long"),
        "stream_format": cam.get("stream_format"),
        "live_confirmed": liveness["live_confirmed"],
        "confirmed_dead": liveness["confirmed_dead"],
        "live_status": liveness["live_status"],
        "live_checked_at": liveness["checked_at"],
    }


@app.get("/api/cameras/{camera_id}/thumbnail.jpg")
async def camera_thumbnail(camera_id: str):
    cam = db_manager.get_camera_by_id(camera_id)
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
    cam = db_manager.get_camera_by_id(camera_id)
    if cam is None:
        return {"url": None, "video_id": None}

    source_url = cam.get("url", "")
    resolved = await resolve_stream_url(camera_id, source_url)
    
    video_id = cam.get("video_id")
    if not video_id and cam.get("stream_format") != "SNAPSHOT_JPEG" and "youtube.com" in source_url and "v=" in source_url:
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
    Captura um frame REAL e atual da transmissão pra uso forense (crop de
    placa/rosto). Antes só buscava a thumbnail estática do YouTube — o
    usuário reportou que isso não reflete o que a câmera está gravando
    agora, e pra perícia isso importa de verdade, não é cosmético.
    """
    cam = db_manager.get_camera_by_id(camera_id)
    if not cam:
        if not camera_id.startswith("cam_"):
            cam = db_manager.get_camera_by_id(f"cam_{camera_id}")
        else:
            raw_id = camera_id.replace("cam_", "")
            cam = db_manager.get_camera_by_id(raw_id)

    if not cam:
        return Response(content=_PLACEHOLDER_JPEG, media_type="image/jpeg")

    real_id = str(cam.get("id", camera_id))
    source_url = cam.get("url", "")
    jpeg_bytes = await capture_thumbnail(real_id, source_url)

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "X-Camera-ID": real_id,
            "X-Capture-Timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )



@app.get("/api/cameras/{camera_id}/comprovante")
async def camera_comprovante(camera_id: str):
    import hashlib
    from datetime import datetime

    cam = db_manager.get_camera_by_id(camera_id)
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


@app.get("/api/metadata/countries")
async def get_countries():
    return db_manager.get_unique_countries()

@app.get("/api/metadata/areas")
async def get_areas():
    return db_manager.get_unique_areas()

@app.get("/api/metadata/sources")
async def get_sources():
    """Fontes de ingestão (Ontario511, NZTA, Vegagerdin, OpenTrafficCamMap,
    etc) com contagem — câmeras da curadoria original anterior a esse
    campo existir aparecem com source=null, não entram na lista."""
    return db_manager.get_sources_with_counts()

if __name__ == "__main__":
    reload_cameras()
    uvicorn.run(app, host="0.0.0.0", port=8001)

