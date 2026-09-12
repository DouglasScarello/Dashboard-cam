#!/usr/bin/env python3
"""
monitor_plates.py — Olho de Deus

Liga a leitura de placa ao vivo (PlateProcessor) numa câmera real do
catálogo (database/live_cameras.db) — equivalente do monitor_camera.py
(rosto), mas pro lado de veículo/placa.

Pedido do usuário em 2026-09-11 depois de comprovar, testando frame a frame
numa câmera de Bangkok/Osaka/Davao, que uma leitura de OCR de frame ÚNICO é
instável (mesma placa lida como "1903"/"7903"/"79203" em tentativas
diferentes) — este script implementa a correção real: vota caractere-por-
posição entre vários frames enquanto o veículo está na tela (ver
plate_processor.py) antes de aceitar qualquer leitura como definitiva.

Também usa o país cadastrado da câmera (coluna `pais` do catálogo) pra
escolher automaticamente o idioma de OCR e a regex de validação certos
(ver plate_formats.py / database/plate_formats.db) — sem isso, o motor
assumia sempre formato brasileiro.

Uso:
    poetry run python3 monitor_plates.py --camera-id <id do catálogo>
    poetry run python3 monitor_plates.py --camera-id <id> --country PH   # força país
"""
import argparse
import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

import db_manager
from monitor_camera import resolve_source_type
from plate_processor import PlateProcessor
from vehicle_attributes import vehicle_attribute_classifier
from youtube_stream import get_live_url

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))
from intelligence_db import DB, init_db, register_plate_read, check_plate_watchlist, find_or_create_vehicle  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("monitor_plates")

YOLO_MODEL = str(Path(__file__).resolve().parent / "yolov8n_openvino_model")
EVIDENCE_DIR = ROOT / "intelligence" / "evidence"
LIVEVIEW_DIR = ROOT / "olho_de_deus" / "live_view"


def _safe_filename(camera_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(camera_id))


def _draw_hud(frame, results, fps: float):
    h, w = frame.shape[:2]
    cv2.putText(frame, f"PLACAS | FPS: {fps:.1f}", (w - 260, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    for res in results:
        x1, y1, x2, y2 = res["box"]
        if res["resolved"]:
            color = (0, 255, 255)  # ciano = placa consolidada
            label = f"PLACA: {res['plate_text']} ({res['plate_conf']:.0%})"
        else:
            color = (0, 200, 0)
            label = f"ID {res['track_id']} | votos {res['votes_so_far']}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, label, (x1, max(15, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


def main():
    parser = argparse.ArgumentParser(description="Monitora leitura de placa ao vivo numa câmera do catálogo")
    parser.add_argument("--camera-id", required=True, help="ID da câmera em database/live_cameras.db")
    parser.add_argument("--country", help="Força o país (ISO alpha-2) em vez de usar a coluna 'pais' do catálogo")
    parser.add_argument("--conf", type=float, default=0.3, help="Confiança mínima do YOLO pra veículo")
    parser.add_argument("--read-every", type=int, default=2, help="Tenta OCR a cada N frames por veículo rastreado")
    args = parser.parse_args()

    cam = db_manager.get_camera_by_id(args.camera_id)
    if not cam:
        raise SystemExit(f"Câmera '{args.camera_id}' não encontrada em live_cameras.db")

    source_type = resolve_source_type(cam)
    country = (args.country or cam.get("pais") or "").upper() or "BR"
    print(f"[monitor_plates] {cam.get('nome')} | país={country} | stream_format={cam.get('stream_format')} → {source_type}")

    if source_type == "youtube":
        video_id = cam.get("video_id") or cam["id"]
        stream_url = get_live_url(video_id)
        if not stream_url:
            raise SystemExit(f"Não consegui resolver a URL de stream do YouTube pra {video_id}")
    elif source_type == "snapshot_jpeg":
        raise SystemExit("monitor_plates.py ainda não suporta SNAPSHOT_JPEG (câmera contínua só, por enquanto).")
    else:
        stream_url = cam["url"]

    init_db()
    db = DB()
    processor = PlateProcessor(YOLO_MODEL, country=country, conf=args.conf, read_every_n=args.read_every)

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        raise SystemExit(f"Não consegui abrir o stream: {stream_url}")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    LIVEVIEW_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = _safe_filename(args.camera_id)
    liveview_path = LIVEVIEW_DIR / f"{safe_id}_plates.jpg"
    liveview_tmp = LIVEVIEW_DIR / f".{safe_id}_plates.tmp.jpg"

    already_logged = set()  # track_id já persistido, não repete a cada frame
    fps_t0 = time.time()
    frame_count = 0
    consecutive_failures = 0

    log.info("Pipeline de placas ativo.")
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                consecutive_failures += 1
                log.warning(f"Falha na captura ({consecutive_failures}). Reconectando...")
                cap.release()
                time.sleep(2)
                if consecutive_failures > 10:
                    raise SystemExit("Muitas falhas de captura seguidas — desistindo.")
                if source_type == "youtube":
                    # 2026-09-11: achado ao vivo — a URL assinada do googlevideo.com
                    # tem prazo de validade embutido (?expire=...). Reabrir a MESMA
                    # URL depois que ela expira falha sempre (OpenCV nem reporta o
                    # motivo real, só um erro genérico de parsing). Tem que resolver
                    # de novo a cada reconexão, não reusar a antiga.
                    fresh_url = get_live_url(video_id)
                    if fresh_url:
                        stream_url = fresh_url
                cap = cv2.VideoCapture(stream_url)
                continue
            consecutive_failures = 0

            results = processor.process_frame(frame)

            for res in results:
                if res["resolved"] and res["track_id"] not in already_logged:
                    already_logged.add(res["track_id"])
                    track = processor.tracked.get(res["track_id"])
                    fmt_name = track.resolved_format if track else None

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filename = f"plate_{res['plate_text']}_{timestamp}.jpg"
                    evidence_path = EVIDENCE_DIR / filename
                    x1, y1, x2, y2 = res["box"]
                    vehicle_crop = frame[max(0, y1):y2, max(0, x1):x2]
                    cv2.imwrite(str(evidence_path), vehicle_crop)

                    color, body_type, color_conf, body_conf = vehicle_attribute_classifier.classify(vehicle_crop)

                    vehicle = find_or_create_vehicle(
                        db, plate_text=res["plate_text"], country_code=country,
                        camera_id=args.camera_id, color=color, body_type=body_type,
                    )
                    register_plate_read(
                        db, camera_id=args.camera_id, country_code=country,
                        plate_text=res["plate_text"], plate_format=fmt_name or "INCERTO",
                        confidence=res["plate_conf"], frames_voted=res["votes_so_far"],
                        evidence_path=str(evidence_path), vehicle_id=vehicle["id"],
                        vehicle_color=color, vehicle_type=body_type,
                    )
                    descricao = f"{color or '?'} {body_type or '?'}"
                    if vehicle["is_recurring"]:
                        log.info(f"[REGISTRADO] placa='{res['plate_text']}' ({descricao}) conf={res['plate_conf']:.0%} "
                                 f"— 🔁 JÁ VISTO ANTES (veículo #{vehicle['id']}, "
                                 f"{vehicle['times_seen']}ª vez, match={vehicle['match_score']:.0%})")
                    else:
                        log.info(f"[REGISTRADO] placa='{res['plate_text']}' ({descricao}) conf={res['plate_conf']:.0%} "
                                 f"formato={fmt_name} evidencia={filename} (veículo novo #{vehicle['id']})")

                    hit = check_plate_watchlist(db, res["plate_text"])
                    if hit:
                        log.warning(f"🚨 PLACA NA LISTA DE OBSERVAÇÃO: {res['plate_text']} — {hit.get('reason')}")

            frame_count += 1
            now = time.time()
            fps = frame_count / (now - fps_t0) if now > fps_t0 else 0.0
            display = frame.copy()
            _draw_hud(display, results, fps)
            try:
                cv2.imwrite(str(liveview_tmp), display)
                os.replace(liveview_tmp, liveview_path)
            except Exception as e:
                log.error(f"[liveview] falha ao escrever frame: {e}")

    except KeyboardInterrupt:
        log.info("Encerrando (Ctrl+C).")
    finally:
        cap.release()
        db.close()


if __name__ == "__main__":
    main()
