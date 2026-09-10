#!/usr/bin/env python3
"""
person_reid.py — Olho de Deus

Re-identificação de pessoa por aparência (roupa/porte físico), pra reconhecer
a MESMA pessoa passando por câmeras diferentes quando o rosto não está visível
(de costas, longe, ângulo ruim) — complementa o reconhecimento facial
(biometric_processor.py), não substitui.

Usa OSNet (Torchreid) — rede pequena (2.2M parâmetros), roda bem em CPU.

Pesos reais de ReID (não ImageNet genérico): `models/osnet_x1_0_market1501.pth`,
treinado no dataset Market-1501 (pessoas fotografadas por 6 câmeras reais de
um campus) — rank-1 94.2%, mAP 82.6% (número oficial do autor do OSNet).
Baixado de https://kaiyangzhou.github.io/deep-person-reid/MODEL_ZOO.html.

Uso:
    from person_reid import PersonReID
    reid = PersonReID()
    vec_a = reid.extract(crop_pessoa_camera_a)   # np.ndarray BGR (OpenCV)
    vec_b = reid.extract(crop_pessoa_camera_b)
    similaridade = reid.cosine_similarity(vec_a, vec_b)  # 1.0 = idêntico
"""
from pathlib import Path

import numpy as np
import torch
import torchreid

DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "models" / "osnet_x1_0_market1501.pth"


class PersonReID:
    def __init__(self, model_name: str = "osnet_x1_0", model_path: str = str(DEFAULT_WEIGHTS), device: str = "cpu"):
        self.extractor = torchreid.utils.FeatureExtractor(
            model_name=model_name, model_path=model_path, device=device
        )

    def extract(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Recebe um crop de pessoa (array BGR do OpenCV) e devolve o embedding (512-D)."""
        # FeatureExtractor aceita array numpy diretamente (RGB) além de caminho de arquivo
        crop_rgb = crop_bgr[:, :, ::-1]
        feat = self.extractor([crop_rgb])
        vec = feat.cpu().numpy()[0]
        return vec / (np.linalg.norm(vec) + 1e-8)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))


if __name__ == "__main__":
    import cv2
    import sys

    if len(sys.argv) != 3:
        print("Uso: python3 person_reid.py <imagem_pessoa_a> <imagem_pessoa_b>")
        sys.exit(1)

    reid = PersonReID()
    img_a = cv2.imread(sys.argv[1])
    img_b = cv2.imread(sys.argv[2])
    vec_a = reid.extract(img_a)
    vec_b = reid.extract(img_b)
    sim = reid.cosine_similarity(vec_a, vec_b)
    print(f"Similaridade: {sim:.3f} (1.0 = mesma pessoa/roupa idêntica, ~0 = totalmente diferente)")
