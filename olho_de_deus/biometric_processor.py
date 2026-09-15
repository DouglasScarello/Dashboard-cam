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
import logging
import os
import time
from collections import Counter
from ultralytics import YOLO
from deepface import DeepFace
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.vector_cache import VectorCache

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# Sem handler/basicConfig própria — reaproveita a config já feita pelo
# entrypoint (monitor_camera.py -> live_pipeline.py), mesma convenção do
# resto do projeto (ver live_pipeline.py:91).
log = logging.getLogger("biometric_processor")

# 2026-09-12: instrumentação temporária pra diagnóstico ao vivo (pedido do
# usuário) — `_face_quality_ok` sempre soube o motivo exato de rejeitar um
# rosto (retorna a razão como string), mas ninguém nunca logava isso, então
# não dava pra saber SE o gate estava rejeitando por rosto pequeno demais,
# ângulo, blur ou confiança do detector — só que zero pessoa era registrada.
# Contador agregado (não loga cada frame individualmente, senão em câmera
# de rua movimentada isso inunda o log) + amostra ocasional com os números
# reais medidos, pra decidir com dado, não achismo, se vale afrouxar algum
# limiar ou trocar de câmera.
_gate_reject_counts = Counter()
_gate_accept_count = [0]
_gate_last_report = [0.0]
_GATE_REPORT_INTERVAL_SEC = 30.0

YUNET_MODEL_PATH = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"

# Template de referência ArcFace 112x112 (padrão insightface) — mesma ordem de
# pontos que o YuNet devolve: olho direito, olho esquerdo, nariz, boca-direita,
# boca-esquerda. Alinhar contra isso é o que o DeepFace faz internamente quando
# detector_backend="retinaface" (usado no cadastro via delta_embedder.py) — sem
# alinhar aqui também, o embedding da câmera ao vivo (YuNet, sem alinhamento)
# fica sistematicamente mais distante do embedding cadastrado da MESMA pessoa
# só por causa da diferença de pipeline, não por diferença de identidade.
# Medido: sem alinhamento, distância de auto-match variava 0.04–0.70 (faixa tão
# larga que se sobrepõe à de gente DIFERENTE — nenhum threshold resolveria isso).
_ARCFACE_112_TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


# ─── Filtro de qualidade facial (2026-09-11) ───
# Achado real testando câmera de rua ao vivo (Bangkok): sem filtro nenhum, rosto
# pequeno/de lado/parcialmente coberto (capacete, óculos escuros) gerava "match"
# contra o FBI em segundos — sempre falso-positivo confirmado visualmente pelo
# usuário. Causa raiz: YuNet aceita QUALQUER blob face-like acima de 0.6 de
# confiança (limiar pensado só pra "existe um rosto aqui", não pra "esse rosto
# é confiável pra identificação"), sem checar tamanho, ângulo ou nitidez — o
# ArcFace então embeda ruído (cor do capacete/óculos domina, não geometria
# facial) e a busca por vizinho mais próximo acha "parecido" por acaso.
#
# Padrão da indústria (pesquisado): o próprio pipeline de limpeza de dataset do
# InsightFace (WebFace42M) descarta rosto borrado, ocluso ou com pose > 45°
# ANTES de treinar/comparar — pré-filtro é a alavanca que mais reduz erro,
# mais do que ajustar o limiar de distância. NIST FRVT Part 3 (2019) documenta
# que taxa de falso-positivo varia até 7203x entre grupos demográficos, e é
# consistentemente pior em imagem de baixa qualidade — ou seja, o viés racial
# que o usuário suspeitou é um efeito real e documentado, que piora ainda mais
# quando a entrada já é ruim. Por isso o gate abaixo, não só o limiar de match.
MIN_INTEROCULAR_PX = 40    # abaixo disso, rosto longe/pequeno demais pro ArcFace confiar (~48px é a referência da literatura pra "condição difícil")
MIN_DET_CONFIDENCE = 0.85  # confiança do YuNet — 0.6 é limiar de "existe rosto", não de "confiável pra identificar"
MAX_YAW_ASYMMETRY = 0.68   # proxy de perfil/pose extrema (~>45°) via posição do nariz entre os dois olhos
MIN_BLUR_VARIANCE = 25.0   # variância do Laplaciano no rosto alinhado — abaixo disso, borrado demais

# 2026-09-11: em teste ao vivo numa câmera de rua real, o YOLO nano (vídeo
# comprimido) de vez em quando "detectava pessoa" numa sombra ou bueiro na
# calçada por 1 frame só, isolado. Exigir 2 detecções seguidas do mesmo track
# antes de desenhar a caixa elimina esse ruído sem atraso perceptível pra
# gente de verdade (que persiste dezenas de frames).
MIN_HITS_TO_DISPLAY = 2


def _face_quality_ok(landmarks: np.ndarray, det_score: float, aligned: np.ndarray) -> Tuple[bool, str]:
    """Gate de qualidade ANTES do ArcFace — rejeitar aqui é mais barato e mais
    eficaz que tentar compensar depois só com o limiar de distância."""
    if det_score < MIN_DET_CONFIDENCE:
        return False, f"confiança do detector baixa ({det_score:.2f})"

    right_eye, left_eye, nose = landmarks[0], landmarks[1], landmarks[2]
    interocular = float(np.linalg.norm(right_eye - left_eye))
    if interocular < MIN_INTEROCULAR_PX:
        return False, f"rosto pequeno demais ({interocular:.0f}px entre os olhos)"

    d_r = abs(nose[0] - right_eye[0])
    d_l = abs(nose[0] - left_eye[0])
    yaw_ratio = d_r / max(d_r + d_l, 1e-6)
    if yaw_ratio < (1 - MAX_YAW_ASYMMETRY) or yaw_ratio > MAX_YAW_ASYMMETRY:
        return False, f"pose de lado demais (razão {yaw_ratio:.2f})"

    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if blur < MIN_BLUR_VARIANCE:
        return False, f"borrado demais (var={blur:.1f})"

    return True, "ok"


def _detect_and_align_face(face_detector, crop: np.ndarray, out_size: int = 112) -> Optional[np.ndarray]:
    """
    Roda YuNet dentro de um recorte de PESSOA (não do frame inteiro — mais rápido
    e evita achar rosto de outra pessoa ao fundo), e devolve o rosto já ALINHADO
    (rotação/escala pelos 5 pontos faciais, mesmo padrão que o ArcFace espera) em
    112x112 — pronto pra ir direto pro DeepFace com detector_backend="skip".
    None se não achar rosto (pessoa de costas, ângulo ruim, fora de quadro) OU
    se o rosto encontrado não passar no filtro de qualidade (ver _face_quality_ok).
    """
    h, w = crop.shape[:2]
    if h < 10 or w < 10:
        _report_gate_result("recorte_pequeno_demais")
        return None
    face_detector.setInputSize((w, h))
    _, faces = face_detector.detect(crop)
    if faces is None or len(faces) == 0:
        _report_gate_result("nenhum_rosto_no_recorte")
        return None
    best = max(faces, key=lambda f: f[14])  # coluna 14 = score de confiança
    landmarks = best[4:14].reshape(5, 2).astype(np.float32)
    det_score = float(best[14])

    transform, _ = cv2.estimateAffinePartial2D(landmarks, _ARCFACE_112_TEMPLATE, method=cv2.LMEDS)
    if transform is None:
        _report_gate_result("falha_no_alinhamento")
        return None
    aligned = cv2.warpAffine(crop, transform, (out_size, out_size), borderValue=0.0)

    ok, reason = _face_quality_ok(landmarks, det_score, aligned)
    if not ok:
        _report_gate_result(reason)
        return None
    _report_gate_result("aceito", accepted=True)
    return aligned


def _report_gate_result(reason: str, accepted: bool = False) -> None:
    """Agrega motivos de rejeição/aceite do gate de qualidade facial e
    imprime um resumo periódico (não frame a frame — inundaria o log numa
    câmera de rua movimentada). Instrumentação de diagnóstico pedida pelo
    usuário em 2026-09-12 (ver MIN_INTEROCULAR_PX etc.) — antes disso o
    motivo exato existia (a string já vinha pronta) mas nunca era logado,
    então não dava pra saber SE o gate estava rejeitando por rosto pequeno,
    ângulo, blur ou falta de rosto na silhueta."""
    if accepted:
        _gate_accept_count[0] += 1
    else:
        # Agrupa pela categoria (antes do "(") pra não estourar o Counter
        # com uma chave distinta por valor medido — queremos saber QUAL
        # limiar está barrando, não cada leitura individual em px/variância.
        category = reason.split("(")[0].strip()
        _gate_reject_counts[category] += 1

    now = time.time()
    if now - _gate_last_report[0] >= _GATE_REPORT_INTERVAL_SEC:
        _gate_last_report[0] = now
        total_rejected = sum(_gate_reject_counts.values())
        total = total_rejected + _gate_accept_count[0]
        if total == 0:
            return
        breakdown = ", ".join(f"{k}={v}" for k, v in _gate_reject_counts.most_common())
        log.info(
            f"[face_gate] últimos {_GATE_REPORT_INTERVAL_SEC:.0f}s: "
            f"{_gate_accept_count[0]}/{total} rostos aceitos ({100*_gate_accept_count[0]/total:.0f}%). "
            f"Rejeitados por: {breakdown or 'nenhum'}"
        )
        _gate_reject_counts.clear()
        _gate_accept_count[0] = 0

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
        # Achado 2026-09-11 testando ao vivo: YOLO (nano, vídeo comprimido de
        # câmera pública) de vez em quando "detecta pessoa" numa sombra ou
        # bueiro na calçada — um blob falso-positivo isolado, sem persistir.
        # Exigir >=2 detecções seguidas antes de mostrar a caixa filtra esse
        # ruído sem atrasar gente de verdade (que naturalmente persiste vários
        # frames).
        self.hits = 1

    def update(self, box: Tuple):
        self.box = box
        self.last_seen = time.time()
        self.missed_frames = 0
        self.hits += 1


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

        # Detector de ROSTO real (YuNet) — segundo estágio depois do YOLO achar a
        # pessoa. Sem isso, o crop de PESSOA INTEIRA ia direto pro ArcFace com
        # detector_backend="skip" (sem detecção/alinhamento nenhum), o que é
        # impreciso pra reconhecimento biométrico. Leve o suficiente pra rodar
        # por frame em CPU (ONNX ~230KB, bem mais leve que RetinaFace).
        try:
            self.face_detector = cv2.FaceDetectorYN.create(
                str(YUNET_MODEL_PATH), "", (320, 320), score_threshold=0.6
            )
        except Exception as e:
            print(f"[warning] YuNet indisponível ({e}) — cai de volta pro crop de pessoa inteira.")
            self.face_detector = None

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
        """YOLO + ByteTrack (IDs estáveis) → ArcFace apenas para track_id novo."""
        results = []
        h, w = frame.shape[:2]
        
        # Otimização OpenVINO: Forçar 320x320
        scale_x = w / 320.0
        scale_y = h / 320.0
        small_static = cv2.resize(frame, (320, 320))

        try:
            # TUNING FASE 33-STABLE: conf=0.5, iou=0.45, classes=[0] (pessoa) —
            # 2026-09-11: cogitei subir pra 0.6 depois de achar falso-positivo
            # em sombra/bueiro, mas medi direto (ver histórico) que gente real
            # e visível nessa câmera às vezes fica com conf~0.38 (longe/pequena
            # demais) — subir o limiar mataria detecção de verdade sem
            # resolver o problema. O que corrige o falso-positivo é
            # MIN_HITS_TO_DISPLAY (exigir 2 frames seguidos), não o limiar.
            detections = self.detector.track(
                small_static, persist=True, verbose=False,
                conf=0.5, iou=0.45, classes=[0],
                tracker="bytetrack.yaml"
            )[0]
        except Exception:
            return self._process_frame_iou(frame)

        now = time.time()
        self.tracked_faces = {
            tid: t for tid, t in self.tracked_faces.items()
            if (now - t.last_seen) <= self.track_cache_ttl_sec
        }

        if detections.boxes is None or len(detections.boxes) == 0:
            return results

        for i, box in enumerate(detections.boxes):
            # Escala X/Y independente para compensar o crunch 320x320
            x1_raw, y1_raw, x2_raw, y2_raw = box.xyxy[0].cpu().numpy()
            x1 = int(x1_raw * scale_x)
            y1 = int(y1_raw * scale_y)
            x2 = int(x2_raw * scale_x)
            y2 = int(y2_raw * scale_y)
            
            conf = float(box.conf[0])
            tid = None
            if hasattr(box, "id") and box.id is not None:
                try:
                    tid = int(box.id.item()) if hasattr(box.id, "item") else int(box.id)
                except (ValueError, TypeError):
                    pass
            if tid is None:
                tid = -1 - i

            face_img = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if face_img.size == 0:
                continue

            if tid in self.tracked_faces:
                track = self.tracked_faces[tid]
                track.update((x1, y1, x2, y2))
                if track.hits >= MIN_HITS_TO_DISPLAY:
                    results.append({
                        "box": track.box,
                        "conf": conf,
                        "track_id": tid,
                        "match": track.match
                    })
            else:
                embedding, match = None, None
                if self.face_detector is not None:
                    aligned_face = _detect_and_align_face(self.face_detector, face_img)
                    if aligned_face is not None:
                        embedding, match = self._identify(aligned_face)
                    # sem rosto detectado dentro da pessoa (de costas, ângulo ruim) —
                    # não arrisca identificar com o corpo inteiro, fica sem match mesmo
                else:
                    embedding, match = self._identify(face_img)  # fallback sem YuNet
                new_track = TrackedFace((x1, y1, x2, y2), embedding, match)
                new_track.track_id = tid
                self.tracked_faces[tid] = new_track
                # hits=1 na criação — só aparece no HUD/resultado quando confirmado
                # de novo no próximo frame (ver MIN_HITS_TO_DISPLAY)

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

        # Forçar redimensionamento para 320x320 com cálculo correto de escala X e Y
        small_static = cv2.resize(frame, (320, 320))
        scale_x = w / 320.0
        scale_y = h / 320.0
        detections = self.detector(small_static, verbose=False, conf=0.5, iou=0.45, classes=[0])[0]
        detected_boxes = []
        for box in detections.boxes:
            bx = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy[0], "cpu") else box.xyxy[0]
            x1 = int(bx[0] * scale_x)
            y1 = int(bx[1] * scale_y)
            x2 = int(bx[2] * scale_x)
            y2 = int(bx[3] * scale_y)
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
                if track.hits >= MIN_HITS_TO_DISPLAY:
                    results.append({
                        "box": track.box,
                        "conf": detected_boxes[best_box_idx][4],
                        "track_id": track_id,
                        "match": track.match,   # Reutiliza resultado anterior!
                        "embedding": track.embedding,  # None se o rosto nunca passou no filtro de qualidade
                    })
            else:
                # Pessoa saiu do frame
                track.missed_frames += 1
                if track.missed_frames <= self.max_missed_frames and track.hits >= MIN_HITS_TO_DISPLAY:
                    # Manter no resultado com a última posição conhecida
                    results.append({
                        "box": track.box,
                        "conf": 0.0,
                        "track_id": track_id,
                        "match": track.match,
                        "embedding": track.embedding,
                    })

        # --- Novas faces não associadas — processar biometria (ArcFace só aqui; tracks reutilizam match) ---
        for i, (x1, y1, x2, y2, conf) in enumerate(detected_boxes):
            if i in assigned_boxes:
                continue

            person_img = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if person_img.size == 0:
                continue

            embedding, match = None, None
            if self.face_detector is not None:
                aligned_face = _detect_and_align_face(self.face_detector, person_img)
                if aligned_face is not None:
                    embedding, match = self._identify(aligned_face)
                # sem rosto achado dentro da pessoa — não identifica com o corpo todo
            else:
                # Fallback sem YuNet: heurística antiga (terço superior da silhueta)
                bh = max(1, y2 - y1)
                face_y2 = y1 + int(bh * 0.35)
                fallback_img = frame[max(0, y1):min(h, face_y2), max(0, x1):min(w, x2)]
                if fallback_img.size > 0:
                    embedding, match = self._identify(fallback_img)

            new_track = TrackedFace((x1, y1, x2, y2), embedding, match)
            self.tracked_faces[new_track.track_id] = new_track
            # hits=1 na criação — só aparece no HUD/resultado quando confirmado
            # de novo no próximo frame (ver MIN_HITS_TO_DISPLAY), pra não exibir
            # blob falso-positivo isolado (sombra, bueiro) como se fosse pessoa

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
                # Normalizar igual ao índice (ver nota em delta_embedder.FaissIDMap.upsert) —
                # sem isso a distância L2 crua nunca cai dentro de nenhum threshold configurado.
                query_vec = np.array([embedding]).astype('float32')
                faiss.normalize_L2(query_vec)
                D, I = self.index.search(query_vec, 1)
                distance = float(D[0][0])
                probability = _distance_to_probability(distance)
                confidence = _probability_to_confidence(probability)

                match_key = str(int(I[0][0]))
                if distance < self.match_threshold and match_key in self.metadata:
                    match_data = self.metadata[match_key].copy()
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
