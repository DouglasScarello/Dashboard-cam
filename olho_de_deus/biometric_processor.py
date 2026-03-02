#!/usr/bin/env python3
"""
BiometricProcessor v2.0 - Com REID (Re-Identificação)
Inspirado na arquitetura SCRFD + ArcFace + Tracker do Hailo Community Guide.
Adaptado para CPU AMD Ryzen (sem NPU) via YOLO + DeepFace.
"""
import cv2
import numpy as np
import faiss
import json
import os
import time
from ultralytics import YOLO
from deepface import DeepFace
from typing import List, Dict, Optional, Tuple

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


def _iou(box_a: Tuple, box_b: Tuple) -> float:
    """Calcula Intersection over Union entre dois bounding boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class TrackedFace:
    """Representa uma face sendo rastreada entre frames."""
    _id_counter = 0

    def __init__(self, box: Tuple, embedding: Optional[List] = None, match: Optional[Dict] = None):
        TrackedFace._id_counter += 1
        self.track_id = TrackedFace._id_counter
        self.box = box
        self.embedding = embedding
        self.match = match
        self.last_seen = time.time()
        self.missed_frames = 0

    def update(self, box: Tuple):
        self.box = box
        self.last_seen = time.time()
        self.missed_frames = 0


class BiometricProcessor:
    def __init__(self,
                 model_path: str = "yolov8n-face.pt",
                 index_path: str = "data/vector_db.faiss",
                 metadata_path: str = "data/vector_metadata.json",
                 iou_threshold: float = 0.4,
                 match_threshold: float = 0.7,
                 max_missed_frames: int = 15):

        self.iou_threshold = iou_threshold
        self.match_threshold = match_threshold
        self.max_missed_frames = max_missed_frames

        # REID: dicionário de faces ativamente rastreadas {track_id: TrackedFace}
        self.tracked_faces: Dict[int, TrackedFace] = {}

        # Modelo de detecção YOLO (Nano — otimizado p/ Ryzen 4600H)
        try:
            self.detector = YOLO(model_path)
        except Exception as e:
            print(f"[warning] YOLO falhou ({e}), tentando yolov8n...")
            try:
                self.detector = YOLO("yolov8n.pt")
            except Exception:
                self.detector = None

        # Base vetorial FAISS
        self.index = None
        self.metadata = []
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            self.index = faiss.read_index(index_path)
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            print(f"[biometria] Base carregada: {len(self.metadata)} indivíduos.")
        else:
            print("[warning] Base vetorial não encontrada. Execute fbi_ingestion.py primeiro.")

    def process_frame(self, frame: np.ndarray) -> List[Dict]:
        """
        Detecta faces, aplica REID para não reprocessar o mesmo rosto,
        e retorna resultados para o HUD tático.
        """
        results = []
        h, w = frame.shape[:2]

        # --- DETECÇÃO ---
        scale = 1.0
        if w > 640:
            scale = 640 / w
            small = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        else:
            small = frame

        if not self.detector:
            return results

        detections = self.detector(small, verbose=False, imgsz=320)[0]
        detected_boxes = []
        for box in detections.boxes:
            x1, y1, x2, y2 = map(lambda v: int(v / scale), box.xyxy[0])
            conf = float(box.conf[0])
            detected_boxes.append((x1, y1, x2, y2, conf))

        # --- REID: Associar detecções com tracks existentes via IoU ---
        matched_track_ids = set()
        assigned_boxes = set()

        for track_id, track in list(self.tracked_faces.items()):
            best_iou = 0.0
            best_box_idx = -1

            for i, (x1, y1, x2, y2, conf) in enumerate(detected_boxes):
                if i in assigned_boxes:
                    continue
                iou = _iou(track.box, (x1, y1, x2, y2))
                if iou > best_iou:
                    best_iou = iou
                    best_box_idx = i

            if best_iou >= self.iou_threshold and best_box_idx >= 0:
                # Mesma pessoa — atualizar posição, reusar embedding/match
                bx = detected_boxes[best_box_idx]
                track.update((bx[0], bx[1], bx[2], bx[3]))
                matched_track_ids.add(track_id)
                assigned_boxes.add(best_box_idx)
                results.append({
                    "box": track.box,
                    "conf": detected_boxes[best_box_idx][4],
                    "track_id": track_id,
                    "match": track.match   # Reutiliza resultado anterior!
                })
            else:
                # Pessoa saiu do frame
                track.missed_frames += 1
                if track.missed_frames <= self.max_missed_frames:
                    # Manter no resultado com a última posição conhecida
                    results.append({
                        "box": track.box,
                        "conf": 0.0,
                        "track_id": track_id,
                        "match": track.match
                    })

        # --- Novas faces não associadas — processar biometria ---
        for i, (x1, y1, x2, y2, conf) in enumerate(detected_boxes):
            if i in assigned_boxes:
                continue

            # Nova face detectada → extrair embedding e buscar match
            face_img = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if face_img.size == 0:
                continue

            embedding, match = self._identify(face_img)
            new_track = TrackedFace((x1, y1, x2, y2), embedding, match)
            self.tracked_faces[new_track.track_id] = new_track

            results.append({
                "box": (x1, y1, x2, y2),
                "conf": conf,
                "track_id": new_track.track_id,
                "match": match
            })

        # Remover tracks muito antigos
        self.tracked_faces = {
            tid: t for tid, t in self.tracked_faces.items()
            if t.missed_frames <= self.max_missed_frames
        }

        return results

    def _identify(self, face_img: np.ndarray) -> Tuple[Optional[List], Optional[Dict]]:
        """Extrai embedding ArcFace e busca match no FAISS."""
        if self.index is None:
            return None, None

        try:
            objs = DeepFace.represent(
                img_path=face_img,
                model_name="ArcFace",
                enforce_detection=False,
                detector_backend="skip"
            )
            if not objs:
                return None, None

            embedding = objs[0]["embedding"]
            query_vec = np.array([embedding]).astype('float32')
            distances, indices = self.index.search(query_vec, 1)

            idx = indices[0][0]
            score = float(distances[0][0])

            if idx != -1 and score < self.match_threshold:
                match = {
                    "uid": self.metadata[idx]["uid"],
                    "title": self.metadata[idx]["title"],
                    "score": score
                }
                return embedding, match

            return embedding, None

        except Exception:
            return None, None
