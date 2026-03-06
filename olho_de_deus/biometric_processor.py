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
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.vector_cache import VectorCache

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ─── Confidence score (Etapa 1: calibração → probabilidade → classificação) ───
# Distância L2 → probabilidade; thresholds para HIGH/MEDIUM/LOW (calibrar com match_logs depois)
# k menor = probabilidade decai mais devagar (d=0.25 pode virar MEDIUM/HIGH)
PROB_K = 1.2  # probability = exp(-distance * k)
CONFIDENCE_HIGH_PROB = 0.85
CONFIDENCE_MEDIUM_PROB = 0.60


def _distance_to_probability(distance: float) -> float:
    """Calibração: distância L2 → probabilidade (0–1). Modelo inicial: exp(-d*k)."""
    return float(np.exp(-distance * PROB_K))


def _probability_to_confidence(probability: float) -> str:
    """Classificação: probabilidade → HIGH / MEDIUM / LOW."""
    if probability >= CONFIDENCE_HIGH_PROB:
        return "HIGH"
    if probability >= CONFIDENCE_MEDIUM_PROB:
        return "MEDIUM"
    return "LOW"


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
                 model_path: str = "yolov8n_openvino_model",
                 index_path: Optional[str] = None,
                 metadata_path: Optional[str] = None,
                 iou_threshold: float = 0.4,
                 match_threshold: float = 0.7,
                 max_missed_frames: int = 15,
                 use_byte_track: bool = False,
                 track_cache_ttl_sec: float = 30.0):

        self.iou_threshold = iou_threshold
        self.match_threshold = match_threshold
        self.max_missed_frames = max_missed_frames
        self.use_byte_track = use_byte_track
        self.track_cache_ttl_sec = track_cache_ttl_sec

        # Paths dinâmicos (Busca na estrutura do projeto)
        root = Path(__file__).parent.parent.resolve()
        idx_p = index_path or str(root / "intelligence" / "data" / "vector_db.faiss")
        meta_p = metadata_path or str(root / "intelligence" / "data" / "vector_metadata.json")

        # REID: dicionário de faces ativamente rastreadas {track_id: TrackedFace}
        self.tracked_faces: Dict[int, TrackedFace] = {}

        # Modelo de detecção YOLO (OpenVINO Otimizado — Ryzen 7)
        try:
            # Buscar preferencialmente o modelo OpenVINO na pasta corrrente
            ov_model = str(root / "olho_de_deus" / "yolov8n_openvino_model")
            if os.path.exists(ov_model):
                log_msg = f"Iniciando YOLO com OpenVINO em: {ov_model}"
                self.detector = YOLO(ov_model, task="detect")
            else:
                self.detector = YOLO(model_path)
            print(f"[🛰️] Engine de Visão: OpenVINO / CPU RT")
        except Exception as e:
            print(f"[warning] OpenVINO/YOLO falhou ({e}), tentando fallback...")
            try:
                self.detector = YOLO("yolov8n.pt")
            except Exception:
                self.detector = None

        # Base vetorial FAISS
        self.index = None
        self.metadata = []
        if os.path.exists(idx_p) and os.path.exists(meta_p):
            self.index = faiss.read_index(idx_p)
            with open(meta_p, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            print(f"[🛰️] Biometria Ativa: {len(self.metadata)} alvos indexados.")
        else:
            print(f"[warning] Base vetorial não encontrada em {idx_p}. Rodar extract_embeddings.py.")

        # Cache Redis (Fase 31.2)
        self.cache = VectorCache()

    def process_frame(self, frame: np.ndarray) -> List[Dict]:
        """
        Detecta faces, aplica REID para não reprocessar o mesmo rosto,
        e retorna resultados para o HUD tático.
        Com use_byte_track=True: ByteTrack entre YOLO e ArcFace (IDs estáveis; ArcFace só em tracks novos).
        """
        if self.use_byte_track and self.detector:
            return self._process_frame_bytetrack(frame)
        return self._process_frame_iou(frame)

    def _process_frame_bytetrack(self, frame: np.ndarray) -> List[Dict]:
        """YOLO + ByteTrack (IDs estáveis) → ArcFace apenas para track_id novo. Reduz CPU e melhora tracking."""
        results = []
        h, w = frame.shape[:2]
        scale = 1.0
        if w > 640:
            scale = 640 / w
            small = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
        else:
            small = frame

        try:
            # ByteTrack mantém estado entre frames (persist=True)
            detections = self.detector.track(
                small, persist=True, verbose=False, imgsz=320,
                tracker="bytetrack.yaml"
            )[0]
        except Exception:
            # Fallback: modelo OpenVINO ou build sem tracker → usar pipeline IoU
            return self._process_frame_iou(frame)

        now = time.time()
        # Expirar cache: ByteTrack reutiliza IDs; não reusar match de pessoa que sumiu há > TTL
        self.tracked_faces = {
            tid: t for tid, t in self.tracked_faces.items()
            if (now - t.last_seen) <= self.track_cache_ttl_sec
        }

        if detections.boxes is None or len(detections.boxes) == 0:
            return results

        for i, box in enumerate(detections.boxes):
            x1, y1, x2, y2 = map(lambda v: int(v / scale), box.xyxy[0])
            conf = float(box.conf[0])
            tid = None
            if hasattr(box, "id") and box.id is not None:
                try:
                    tid = int(box.id.item()) if hasattr(box.id, "item") else int(box.id)
                except (ValueError, TypeError):
                    pass
            if tid is None:
                tid = -1 - i  # temporário para esta detecção sem id

            face_img = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if face_img.size == 0:
                continue

            if tid in self.tracked_faces:
                track = self.tracked_faces[tid]
                track.update((x1, y1, x2, y2))
                results.append({
                    "box": track.box,
                    "conf": conf,
                    "track_id": tid,
                    "match": track.match
                })
            else:
                embedding, match = self._identify(face_img)
                new_track = TrackedFace((x1, y1, x2, y2), embedding, match)
                new_track.track_id = tid  # sobrescrever para usar id do ByteTrack
                self.tracked_faces[tid] = new_track
                results.append({
                    "box": (x1, y1, x2, y2),
                    "conf": conf,
                    "track_id": tid,
                    "match": match
                })

        return results

    def _process_frame_iou(self, frame: np.ndarray) -> List[Dict]:
        """Pipeline original: YOLO → associação por IoU → ArcFace só para faces novas."""
        results = []
        h, w = frame.shape[:2]

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

        # --- Novas faces não associadas — processar biometria (ArcFace só aqui; tracks reutilizam match) ---
        for i, (x1, y1, x2, y2, conf) in enumerate(detected_boxes):
            if i in assigned_boxes:
                continue

            # Nova face detectada → extrair embedding e buscar match (detectar → rastrear → reconhecer raramente)
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

            # 2. MATCH VETORIAL (Ghost Search)
            # Primeiro tentamos o Cache Redis para latência zero
            cached_match = self.cache.get_match(embedding)
            if cached_match:
                match_data = cached_match
                # Garantir campos de confidence (cache antigo pode não ter)
                if "match_probability" not in match_data and "score" in match_data:
                    match_data["match_probability"] = _distance_to_probability(match_data["score"])
                    match_data["identity_confidence"] = _probability_to_confidence(match_data["match_probability"])
            elif self.index is not None:
                # Busca (FAISS) → calibração → probabilidade → classificação
                D, I = self.index.search(np.array([embedding]).astype('float32'), 1)
                distance = float(D[0][0])
                probability = _distance_to_probability(distance)
                confidence = _probability_to_confidence(probability)

                if distance < self.match_threshold:
                    match_data = self.metadata[I[0][0]].copy()
                    match_data["score"] = distance
                    match_data["match_probability"] = probability
                    match_data["identity_confidence"] = confidence
                    self.cache.set_match(embedding, match_data)
                else:
                    match_data = None
            else:
                match_data = None

            if match_data:
                match = {
                    "uid": match_data["uid"],
                    "title": match_data["title"],
                    "score": match_data["score"],
                    "match_probability": match_data.get("match_probability"),
                    "identity_confidence": match_data.get("identity_confidence"),
                }
                return embedding, match
            else:
                return embedding, None

        except Exception:
            return None, None
