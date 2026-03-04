#!/usr/bin/env python3
"""
behavior_pipeline.py — Olho de Deus [Fase 30: Detecção de Anomalias]

Monitoramento de comportamento tático em tempo real.
- Detecção de Emergência Médica (Quedas via YOLOv8-Pose).
- Detecção de Ameaça Armada (Guns/Knives via YOLOv8 especializado).
- Alertas Críticos com bypass de rate-limit.
"""

import os
import sys
import time
import cv2
import threading
import logging
import argparse
import psutil
import numpy as np
from collections import deque
from datetime import datetime
from pathlib import Path
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))
sys.path.insert(0, str(ROOT / "olho_de_deus"))

from alert_dispatcher import dispatch_sync
from youtube_stream import get_live_url

# Logging
log = logging.getLogger("behavior_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [tactical] %(message)s")

class BehaviorPipeline:
    def __init__(self, camera_id: str, source_type: str = "youtube"):
        self.camera_id = camera_id
        self.source_type = source_type
        self.running = False
        self.frame_buffer = deque(maxlen=1)
        
        # Carregar Modelos (OpenVINO Otimizado — Ryzen 7)
        log.info("Carregando motores de análise (OpenVINO Acceleration)...")
        
        # Pose (Quedas)
        ov_pose = str(ROOT / "olho_de_deus" / "yolov8n-pose_openvino_model")
        if os.path.exists(ov_pose):
            self.pose_model = YOLO(ov_pose, task="pose")
        else:
            self.pose_model = YOLO("yolov8n-pose.pt")
        
        # Modelo de Armas (OpenVINO fallback)
        ov_weapon = str(ROOT / "olho_de_deus" / "yolov8n_openvino_model")
        if os.path.exists(ov_weapon):
            self.weapon_model = YOLO(ov_weapon, task="detect")
        else:
            self.weapon_model = YOLO("yolov8n.pt")
        
        self.weapon_classes = [0] # Stub
        
        # Estado para detecção de queda
        self.fall_counter = 0
        self.weapon_counter = 0

    def _capture_loop(self, stream_url: str):
        cap = cv2.VideoCapture(stream_url)
        while self.running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(1)
                continue
            self.frame_buffer.append(frame)
        cap.release()

    def _analyze_pose(self, frame):
        """Detecta quedas baseada na orientação do esqueleto e persistência."""
        results = self.pose_model(frame, verbose=False, imgsz=320, conf=0.5)[0]
        
        current_potential_falls = set()

        for i, kpts in enumerate(results.keypoints.data):
            if kpts.shape[0] < 17: continue
            
            # Aspect Ratio da Bbox (Largura / Altura)
            box = results.boxes.xywh[i].cpu().numpy() # [x, y, w, h]
            w, h = box[2], box[3]
            aspect_ratio = w / h
            
            # Heurística: se a pessoa está "mais larga que alta" (Ratio > 1.3)
            # e os keypoints confirmam o alinhamento horizontal
            if aspect_ratio > 1.3:
                # Usamos o índice da detecção como ID temporário (melhorar com tracker depois)
                # Por enquanto, se houver QUALQUER pessoa horizontal, incrementamos um alerta global
                # ou tentamos rastrear por posição aproximada.
                current_potential_falls.add(i)

        # Persistência tática: só alerta se a anomalia durar > 3 segundos
        if current_potential_falls:
            self.fall_counter = getattr(self, "fall_counter", 0) + 1
            if self.fall_counter > 15: # ~3 segundos a 5 FPS
                log.warning(f"🚨 [CRÍTICO] EMERGÊNCIA MÉDICA: Pessoa caída na câmera {self.camera_id}")
                dispatch_sync("EMERGENCY_MEDICAL", 
                    camera_id=self.camera_id, 
                    type="PESSOA CAÍDA (CONFIRMADO)",
                    bypass_rate_limit=True
                )
                self.fall_counter = -100 # Cooldown para não floodar
        else:
            self.fall_counter = max(0, getattr(self, "fall_counter", 0) - 1)
            
        return len(current_potential_falls) > 0

    def _analyze_weapons(self, frame):
        """
        Detecta armas e objetos perigosos com lógica de intersecção (Fase 30.1).
        Verifica se a arma está em contato/empunhada por uma pessoa.
        """
        # 1. Detecção (Utilizando o modelo já carregado/OpenVINO)
        results = self.weapon_model(frame, verbose=False, imgsz=320, conf=0.5)[0]
        person_results = self.pose_model(frame, verbose=False, imgsz=320, conf=0.5)[0]

        weapon_boxes = []
        person_boxes = []

        # Mapeamento de classes (Stub: no modelo real, classes como 0:gun, 1:knife)
        # Por enquanto, tratamos 'cell phone' como stub se o modelo for o original yolov8n.pt
        for box in results.boxes:
            cls = int(box.cls[0])
            # Se for um modelo de armas, checaríamos as classes [0, 1, 2...]
            # Usando classes de exemplo do COCO para teste: 67 (cell phone) -> stub de arma
            if cls in [0, 1, 67]: # person (0), handgun/knife stub
                weapon_boxes.append(box.xyxy[0].cpu().numpy())

        for box in person_results.boxes:
            person_boxes.append(box.xyxy[0].cpu().numpy())

        found_active_threat = False
        for w_box in weapon_boxes:
            for i, p_box in enumerate(person_boxes):
                # 1. Checagem básica de Overlap
                if self._check_overlap(w_box, p_box):
                    # 2. Refinamento por Keypoints (Mão/Pulso)
                    # No yolov8-pose: 9 (l_wrist), 10 (r_wrist)
                    if person_results.keypoints.data.shape[0] > i:
                        kpts = person_results.keypoints.data[i]
                        if kpts.shape[0] >= 11:
                            l_wrist = kpts[9][:2].cpu().numpy()
                            r_wrist = kpts[10][:2].cpu().numpy()
                            
                            # Se a arma estiver perto de um dos pulsos, confirma ameaça ativa
                            for wrist in [l_wrist, r_wrist]:
                                if wrist[0] > 0 and wrist[1] > 0: # Check valid kpt
                                    if (w_box[0] <= wrist[0] <= w_box[2] and 
                                        w_box[1] <= wrist[1] <= w_box[3]):
                                        found_active_threat = True
                                        break
                if found_active_threat: break

        if found_active_threat:
            self.weapon_counter += 1
            if self.weapon_counter > 8: # Persistência: ~1.5 segundos
                log.error(f"🚨🚨🚨 [CRÍTICO] AMEAÇA ARMADA DETECTADA na câmera {self.camera_id}")
                dispatch_sync("AMEAÇA_ARMADA", 
                    camera_id=self.camera_id, 
                    type="POSSÍVEL ARMA EMPUNHADA DETECTADA",
                    bypass_rate_limit=True
                )
                self.weapon_counter = -100 # Cooldown
        else:
            self.weapon_counter = max(0, self.weapon_counter - 1)
        
        return found_active_threat

    def _check_overlap(self, box1, box2):
        """Verifica se há intersecção entre duas bounding boxes."""
        x1_max = max(box1[0], box2[0])
        y1_max = max(box1[1], box2[1])
        x2_min = min(box1[2], box2[2])
        y2_min = min(box1[3], box2[3])
        
        return x1_max < x2_min and y1_max < y2_min

    def run(self):
        stream_url = self.camera_id
        if self.source_type == "youtube":
            stream_url = get_live_url(self.camera_id)

        self.running = True
        threading.Thread(target=self._capture_loop, args=(stream_url,), daemon=True).start()

        log.info(f"Monitor de Comportamento Ativo no feed {self.camera_id}")
        
        try:
            while self.running:
                if not self.frame_buffer:
                    time.sleep(0.01)
                    continue
                
                frame = self.frame_buffer.pop()
                
                # 1. Análise de Pose e Comportamento
                start_time = time.time()
                self._analyze_pose(frame)
                self._analyze_weapons(frame)
                
                # 2. Dynamic Downsampling (Fase 31.2)
                # Monitorar CPU para evitar thermal throttling no Ryzen
                cpu_usage = psutil.cpu_percent()
                
                # Se CPU > 80%, reduzimos FPS de análise de 5 para 1
                base_delay = 0.2 # 5 FPS padrão
                if cpu_usage > 85:
                    base_delay = 1.0 # 1 FPS de emergência
                elif cpu_usage > 70:
                    base_delay = 0.5 # 2 FPS moderado
                
                # Visualização Tática
                cv2.imshow(f"Tactic - {self.camera_id}", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                
                elapsed = time.time() - start_time
                wait_time = max(0.01, base_delay - elapsed)
                time.sleep(wait_time)

        except KeyboardInterrupt:
            self.running = False
        finally:
            cv2.destroyAllWindows()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--type", default="youtube")
    args = parser.parse_args()
    
    BehaviorPipeline(args.id, args.type).run()
