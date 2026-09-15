"""
reid_osnet.py — Olho de Deus

Re-identificação de PESSOA por aparência (OSNet, `osnet_x0_25`, treinado no
MSMT17 — um dos datasets padrão de re-id, gente real fotografada por várias
câmeras de vigilância) — Fase 2 do plano de mesclar técnicas de projetos
maduros (2026-09-15). Complementa o reconhecimento FACIAL (ArcFace/
InsightFace, Fase 1): re-id de corpo funciona mesmo sem ver o rosto — de
costas, de longe, ângulo ruim — porque descreve "como a pessoa está
vestida/formato do corpo", não o rosto.

De propósito, NÃO importa o pacote `boxmot` inteiro — a lib de origem tem
uma camada grande de gerência de sessão (buckets de batch pro CoreML,
múltiplos backends, providers por SO) que não serve aqui. O contrato de
pré-processamento (256x128, normalização ImageNet) foi confirmado lendo o
código-fonte real (`boxmot/reid/backends/base_backend.py`, linhas
78-90: `mean=[0.485,0.456,0.406]`, `std=[0.229,0.224,0.225]` — padrão
ImageNet, não inventado). O peso ONNX usado é uma conversão de terceiro
(`anriha/osnet_x0_25_msmt17`, Hugging Face) do checkpoint oficial do
torchreid (KaiyangZhou) — não veio pré-exportado pelo BoxMOT nem pelo autor
original do OSNet, então é tratado com mais cautela (ver `PROVENIENCIA`
abaixo) até ser validado com dado próprio.

IMPORTANTE — confiança MENOR que reconhecimento facial: duas pessoas com
roupa parecida no mesmo dia dão embedding de corpo próximo sem serem a
mesma pessoa. Nunca usar isto pra CONFIRMAR identidade sozinho — só pra
SUGERIR correlação de movimento entre câmeras, sempre junto com o resultado
do rosto quando existir (ver `MEMORY`/plano de 2026-09-15).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import onnxruntime

MODELO_PATH = Path(__file__).parent / "models" / "reid" / "osnet_x0_25_msmt17.onnx"

PROVENIENCIA = (
    "Conversão de terceiro (huggingface.co/anriha/osnet_x0_25_msmt17) do "
    "checkpoint oficial do torchreid (KaiyangZhou/deep-person-reid), não "
    "publicada pelos autores originais do OSNet nem pelo BoxMOT — validar "
    "com par de fotos reais da mesma pessoa antes de confiar no limiar de "
    "similaridade em produção."
)

# Confirmado inspecionando o grafo ONNX real: entrada (N,3,256,128) — altura
# 256, largura 128 (convenção "retrato" de re-id de pessoa, câmera vê o
# corpo inteiro em pé) — e BATCH FIXO EM 16 (não dinâmico). Por isso
# `_embed_lote` sempre lida com um lote de 16, preenchendo com zero o que
# sobrar quando processar menos gente que isso.
INPUT_HEIGHT = 256
INPUT_WIDTH = 128
BATCH_FIXO = 16

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)

_session: Optional[onnxruntime.InferenceSession] = None


def _get_session() -> onnxruntime.InferenceSession:
    global _session
    if _session is None:
        _session = onnxruntime.InferenceSession(
            str(MODELO_PATH), providers=["CPUExecutionProvider"]
        )
    return _session


def _preprocessa(crop_pessoa_bgr: np.ndarray) -> np.ndarray:
    """BGR (OpenCV) -> RGB, resize 256x128, normalização ImageNet, layout
    CHW — mesmo contrato que `base_backend.py` aplica antes de mandar pro
    modelo (confirmado lendo o código-fonte, não assumido)."""
    rgb = cv2.cvtColor(crop_pessoa_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (INPUT_WIDTH, INPUT_HEIGHT))
    chw = resized.transpose(2, 0, 1).astype(np.float32) / 255.0
    normalizado = (chw - IMAGENET_MEAN) / IMAGENET_STD
    return normalizado


def embedding_corpo(crop_pessoa_bgr: np.ndarray) -> np.ndarray:
    """Embedding de aparência (512d, L2-normalizado) de UM recorte de
    pessoa. O modelo só aceita lote fixo de 16 — preenche o resto com zero
    e descarta as saídas correspondentes (elas não afetam a saída do índice
    0 porque a rede não tem normalização entre itens do lote, só BatchNorm
    já congelado em modo de inferência)."""
    entrada = _preprocessa(crop_pessoa_bgr)
    lote = np.zeros((BATCH_FIXO, 3, INPUT_HEIGHT, INPUT_WIDTH), dtype=np.float32)
    lote[0] = entrada

    sessao = _get_session()
    saida = sessao.run(None, {sessao.get_inputs()[0].name: lote})[0]
    vetor = saida[0]

    norma = np.linalg.norm(vetor)
    if norma > 0:
        vetor = vetor / norma
    return vetor.astype(np.float32)


def similaridade_corpo(vetor_a: np.ndarray, vetor_b: np.ndarray) -> float:
    """Similaridade de cosseno entre dois embeddings de corpo (já
    L2-normalizados por `embedding_corpo` — o produto escalar já É a
    similaridade de cosseno)."""
    return float(np.dot(vetor_a, vetor_b))
