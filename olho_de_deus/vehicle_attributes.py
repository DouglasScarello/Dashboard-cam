#!/usr/bin/env python3
"""
vehicle_attributes.py — Olho de Deus

Classifica cor e tipo de carroceria do veículo via CLIP zero-shot — mesma
técnica/modelo já usado em intelligence/classify_images.py pra classificar
foto de rosto/tatuagem/documento, só que com rótulos de veículo. Pedido do
usuário em 2026-09-12: descrever modelo (aproximado, por tipo de carroceria
— marca/modelo exato precisaria de um classificador dedicado, fora do
escopo aqui) e cor junto com a placa lida.

Rodado só quando uma placa FECHA consenso (não a cada frame) — cor/
carroceria não mudam frame a frame, então não faz sentido gastar CLIP
repetidamente no mesmo veículo.
"""
import logging
from typing import Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("vehicle_attributes")

COLOR_LABELS = [
    "a white vehicle", "a black vehicle", "a gray or silver vehicle",
    "a red vehicle", "a blue vehicle", "a green vehicle",
    "a yellow vehicle", "a brown or beige vehicle", "an orange vehicle",
]
_COLOR_PT = {
    "a white vehicle": "branco", "a black vehicle": "preto",
    "a gray or silver vehicle": "cinza/prata", "a red vehicle": "vermelho",
    "a blue vehicle": "azul", "a green vehicle": "verde",
    "a yellow vehicle": "amarelo", "a brown or beige vehicle": "marrom/bege",
    "an orange vehicle": "laranja",
}

BODY_LABELS = [
    "a sedan car", "an SUV", "a pickup truck", "a van or minivan",
    "a large cargo truck or lorry", "a bus", "a motorcycle or scooter",
    "a motorized tricycle or auto rickshaw",
]
_BODY_PT = {
    "a sedan car": "sedã", "an SUV": "SUV", "a pickup truck": "picape",
    "a van or minivan": "van/minivan", "a large cargo truck or lorry": "caminhão",
    "a bus": "ônibus", "a motorcycle or scooter": "moto/scooter",
    "a motorized tricycle or auto rickshaw": "triciclo motorizado",
}


class VehicleAttributeClassifier:
    """Carrega o modelo CLIP sob demanda (lazy) — igual ao padrão já usado
    em ForensicALPR pro EasyOCR, evita custo de import/carga se nunca for
    chamado."""

    def __init__(self):
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device = "cpu"
        self._color_tokens = None
        self._body_tokens = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        import open_clip
        import torch
        # Mesmo checkpoint já usado em intelligence/classify_images.py —
        # reaproveita o peso já baixado em vez de puxar outro.
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32-quickgelu", pretrained="openai"
        )
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")
        with torch.no_grad():
            self._color_tokens = self._model.encode_text(self._tokenizer(COLOR_LABELS))
            self._color_tokens /= self._color_tokens.norm(dim=-1, keepdim=True)
            self._body_tokens = self._model.encode_text(self._tokenizer(BODY_LABELS))
            self._body_tokens /= self._body_tokens.norm(dim=-1, keepdim=True)

    def classify(self, vehicle_img_bgr: np.ndarray) -> Tuple[Optional[str], Optional[str], float, float]:
        """Retorna (cor_pt, carroceria_pt, confianca_cor, confianca_carroceria).
        Nunca lança — em caso de erro, devolve (None, None, 0.0, 0.0) e loga."""
        try:
            import torch
            from PIL import Image

            self._ensure_loaded()
            rgb = cv2.cvtColor(vehicle_img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            image_input = self._preprocess(pil_img).unsqueeze(0)

            with torch.no_grad():
                image_features = self._model.encode_image(image_input)
                image_features /= image_features.norm(dim=-1, keepdim=True)

                # *100.0: mesmo fator de temperatura usado em
                # intelligence/classify_images.py (e no exemplo oficial da
                # OpenAI) — sem isso o softmax fica achatado demais (10-15%
                # pra tudo) mesmo quando a classificação em si está certa.
                color_sims = (100.0 * image_features @ self._color_tokens.T).squeeze(0)
                body_sims = (100.0 * image_features @ self._body_tokens.T).squeeze(0)

                color_probs = color_sims.softmax(dim=0)
                body_probs = body_sims.softmax(dim=0)

                color_idx = int(color_probs.argmax())
                body_idx = int(body_probs.argmax())

            color_pt = _COLOR_PT[COLOR_LABELS[color_idx]]
            body_pt = _BODY_PT[BODY_LABELS[body_idx]]
            return color_pt, body_pt, float(color_probs[color_idx]), float(body_probs[body_idx])
        except Exception as e:
            log.warning(f"Falha ao classificar atributos do veículo: {e}")
            return None, None, 0.0, 0.0


# Instância global compartilhada — mesmo padrão do alpr_engine em
# forensic_sr_engine.py, evita recarregar o modelo a cada chamada.
vehicle_attribute_classifier = VehicleAttributeClassifier()
