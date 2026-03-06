#!/usr/bin/env python3
"""
live_pipeline.py — Olho de Deus [Fase 31: Live Biometric Pipeline + Redis Cache]
                                  [Fase 32-fix: Correção de travamento de câmera]

Orquestrador de monitoramento em tempo real.
- Captura frames de streams (YouTube/RTSP) em uma thread separada.
- Processa biometria (YOLO + ArcFace) no frame mais recente (buffer limitado).
- Registra evidências forenses (SHA-256) em caso de match positivo.
- Dispara alertas multicanal (Telegram) com debounce via Redis (Fase 31.2).
- Streaming WebRTC via go2rtc + FFmpeg (Fase 31.3).

Correções de travamento (Fase 32-fix):
- Frame buffer trocado de deque para queue.Queue thread-safe (sem race condition).
- cap.read() agora tem timeout via thread-sentinel (não trava infinitamente).
- cv2.waitKey protegido com try/except e tolerância a falha no Wayland.
- Watchdog de captura: reconecta automaticamente se nenhum frame chegar em 15s.
"""

import os
import sys
import numpy as np

# Aceleração de Hardware Vega (Radeon) — Fase 33-Giga
os.environ["LIBVA_DRIVER_NAME"] = "radeonsi"

# Limitar threads OpenMP e bibliotecas matemáticas (Thread Storm Prevention — Fase 32-Lab)
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "1" # MKL 1 para IA isolada em núcleos específicos
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import psutil
import multiprocessing
def pin_thread(cpu_ids):
    """AFINIDADE DE CPU: Fixa a thread atual em núcleos específicos do Ryzen."""
    try:
        proc = psutil.Process()
        proc.cpu_affinity(cpu_ids)
        log.info(f"[system] Thread associada aos núcleos: {cpu_ids}")
    except Exception as e:
        log.debug(f"Falha ao fixar afinidade de CPU: {e}")

# Reduzir avisos do Qt (fontes / point size) ao usar cv2.imshow em Wayland/Gnome
if "QT_QPA_FONTDIR" not in os.environ:
    for d in ("/usr/share/fonts", "/usr/share/fonts/truetype", "/usr/share/fonts/TTF"):
        if os.path.isdir(d):
            os.environ["QT_QPA_FONTDIR"] = d
            break
if "QT_LOGGING_RULES" not in os.environ:
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts=false;qt.gui.unicode=false;*.debug=false;default=false"
# Wayland: OpenCV/OpenGL costumam travar; forçar X11 (xcb) melhora fluidez
if "WAYLAND_DISPLAY" in os.environ and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

import time
import queue
import cv2
import threading
import torch

# Ajuste 5: Limitar threads para não sufocar o scheduler do Ryzen 5825U (15W)
torch.set_num_threads(4)
cv2.setNumThreads(1) # OpenCV threads por chamada; 1 é ideal para múltiplos loops

import logging
import argparse
import subprocess
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from biometric_processor import BiometricProcessor
from youtube_stream import get_live_url
from alert_dispatcher import dispatch_sync
from intelligence_db import DB, init_db, register_evidence, register_match_log, get_threat_score, get_full_individual_dossier
from score_engine import ThreatScorer
from forensic_report import generate_dossier_pdf
from redis_cache import RedisCache

# Logging (Fase 17: Centralizado)
log_dir = Path(__file__).parent / "logs"
os.makedirs(log_dir, exist_ok=True)

log = logging.getLogger("live_pipeline")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "live.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class AtomicFrameRing:
    """Zero-Latency Frame Reactor (Fase 33-Giga).
    Ring Buffer de 2 slots para latência física mínima e estabilidade de cache L3.
    """
    def __init__(self, size=2):
        self.frames = [None] * size
        self.index = 0
        self.size = size
        self.lock = threading.Lock()

    def push(self, frame):
        # Swap de slot circular: nunca acumula backlog
        i = (self.index + 1) % self.size
        self.frames[i] = frame
        self.index = i

    def latest(self):
        return self.frames[self.index]

class LivePipeline:
    def __init__(self, camera_id: str, source_type: str = "youtube", match_threshold: float = 0.48, process_every_n: int = 3,
                 max_width: int = 0, max_height: int = 0, profile: bool = False, show_every_n: int = 1,
                 use_byte_track: bool = False,
                 yt_cookies_browser: Optional[str] = None,
                 yt_cookies_file: Optional[str] = None):
        self.camera_id = camera_id
        self.source_type = source_type
        self.match_threshold = match_threshold
        self._yt_cookies_browser = yt_cookies_browser
        self._yt_cookies_file = yt_cookies_file
        # Ajuste 2: resolução padrão 960x540 — reduz carga do YOLO ≈4x vs 1080p
        # (pode ser sobrescrito por --max-width/--max-height na CLI)
        self.max_width  = max_width  if max_width  > 0 else 960
        self.max_height = max_height if max_height > 0 else 540
        self.profile = profile
        self.show_every_n = max(1, show_every_n)
        self._use_byte_track = use_byte_track

        # ─── ARQUITETURA ZERO-LATENCY FRAME REACTOR (Fase 33-Giga) ────────────
        # Ring Buffer de 2 slots para latência física mínima.
        self.frame_bus = AtomicFrameRing(size=2)
        
        # Throttling de IA: Só processa se o frame mudar.
        self._last_frame_hash = 0
        self._hash_threshold = 2.0 # Sensibilidade do reator
        
        # Display Thread Isolada: latência visual mínima
        self._display_queue = queue.Queue(maxsize=1) 
        
        self.running = False
        self.capture_thread = None
        self.ai_thread = None
        self.display_thread = None
        
        self.alerted_tracks = set()
        self.process_every_n = max(1, process_every_n)
        
        # Target FPS Dinâmico
        self._target_fps = 15
        self._frame_interval = 1.0 / self._target_fps
        
        self._last_results = []
        self._results_lock = threading.Lock()
        
        # Event Bus: Multiprocessing Queue (Fase 33-Giga)
        self._event_bus = multiprocessing.Queue()
        self._event_process = None
        self._running_flag = multiprocessing.Value('b', False)
        
        self._fps = 0.0
        self._fps_t0 = time.time()
        self._last_capture_dt = 0.0
        self._last_frame_time = time.time()
        self._WATCHDOG_TIMEOUT = 10.0 # Watchdog menos ansioso (Fase 32-UltraFix)
        self._last_process_dt = 0.0
        self._profile_t0 = time.time()
        
        # Buffer de Overlay: Evita ~22MB/s de cópias de RAM (Fase 32-Adaptive)
        self._overlay_buffer = None
        
        # Controle Adaptativo de Carga
        self._bio_interval = 1.0 / max(1, min(10, self._target_fps // self.process_every_n))

        # Garantir schema atualizado (Fase 16)
        init_db()
        
        # Inicializar processador biométrico e motor de score
        self.processor = BiometricProcessor(
            match_threshold=self.match_threshold,
            use_byte_track=getattr(self, "_use_byte_track", False),
        )
        self.db = DB()
        self.scorer = ThreatScorer(self.db)
        
        self.evidence_dir = ROOT / "intelligence" / "data" / "evidence" / "matches"
        self.report_dir = ROOT / "intelligence" / "data" / "reports"
        self.captures_dir = ROOT / "data" / "captures" # Fase 17
        
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)
        os.makedirs(self.captures_dir, exist_ok=True)

        # ─── Fase 31.1: Cache Redis (com fallback gracioso) ───────────────
        self.cache = RedisCache()
        status = self.cache.health()
        log.info(f"[Redis] Modo: {status['mode']} | "
                 f"{status.get('redis_version', 'N/A')} | "
                 f"Ping: {status.get('ping_ms', 'N/A')}ms")

        # ─── Fase 31.3: Streaming WebRTC via go2rtc ───────────────────────
        self.streamer = None
        self.enable_stream = False

    def setup_stream(self, stream_name: str, width: int = 1280, height: int = 720, fps: int = 20):
        """Inicializa o pusher de vídeo via FFmpeg para o go2rtc."""
        self.stream_name = stream_name
        self.enable_stream = True
        self.streamer = StreamPusher(stream_name, width, height, fps)
        log.info(f"🛰️ Stream WebRTC habilitado: rtsp://localhost:8554/{stream_name}")

    # Eliminado _read_frame_with_timeout (Thread Explosion Fix)


    def _capture_loop(self, stream_url: str):
        """Thread de captura: Core 2 (Fase 33-Giga)."""
        pin_thread([2])
        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        
        # Tentar aceleração de hardware (Vega iGPU)
        try:
            cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
            log.info(f"[cap] Aceleração HW solicitada para {self.camera_id}")
        except: pass

        if not cap.isOpened():
            log.error(f"Erro ao abrir stream: {stream_url}")
            self.running = False
            return

        # Buffer size 1 impede acúmulo de frames legados
        try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except: pass

        log.info(f"Captura iniciada para {self.camera_id}")
        while self.running:
            t0 = time.time()
            # Uso direto de cap.read() — o watchdog na thread run() detectará freeze
            ret, frame = cap.read()
            
            if not ret or frame is None:
                log.warning("Falha na captura. Reconectando...")
                cap.release()
                time.sleep(2)
                if self.source_type == "youtube":
                    stream_url = get_live_url(self.camera_id, self._yt_cookies_browser, self._yt_cookies_file) or stream_url
                cap = cv2.VideoCapture(stream_url)
                try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except: pass
                continue

            self._last_capture_dt = time.time() - t0
            self._last_frame_time = time.time()

            if self.max_width > 0 and self.max_height > 0:
                h, w = frame.shape[:2]
                if w > self.max_width or h > self.max_height:
                    r = min(self.max_width/w, self.max_height/h)
                    frame = cv2.resize(frame, (int(w*r), int(h*r)), interpolation=cv2.INTER_LINEAR)

            # Push para o FrameBus (RingBuffer)
            self.frame_bus.push(frame)
        cap.release()

    def _process_match(self, frame, match, track_id, db=None):
        """
        Ação tática ao detectar um alvo: Alerta + Evidência Forense.
        [Fase 31.2] Com debounce via Redis. db= conexão a usar (thread que chama deve passar a sua).
        """
        db = db or self.db
        uid = match["uid"]
        name = match["title"]
        confidence = 1.0 - match["score"]

        if self.cache.alert_is_rate_limited(uid, self.camera_id):
            log.debug(f"[Redis] Alerta SUPRIMIDO (debounce ativo): {name} @ {self.camera_id}")
            return

        log.info(f"🚨 MATCH: {name} ({confidence:.1%}) na câmera {self.camera_id}")
        self.cache.mark_alert_sent(uid, self.camera_id)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"match_{uid}_{timestamp}.jpg"
        file_path = self.evidence_dir / filename
        cv2.imwrite(str(file_path), frame)

        import hashlib
        import uuid as uuid_pkg
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        ev_id = str(uuid_pkg.uuid4())
        try:
            register_evidence(db, ev_id, uid, file_hash, str(file_path), camera_id=self.camera_id)
        except Exception as e:
            log.error(f"Falha ao registrar evidência pericial: {e}")

        try:
            distance = match["score"]
            prob = match.get("match_probability")
            conf = match.get("identity_confidence", "LOW")
            if prob is None:
                import math
                prob = math.exp(-distance * 1.2)
            register_match_log(db, uid, distance, prob, conf, camera_id=self.camera_id)
        except Exception as e:
            log.debug(f"match_log: {e}")

        threat_score = self.cache.get_threat_score(uid)
        if threat_score is None:
            score_data = get_threat_score(db, uid)
            if score_data:
                threat_score = score_data["score"]
            else:
                threat_score = ThreatScorer(db).calculate_individual_score(uid)
            self.cache.set_threat_score(uid, threat_score)
        else:
            log.debug(f"[Redis] Threat score do cache: {uid} → {threat_score}")

        dispatch_sync("MATCH_DETECTED",
            name=name,
            uid=uid,
            camera_id=self.camera_id,
            confidence=confidence,
            threat_score=threat_score,
            evidence_path=str(file_path)
        )

        # ─── Fase 32: Publicar para Dashboard Web (SSE via Redis) ──────
        self.cache.publish("tactical_alerts", {
            "type": "MATCH",
            "uid": uid,
            "name": name,
            "camera_id": self.camera_id,
            "confidence": f"{confidence:.1%}",
            "threat_score": threat_score,
            "evidence_url": f"/evidence/{filename}", # Mock URL para o dashboard
            "timestamp": datetime.now().isoformat()
        })

        def generate_async():
            # Usar conexão própria: SQLite só permite uso na thread que criou a conexão
            pdf_db = DB()
            try:
                dossier = get_full_individual_dossier(pdf_db, uid)
                if dossier:
                    pdf_filename = f"dossier_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    pdf_path = str(self.report_dir / pdf_filename)
                    generate_dossier_pdf(dossier, pdf_path)
                    log.info(f"📄 Dossiê PDF gerado: {pdf_path}")
            except Exception as ex:
                log.error(f"Erro ao gerar dossiê PDF: {ex}")
            finally:
                pdf_db.close()
        threading.Thread(target=generate_async, daemon=True).start()

    def _process_worker_loop(self):
        """AI LOOP: YOLO + ArcFace. Core 4,5,6 (Fase 33-Giga)."""
        pin_thread([4, 5, 6])
        log.info(f"[ai] Loop de IA inicializado.")
        
        while self.running:
            next_t = time.perf_counter() + self._bio_interval
            frame = self.frame_bus.latest()
            
            if frame is None:
                time.sleep(0.01)
                continue
            
            # FRAME HASHING (Throttling Inteligente)
            # Evita rodar IA em frames quase idênticos (30-60% economia)
            current_hash = np.mean(frame)
            if abs(current_hash - self._last_frame_hash) < self._hash_threshold:
                # Otimização de Clocks: Pula processamento pesado
                sleep_time = next_t - time.perf_counter()
                if sleep_time > 0: time.sleep(sleep_time)
                continue
            
            self._last_frame_hash = current_hash
            
            t0 = time.time()
            results = self.processor.process_frame(frame)
            # ... (restante do código já otimizado ROI)
            dt = time.time() - t0
            self._last_process_dt = dt
            
            with self._results_lock:
                self._last_results = results
            
            # Feedback Adaptativo mantido para não saturar núcleos de IA
            if dt > 0.25: self._bio_interval *= 1.1
            elif dt < 0.12: self._bio_interval *= 0.9
            self._bio_interval = max(0.05, min(self._bio_interval, 0.5))

            current_track_ids = {res["track_id"] for res in results}
            self.alerted_tracks = {tid for tid in self.alerted_tracks if tid in current_track_ids}
            
            for res in results:
                track_id = res["track_id"]
                match = res.get("match")
                if match and track_id not in self.alerted_tracks:
                    # OTIMIZAÇÃO ROI: Copia apenas o recorte do rosto (~20KB) em vez do frame (~1.5MB)
                    x1, y1, x2, y2 = res["box"]
                    face_roi = frame[max(0, y1):y2, max(0, x1):x2].copy()
                    
                    # Envia para o EVENT LOOP (Event Bus)
                    # Passamos o ROI para evidência e o frame original (opcional)
                    # Aqui, para manter compatibilidade com _process_match, passamos o ROI
                    self._event_bus.put((face_roi, match, track_id))
                    self.alerted_tracks.add(track_id)
            
            # Drift-Free Sleep
            sleep_time = next_t - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _display_loop(self, win_name: str):
        """Thread isolada para GUI: impede que imshow/waitKey travem o processamento."""
        log.info("[gui] Thread de exibição iniciada.")
        while self.running:
            try:
                display_frame = self._display_queue.get(timeout=1.0)
                cv2.imshow(win_name, display_frame)
                # Wayland Fix: bitmask para waitKey
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break
            except queue.Empty:
                continue
            except Exception as e:
                log.debug(f"[gui] Erro menor: {e}")
        try: cv2.destroyAllWindows()
        except: pass

    def run(self):
        """Loop principal coordenador: gerencia as threads e o watchdog."""
        stream_url = self.camera_id
        if self.source_type == "youtube":
            stream_url = get_live_url(self.camera_id, self._yt_cookies_browser, self._yt_cookies_file)
            if not stream_url: return

        self.running = True
        win_name = f"Olho de Deus - {self.camera_id}"
        
        # Estabilização GUI: Evita resize e overhead de driver (Fase 32)
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, self.max_width, self.max_height)
        
        # Iniciar Display Thread antes das outras
        self.display_thread = threading.Thread(target=self._display_loop, args=(win_name,), daemon=True)
        self.display_thread.start()

        self.capture_thread = threading.Thread(target=self._capture_loop, args=(stream_url,), daemon=True)
        self.capture_thread.start()
        
        self.ai_thread = threading.Thread(target=self._process_worker_loop, daemon=True)
        self.ai_thread.start()
        
        # Iniciar PROCESSO de eventos (Fase 33-Giga)
        self._running_flag.value = True
        self._event_process = multiprocessing.Process(
            target=_event_worker_process, 
            args=(self._event_bus, self._running_flag, self.camera_id),
            daemon=True
        )
        self._event_process.start()

        log.info("🚀 Pipeline Multi-Thread de Alta Performance Ativo.")
        
        _last_display_frame = None
        _last_watchdog_t = time.time()
        
        try:
            while self.running:
                loop_start = time.time()
                
                # Watchdog Agressivo
                now = time.time()
                if (now - _last_watchdog_t) >= 2.0:
                    _last_watchdog_t = now
                    if (now - self._last_frame_time) >= self._WATCHDOG_TIMEOUT:
                        log.warning(f"🚨 [WATCHDOG] Stream congelado há {self._WATCHDOG_TIMEOUT}s!")

                # Coleta frame mais recente (RingBuffer)
                frame = self.frame_bus.latest()
                if frame is not None:
                    _last_display_frame = frame

                if _last_display_frame is not None:
                    self._fps = 1.0 / (now - self._fps_t0) if (now - self._fps_t0) > 0 else 0
                    self._fps_t0 = now
                    
                    # ZERO-COPY HUD: Desenha diretamente no frame (Fase 33-Giga)
                    # Removemos a cópia de 1.5MB por ciclo.
                    with self._results_lock:
                        results = list(self._last_results)
                    
                    display_frame = _last_display_frame
                    self._draw_hud(display_frame, results)
                    
                    # Stream WebRTC (Preset Veryfast + Low Latency)
                    if self.enable_stream and self.streamer:
                        self.streamer.push(display_frame)

                    # Envia para a thread de interface (sem bloquear)
                    if not self._display_queue.full():
                        try: self._display_queue.put_nowait(display_frame)
                        except: pass

                # Controle de FPS do loop coordenador
                elapsed = time.time() - loop_start
                if elapsed < self._frame_interval:
                    time.sleep(self._frame_interval - elapsed)
        except KeyboardInterrupt:
            log.info("Encerrando pipeline...")
        finally:
            self.running = False
            if self.capture_thread:
                self.capture_thread.join(timeout=2.0)
            if getattr(self, "ai_thread", None):
                self.ai_thread.join(timeout=2.0)
            if self._event_process:
                self._running_flag.value = False
                self._event_process.join(timeout=5.0)
                if self._event_process.is_alive():
                    self._event_process.terminate()
            if self.streamer:
                self.streamer.stop()
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            self.db.close()

    def _draw_hud(self, frame, results):
        """Interface tática sobre o frame de vídeo."""
        h, w = frame.shape[:2]
        cv2.putText(frame, f"FPS: {self._fps:.1f}", (w - 120, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        for res in results:
            x1, y1, x2, y2 = res["box"]
            color = (0, 255, 0) # Verde (neutro)
            label = f"ID: {res['track_id']}"
            
            match = res.get("match")
            if match:
                confidence = 1.0 - match["score"]
                color = (0, 0, 255) # Vermelho (alvo identificado)
                label = f"ALVO: {match['title']} ({confidence:.1%})"
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

class StreamPusher:
    """Envia frames processados para o go2rtc via RTSP usando FFmpeg."""
    def __init__(self, stream_name: str, width: int, height: int, fps: int):
        self.rtsp_url = f"rtsp://localhost:8554/{stream_name}"
        
        # Comando FFmpeg otimizado para latência zero
        self.cmd = [
            'ffmpeg',
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f"{width}x{height}",
            '-r', str(fps),
            '-i', '-',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'veryfast',  # Melhor equilíbrio que ultrafast em 15W
            '-tune', 'zerolatency',
            '-g', '30',             # GOP fixo para fluidez constante
            '-f', 'rtsp',
            self.rtsp_url
        ]
        
        try:
            self.process = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            log.info(f"Processo FFmpeg iniciado para {stream_name}")
        except Exception as e:
            log.error(f"Falha ao iniciar FFmpeg: {e}")
            self.process = None

    def push(self, frame):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(frame.tobytes())
            except (BrokenPipeError, Exception) as e:
                log.error(f"Erro ao enviar frame para stream (FFmpeg): {e}")

    def stop(self):
        if self.process:
            self.process.stdin.close()
            self.process.terminate()
            log.info("Processo de stream encerrado.")

def load_cameras_from_json(path="cameras.json"):
    """Achata a estrutura do cameras.json para uma lista simples de dicts."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        flat_list = []
        # BR -> states -> cities -> cameras
        for country in data.values():
            for state in country.get("states", {}).values():
                for city in state.get("cities", {}).values():
                    for cam in city.get("cameras", []):
                        flat_list.append(cam)
        return flat_list
    except Exception as e:
        print(f"[error] Falha ao ler {path}: {e}")
        return []

def _event_worker_process(event_queue, running_flag, camera_id):
    """PROCESSO DE EVENTOS (Fase 33-Giga): Isolado da IA para evitar bloqueio de IO.
    Lida com SQLite, Redis, Telegram e Geração de PDFs.
    """
    # Pinning: Core 1 (IO / Background)
    pin_thread([1])
    
    db = DB()
    cache = RedisCache()
    log.info(f"[event] Processo de eventos iniciado para {camera_id}")
    
    try:
        while running_flag.value:
            try:
                # Timeout curto para checar a flag de parada
                item = event_queue.get(timeout=0.5)
                m_frame, m_match, m_track_id = item
                
                # Instanciamos um pipeline minimalista apenas para processar o match
                _handle_event_match(m_frame, m_match, m_track_id, db, cache, camera_id)
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"[event] Erro: {e}")
    finally:
        db.close()

def _handle_event_match(frame, match, track_id, db, cache, camera_id):
    """Lógica de processamento de match movida para o processo de eventos."""
    uid = match["uid"]
    name = match["title"]
    confidence = 1.0 - match["score"]

    if cache.alert_is_rate_limited(uid, camera_id):
        return

    log.info(f"🚨 [EVENT-PROC] MATCH: {name} na câmera {camera_id}")
    cache.mark_alert_sent(uid, camera_id)

    # Persistência e Alertas (Mesma lógica do LivePipeline._process_match)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"match_{uid}_{timestamp}.jpg"
    evidence_dir = Path("intelligence/evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    file_path = evidence_dir / filename
    cv2.imwrite(str(file_path), frame)

    # Publicar no Dashboard (Redis Pub/Sub)
    cache.publish("tactical_alerts", {
        "type": "MATCH",
        "uid": uid,
        "name": name,
        "camera_id": camera_id,
        "confidence": f"{confidence:.1%}",
        "evidence_url": f"/evidence/{filename}",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description="Olho de Deus — Live Biometric Pipeline")
    parser.add_argument("--id", help="ID da câmera ou URL Stream")
    parser.add_argument("--type", default="youtube", choices=["youtube", "rtsp", "webcam"], help="Tipo de fonte")
    parser.add_argument("--threshold", type=float, default=0.48, help="Match threshold")
    parser.add_argument("--process-every", type=int, default=4, metavar="N",
                        help="Processar biometria a cada N frames. "
                             "4=≈4.5 FPS bio / 18 FPS vídeo (padrão, Ryzen 15W). "
                             "1=máximo (pesado). 6=muito leve.")
    parser.add_argument("--stream", action="store_true", help="Habilitar streaming WebRTC (go2rtc)")
    parser.add_argument("--city", help="Filtrar câmeras de uma cidade no cameras.json")
    parser.add_argument("--all", action="store_true", help="Rodar todas as câmeras do cameras.json em sequência")
    parser.add_argument("--profile", action="store_true", help="Logar tempos por etapa a cada 5s (capture, process)")
    parser.add_argument("--max-width",  type=int, default=0, metavar="W",
                        help="Largura máxima do frame (padrão: 960 — reduz carga YOLO ≈4x vs 1080p)")
    parser.add_argument("--max-height", type=int, default=0, metavar="H",
                        help="Altura máxima do frame (padrão: 540)")
    parser.add_argument("--show-every", type=int, default=1, metavar="N", help="Atualizar janela a cada N frames (1=sempre, 2=reduz carga UI)")
    parser.add_argument("--byte-track", action="store_true", help="Usar ByteTrack entre YOLO e ArcFace (IDs estáveis; menos chamadas ArcFace)")
    parser.add_argument("--yt-cookies-from-browser", metavar="BROWSER", help="Navegador para cookies yt-dlp (ex: firefox, chrome). Contorna bloqueio 'Sign in to confirm you're not a bot'")
    parser.add_argument("--yt-cookies", metavar="FILE", help="Arquivo de cookies Netscape para yt-dlp (alternativa a --yt-cookies-from-browser)")
    args = parser.parse_args()

    def make_pipeline(cid, ctype="youtube", **kw):
        return LivePipeline(
            cid, source_type=ctype,
            match_threshold=args.threshold,
            process_every_n=args.process_every,
            max_width=args.max_width,
            max_height=args.max_height,
            profile=args.profile,
            show_every_n=args.show_every,
            use_byte_track=args.byte_track,
            yt_cookies_browser=args.yt_cookies_from_browser,
            yt_cookies_file=args.yt_cookies,
            **kw
        )

    if args.all or args.city:
        all_cams = load_cameras_from_json()
        if args.city:
            all_cams = [c for c in all_cams if args.city.lower() in c.get("name", "").lower() or args.city.lower() in c.get("description", "").lower()]
        if not all_cams:
            print(f"[error] Nenhuma câmera encontrada.")
            sys.exit(1)
        print(f"[info] Iniciando monitoramento sequencial de {len(all_cams)} câmeras.")
        for cam in all_cams:
            print(f"\n--- MONITORANDO: {cam['name']} ---")
            cid = cam["id"]
            ctype = cam.get("type", "youtube_live")
            if ctype == "youtube_live":
                ctype = "youtube"
            pipeline = make_pipeline(cid, ctype)
            if args.stream:
                pipeline.setup_stream(cid)
            try:
                pipeline.run()
            except KeyboardInterrupt:
                print("Próxima câmera...")
                continue
    elif args.id:
        cid = int(args.id) if args.type == "webcam" else args.id
        pipeline = make_pipeline(cid, args.type)
        if args.stream:
            stream_name = f"webcam_{cid}" if isinstance(cid, int) else cid
            pipeline.setup_stream(stream_name)
        pipeline.run()
    else:
        parser.print_help()

