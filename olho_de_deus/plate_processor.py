#!/usr/bin/env python3
"""
plate_processor.py — Olho de Deus

Motor de leitura de placa ao vivo — equivalente do biometric_processor.py
(rosto) mas pra veículo: YOLO detecta o veículo, rastreia por IoU (mesma
técnica do lado de rosto), e em vez de confiar na leitura de UM frame só
(que testamos e comprovou ser instável — ver SESSAO_CAMERAS_2026-09-10.md e
a conversa de 2026-09-11 sobre a câmera de Davao, Filipinas: "1903" lido
como "7903", "79203", "11903" em tentativas diferentes da MESMA imagem
estática), vota caractere-por-posição entre vários frames enquanto o
veículo está na tela — técnica real de ANPR (múltiplas amostras da mesma
placa convergem pra leitura mais provável, erro de OCR de frame único tende
a não se repetir sempre no mesmo jeito).
"""
import time
import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from ultralytics import YOLO

from biometric_processor import _iou
from forensic_sr_engine import alpr_engine
from plate_formats import get_format

log = logging.getLogger("plate_processor")

VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck (COCO)

# 2026-09-11: 4 amostras / 50% provou ser fraco demais na prática — primeira
# placa fechada com esses valores ("7822") não batia com a placa real da
# evidência ("LXB827"-ish). Subindo pra exigir bem mais concordância antes
# de aceitar qualquer leitura como definitiva.
MIN_FRAMES_FOR_CONSENSUS = 8    # amostras mínimas antes de aceitar uma leitura
MIN_CONSENSUS_CONFIDENCE = 0.7  # fração mínima de concordância na posição mais fraca
MAX_MISSED_FRAMES = 8


class TrackedVehicle:
    """Um veículo rastreado + urna de votos de OCR por posição de caractere."""

    _id_counter = 0

    def __init__(self, box: Tuple[int, int, int, int]):
        TrackedVehicle._id_counter += 1
        self.track_id = TrackedVehicle._id_counter
        self.box = box
        self.hits = 1
        self.missed_frames = 0
        self.last_seen = time.time()
        self.votes: List[Counter] = []
        self.frames_voted = 0
        self.resolved = False
        self.resolved_text: Optional[str] = None
        self.resolved_format: Optional[str] = None
        self.resolved_conf: Optional[float] = None

    def update(self, box: Tuple[int, int, int, int]):
        self.box = box
        self.missed_frames = 0
        self.hits += 1
        self.last_seen = time.time()

    def add_vote(self, text: str) -> None:
        """Some um voto por posição. Leituras de tamanho diferente do
        consenso em andamento são descartadas — misturar tamanhos diferentes
        na mesma urna produziria lixo garantido."""
        if self.resolved or not text:
            return
        if not self.votes:
            self.votes = [Counter() for _ in text]
        elif len(text) != len(self.votes):
            return
        for i, ch in enumerate(text):
            self.votes[i][ch] += 1
        self.frames_voted += 1

    def try_resolve(self, min_frames: int = MIN_FRAMES_FOR_CONSENSUS,
                     min_conf: float = MIN_CONSENSUS_CONFIDENCE) -> bool:
        """Fecha o consenso se já tem amostra suficiente e a posição MAIS
        fraca (não a média) passa do limiar — um caractere errado sempre
        derruba a placa inteira, então o critério tem que ser o pior caso."""
        if self.resolved or self.frames_voted < min_frames or not self.votes:
            return False
        chars, worst_conf = [], 1.0
        for counter in self.votes:
            ch, n = counter.most_common(1)[0]
            conf = n / self.frames_voted
            chars.append(ch)
            worst_conf = min(worst_conf, conf)
        if worst_conf < min_conf:
            return False
        self.resolved = True
        self.resolved_text = "".join(chars)
        self.resolved_conf = round(worst_conf, 3)
        return True


class PlateProcessor:
    """Detecção de veículo + leitura de placa com consenso multi-frame."""

    def __init__(self, yolo_model_path: str, country: str = "BR",
                 conf: float = 0.3, iou_threshold: float = 0.3,
                 read_every_n: int = 2):
        self.detector = YOLO(yolo_model_path, task="detect")
        self.country = country.upper()
        self.plate_format = get_format(self.country)
        self.conf = conf
        self.iou_threshold = iou_threshold
        self.read_every_n = read_every_n  # tenta OCR a cada N frames por track (custo alto)
        self.tracked: Dict[int, TrackedVehicle] = {}
        self._frame_i = 0
        log.info(f"[plate] país={self.country} formato={self.plate_format.pattern_desc_pt[:60]}... "
                 f"idiomas_ocr={self.plate_format.ocr_langs}")

    def process_frame(self, frame: np.ndarray) -> List[Dict]:
        """Retorna lista de {box, track_id, plate_text, plate_conf, resolved}
        pra desenhar no HUD — mesma forma de resultado do biometric_processor,
        pra reaproveitar o mesmo estilo de desenho."""
        self._frame_i += 1
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (320, 320))
        sx, sy = w / 320.0, h / 320.0

        detections = self.detector(small, verbose=False, conf=self.conf,
                                    iou=0.45, classes=VEHICLE_CLASSES)[0]
        boxes = []
        for b in detections.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append((int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)))

        assigned = set()
        results = []
        for tid, track in list(self.tracked.items()):
            best_iou, best_idx = 0.0, -1
            for i, box in enumerate(boxes):
                if i in assigned:
                    continue
                iou = _iou(track.box, box)
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_iou >= self.iou_threshold and best_idx >= 0:
                track.update(boxes[best_idx])
                assigned.add(best_idx)
            else:
                track.missed_frames += 1
                if track.missed_frames > MAX_MISSED_FRAMES:
                    continue  # removido no fim da função

            if not track.resolved and track.hits % self.read_every_n == 0:
                self._attempt_read(frame, track)

            results.append(self._to_result(track))

        for i, box in enumerate(boxes):
            if i in assigned:
                continue
            track = TrackedVehicle(box)
            self.tracked[track.track_id] = track
            results.append(self._to_result(track))

        self.tracked = {tid: t for tid, t in self.tracked.items() if t.missed_frames <= MAX_MISSED_FRAMES}
        return results

    def _attempt_read(self, frame: np.ndarray, track: TrackedVehicle) -> None:
        x1, y1, x2, y2 = track.box
        h, w = frame.shape[:2]
        vehicle_img = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        if vehicle_img.size == 0:
            return
        bbox, det_conf = alpr_engine.detect_plate_bbox(vehicle_img, conf_threshold=0.1)
        if not bbox:
            # 2026-09-11: cair pro crop do veículo INTEIRO como "fallback honesto"
            # (comportamento original de detect_plate_bbox) provou ser um problema
            # real testando ao vivo — o OCR lia o relógio sobreposto no canto do
            # vídeo como se fosse placa. Sem achar a placa de verdade dentro do
            # veículo, não arrisca (mesmo princípio já usado pro rosto: sem rosto
            # detectado dentro da pessoa, não identifica com o corpo inteiro).
            return
        px1, py1, px2, py2 = bbox
        plate_img = vehicle_img[py1:py2, px1:px2]
        if plate_img.size == 0:
            return
        text, fmt_name, conf = alpr_engine.read_plate(plate_img, country=self.country)
        log.info(f"[voto] track={track.track_id} leu={text!r} conf={conf} plate_crop_shape={plate_img.shape[:2]}")
        if text:
            track.add_vote(text)
            if track.try_resolve():
                track.resolved_format = fmt_name
                log.info(f"[plate] CONSENSO track={track.track_id}: "
                         f"'{track.resolved_text}' (conf={track.resolved_conf}, "
                         f"formato={fmt_name}, {track.frames_voted} frames)")

    def _to_result(self, track: TrackedVehicle) -> Dict:
        return {
            "box": track.box,
            "track_id": track.track_id,
            "resolved": track.resolved,
            "plate_text": track.resolved_text if track.resolved else None,
            "plate_conf": track.resolved_conf,
            "votes_so_far": track.frames_voted,
        }
