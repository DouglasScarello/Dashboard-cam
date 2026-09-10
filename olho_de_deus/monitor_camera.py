#!/usr/bin/env python3
"""
monitor_camera.py — Olho de Deus

Liga o reconhecimento facial ao vivo (LivePipeline) numa câmera REAL do
catálogo atual (database/live_cameras.db via db_manager.py) — não mais o
cameras.json antigo (100% YouTube, removido do projeto).

Escolhe automaticamente o modo de captura certo baseado em stream_format:
  - M3U8 (HLS direto)   → source_type="direct"   (cv2.VideoCapture contínuo)
  - SNAPSHOT_JPEG        → source_type="snapshot_jpeg" (polling HTTP periódico)

Uso:
    poetry run python3 monitor_camera.py --camera-id <id do catálogo>
    poetry run python3 monitor_camera.py --webcam 0   # teste local, sem catálogo
"""
import argparse

import db_manager
from live_pipeline import LivePipeline


def resolve_source_type(cam: dict) -> str:
    """Decide o modo de captura certo a partir do stream_format do catálogo.
    Extraído do corpo de main() pra dar pra testar sem precisar abrir stream de verdade."""
    return "snapshot_jpeg" if cam.get("stream_format") == "SNAPSHOT_JPEG" else "direct"


def main():
    parser = argparse.ArgumentParser(description="Monitora UMA câmera real do catálogo com reconhecimento facial")
    parser.add_argument("--camera-id", help="ID da câmera em database/live_cameras.db")
    parser.add_argument("--webcam", type=int, default=None, help="Índice da webcam local, pra teste (ex: 0)")
    # Ver comentário de calibração em live_pipeline.py (mesma constante) — 0.6 é o
    # valor empírico, não um chute.
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--process-every", type=int, default=4)
    parser.add_argument("--poll-interval", type=float, default=10.0, help="Intervalo (s) pra câmeras SNAPSHOT_JPEG")
    args = parser.parse_args()

    if args.webcam is not None:
        print(f"[monitor] Webcam local índice {args.webcam}")
        pipeline = LivePipeline(
            camera_id=f"webcam_{args.webcam}", source_type="webcam", stream_url=str(args.webcam),
            match_threshold=args.threshold, process_every_n=args.process_every,
        )
        pipeline.run()
        return

    if not args.camera_id:
        raise SystemExit("Passe --camera-id <id> ou --webcam <indice>.")

    cam = db_manager.get_camera_by_id(args.camera_id)
    if not cam:
        raise SystemExit(f"Câmera '{args.camera_id}' não encontrada em live_cameras.db")

    source_type = resolve_source_type(cam)
    is_snapshot = source_type == "snapshot_jpeg"
    print(f"[monitor] {cam.get('nome')} | stream_format={cam.get('stream_format')} → source_type={source_type}")
    print(f"[monitor] URL: {cam.get('url')}")

    pipeline = LivePipeline(
        camera_id=cam["id"], source_type=source_type, stream_url=cam["url"],
        match_threshold=args.threshold, process_every_n=args.process_every,
    )
    if is_snapshot:
        # process_every_n não se aplica ao intervalo de captura no modo snapshot —
        # o próprio poll_interval_s do _capture_loop_snapshot já controla a cadência.
        pipeline._snapshot_poll_interval = args.poll_interval
    pipeline.run()


if __name__ == "__main__":
    main()
