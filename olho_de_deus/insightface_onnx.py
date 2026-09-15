"""
insightface_onnx.py — Olho de Deus

Detector SCRFD + reconhecedor ArcFace do InsightFace, rodados direto via
`onnxruntime` (já é dependência do projeto — usada em forensic_sr_engine.py
pro Real-ESRGAN/CodeFormer, nenhuma dependência nova aqui).

Por que existe (2026-09-15, Fase 1 do plano de mesclar técnicas de projetos
maduros): `biometric_processor.py` hoje detecta rosto com YuNet (genérico) e
reconhece com `DeepFace` (que carrega TensorFlow inteiro só pra rodar o
ArcFace) — mas o próprio módulo já cita "SCRFD + ArcFace" como a arquitetura
de referência original (Hailo Community Guide), nunca implementada de fato.
Este módulo implementa essa dupla de verdade, com o modelo `buffalo_sc`
oficial do InsightFace (16MB, explicitamente otimizado pra CCTV — o caso de
uso daqui) — só a técnica de inferência foi reimplementada a partir da
leitura do código-fonte real
(github.com/deepinsight/insightface/python-package/insightface/model_zoo/
scrfd.py + arcface_onnx.py, lidos e confirmados nesta sessão), não a
biblioteca `insightface` inteira (que traz gerência própria de sessão,
cache em `~/.insightface`, download automático — nada disso serve aqui,
onde os 2 arquivos ONNX já estão versionados em `models/`).

Contrato de saída pensado pra plugar direto no gate de qualidade já
existente (`biometric_processor._face_quality_ok`) sem mudar nada lá: os 5
pontos faciais saem na MESMA ordem que o YuNet já usa (olho direito, olho
esquerdo, nariz, boca-direita, boca-esquerda) — é a ordem que o template
`_ARCFACE_112_TEMPLATE` (idêntico ao `arcface_dst` do InsightFace,
confirmado valor por valor) já espera.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
import onnxruntime

MODELO_DIR = Path(__file__).parent / "models" / "insightface_buffalo_sc"
DET_MODEL_PATH = MODELO_DIR / "det_500m.onnx"
REC_MODEL_PATH = MODELO_DIR / "w600k_mbf.onnx"

# Limiares copiados do próprio scrfd.py (self.nms_thresh=0.4, self.det_thresh=0.5
# são os padrões da lib original — não inventados aqui).
DET_THRESH = 0.5
NMS_THRESH = 0.4

# Pré-processamento do detector (scrfd.py:580-581) — mean/std ASSIMÉTRICOS
# (127.5 / 128.0, não os dois iguais), confirmado lendo o código-fonte real,
# não documentação resumida.
DET_INPUT_MEAN = 127.5
DET_INPUT_STD = 128.0

# Pré-processamento do reconhecedor (arcface_onnx.py:38-42) — modelos
# buffalo_* (ONNX exportado, não mxnet) caem no ramo "else": mean=std=127.5.
REC_INPUT_MEAN = 127.5
REC_INPUT_STD = 127.5
REC_INPUT_SIZE = 112


def distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """Decodifica previsão de distância (l,t,r,b) em bbox — cópia fiel de
    scrfd.py:distance2bbox (matemática simples, não há "jeito nosso" de
    fazer diferente sem estar errado)."""
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """Decodifica previsão de distância em 5 pontos faciais — cópia fiel de
    scrfd.py:distance2kps."""
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, i % 2] + distance[:, i]
        py = points[:, i % 2 + 1] + distance[:, i + 1]
        preds.append(px)
        preds.append(py)
    return np.stack(preds, axis=-1)


def _nms(dets: np.ndarray, thresh: float) -> list:
    """NMS clássico — cópia fiel de scrfd.py:nms."""
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = np.argsort(-scores, kind='stable')
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= thresh)[0]
        order = order[inds + 1]
    return keep


class _ScrfdDetector:
    """Detector de rosto SCRFD (det_500m, pacote buffalo_sc) — 3 níveis de
    FPN (stride 8/16/32), 2 âncoras por posição, com key points — mesma
    forma de saída confirmada rodando o modelo (9 tensores: 3x score,
    3x bbox, 3x kps)."""

    FEAT_STRIDE_FPN = [8, 16, 32]
    NUM_ANCHORS = 2

    def __init__(self, model_path: Path):
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self._center_cache: Dict[Any, np.ndarray] = {}

    def _forward(self, det_img: np.ndarray, threshold: float):
        blob = cv2.dnn.blobFromImage(
            det_img, 1.0 / DET_INPUT_STD, (det_img.shape[1], det_img.shape[0]),
            (DET_INPUT_MEAN, DET_INPUT_MEAN, DET_INPUT_MEAN), swapRB=True,
        )
        net_outs = self.session.run(self.output_names, {self.input_name: blob})

        input_height, input_width = blob.shape[2], blob.shape[3]
        fmc = 3
        scores_list, bboxes_list, kpss_list = [], [], []
        for idx, stride in enumerate(self.FEAT_STRIDE_FPN):
            scores = net_outs[idx]
            bbox_preds = net_outs[idx + fmc] * stride
            kps_preds = net_outs[idx + fmc * 2] * stride

            height, width = input_height // stride, input_width // stride
            key = (height, width, stride)
            anchor_centers = self._center_cache.get(key)
            if anchor_centers is None:
                anchor_centers = np.stack(
                    np.mgrid[:height, :width][::-1], axis=-1
                ).astype(np.float32)
                anchor_centers = (anchor_centers * stride).reshape((-1, 2))
                anchor_centers = np.stack(
                    [anchor_centers] * self.NUM_ANCHORS, axis=1
                ).reshape((-1, 2))
                if len(self._center_cache) < 100:
                    self._center_cache[key] = anchor_centers

            pos_inds = np.where(scores.ravel() >= threshold)[0]
            bboxes = distance2bbox(anchor_centers, bbox_preds)
            kpss = distance2kps(anchor_centers, kps_preds).reshape(
                (kps_preds.shape[0], -1, 2)
            )
            scores_list.append(scores.ravel()[pos_inds])
            bboxes_list.append(bboxes[pos_inds])
            kpss_list.append(kpss[pos_inds])
        return scores_list, bboxes_list, kpss_list

    # Resolução fixa pra inferência — achado testando com imagem real
    # (2026-09-15): alimentar o modelo com resolução arbitrária faz o
    # onnxruntime avisar "shape mismatch" e a grade de âncoras
    # (height = input_height // stride) parar de bater com o tensor de
    # saída de verdade, porque o grafo do modelo foi exportado assumindo
    # dimensão múltipla de 32 (maior stride). scrfd.py::_detect_candidates
    # resolve isso com letterbox (redimensiona preservando proporção +
    # preenche com zero até um quadrado fixo) antes de rodar — replicado
    # aqui, não inventado.
    INPUT_SIZE = 640

    def detect(self, img: np.ndarray, threshold: float = DET_THRESH,
               nms_thresh: float = NMS_THRESH) -> Optional[Dict[str, Any]]:
        """Detecta o rosto de maior confiança em `img` (um recorte de
        pessoa, mesmo input que YuNet recebe hoje). Retorna None se nada
        passar do limiar — mesmo contrato de `cv2.FaceDetectorYN.detect`."""
        h, w = img.shape[:2]
        if h < 10 or w < 10:
            return None

        im_ratio = float(h) / w
        if im_ratio > 1.0:
            new_height = self.INPUT_SIZE
            new_width = int(new_height / im_ratio)
        else:
            new_width = self.INPUT_SIZE
            new_height = int(new_width * im_ratio)
        det_scale = float(new_height) / h
        resized = cv2.resize(img, (new_width, new_height))
        det_img = np.zeros((self.INPUT_SIZE, self.INPUT_SIZE, 3), dtype=np.uint8)
        det_img[:new_height, :new_width, :] = resized

        scores_list, bboxes_list, kpss_list = self._forward(det_img, threshold)
        if sum(s.size for s in scores_list) == 0:
            return None

        scores = np.concatenate(scores_list)
        bboxes = np.concatenate(bboxes_list) / det_scale
        kpss = np.concatenate(kpss_list) / det_scale
        order = np.argsort(-scores, kind='stable')
        pre_det = np.hstack([bboxes, scores[:, None]]).astype(np.float32)[order]
        kpss = kpss[order]

        keep = _nms(pre_det, nms_thresh)
        if not keep:
            return None
        melhor = keep[0]  # já ordenado por confiança antes do NMS
        return {
            "bbox": pre_det[melhor, :4],
            "det_score": float(pre_det[melhor, 4]),
            "landmarks": kpss[melhor].astype(np.float32),  # (5,2), mesma ordem do YuNet
        }


class _ArcFaceRecognizer:
    """Reconhecedor ArcFace (w600k_mbf, MobileFaceNet — variante leve do
    buffalo_sc) — recebe rosto JÁ ALINHADO 112x112, devolve embedding 512d."""

    def __init__(self, model_path: Path):
        self.session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def embed(self, aligned_face_bgr: np.ndarray) -> np.ndarray:
        blob = cv2.dnn.blobFromImage(
            aligned_face_bgr, 1.0 / REC_INPUT_STD,
            (REC_INPUT_SIZE, REC_INPUT_SIZE),
            (REC_INPUT_MEAN, REC_INPUT_MEAN, REC_INPUT_MEAN), swapRB=True,
        )
        out = self.session.run([self.output_name], {self.input_name: blob})[0]
        return out.flatten()


_detector: Optional[_ScrfdDetector] = None
_recognizer: Optional[_ArcFaceRecognizer] = None


def _get_detector() -> _ScrfdDetector:
    global _detector
    if _detector is None:
        _detector = _ScrfdDetector(DET_MODEL_PATH)
    return _detector


def _get_recognizer() -> _ArcFaceRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = _ArcFaceRecognizer(REC_MODEL_PATH)
    return _recognizer


def detecta_rosto_scrfd(crop: np.ndarray) -> Optional[Dict[str, Any]]:
    """Ponto de entrada público — detecta o melhor rosto num recorte de
    pessoa. Retorna {"landmarks": (5,2) float32, "det_score": float,
    "bbox": (4,) float32} ou None."""
    return _get_detector().detect(crop)


def embedding_arcface_onnx(aligned_face_bgr: np.ndarray) -> np.ndarray:
    """Ponto de entrada público — embedding 512d de um rosto já alinhado
    112x112 (mesmo formato que `DeepFace.represent(..., detector_backend=
    "skip")` recebe hoje)."""
    return _get_recognizer().embed(aligned_face_bgr)
