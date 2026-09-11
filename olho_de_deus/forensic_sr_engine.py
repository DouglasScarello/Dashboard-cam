#!/usr/bin/env python3
"""
===============================================================================
OLHO DE DEUS — MÓDULO FORENSE DE SUPER-RESOLUÇÃO & APRIMORAMENTO DE ROIS
===============================================================================
Implementação completa:
  1. Restauração de Movimento: Wiener Deconvolution & Richardson-Lucy
  2. Binarização & Deskewing: Sauvola Adaptativo, Homografia 4-pontos, Black-Hat
  3. Super-Resolução Neural: OpenCV dnn_superres (ESPCN/EDSR) + Lanczos-4 com Unsharp
  4. Avaliação de Qualidade Forense: Variância do Laplaciano, Gradiente Brenner, Entropia
  5. Endpoints FastAPI: /api/forensic/enhance-roi e /api/forensic/license-plate
===============================================================================
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import os
import re
import time
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from plate_formats import get_format as get_plate_format


# ─────────────────────────────────────────────────────────────────────────────
# 1. PROCESSAMENTO DE SINAIS & DESCONVOLUÇÃO FORENSE (WIENER & RICHARDSON-LUCY)
# ─────────────────────────────────────────────────────────────────────────────

class MotionDeblurEngine:
    """Motor de restauração de desfoque de movimento linear (Motion Blur)."""

    @staticmethod
    def generate_motion_psf(length: int = 15, angle_deg: float = 0.0) -> np.ndarray:
        """
        Gera a Point Spread Function (PSF) para movimento linear.
        length: comprimento do arrasto em pixels
        angle_deg: direção do movimento em graus (0° = horizontal)
        """
        if length <= 1:
            return np.ones((1, 1), dtype=np.float32)

        length = int(length)
        psf = np.zeros((length, length), dtype=np.float32)
        center = (length - 1) / 2.0
        angle_rad = np.deg2rad(angle_deg)

        dx = np.cos(angle_rad)
        dy = np.sin(angle_rad)

        for i in range(length):
            offset = i - center
            x = int(round(center + offset * dx))
            y = int(round(center - offset * dy))
            if 0 <= x < length and 0 <= y < length:
                psf[y, x] = 1.0

        total = psf.sum()
        return psf / (total if total > 0 else 1.0)

    @classmethod
    def wiener_deconvolution(
        cls,
        image_gray: np.ndarray,
        psf: np.ndarray,
        nsr: float = 0.01
    ) -> np.ndarray:
        """
        Desconvolução de Wiener 2D no domínio da frequência.
        W(u, v) = H*(u, v) / (|H(u, v)|^2 + NSR)
        """
        img_h, img_w = image_gray.shape[:2]
        psf_h, psf_w = psf.shape[:2]

        # Padding da PSF para o tamanho da imagem
        psf_padded = np.zeros((img_h, img_w), dtype=np.float32)
        r_start = (img_h - psf_h) // 2
        c_start = (img_w - psf_w) // 2
        psf_padded[r_start:r_start + psf_h, c_start:c_start + psf_w] = psf
        psf_padded = np.fft.ifftshift(psf_padded)

        # FFT 2D
        img_fft = np.fft.fft2(image_gray.astype(np.float32) / 255.0)
        psf_fft = np.fft.fft2(psf_padded)

        # Filtro de Wiener
        psf_conj = np.conj(psf_fft)
        wiener_filter = psf_conj / (np.abs(psf_fft) ** 2 + nsr)
        deblurred_fft = img_fft * wiener_filter

        # IFFT 2D
        deblurred = np.abs(np.fft.ifft2(deblurred_fft))
        deblurred = np.clip(deblurred * 255.0, 0, 255).astype(np.uint8)
        return deblurred

    @classmethod
    def richardson_lucy(
        cls,
        image_gray: np.ndarray,
        psf: np.ndarray,
        iterations: int = 20
    ) -> np.ndarray:
        """
        Desconvolução Iterativa de Richardson-Lucy sob modelo de ruído Poisson.
        f^(t+1) = f^(t) * [ (g / (f^(t) * h)) * h^T ]
        """
        g = image_gray.astype(np.float32) / 255.0
        g = np.maximum(g, 1e-6)
        f_est = np.copy(g)
        psf_flipped = np.flip(np.flip(psf, 0), 1)

        for _ in range(max(1, iterations)):
            # Convolução com PSF
            reprojected = cv2.filter2D(f_est, -1, psf, borderType=cv2.BORDER_REFLECT)
            reprojected = np.maximum(reprojected, 1e-6)

            # Razão entre imagem observada e estimada
            relative_blur = g / reprojected

            # Convolução com PSF invertida e atualização multiplicativa
            error_correction = cv2.filter2D(relative_blur, -1, psf_flipped, borderType=cv2.BORDER_REFLECT)
            f_est *= error_correction
            f_est = np.clip(f_est, 0.0, 1.0)

        return (f_est * 255.0).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DESKEWING HOMOGRÁFICO & BINARIZAÇÃO ADAPTATIVA (SAUVOLA / CLAHE)
# ─────────────────────────────────────────────────────────────────────────────

class ForensicPlateEnhancer:
    """Pipeline geométrico e radiométrico especializado em placas veiculares."""

    MERCOSUL_REGEX = re.compile(r"^[A-Z]{3}[0-9][A-Z][0-9]{2}$")
    ANTIGO_REGEX = re.compile(r"^[A-Z]{3}[0-9]{4}$")

    @staticmethod
    def order_quad_points(pts: np.ndarray) -> np.ndarray:
        """Ordena 4 pontos em: Top-Left, Top-Right, Bottom-Right, Bottom-Left."""
        rect = np.zeros((4, 2), dtype=np.float32)
        pts = pts.reshape(4, 2)

        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # TL
        rect[2] = pts[np.argmax(s)]  # BR

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # TR
        rect[3] = pts[np.argmax(diff)]  # BL

        return rect

    @classmethod
    def auto_deskew_homography(
        cls,
        image: np.ndarray,
        target_size: Tuple[int, int] = (400, 130)
    ) -> Tuple[np.ndarray, bool]:
        """
        Detecta automaticamente o quadrilátero da placa e aplica homografia retificadora.
        target_size: (largura, altura) padrão Mercosul (400x130).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 200)

        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

        target_w, target_h = target_size
        dst_pts = np.array([
            [0, 0],
            [target_w - 1, 0],
            [target_w - 1, target_h - 1],
            [0, target_h - 1]
        ], dtype=np.float32)

        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)

            if len(approx) == 4:
                src_pts = cls.order_quad_points(approx.astype(np.float32))
                M = cv2.getPerspectiveTransform(src_pts, dst_pts)
                rectified = cv2.warpPerspective(image, M, (target_w, target_h), flags=cv2.INTER_LANCZOS4)
                return rectified, True

        # Fallback: resize Lanczos com proporção canônica
        rectified = cv2.resize(image, target_size, interpolation=cv2.INTER_LANCZOS4)
        return rectified, False

    @staticmethod
    def sauvola_binarization(
        image_gray: np.ndarray,
        window_size: int = 25,
        k: float = 0.3,
        r: float = 128.0
    ) -> np.ndarray:
        """
        Binarização de Sauvola vetorizada com complexidade O(1) via boxFilter.
        T = m * (1 + k * (s / r - 1))
        """
        if window_size % 2 == 0:
            window_size += 1

        img_f = image_gray.astype(np.float32)
        mean = cv2.boxFilter(img_f, cv2.CV_32F, (window_size, window_size), borderType=cv2.BORDER_REFLECT)
        sq_mean = cv2.boxFilter(img_f ** 2, cv2.CV_32F, (window_size, window_size), borderType=cv2.BORDER_REFLECT)
        variance = np.maximum(sq_mean - mean ** 2, 0)
        std_dev = np.sqrt(variance)

        threshold = mean * (1.0 + k * ((std_dev / r) - 1.0))
        binary = np.zeros_like(image_gray, dtype=np.uint8)
        binary[img_f >= threshold] = 255
        return binary

    @staticmethod
    def apply_blackhat_contrast(image_gray: np.ndarray, kernel_size: int = 15) -> np.ndarray:
        """Realce morfológico Black-Hat para destacar caracteres pretos em chapa clara."""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        blackhat = cv2.morphologyEx(image_gray, cv2.MORPH_BLACKHAT, kernel)
        enhanced = cv2.add(image_gray, blackhat)
        return enhanced


# ─────────────────────────────────────────────────────────────────────────────
# 3. MOTOR DE SUPER-RESOLUÇÃO NEURAL & CLÁSSICA (LANCZOS-4 & UNSHARP)
# ─────────────────────────────────────────────────────────────────────────────

class NeuralSuperResolution:
    """Motor de Super-Resolução: Real-ESRGAN real via ONNX Runtime (não mais
    um caminho morto que nunca era chamado — achado de auditoria
    2026-08-29), com fallback determinístico Lanczos-4 quando o modelo não
    carrega ou a imagem é grande demais pra rodar em tempo hábil na CPU.

    Pesos: `realesr-general-x4v3.onnx` (variante compacta, recomendada pra
    CPU pela pesquisa de 2026-08-29), de Heliosoph/realesrgan-onnx no
    Hugging Face — BSD-3-Clause (uso comercial permitido), export da rede
    oficial de xinntao/Real-ESRGAN. Rede fixa em 4x; pra outros
    `scale_factor` o resultado 4x real é redimensionado pro tamanho alvo.
    """

    # Acima disso (pixels de entrada), inferência ONNX em CPU pode levar
    # muitos segundos — cai pro fallback Lanczos em vez de travar a resposta
    # HTTP. Calibrado pra crops forenses (rosto/placa), não frames inteiros.
    MAX_INPUT_PIXELS = 400 * 400

    def __init__(self, scale: int = 4, device: str = "cpu",
                 onnx_path: Optional[str] = None):
        self.scale = scale
        self.device = device
        self._onnx_path = onnx_path or str(Path(__file__).resolve().parent / "models" / "realesr-general-x4v3.onnx")
        self._onnx_session = None
        self._onnx_load_failed = False
        # Mantido só por compatibilidade com chamadores antigos — o caminho
        # real agora é o ONNX acima, não o OpenCV dnn_superres (que nunca
        # tinha peso nenhum carregado, ver achado de auditoria).
        self._sr_dnn = None
        self._loaded_model_name = ""

    def _get_onnx_session(self):
        if self._onnx_session is not None or self._onnx_load_failed:
            return self._onnx_session
        try:
            import onnxruntime as ort
            if not os.path.exists(self._onnx_path):
                raise FileNotFoundError(self._onnx_path)
            self._onnx_session = ort.InferenceSession(self._onnx_path, providers=["CPUExecutionProvider"])
        except Exception as e:
            log_alpr_error(e)
            self._onnx_load_failed = True
            self._onnx_session = None
        return self._onnx_session

    def _run_real_esrgan(self, img: np.ndarray) -> np.ndarray:
        """Roda a rede real (4x fixo) e devolve BGR uint8."""
        session = self._get_onnx_session()
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = np.transpose(img_rgb, (2, 0, 1))[None, ...]
        out = session.run(None, {"input": inp})[0]
        out_img = np.transpose(out[0], (1, 2, 0))
        out_img = np.clip(out_img, 0.0, 1.0) * 255.0
        return cv2.cvtColor(out_img.astype(np.uint8), cv2.COLOR_RGB2BGR)

    def load_opencv_dnn(self, model_name: str = "espcn", model_path: Optional[str] = None):
        """Mantido por compatibilidade — não é mais o caminho real de SR
        (ver `_run_real_esrgan`). Sem uso nesta classe desde 2026-08-29."""
        try:
            if hasattr(cv2, "dnn_superres"):
                sr = cv2.dnn_superres.DnnSuperResImpl_create()
                if model_path and os.path.exists(model_path):
                    sr.readModel(model_path)
                    sr.setModel(model_name.lower(), self.scale)
                    if self.device == "cuda":
                        sr.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                        sr.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                    self._sr_dnn = sr
                    self._loaded_model_name = model_name
        except Exception:
            self._sr_dnn = None

    def upscale(self, img: np.ndarray, model_name: str = "lanczos") -> Tuple[np.ndarray, str]:
        """Real-ESRGAN real via ONNX Runtime, com fallback Lanczos-4
        honestamente rotulado quando o modelo não roda (não instalado ou
        erro de inferência).

        Se a entrada exceder `MAX_INPUT_PIXELS` (comum quando o usuário
        pede "melhorar" sem zoom antes — o crop vira o frame inteiro da
        câmera, não um recorte pequeno de placa/rosto), a rede real ainda
        roda — só sobre uma versão reduzida da entrada primeiro — em vez de
        desistir da rede neural inteiramente. Achado real desta sessão:
        antes disso, qualquer crop de câmera sem zoom prévio caía sempre no
        Lanczos, e o usuário via isso como "a função parece mock"."""
        h, w = img.shape[:2]
        target_w, target_h = w * self.scale, h * self.scale

        session = self._get_onnx_session()
        if session is not None:
            try:
                net_input = img
                if h * w > self.MAX_INPUT_PIXELS:
                    ratio = (self.MAX_INPUT_PIXELS / float(h * w)) ** 0.5
                    small_w, small_h = max(1, int(w * ratio)), max(1, int(h * ratio))
                    net_input = cv2.resize(img, (small_w, small_h), interpolation=cv2.INTER_AREA)

                real_4x = self._run_real_esrgan(net_input)
                if (real_4x.shape[1], real_4x.shape[0]) != (target_w, target_h):
                    real_4x = cv2.resize(real_4x, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
                return real_4x, "RealESRGAN-x4v3-ONNX"
            except Exception as e:
                log_alpr_error(e)

        # Fallback de alta fidelidade: Lanczos-4 + Unsharp Masking Laplaciano
        # — rotulado como o que é, nunca disfarçado de rede neural.
        upscaled = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
        gaussian = cv2.GaussianBlur(upscaled, (0, 0), 1.5)
        sharpened = cv2.addWeighted(upscaled, 1.35, gaussian, -0.35, 0)
        return sharpened, f"Lanczos4-Sharpened-x{self.scale} (fallback — sem rede neural)"


# ─────────────────────────────────────────────────────────────────────────────
# 3.5 RESTAURAÇÃO FACIAL REAL — CODEFORMER (ONNX)
#
# Substitui o caminho comentado que sempre caía em CLAHE+bilateral simples
# (achado de auditoria: "fidelity_weight nunca tinha efeito real"). Pesos
# de bluefoxcreation/Codeformer-ONNX (export oficial do sczhou/CodeFormer),
# LICENÇA S-LAB 1.0 — NÃO-COMERCIAL. Ok pra portfólio pessoal; não pode ser
# usado se este projeto virar produto comercial sem licenciar separado
# (ver PLANO_CONTINUACAO.md Seção 5.3).
#
# IMPORTANTE (honestidade de produto, não só de código): CodeFormer é um
# modelo GENERATIVO — ele completa detalhe facial plausível a partir de um
# prior aprendido, não reconstrói o rosto real pixel-a-pixel. Pesquisa de
# 2026-08-29 encontrou evidência de que pré-processamento deste tipo pode
# DEGRADAR a confiabilidade de reconhecimento facial forense. Rotular
# sempre como apoio visual investigativo, nunca como prova pericial.
# ─────────────────────────────────────────────────────────────────────────────

class CodeFormerRestorer:
    """Restauração facial real via CodeFormer (ONNX Runtime, CPU)."""

    INPUT_SIZE = 512

    def __init__(self, onnx_path: Optional[str] = None):
        self._onnx_path = onnx_path or str(Path(__file__).resolve().parent / "models" / "codeformer.onnx")
        self._session = None
        self._load_failed = False

    def _get_session(self):
        if self._session is not None or self._load_failed:
            return self._session
        try:
            import onnxruntime as ort
            if not os.path.exists(self._onnx_path):
                raise FileNotFoundError(self._onnx_path)
            self._session = ort.InferenceSession(self._onnx_path, providers=["CPUExecutionProvider"])
        except Exception as e:
            log_alpr_error(e)
            self._load_failed = True
            self._session = None
        return self._session

    def restore(self, img_bgr: np.ndarray, fidelity_weight: float = 0.5) -> Optional[np.ndarray]:
        """Retorna o rosto restaurado (BGR, mesmo tamanho da entrada) ou
        `None` se o modelo não puder rodar — o chamador decide o fallback,
        nunca fingimos sucesso aqui."""
        session = self._get_session()
        if session is None:
            return None
        try:
            h, w = img_bgr.shape[:2]
            face_512 = cv2.resize(img_bgr, (self.INPUT_SIZE, self.INPUT_SIZE), interpolation=cv2.INTER_LANCZOS4)
            rgb = cv2.cvtColor(face_512, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            normalized = (rgb - 0.5) / 0.5  # CodeFormer espera entrada em [-1, 1]
            inp = np.transpose(normalized, (2, 0, 1))[None, ...]
            w_arr = np.array(float(np.clip(fidelity_weight, 0.0, 1.0)), dtype=np.float64)

            y = session.run(["y"], {"x": inp, "w": w_arr})[0]
            out = np.transpose(y[0], (1, 2, 0))
            out = (out * 0.5 + 0.5) * 255.0
            out = np.clip(out, 0, 255).astype(np.uint8)
            out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
            if (w, h) != (self.INPUT_SIZE, self.INPUT_SIZE):
                out_bgr = cv2.resize(out_bgr, (w, h), interpolation=cv2.INTER_LANCZOS4)
            return out_bgr
        except Exception as e:
            log_alpr_error(e)
            return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. AVALIAÇÃO DE QUALIDADE FORENSE
# ─────────────────────────────────────────────────────────────────────────────

class ForensicQualityAssessor:
    """Calcula métricas de nitidez, foco e entropia informacional."""

    @staticmethod
    def compute_laplacian_variance(gray: np.ndarray) -> float:
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def compute_brenner_gradient(gray: np.ndarray) -> float:
        h, w = gray.shape
        if h < 3 or w < 3:
            return 0.0
        diff = gray[:, 2:].astype(np.float64) - gray[:, :-2].astype(np.float64)
        return float(np.mean(diff ** 2))

    @staticmethod
    def compute_shannon_entropy(gray: np.ndarray) -> float:
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
        hist = hist / (hist.sum() + 1e-12)
        non_zeros = hist[hist > 0]
        return float(-np.sum(non_zeros * np.log2(non_zeros)))

    @classmethod
    def evaluate(cls, image: np.ndarray) -> Dict[str, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        return {
            "laplacian_variance": round(cls.compute_laplacian_variance(gray), 2),
            "brenner_gradient": round(cls.compute_brenner_gradient(gray), 2),
            "shannon_entropy": round(cls.compute_shannon_entropy(gray), 3),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4.5 ALPR REAL — DETECÇÃO YOLOv8 + LEITURA EASYOCR (Mercosul)
#
# Substitui o `plate_ocr = "BRA2E19"` hardcoded (achado de auditoria
# 2026-08-29). Duas etapas reais, não simuladas:
#   1. Detecção: YOLOv8n fine-tuned pra placa (pesos MIT de
#      huggingface.co/Koushim/yolov8-license-plate-detection, genérico —
#      detecção transfere razoavelmente entre formatos de placa, mas NÃO
#      foi fine-tuned especificamente em placas Mercosul reais; validar
#      antes de confiar em produção, ver PLANO_CONTINUACAO.md Seção 5.2).
#   2. Leitura: EasyOCR (não PaddleOCR — PaddleOCR precisa de
#      `paddlepaddle`, que não tem wheel pra Python 3.14 neste ambiente;
#      EasyOCR é a alternativa real de 2º lugar da pesquisa, funciona aqui).
# ─────────────────────────────────────────────────────────────────────────────

class ForensicALPR:
    """Pipeline real de detecção + leitura de placa. Modelos carregados sob
    demanda (lazy) — YOLO é rápido de carregar, EasyOCR leva ~20-30s na
    primeira chamada porque baixa/inicializa os pesos de detecção de texto."""

    MERCOSUL_FMT = "LLLNLNN"  # 3 letras, 1 dígito, 1 letra, 2 dígitos
    ANTIGO_FMT = "LLLNNNN"    # 3 letras, 4 dígitos

    # Confusões de OCR mais comuns entre dígito e letra visualmente parecidos.
    DIGIT_TO_LETTER = {"0": "O", "1": "I", "5": "S", "2": "Z", "8": "B", "6": "G"}
    LETTER_TO_DIGIT = {"O": "0", "I": "1", "S": "5", "Z": "2", "B": "8", "G": "6", "Q": "0"}

    # Cache de leitores EasyOCR por conjunto de idiomas (2026-09-11) —
    # compartilhado entre TODAS as instâncias/países, porque cada
    # easyocr.Reader(...) novo custa ~20-30s pra inicializar (baixa/carrega
    # pesos de detecção de texto). Sem isso, alternar país a cada chamada
    # recarregaria o mesmo modelo repetidamente.
    _reader_cache: Dict[Tuple[str, ...], Any] = {}

    def __init__(self, weights_path: str, country: str = "BR"):
        self._weights_path = weights_path
        self._detector = None
        self.country = country.upper()

    def _get_detector(self):
        if self._detector is None:
            from ultralytics import YOLO
            self._detector = YOLO(self._weights_path)
        return self._detector

    def _get_reader(self, langs: Tuple[str, ...]):
        if langs not in self._reader_cache:
            import easyocr
            self._reader_cache[langs] = easyocr.Reader(list(langs), gpu=False, verbose=False)
        return self._reader_cache[langs]

    def detect_plate_bbox(self, image_bgr: np.ndarray, conf_threshold: float = 0.25) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[float]]:
        """Localiza a placa de verdade dentro do crop recebido — antes disso
        o pipeline tratava o crop inteiro como se já fosse a placa (achado de
        auditoria). Sem detecção acima do threshold, retorna (None, None) e
        o chamador decide se cai pro crop inteiro como fallback honesto."""
        try:
            detector = self._get_detector()
            results = detector.predict(image_bgr, verbose=False, conf=conf_threshold)
            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return None, None
            best_idx = int(boxes.conf.argmax())
            x1, y1, x2, y2 = boxes.xyxy[best_idx].cpu().numpy().astype(int)
            confidence = float(boxes.conf[best_idx])
            h, w = image_bgr.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None, None
            return (x1, y1, x2, y2), confidence
        except Exception as e:
            log_alpr_error(e)
            return None, None

    def _correct_for_format(self, raw: str, fmt: str) -> str:
        """Corrige caractere-por-posição contra o template fixo do formato
        (ex: posição de letra que o OCR leu como dígito vira a letra visual
        mais provável, e vice-versa) — não é find-and-replace cego, respeita
        a posição exigida por cada formato real de placa brasileira."""
        raw = raw.upper()
        if len(raw) != len(fmt):
            return raw
        out = []
        for ch, slot in zip(raw, fmt):
            if slot == "L" and ch.isdigit():
                out.append(self.DIGIT_TO_LETTER.get(ch, ch))
            elif slot == "N" and ch.isalpha():
                out.append(self.LETTER_TO_DIGIT.get(ch, ch))
            else:
                out.append(ch)
        return "".join(out)

    def read_plate(self, image_bgr: np.ndarray, country: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """OCR real via EasyOCR + validação contra o formato oficial do país
        (ver plate_formats.py — pesquisado em 2026-09-11 depois de descobrir,
        testando com câmera japonesa, que o motor só reconhecia formato
        brasileiro). `country` sobrescreve o país da instância pra essa
        chamada só (útil quando o mesmo processo lê placas de câmeras de
        países diferentes). Retorna (texto, formato, confiança) ou
        (None, None, None) se nada plausível foi lido — nunca inventa placa.

        Correção posicional dígito↔letra (_correct_for_format) só se aplica
        pro Brasil — é conhecimento específico de como o CONTRAN define slot
        fixo de letra/dígito; pra outros países só validamos a regex crua."""
        fmt = get_plate_format(country or self.country)
        is_pure_latin = fmt.script == "latin"

        try:
            reader = self._get_reader(tuple(fmt.ocr_langs))
            # Allowlist restrito só faz sentido pra alfabeto puramente latino —
            # pra kanji/thai/hangul/han ele bloquearia o próprio script que
            # queremos ler.
            kwargs = {"allowlist": "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"} if is_pure_latin else {}
            results = reader.readtext(image_bgr, detail=1, **kwargs)
        except Exception as e:
            log_alpr_error(e)
            return None, None, None

        if not results:
            return None, None, None

        # Concatena os fragmentos de texto lidos (o OCR às vezes separa a
        # placa em 2 blocos) ordenados da esquerda pra direita.
        results_sorted = sorted(results, key=lambda r: r[0][0][0])
        raw_text = "".join(r[1] for r in results_sorted).upper()
        if is_pure_latin:
            raw_text = re.sub(r"[^A-Z0-9]", "", raw_text)
        avg_conf = float(np.mean([r[2] for r in results_sorted]))

        if self.country == "BR" and country is None:
            # Caminho original — 2 sub-formatos brasileiros com correção
            # posicional, mantido idêntico ao comportamento de antes.
            for fmt_name, fmt_template, regex in (
                ("MERCOSUL", self.MERCOSUL_FMT, ForensicPlateEnhancer.MERCOSUL_REGEX),
                ("ANTIGO", self.ANTIGO_FMT, ForensicPlateEnhancer.ANTIGO_REGEX),
            ):
                if len(raw_text) != len(fmt_template):
                    continue
                corrected = self._correct_for_format(raw_text, fmt_template)
                if regex.match(corrected):
                    return corrected, fmt_name, round(avg_conf, 3)
        elif fmt.regex and fmt.regex.match(raw_text):
            return raw_text, fmt.country_code, round(avg_conf, 3)

        # Nada bateu com um formato oficial — reporta o texto cru como
        # "candidato incerto" em vez de descartar silenciosamente ou de
        # forçar num formato que não confere.
        return raw_text or None, "INCERTO" if raw_text else None, round(avg_conf, 3) if raw_text else None


def log_alpr_error(e: Exception) -> None:
    import logging
    logging.getLogger("ForensicALPR").warning(f"Falha no pipeline de ALPR: {type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. SCHEMAS PYDANTIC & ROUTER FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

class EnhanceROIRequest(BaseModel):
    image_base64: str = Field(..., description="Imagem ou crop do ROI em Base64")
    roi_type: str = Field("plate", description="Tipo do ROI: 'plate', 'face', 'general'")
    scale_factor: int = Field(4, ge=1, le=8, description="Fator de Super-Resolução (2x, 4x, 8x)")
    apply_deskew: bool = Field(True, description="Executa retificação homográfica de perspectiva")
    deblur_method: str = Field("none", description="Método de deblur: 'wiener', 'richardson_lucy', 'none'")
    motion_length: int = Field(15, ge=1, le=100, description="Arrasto estimado do movimento em pixels")
    motion_angle: float = Field(0.0, ge=-180.0, le=180.0, description="Ângulo do movimento em graus")
    wiener_nsr: float = Field(0.01, ge=0.0001, le=1.0, description="NSR para filtro de Wiener")
    rl_iterations: int = Field(20, ge=1, le=100, description="Iterações Richardson-Lucy")
    binarization: str = Field("sauvola", description="Binarização: 'sauvola', 'otsu', 'none'")
    sauvola_k: float = Field(0.3, ge=0.05, le=0.9, description="Constante k do algoritmo Sauvola")
    fidelity_weight: float = Field(0.5, ge=0.0, le=1.0, description="CodeFormer: 0=máxima qualidade/alucinação, 1=máxima fidelidade ao original")


class ForensicAnalysisResponse(BaseModel):
    status: str
    roi_type: str
    model_used: str
    original_dimensions: Tuple[int, int]
    enhanced_dimensions: Tuple[int, int]
    processing_time_ms: float
    sha256_original: str
    sha256_enhanced: str
    quality_metrics_original: Dict[str, float]
    quality_metrics_enhanced: Dict[str, float]
    plate_ocr_candidate: Optional[str] = None
    plate_format: Optional[str] = None
    plate_ocr_confidence: Optional[float] = None
    plate_bbox_detected: bool = False
    plate_detection_confidence: Optional[float] = None
    enhanced_image_base64: str
    binary_image_base64: Optional[str] = None
    timestamp_utc: str


sr_engine = NeuralSuperResolution(scale=4)
deblur_engine = MotionDeblurEngine()
plate_enhancer = ForensicPlateEnhancer()
quality_assessor = ForensicQualityAssessor()
alpr_engine = ForensicALPR(weights_path=str(Path(__file__).resolve().parent / "models" / "best.pt"))
face_restorer = CodeFormerRestorer()

forensic_sr_router = APIRouter(prefix="/api/forensic", tags=["Forensic Super-Resolution & ALPR"])


def decode_base64_image(b64_str: str) -> np.ndarray:
    """Converte string Base64 para ndarray BGR do OpenCV."""
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_str)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Falha na decodificação do buffer de imagem.")
        return img
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 inválido: {str(e)}")


def encode_image_base64(img: np.ndarray, ext: str = ".png") -> str:
    """Codifica imagem OpenCV para Base64 data URL."""
    success, buffer = cv2.imencode(ext, img)
    if not success:
        return ""
    return f"data:image/{ext[1:]};base64," + base64.b64encode(buffer).decode("utf-8")


@forensic_sr_router.post("/enhance-roi", response_model=ForensicAnalysisResponse)
async def enhance_roi(payload: EnhanceROIRequest):
    """
    Endpoint pericial para aprimoramento de ROIs (placas, rostos e detalhes).
    Aplica cadeia de restauração: Deblur -> SR -> Contraste -> Métricas de Qualidade.
    """
    t0 = time.time()
    img_orig = decode_base64_image(payload.image_base64)
    h_orig, w_orig = img_orig.shape[:2]
    sha256_orig = hashlib.sha256(img_orig.tobytes()).hexdigest().upper()
    metrics_orig = quality_assessor.evaluate(img_orig)

    processed = img_orig.copy()

    # 0. Detecção real da placa dentro do crop recebido (YOLOv8) — antes
    # disso, o crop inteiro era tratado como se já fosse a placa (achado de
    # auditoria 2026-08-29). Sem detecção confiável, cai pro crop inteiro
    # como fallback (mesmo comportamento de antes), mas isso fica registrado
    # em `plate_bbox_detected=False` na resposta, não escondido.
    plate_bbox = None
    plate_detect_conf = None
    if payload.roi_type == "plate":
        plate_bbox, plate_detect_conf = alpr_engine.detect_plate_bbox(processed)
        if plate_bbox:
            x1, y1, x2, y2 = plate_bbox
            processed = processed[y1:y2, x1:x2]

    # 1. Retificação de Perspectiva (se habilitado) — só quando há uma
    # detecção de placa confiável pra guiar a retificação. O algoritmo de
    # homografia assume um contorno de placa real pra corrigir; aplicado
    # sobre um crop sem detecção (fallback) ele pode DEGRADAR a imagem a
    # ponto de quebrar o OCR depois (confirmado em teste: leitura que
    # funcionava direto no crop original virava ilegível após o deskew
    # sem bbox real por trás).
    if payload.apply_deskew and payload.roi_type == "plate" and plate_bbox is not None:
        processed, _ = plate_enhancer.auto_deskew_homography(processed, target_size=(400, 130))

    # 2. Desconvolução de Movimento (se habilitado)
    if payload.deblur_method in ["wiener", "richardson_lucy"]:
        psf = deblur_engine.generate_motion_psf(payload.motion_length, payload.motion_angle)
        if processed.ndim == 3:
            lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            if payload.deblur_method == "wiener":
                l_deblurred = deblur_engine.wiener_deconvolution(l_ch, psf, nsr=payload.wiener_nsr)
            else:
                l_deblurred = deblur_engine.richardson_lucy(l_ch, psf, iterations=payload.rl_iterations)
            processed = cv2.cvtColor(cv2.merge([l_deblurred, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
        else:
            if payload.deblur_method == "wiener":
                processed = deblur_engine.wiener_deconvolution(processed, psf, nsr=payload.wiener_nsr)
            else:
                processed = deblur_engine.richardson_lucy(processed, psf, iterations=payload.rl_iterations)

    # 2.5 Tratamento Específico para Perícia Facial (Conformidade CNJ nº 484/2022)
    if payload.roi_type == "face":
        # Correção de Iluminação CIELAB/CLAHE
        lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_norm = clahe.apply(l_ch)
        processed = cv2.cvtColor(cv2.merge([l_norm, a_ch, b_ch]), cv2.COLOR_LAB2BGR)
        # Redução de ruído de compressão CFTV
        processed = cv2.fastNlMeansDenoisingColored(processed, None, 6.0, 6.0, 7, 21)

    # 3. Super-Resolução / Restauração — CodeFormer real pra rosto (rede
    # generativa dedicada, respeita fidelity_weight de verdade agora),
    # Real-ESRGAN pra placa/cena geral. Sem fallback silencioso: se o
    # CodeFormer não puder rodar, cai pro Real-ESRGAN genérico e ISSO fica
    # registrado em `model_used`, não escondido.
    face_restored = None
    if payload.roi_type == "face":
        face_restored = face_restorer.restore(processed, fidelity_weight=payload.fidelity_weight)

    if face_restored is not None:
        enhanced_img = face_restored
        model_used = f"CodeFormer-ONNX-w{payload.fidelity_weight:.2f}"
    else:
        sr_engine.scale = payload.scale_factor
        enhanced_img, model_used = sr_engine.upscale(processed, model_name="edsr")
        if payload.roi_type == "face":
            model_used += " (fallback — CodeFormer indisponível)"
            # Nitidez genérica só entra quando o CodeFormer real não rodou.
            bilateral = cv2.bilateralFilter(enhanced_img, d=9, sigmaColor=75, sigmaSpace=75)
            high_freq = cv2.subtract(enhanced_img, bilateral)
            enhanced_img = cv2.addWeighted(enhanced_img, 1.2, high_freq, 0.4, 0)

    # 4. Binarização Forense & OCR de Placas
    binary_b64 = None
    plate_ocr = None
    plate_fmt = None
    plate_ocr_conf = None

    if payload.roi_type == "plate":
        gray_enhanced = cv2.cvtColor(enhanced_img, cv2.COLOR_BGR2GRAY)
        if payload.binarization == "sauvola":
            bin_img = plate_enhancer.sauvola_binarization(gray_enhanced, window_size=25, k=payload.sauvola_k)
            binary_b64 = encode_image_base64(bin_img)
        elif payload.binarization == "otsu":
            _, bin_img = cv2.threshold(gray_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            binary_b64 = encode_image_base64(bin_img)
        
        # OCR real (EasyOCR) + correção posicional + validação de formato —
        # nunca retorna uma placa inventada; sem leitura plausível, os 3
        # campos ficam None e a resposta reflete isso com honestidade.
        plate_ocr, plate_fmt, plate_ocr_conf = alpr_engine.read_plate(enhanced_img)

    metrics_enh = quality_assessor.evaluate(enhanced_img)
    sha256_enh = hashlib.sha256(enhanced_img.tobytes()).hexdigest().upper()
    elapsed_ms = (time.time() - t0) * 1000.0

    return ForensicAnalysisResponse(
        status="SUCCESS",
        roi_type=payload.roi_type,
        # "[CNJ-484 Compliant]" removido daqui (achado de auditoria: rótulo
        # cosmético sem verificação real de conformidade). O alinhamento
        # duplo-cego CNJ 484/2022 de verdade é feito por CNJLineupEngine em
        # forensic_core.py, não por este endpoint de enhancement de imagem.
        model_used=model_used,
        original_dimensions=(w_orig, h_orig),
        enhanced_dimensions=(enhanced_img.shape[1], enhanced_img.shape[0]),
        processing_time_ms=round(elapsed_ms, 2),
        sha256_original=sha256_orig,
        sha256_enhanced=sha256_enh,
        quality_metrics_original=metrics_orig,
        quality_metrics_enhanced=metrics_enh,
        plate_ocr_candidate=plate_ocr,
        plate_format=plate_fmt,
        plate_ocr_confidence=plate_ocr_conf,
        plate_bbox_detected=plate_bbox is not None,
        plate_detection_confidence=plate_detect_conf,
        enhanced_image_base64=encode_image_base64(enhanced_img),
        binary_image_base64=binary_b64,
        timestamp_utc=datetime.now(timezone.utc).isoformat()
    )


@forensic_sr_router.post("/license-plate")
async def enhance_license_plate_file(
    file: UploadFile = File(..., description="Arquivo de imagem da placa veicular (crop/ROI)"),
    deskew: bool = Form(True),
    deblur: bool = Form(False),
    motion_length: int = Form(12),
    motion_angle: float = Form(0.0)
):
    """Endpoint de conveniência para upload de arquivo da placa."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Arquivo de imagem inválido.")

    req = EnhanceROIRequest(
        image_base64=base64.b64encode(contents).decode("utf-8"),
        roi_type="plate",
        scale_factor=4,
        apply_deskew=deskew,
        deblur_method="wiener" if deblur else "none",
        motion_length=motion_length,
        motion_angle=motion_angle,
        binarization="sauvola"
    )
    return await enhance_roi(req)
