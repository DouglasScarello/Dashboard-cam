#!/usr/bin/env python3
"""
live_pipeline.py — Olho de Deus [Fase 11: Live Biometric Pipeline]

Orquestrador de monitoramento em tempo real.
- Captura frames de streams (YouTube/RTSP) em uma thread separada.
- Processa biometria (YOLO + ArcFace) no frame mais recente (Buffer size 1).
- Registra evidências forenses (SHA-256) em caso de match positivo.
- Dispara alertas multicanal (Telegram).
"""

import os
import sys
import time
import cv2
import threading
import logging
import argparse
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from biometric_processor import BiometricProcessor
from youtube_stream import get_live_url
from alert_dispatcher import dispatch_sync
from intelligence_db import DB, init_db, register_evidence, get_threat_score, get_full_individual_dossier
from score_engine import ThreatScorer
from forensic_report import generate_dossier_pdf

# Logging
log = logging.getLogger("live_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class LivePipeline:
    def __init__(self, camera_id: str, source_type: str = "youtube", match_threshold: float = 0.48):
        self.camera_id = camera_id
        self.source_type = source_type
        self.match_threshold = match_threshold
        
        self.frame_buffer = deque(maxlen=1)
        self.running = False
        self.capture_thread = None
        self.alerted_tracks = set() # Track IDs que já dispararam alerta vivo
        
        # Garantir schema atualizado (Fase 16)
        init_db()
        
        # Inicializar processador biométrico e motor de score
        self.processor = BiometricProcessor(match_threshold=self.match_threshold)
        self.db = DB()
        self.scorer = ThreatScorer(self.db)
        
        # Diretório de evidências (Fase 16)
        self.evidence_dir = ROOT / "intelligence" / "data" / "evidence" / "matches"
        self.report_dir = ROOT / "intelligence" / "data" / "reports"
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)

    def _capture_loop(self, stream_url: str):
        """Thread que mantém o buffer de frames sempre atualizado (descartando atraso)."""
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            log.error(f"Erro ao abrir stream: {stream_url}")
            self.running = False
            return

        log.info(f"Captura iniciada para {self.camera_id}")
        while self.running:
            ret, frame = cap.read()
            if not ret:
                log.warning("Falha ao ler frame. Tentando reconectar...")
                cap.release()
                time.sleep(5)
                # Tentar reobter URL se for YouTube
                if self.source_type == "youtube":
                    stream_url = get_live_url(self.camera_id) or stream_url
                cap = cv2.VideoCapture(stream_url)
                continue
            
            self.frame_buffer.append(frame)
        
        cap.release()

    def _process_match(self, frame, match, track_id):
        """Ação tática ao detectar um alvo: Alerta + Evidência Forense."""
        uid = match["uid"]
        name = match["title"]
        confidence = 1.0 - match["score"]
        
        log.info(f"🚨 MATCH: {name} ({confidence:.1%}) na câmera {self.camera_id}")
        
        # 1. Salvar Frame de Evidência
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"match_{uid}_{timestamp}.jpg"
        file_path = self.evidence_dir / filename
        cv2.imwrite(str(file_path), frame)
        
        # 2. Registrar na Cadeia de Custódia (Fase 16)
        import hashlib
        import uuid as uuid_pkg
        
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        ev_id = str(uuid_pkg.uuid4())
        try:
            register_evidence(self.db, ev_id, uid, file_hash, str(file_path), camera_id=self.camera_id)
        except Exception as e:
            log.error(f"Falha ao registrar evidência pericial: {e}")

        # 3. Obter ou Calcular Score de Ameaça (Fase 12)
        score_data = get_threat_score(self.db, uid)
        if score_data:
            threat_score = score_data["score"]
        else:
            threat_score = self.scorer.calculate_individual_score(uid)

        # 4. Disparar Alerta Multicanal (Fase 21)
        dispatch_sync("MATCH_DETECTED",
            name=name,
            uid=uid,
            camera_id=self.camera_id,
            confidence=confidence,
            threat_score=threat_score,
            evidence_path=str(file_path)
        )

        # 5. Gerar Dossiê Forense PDF (Fase 18) — Em Thread separada para não travar o vídeo
        def generate_async():
            try:
                dossier = get_full_individual_dossier(self.db, uid)
                if dossier:
                    pdf_filename = f"dossier_{uid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    pdf_path = str(self.report_dir / pdf_filename)
                    generate_dossier_pdf(dossier, pdf_path)
                    log.info(f"📄 Dossiê PDF gerado: {pdf_path}")
            except Exception as ex:
                log.error(f"Erro ao gerar dossiê PDF: {ex}")

        threading.Thread(target=generate_async, daemon=True).start()


    def run(self):
        """Loop principal de processamento biométrico."""
        stream_url = self.camera_id
        if self.source_type == "youtube":
            stream_url = get_live_url(self.camera_id)
            if not stream_url:
                return

        self.running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, args=(stream_url,), daemon=True)
        self.capture_thread.start()

        log.info(f"Pipeline Bio-Live ativo. Pressione Ctrl+C para encerrar.")
        
        try:
            while self.running:
                if not self.frame_buffer:
                    time.sleep(0.01)
                    continue
                
                frame = self.frame_buffer.pop()
                
                # Processamento Biométrico (YOLO + ArcFace)
                results = self.processor.process_frame(frame)
                
                current_track_ids = {res["track_id"] for res in results}
                
                # Limpar alertas de track_ids que saíram do frame
                self.alerted_tracks = {tid for tid in self.alerted_tracks if tid in current_track_ids}
                
                for res in results:
                    track_id = res["track_id"]
                    match = res.get("match")
                    
                    if match and track_id not in self.alerted_tracks:
                        # Só processamos match "novo" para evitar spam de alertas
                        self._process_match(frame, match, track_id)
                        self.alerted_tracks.add(track_id)
                
                # Visualização opcional (pode ser desativada para servidores)
                self._draw_hud(frame, results)
                cv2.imshow(f"Olho de Deus - {self.camera_id}", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            log.info("Encerrando pipeline...")
        finally:
            self.running = False
            self.capture_thread.join()
            cv2.destroyAllWindows()
            self.db.close()

    def _draw_hud(self, frame, results):
        """Interface tática sobre o frame de vídeo."""
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

if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description="Olho de Deus — Live Biometric Pipeline")
    parser.add_argument("--id", help="ID da câmera ou URL Stream")
    parser.add_argument("--type", default="youtube", choices=["youtube", "rtsp", "webcam"], help="Tipo de fonte")
    parser.add_argument("--threshold", type=float, default=0.48, help="Match threshold")
    parser.add_argument("--city", help="Filtrar câmeras de uma cidade no cameras.json")
    parser.add_argument("--all", action="store_true", help="Rodar todas as câmeras do cameras.json em sequência")
    
    args = parser.parse_args()
    
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
            if ctype == "youtube_live": ctype = "youtube"
            
            pipeline = LivePipeline(cid, source_type=ctype, match_threshold=args.threshold)
            try:
                pipeline.run()
            except KeyboardInterrupt:
                print("Próxima câmera...")
                continue
    elif args.id:
        cid = int(args.id) if args.type == "webcam" else args.id
        pipeline = LivePipeline(cid, source_type=args.type, match_threshold=args.threshold)
        pipeline.run()
    else:
        parser.print_help()

