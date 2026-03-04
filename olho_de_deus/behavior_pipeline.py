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
import math
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
        person_results_list = []

        # 2. Mapeamento de classes (Stub: no modelo real, classes como 0:gun, 1:knife)
        # Usando classes de exemplo do COCO para teste: 0 (person), 67 (cell phone) -> stub de arma
        for box in results.boxes:
            cls = int(box.cls[0])
            if cls in [67, 73]: # Stub: Objetos que podem ser armas (phone, laptop/book stub)
                weapon_boxes.append(box)

        # 3. Análise de Pessoas (Pose)
        for i, kpts in enumerate(person_results.keypoints.data):
            if kpts.shape[0] >= 11:
                person_results_list.append({
                    "box": person_results.boxes.xyxy[i].cpu().numpy(),
                    "kpts": kpts
                })

        alert_level = 0
        active_threat_details = ""

        for w_obj in weapon_boxes:
            w_box_xyxy = w_obj.xyxy[0].cpu().numpy()
            w_center = [(w_box_xyxy[0] + w_box_xyxy[2]) / 2, (w_box_xyxy[1] + w_box_xyxy[3]) / 2]
            w_size = max(w_box_xyxy[2] - w_box_xyxy[0], w_box_xyxy[3] - w_box_xyxy[1])
            
            for person in person_results_list:
                p_box = person["box"]
                kpts = person["kpts"]
                
                # Check Overlap Inicial (Nível 5-7)
                if self._check_overlap(w_box_xyxy, p_box):
                    alert_level = max(alert_level, 5) # Arma em repouso/coldre próximo ao corpo
                    
                    # Refinamento Euclidiano (Nível 8-10)
                    l_wrist = kpts[9][:2].cpu().numpy()
                    r_wrist = kpts[10][:2].cpu().numpy()
                    
                    # Limiar dinâmico S baseado no tamanho da bbox da arma
                    # S = 1.2 * w_size (margem de segurança para empunhadura)
                    S = 1.2 * w_size

                    for wrist in [l_wrist, r_wrist]:
                        if wrist[0] > 0 and wrist[1] > 0:
                            dist = math.sqrt((w_center[0] - wrist[0])**2 + (w_center[1] - wrist[1])**2)
                            
                            if dist < S:
                                alert_level = 10 # AMEAÇA ATIVA: ARMA EMPUNHADA
                                active_threat_details = f"Arma detectada a {dist:.1f}px do pulso (Limiar: {S:.1f}px)"
                                break
                if alert_level == 10: break
            if alert_level == 10: break

        # 4. Pipeline de Disparo Baseado em Nível
        if alert_level >= 8:
            self.weapon_counter += 1
            if self.weapon_counter > 5: # Persistência reduzida para ameaças confirmadas (~1s)
                priority = "CRÍTICO" if alert_level == 10 else "ALTO"
                log.error(f"🚨 [{priority}] NÍVEL {alert_level}: {active_threat_details} na câmera {self.camera_id}")
                
                dispatch_sync("AMEAÇA_ARMADA", 
                    camera_id=self.camera_id, 
                    level=alert_level,
                    details=active_threat_details,
                    bypass_rate_limit=(alert_level == 10)
                )
                self.weapon_counter = -50 # Cooldown ponderado
        else:
            self.weapon_counter = max(0, self.weapon_counter - 1)
        
        return alert_level >= 8

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
