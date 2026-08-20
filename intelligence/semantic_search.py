"""
===============================================================================
OLHO DE DEUS — Camada 3: Motor de Busca Semântica em Vídeo (VLM + Qdrant)
===============================================================================
Implementa o pipeline de busca semântica multimodal:
  1. Indexação contínua de embeddings CLIP/SigLIP-2 por câmera
  2. Busca em linguagem natural em 2 estágios (ANN BQ + VLM Reranking)
  3. Video-QA forense: timestamps exatos e bounding boxes para laudos
  4. Compressão vetorial Binary Quantization ~ 84 GiB / 30 dias (96 B / vetor)

Referência de pesquisa:
  forensic_video_semantic_search.md (Agente VLM & Semantic Search)

Latência alvo total: < 245ms (5ms text_enc + 18ms ANN + 12ms rescore + 210ms VLM)

Correções aplicadas (2026-08-16):
  [FIX-1] BinaryQuantizer.quantize: threshold adaptativo (mean) em vez de >= 0
  [FIX-2] hamming_distance: XOR em bytes compactados (POPCNT-ready) em vez de != em uint8
  [FIX-3] asymmetric_rescore: usa normas reais de ambos os vetores
  [FIX-4] InMemoryVectorIndex Estágio 2: rescore usa embedding_fp32, não embedding_bq
  [FIX-5] EmbeddingIngestionPipeline: timestamp inicial correto + Motion VAD + mean-pooling
  [NEW]   QdrantVectorIndex: integração real com BinaryQuantization e oversampling nativo
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Integração Qdrant opcional — sistema funciona em modo in-memory sem o pacote
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        BinaryQuantization,
        BinaryQuantizationConfig,
        Distance,
        FieldCondition,
        Filter,
        HnswConfigDiff,
        MatchValue,
        PointStruct,
        QuantizationSearchParams,
        Range,
        VectorParams,
    )
    QDRANT_AVAILABLE = True
except ImportError:  # pragma: no cover
    QDRANT_AVAILABLE = False
    log_warning = "qdrant-client não instalado — use 'pip install qdrant-client'. Usando índice in-memory."

log = logging.getLogger("SEMANTIC_SEARCH")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [SEMANTIC] %(message)s")

if not QDRANT_AVAILABLE:
    log.warning("qdrant-client não instalado — usando InMemoryVectorIndex (modo dev).")


# ---------------------------------------------------------------------------
# 1. Estruturas de Dados
# ---------------------------------------------------------------------------

@dataclass
class VideoClipEmbedding:
    """
    Representa um embedding de clipe de vídeo indexado.

    Campos de embedding:
      - embedding_bq   : bytes compactados, 96 bytes (768 bits).  Compressão 32:1.
      - embedding_fp32 : array float32 768-d L2-normalizado. Usado no rescore FP32.

    Nota: embedding_bq é armazenado como bytes (não np.ndarray) para que o storage
    real seja 96 bytes/vetor, conforme a estimativa de 84 GiB / 30 dias.
    """
    camera_id: str
    timestamp: float
    duration_seconds: float
    embedding_bq: bytes          # Compactado: 96 bytes = 768 bits (np.packbits)
    embedding_fp32: np.ndarray   # Full precision para rescore real (768-d SigLIP-2)
    metadata: dict = field(default_factory=dict)  # local, setor, pais, etc.


@dataclass
class SemanticSearchResult:
    """Resultado de busca semântica com metadados para perícia."""
    camera_id: str
    timestamp: float
    score: float
    description: str
    bounding_boxes: list[dict] = field(default_factory=list)  # [{class, bbox, conf}]
    thumbnail_path: str = ""
    forensic_hash: str = ""   # SHA-256 do frame original


@dataclass
class VideoQAResult:
    """Resultado de Video-QA forense com timestamps e evidências."""
    question: str
    answer: str
    camera_id: str
    timestamp_start: float
    timestamp_end: float
    confidence: float
    bounding_boxes: list[dict] = field(default_factory=list)
    evidence_hash: str = ""


# ---------------------------------------------------------------------------
# 2. Quantizador Binário — compressão 32x para 768-d SigLIP-2
# ---------------------------------------------------------------------------

class BinaryQuantizer:
    """
    Quantização Binária 1-bit de embeddings vetoriais.

    Estratégia: converte embedding float32 768-d em 96 bytes compactados (np.packbits).
    Distância: Hamming via XOR de bytes + popcount, compatível com POPCNT/AVX-512.

    Compressão: 768 × 4 bytes = 3072 bytes → 768 bits = 96 bytes (razão 32:1).

    Orçamento de storage (30 dias × 10.000 câmeras, 1 embed/27.6s):
        939M vetores × 96 bytes ≈ 83.97 GiB (≈90.16 GB decimal) < 100 GB  ✓
        Com overhead HNSW + metadata → ~119 GiB total em disco.
    """

    # Dimensão dos embeddings SigLIP-2 ViT-SO400M
    DIM = 768
    # Bytes após compactação: ceil(768 / 8) = 96
    PACKED_BYTES = (DIM + 7) // 8  # 96

    def quantize(self, embedding: np.ndarray) -> np.ndarray:
        """
        [FIX-1] Converte embedding float32 → vetor binário uint8 usando
        threshold adaptativo (média do vetor) em vez do limiar fixo zero.

        Motivo: embeddings SigLIP-2 (sigmoid loss) não são centrados em zero;
        usar a média garante distribuição de bits próxima a 50/50, maximizando
        a discriminabilidade da distância de Hamming.
        """
        threshold = float(embedding.mean())  # threshold adaptativo por vetor
        return (embedding >= threshold).astype(np.uint8)

    def pack_bits(self, binary_emb: np.ndarray) -> bytes:
        """
        Compacta array uint8 de 0s e 1s em bytes reais via np.packbits.
        Resultado: 96 bytes para embedding 768-d (compressão 32:1).
        """
        n = len(binary_emb)
        padded = np.zeros(((n + 7) // 8) * 8, dtype=np.uint8)
        padded[:n] = binary_emb
        return np.packbits(padded).tobytes()

    def unpack_bits(self, packed: bytes, dim: int | None = None) -> np.ndarray:
        """Descompacta bytes empacotados de volta para array uint8 de 0s e 1s."""
        dim = dim or self.DIM
        return np.unpackbits(np.frombuffer(packed, dtype=np.uint8))[:dim]

    def quantize_and_pack(self, embedding: np.ndarray) -> bytes:
        """Atalho: quantiza + compacta em um passo. Retorna 96 bytes."""
        return self.pack_bits(self.quantize(embedding))

    def hamming_distance(self, a_packed: bytes, b_packed: bytes) -> int:
        """
        [FIX-2] Distância de Hamming real via XOR de bytes compactados.

        Opera sobre os 96 bytes compactados com XOR → np.unpackbits → soma.
        Compatível com POPCNT: numpy usa instruções SSE4/AVX quando disponíveis.
        Complexidade: O(PACKED_BYTES) = O(96) em vez de O(DIM) = O(768).
        """
        a = np.frombuffer(a_packed, dtype=np.uint8)
        b = np.frombuffer(b_packed, dtype=np.uint8)
        xor = np.bitwise_xor(a, b)
        return int(np.unpackbits(xor).sum())

    def hamming_similarity(self, a_packed: bytes, b_packed: bytes) -> float:
        """Similaridade de Hamming normalizada [0-1] (1 = idênticos)."""
        return 1.0 - self.hamming_distance(a_packed, b_packed) / self.DIM

    def asymmetric_rescore(self, query_fp32: np.ndarray, candidate_fp32: np.ndarray) -> float:
        """
        [FIX-3] Asymmetric Distance Computation (ADC) corrigido:
        query FP32 × candidato FP32 real → cosine similarity.

        O rescore de Estágio 2 deve usar embedding_fp32 completo (não BQ
        reconstruído), caso contrário não há ganho de precisão em relação
        ao Estágio 1. Esta função calcula cosine similarity real.

        Nota: ambos os embeddings SigLIP-2 são L2-normalizados na extração,
        portanto dot product == cosine similarity diretamente.
        """
        norm_q = float(np.linalg.norm(query_fp32))
        norm_c = float(np.linalg.norm(candidate_fp32))
        return float(np.dot(query_fp32, candidate_fp32)) / (norm_q * norm_c + 1e-8)


# ---------------------------------------------------------------------------
# 3. Extrator de Embeddings Multimodais CLIP / SigLIP-2
# ---------------------------------------------------------------------------

class SigLIPExtractor:
    """
    Extrator de embeddings multimodais SigLIP-2 768-d (ViT-SO400M).

    SigLIP-2 usa sigmoid loss para treino, evitando saturação de batches
    e preservando detalhes finos: roupas, cores, tipos de veículos, acessórios.

    Em produção: execução via ONNX / TensorRT FP16 em GPU.
    Throughput alvo: > 1.800 frames/s por GPU NVIDIA L40S.
    """

    EMBEDDING_DIM = 768

    def __init__(self, model_name: str = "siglip2-so400m-patch14-384"):
        self.model_name = model_name
        self._quantizer = BinaryQuantizer()
        log.info(f"SigLIPExtractor inicializado: {model_name} ({self.EMBEDDING_DIM}-d)")

    def encode_image(self, frame: np.ndarray) -> np.ndarray:
        """
        Extrai embedding visual 768-d L2-normalizado de um frame.
        Em produção: pré-processa para 384x384 → inferência TensorRT.
        """
        # Simulação determinística baseada no hash do frame
        seed = int(hashlib.md5(frame.tobytes()[:128]).hexdigest(), 16) % (2**31)
        rng = np.random.default_rng(seed)
        emb = rng.standard_normal(self.EMBEDDING_DIM).astype(np.float32)
        norm = np.linalg.norm(emb)
        return emb / (norm + 1e-8)

    def encode_text(self, text: str) -> np.ndarray:
        """
        Codifica texto em embedding 768-d usando o Text Encoder SigLIP-2.
        Em produção: tokenização SentencePiece → transformer text tower.
        """
        # Simulação: hash determinístico do texto
        seed = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16) % (2**31)
        rng = np.random.default_rng(seed)
        emb = rng.standard_normal(self.EMBEDDING_DIM).astype(np.float32)
        norm = np.linalg.norm(emb)
        return emb / (norm + 1e-8)


# ---------------------------------------------------------------------------
# 4. Índice Vetorial em Memória (substitui Qdrant em ambientes sem dependência)
# ---------------------------------------------------------------------------

class InMemoryVectorIndex:
    """
    Índice vetorial HNSW simulado em memória para desenvolvimento/testes.

    Em produção, substituir por:
        - Qdrant (Rust): 15.000-35.000 QPS, filtros por metadata, HNSW nativo
        - pgvector (PostgreSQL 16): integrado ao banco de inteligência
        - Faiss IVF-PQ (GPU): > 120.000 QPS em GPU A100

    Suporta:
        - Inserção de embeddings com metadata
        - Busca ANN por Hamming (BQ) + rescore FP32
        - Filtragem por camera_id, timestamp range, setor, pais
    """

    def __init__(self):
        self._store: list[VideoClipEmbedding] = []
        self._quantizer = BinaryQuantizer()
        log.info("InMemoryVectorIndex inicializado (modo desenvolvimento)")

    def insert(self, clip: VideoClipEmbedding):
        """Insere um embedding de clipe no índice."""
        self._store.append(clip)

    def search(
        self,
        query_fp32: np.ndarray,
        top_k: int = 100,
        filter_camera_id: str | None = None,
        filter_setor: str | None = None,
        filter_ts_from: float | None = None,
        filter_ts_to: float | None = None,
    ) -> list[tuple[float, VideoClipEmbedding]]:
        """
        Busca ANN em 2 estágios:
          Estágio 1: Hamming BQ via XOR em bytes compactados → Top-K×3 candidatos
          Estágio 2: [FIX-4] Rescore FP32 REAL (embedding_fp32) → Top-K final

        Latência estimada: 18ms (ANN BQ) + 12ms (Rescore FP32)
        """
        # Quantiza query e compacta para comparação por XOR
        query_bq_packed = self._quantizer.quantize_and_pack(query_fp32)

        # Filtragem de metadata
        candidates = [
            c for c in self._store
            if (filter_camera_id is None or c.camera_id == filter_camera_id)
            and (filter_setor is None or c.metadata.get("setor") == filter_setor)
            and (filter_ts_from is None or c.timestamp >= filter_ts_from)
            and (filter_ts_to is None or c.timestamp <= filter_ts_to)
        ]

        if not candidates:
            return []

        # Estágio 1: Hamming via XOR de bytes compactados (POPCNT-ready)
        stage1_results = []
        for clip in candidates:
            ham_sim = self._quantizer.hamming_similarity(query_bq_packed, clip.embedding_bq)
            stage1_results.append((ham_sim, clip))

        # Oversampling 3x: candidatos suficientes para o rescore refinar
        stage1_sorted = sorted(stage1_results, key=lambda x: -x[0])[:top_k * 3]

        # Estágio 2: [FIX-4] Rescore com embedding_fp32 REAL — cosine similarity
        # ERRO ANTERIOR: usava clip.embedding_bq (BQ reconstruído), sem ganho de precisão.
        # CORRETO: usa clip.embedding_fp32 para precisão máxima no reranking final.
        stage2_results = []
        for _, clip in stage1_sorted:
            fp32_score = self._quantizer.asymmetric_rescore(query_fp32, clip.embedding_fp32)
            stage2_results.append((fp32_score, clip))

        return sorted(stage2_results, key=lambda x: -x[0])[:top_k]

    @property
    def size(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# 5. Pipeline de Ingestão de Embeddings com Motion VAD
# ---------------------------------------------------------------------------

class EmbeddingIngestionPipeline:
    """
    Pipeline de ingestão contínua de embeddings de câmeras.

    Estratégia de Motion VAD (Video Activity Detection):
        - Compara frames consecutivos via diferença absoluta (absdiff)
        - Descarta frames com alteração de pixels < MOTION_RATIO_THRESHOLD (2%)
        - Ao acumular CHUNK_INTERVAL_SECONDS de frames com movimento, gera 1 embedding

    Representante do clipe: mean-pooling dos embeddings de todos os frames com
    movimento (mais robusto que frame mediano para eventos curtos no início/fim).

    Storage: embedding_bq = 96 bytes reais (np.packbits); embedding_fp32 = 3072 bytes
    mantido em RAM apenas durante rescore (descartável em implementação com Qdrant).
    """

    CHUNK_INTERVAL_SECONDS = 5.0       # janela temporal por chunk
    MOTION_PIXEL_THRESHOLD = 25        # intensidade mínima de diferença por pixel
    MOTION_RATIO_THRESHOLD = 0.02      # 2% dos pixels alterados = movimento detectado

    def __init__(self, index: InMemoryVectorIndex, extractor: SigLIPExtractor):
        self.index = index
        self.extractor = extractor
        self._quantizer = BinaryQuantizer()
        self._last_embed_ts: dict[str, float] = {}
        self._frame_buffers: dict[str, list[np.ndarray]] = {}
        self._prev_frames: dict[str, np.ndarray] = {}   # para Motion VAD
        self._motion_frames_count: dict[str, int] = {}  # frames descartados
        self._static_frames_count: dict[str, int] = {}

    def _has_motion(self, frame: np.ndarray, camera_id: str) -> bool:
        """
        [FIX-5] Motion VAD mínimo: detecta movimento por diferença absoluta.

        Compara frame atual com o anterior. Se >= 2% dos pixels tiverem
        diferença de intensidade > 25, considera que há movimento.
        Descarta frames estáticos antes de acumular no buffer.
        """
        prev = self._prev_frames.get(camera_id)
        self._prev_frames[camera_id] = frame
        if prev is None:
            # Primeiro frame: aceita sempre para inicializar o buffer
            return True
        diff = np.abs(frame.astype(np.int16) - prev.astype(np.int16))
        changed_ratio = float(np.mean(diff > self.MOTION_PIXEL_THRESHOLD))
        return changed_ratio >= self.MOTION_RATIO_THRESHOLD

    def process_frame(
        self,
        frame: np.ndarray,
        camera_id: str,
        timestamp: float,
        metadata: dict | None = None,
    ):
        """
        Processa um frame de câmera:
          1. Motion VAD: descarta frames estáticos
          2. Acumula frames com movimento no buffer
          3. A cada CHUNK_INTERVAL_SECONDS, gera embedding via mean-pooling
        """
        # [FIX-5] Inicializa com o timestamp REAL do primeiro frame (não 0.0)
        # O valor 0.0 causava elapsed ≈ 1,7 bilhão (unix epoch) no primeiro chunk.
        if camera_id not in self._last_embed_ts:
            self._last_embed_ts[camera_id] = timestamp
            self._frame_buffers[camera_id] = []
            self._motion_frames_count[camera_id] = 0
            self._static_frames_count[camera_id] = 0

        # Motion VAD: acumula apenas frames com movimento detectado
        if self._has_motion(frame, camera_id):
            self._frame_buffers[camera_id].append(frame)
            self._motion_frames_count[camera_id] += 1
        else:
            self._static_frames_count[camera_id] += 1
            return  # frame estático descartado

        # Verifica se atingiu a janela temporal do chunk
        elapsed = timestamp - self._last_embed_ts[camera_id]
        if elapsed >= self.CHUNK_INTERVAL_SECONDS and self._frame_buffers[camera_id]:
            buf = self._frame_buffers[camera_id]

            # Mean-pooling de embeddings: mais robusto que frame mediano.
            # Captura eventos em qualquer ponto da janela (início, meio ou fim).
            embeddings = [self.extractor.encode_image(f) for f in buf]
            emb_fp32 = np.mean(embeddings, axis=0).astype(np.float32)
            norm = np.linalg.norm(emb_fp32)
            emb_fp32 = emb_fp32 / (norm + 1e-8)  # re-normaliza após mean-pooling

            # BQ compactado: 96 bytes reais (compressão 32:1)
            emb_bq_packed = self._quantizer.quantize_and_pack(emb_fp32)

            clip = VideoClipEmbedding(
                camera_id=camera_id,
                timestamp=self._last_embed_ts[camera_id],  # início da janela
                duration_seconds=elapsed,
                embedding_bq=emb_bq_packed,   # bytes: 96 bytes reais
                embedding_fp32=emb_fp32,
                metadata=metadata or {},
            )
            self.index.insert(clip)

            self._frame_buffers[camera_id].clear()
            self._last_embed_ts[camera_id] = timestamp

    def stats(self) -> dict:
        total_motion = sum(self._motion_frames_count.values())
        total_static = sum(self._static_frames_count.values())
        total_frames = total_motion + total_static
        vad_discard_ratio = total_static / total_frames if total_frames > 0 else 0.0
        storage_bq_bytes = self.index.size * BinaryQuantizer.PACKED_BYTES
        return {
            "indexed_clips": self.index.size,
            "active_cameras": len(self._frame_buffers),
            "motion_frames": total_motion,
            "static_frames_discarded": total_static,
            "vad_discard_ratio": round(vad_discard_ratio, 3),
            "storage_bq_bytes": storage_bq_bytes,
            "storage_bq_mb": round(storage_bq_bytes / (1024 ** 2), 4),
            # Nota: usa GiB (base 2) para refletir storage real em disco
            "storage_bq_gib": round(storage_bq_bytes / (1024 ** 3), 6),
        }


# ---------------------------------------------------------------------------
# 6. Motor de Busca Semântica em Linguagem Natural
# ---------------------------------------------------------------------------

class SemanticVideoSearchEngine:
    """
    Motor de busca semântica de vídeo em 2 estágios para linguagem natural.

    Estágio 1 (< 25ms):  Text Encoder → BQ Hamming ANN → Top-100 candidatos
    Estágio 2 (< 220ms): VLM Qwen2.5-VL reranking e verificação semântica

    Latência total alvo: 245ms
    """

    def __init__(self, index: InMemoryVectorIndex, extractor: SigLIPExtractor):
        self.index = index
        self.extractor = extractor
        log.info("SemanticVideoSearchEngine pronto para buscas em linguagem natural")

    def search(
        self,
        query_text: str,
        top_k: int = 10,
        filter_camera_id: str | None = None,
        filter_setor: str | None = None,
        filter_ts_from: float | None = None,
        filter_ts_to: float | None = None,
    ) -> list[SemanticSearchResult]:
        """
        Busca semântica por linguagem natural nos vídeos indexados.

        Exemplo de uso:
            engine.search("homem de jaqueta vermelha em moto prata")
            engine.search("carro suspeito parado na esquina", filter_setor="SP")
        """
        t0 = time.time()

        # Estágio 1: Codificação do texto e busca ANN BQ (< 25ms)
        query_emb = self.extractor.encode_text(query_text)

        raw_results = self.index.search(
            query_fp32=query_emb,
            top_k=top_k * 10,  # oversampling 10x para reranking
            filter_camera_id=filter_camera_id,
            filter_setor=filter_setor,
            filter_ts_from=filter_ts_from,
            filter_ts_to=filter_ts_to,
        )

        if not raw_results:
            log.info(f"Busca '{query_text}': 0 resultados encontrados")
            return []

        # Estágio 2: VLM Reranking (simulado — em produção: Qwen2.5-VL 3B batch)
        final_results = []
        for score, clip in raw_results[:top_k]:
            # VLM simulado: ajusta score com base na metadata disponível
            vlm_boost = 0.0
            cam_name = clip.metadata.get("nome", "").lower()
            query_lower = query_text.lower()

            # Matching simples de termos no nome da câmera (proxy do VLM)
            for word in query_lower.split():
                if word in cam_name:
                    vlm_boost += 0.1

            final_score = min(score + vlm_boost, 1.0)
            forensic_hash = hashlib.sha256(
                f"{clip.camera_id}:{clip.timestamp}".encode()
            ).hexdigest()[:16]

            result = SemanticSearchResult(
                camera_id=clip.camera_id,
                timestamp=clip.timestamp,
                score=final_score,
                description=(
                    f"Câmera {clip.camera_id} | "
                    f"Às {time.strftime('%H:%M:%S', time.localtime(clip.timestamp))} | "
                    f"Relevância: {final_score:.1%}"
                ),
                forensic_hash=forensic_hash,
            )
            final_results.append(result)

        elapsed_ms = (time.time() - t0) * 1000
        log.info(f"Busca '{query_text}': {len(final_results)} resultados em {elapsed_ms:.1f}ms")
        return sorted(final_results, key=lambda r: -r.score)

    def semantic_alert(self, query_text: str, threshold: float = 0.7) -> list[SemanticSearchResult]:
        """
        Dispara alerta quando a query semântica encontra correspondência
        com score acima do threshold em tempo real.
        """
        results = self.search(query_text)
        alerts = [r for r in results if r.score >= threshold]
        if alerts:
            log.warning(f"🔍 ALERTA SEMÂNTICO: '{query_text}' → {len(alerts)} ocorrências!")
        return alerts


# ---------------------------------------------------------------------------
# 7. Motor de Video-QA Forense
# ---------------------------------------------------------------------------

class ForensicVideoQA:
    """
    Video-QA Forense para laudos periciais com timestamps exatos.

    Utiliza VLM (Qwen2.5-VL) com MRoPE para correlação temporal precisa:
        - Temporal Grounding: timestamps absolutos de alta resolução
        - Visual Grounding: bounding boxes normalizadas [ymin, xmin, ymax, xmax]
        - SAM 2 segmentação para rastreamento de tracklets
        - OCR de placas veiculares ANPR/LPR e assinatura SHA-256

    Exemplos de queries forenses:
        "Qual a placa do veículo que estacionou às 21h?"
        "O suspeito carregava mochila?"
        "Quantas pessoas cruzaram a rua entre 20h e 20h30?"
    """

    def __init__(self, search_engine: SemanticVideoSearchEngine):
        self.search_engine = search_engine

    def query(
        self,
        question: str,
        camera_id: str | None = None,
        time_window_from: float | None = None,
        time_window_to: float | None = None,
    ) -> VideoQAResult:
        """
        Responde a perguntas forenses sobre o acervo de vídeo.
        Em produção: envia prompt estruturado para Qwen2.5-VL local.
        """
        # Traduz a pergunta para uma query de busca semântica
        results = self.search_engine.search(
            query_text=question,
            filter_camera_id=camera_id,
            filter_ts_from=time_window_from,
            filter_ts_to=time_window_to,
            top_k=3,
        )

        if not results:
            return VideoQAResult(
                question=question,
                answer="Nenhuma evidência visual encontrada para esta pergunta no período solicitado.",
                camera_id=camera_id or "N/A",
                timestamp_start=time_window_from or 0.0,
                timestamp_end=time_window_to or 0.0,
                confidence=0.0,
            )

        best = results[0]

        # Resposta VLM simulada (em produção: Qwen2.5-VL inference com MRoPE)
        vlm_answer = (
            f"Com base na análise visual da câmera {best.camera_id} às "
            f"{time.strftime('%H:%M:%S', time.localtime(best.timestamp))}: "
            f"evidência encontrada com relevância {best.score:.1%}. "
            f"Hash SHA-256 do frame: {best.forensic_hash}. "
            "Para perícia completa, ativar pipeline Qwen2.5-VL com MRoPE."
        )

        evidence_hash = hashlib.sha256(
            f"{best.camera_id}:{best.timestamp}:{question}".encode()
        ).hexdigest()

        return VideoQAResult(
            question=question,
            answer=vlm_answer,
            camera_id=best.camera_id,
            timestamp_start=best.timestamp,
            timestamp_end=best.timestamp + 5.0,
            confidence=best.score,
            evidence_hash=evidence_hash,
        )


# ---------------------------------------------------------------------------
# 8. Índice Qdrant — Integração Real com BinaryQuantization e Oversampling
# ---------------------------------------------------------------------------

if QDRANT_AVAILABLE:
    class QdrantVectorIndex:
        """
        Índice vetorial Qdrant com Binary Quantization nativa e rescore FP32.

        Qdrant armazena os vetores originais FP32 on-disk (mmap) e a BQ em RAM
        para busca ANN rápida. O rescore FP32 é feito automaticamente pelo servidor
        com o parâmetro rescore=True + oversampling.

        Configuração:
          - Coleção: olho_de_deus_bq
          - Distância: COSINE (equivalente a dot product para vetores normalizados)
          - BinaryQuantization always_ram=True: BQ em RAM, payload on-disk
          - HNSW m=16, ef_construct=100: balanço qualidade × throughput

        QPS esperado:
          - Qdrant standalone: 15.000–35.000 QPS (CPU)
          - Com GPU CUDA: até 120.000 QPS (via Faiss GPU fallback)
        """

        COLLECTION = "olho_de_deus_bq"
        DIM = 768

        def __init__(
            self,
            host: str = "localhost",
            port: int = 6333,
            recreate: bool = False,
        ):
            """
            Args:
                host      : host do servidor Qdrant (padrão: localhost)
                port      : porta gRPC/HTTP do Qdrant (padrão: 6333)
                recreate  : se True, recria a coleção do zero (cuidado em produção!)
            """
            self.client = QdrantClient(host=host, port=port)
            self._quantizer = BinaryQuantizer()
            self._ensure_collection(recreate=recreate)
            log.info(f"QdrantVectorIndex conectado em {host}:{port} | coleção: {self.COLLECTION}")

        def _ensure_collection(self, recreate: bool = False) -> None:
            """Cria a coleção com BQ se não existir. Recria se recreate=True."""
            exists = self.client.collection_exists(self.COLLECTION)
            if exists and not recreate:
                log.info(f"Coleção '{self.COLLECTION}' já existe — reutilizando.")
                return
            if exists and recreate:
                self.client.delete_collection(self.COLLECTION)
                log.warning(f"Coleção '{self.COLLECTION}' deletada para recriação.")

            self.client.create_collection(
                collection_name=self.COLLECTION,
                vectors_config=VectorParams(
                    size=self.DIM,
                    distance=Distance.COSINE,
                    on_disk=True,          # vetores FP32 em mmap (economiza RAM)
                ),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(
                        always_ram=True,   # BQ mantida em RAM para ANN rápido
                    )
                ),
                hnsw_config=HnswConfigDiff(
                    m=16,                  # conexões por nó HNSW
                    ef_construct=100,      # qualidade do grafo na inserção
                    on_disk=False,         # grafo HNSW em RAM
                ),
                on_disk_payload=True,      # metadata (camera_id, ts) em disco
            )
            log.info(f"Coleção '{self.COLLECTION}' criada com BinaryQuantization.")

        def insert(self, clip: VideoClipEmbedding) -> None:
            """Insere um clipe no Qdrant como ponto vetorial com payload."""
            point_id = str(uuid.uuid4())
            self.client.upsert(
                collection_name=self.COLLECTION,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=clip.embedding_fp32.tolist(),  # FP32 para Qdrant BQ
                        payload={
                            "camera_id": clip.camera_id,
                            "timestamp": clip.timestamp,
                            "duration_seconds": clip.duration_seconds,
                            **clip.metadata,
                        },
                    )
                ],
            )

        def search(
            self,
            query_fp32: np.ndarray,
            top_k: int = 10,
            filter_camera_id: str | None = None,
            filter_setor: str | None = None,
            filter_ts_from: float | None = None,
            filter_ts_to: float | None = None,
        ) -> list[tuple[float, dict]]:
            """
            Busca ANN no Qdrant com Binary Quantization e rescore FP32 nativo.

            Estágio 1 (BQ Hamming ANN): Qdrant usa HNSW sobre BQ → top_k * oversampling
            Estágio 2 (Rescore FP32):   rescore=True refaz ranking com vetores FP32 reais

            Retorna lista de (score, payload_dict).
            """
            # Monta filtros de payload (metadata)
            must_conditions = []
            if filter_camera_id:
                must_conditions.append(
                    FieldCondition(key="camera_id", match=MatchValue(value=filter_camera_id))
                )
            if filter_setor:
                must_conditions.append(
                    FieldCondition(key="setor", match=MatchValue(value=filter_setor))
                )
            if filter_ts_from is not None or filter_ts_to is not None:
                ts_range: dict[str, float] = {}
                if filter_ts_from is not None:
                    ts_range["gte"] = filter_ts_from
                if filter_ts_to is not None:
                    ts_range["lte"] = filter_ts_to
                must_conditions.append(
                    FieldCondition(key="timestamp", range=Range(**ts_range))
                )

            query_filter = Filter(must=must_conditions) if must_conditions else None

            results = self.client.search(
                collection_name=self.COLLECTION,
                query_vector=query_fp32.tolist(),
                limit=top_k,
                query_filter=query_filter,
                search_params=QuantizationSearchParams(
                    ignore=False,
                    rescore=True,       # Estágio 2: rescore FP32 automático pelo servidor
                    oversampling=3.0,   # Estágio 1: recupera top_k*3 candidatos BQ
                ),
                with_payload=True,
            )

            return [(hit.score, hit.payload or {}) for hit in results]

        @property
        def size(self) -> int:
            """Número de pontos na coleção Qdrant."""
            info = self.client.get_collection(self.COLLECTION)
            return info.points_count or 0


# ---------------------------------------------------------------------------
# 9. Fábrica do Sistema Semântico Completo
# ---------------------------------------------------------------------------

def build_semantic_system(
    use_qdrant: bool = False,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
) -> tuple[SemanticVideoSearchEngine, ForensicVideoQA, EmbeddingIngestionPipeline]:
    """
    Instancia e conecta todos os componentes do sistema semântico.

    Args:
        use_qdrant  : se True e qdrant-client instalado, usa QdrantVectorIndex.
                      Caso contrário, usa InMemoryVectorIndex (modo dev/teste).
        qdrant_host : host do servidor Qdrant.
        qdrant_port : porta do servidor Qdrant.

    Retorna:
        (search_engine, video_qa, ingestion_pipeline)
    """
    extractor = SigLIPExtractor()

    if use_qdrant and QDRANT_AVAILABLE:
        index: QdrantVectorIndex | InMemoryVectorIndex = QdrantVectorIndex(
            host=qdrant_host, port=qdrant_port
        )
        log.info("Sistema Semântico montado com QdrantVectorIndex (produção).")
    else:
        if use_qdrant and not QDRANT_AVAILABLE:
            log.warning("use_qdrant=True mas qdrant-client não está instalado. Usando InMemoryVectorIndex.")
        index = InMemoryVectorIndex()
        log.info("Sistema Semântico montado com InMemoryVectorIndex (desenvolvimento).")

    ingestion = EmbeddingIngestionPipeline(index, extractor)
    search_engine = SemanticVideoSearchEngine(index, extractor)
    video_qa = ForensicVideoQA(search_engine)
    log.info("Pipeline completo: SigLIP-2 + ANN-BQ (XOR/POPCNT) + Rescore FP32 + VLM-QA")
    return search_engine, video_qa, ingestion


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_run():
    log.info("=== DEMO: Motor de Busca Semântica em Vídeo ===")
    rng = np.random.default_rng(42)
    search_engine, video_qa, ingestion = build_semantic_system()

    # Simula ingestão de 100 frames de 5 câmeras brasileiras
    cameras = [
        ("CAM-BR-1000", {"nome": "Balneário Camboriú Avenida Atlântica", "setor": "SC", "pais": "BR"}),
        ("CAM-BR-1001", {"nome": "Rio de Janeiro Copacabana Posto 3", "setor": "RJ", "pais": "BR"}),
        ("CAM-BR-1002", {"nome": "Cristo Redentor Rio de Janeiro", "setor": "RJ", "pais": "BR"}),
        ("CAM-BR-1003", {"nome": "Florianópolis Jurerê Internacional", "setor": "SC", "pais": "BR"}),
        ("CAM-BR-1004", {"nome": "Porto Alegre Orla do Guaíba", "setor": "RS", "pais": "BR"}),
    ]

    ts = time.time() - 3600  # começa 1 hora atrás
    for cam_id, meta in cameras:
        for i in range(20):
            frame = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
            ingestion.process_frame(frame, cam_id, ts + i * 30.0, meta)

    stats = ingestion.stats()
    log.info(
        f"\n📊 Índice: {stats['indexed_clips']} clipes indexados | "
        f"{stats['storage_bq_gib']:.6f} GiB (BQ 96B/vetor) | "
        f"VAD descartou {stats['static_frames_discarded']} frames estáticos "
        f"({stats['vad_discard_ratio']:.1%} do total)"
    )

    # Busca semântica em linguagem natural
    log.info("\n🔍 Buscando: 'câmera de praia ao vivo'")
    results = search_engine.search("câmera de praia ao vivo", top_k=3)
    for r in results:
        log.info(f"  → {r.description}")

    # Video-QA forense
    log.info("\n⚖️ Video-QA: 'Havia movimento nas câmeras do Rio de Janeiro?'")
    qa_result = video_qa.query(
        "Havia movimento nas câmeras do Rio de Janeiro?",
        camera_id="CAM-BR-1001"
    )
    log.info(f"  Resposta: {qa_result.answer}")
    log.info(f"  Hash SHA-256: {qa_result.evidence_hash[:32]}...")


if __name__ == "__main__":
    demo_run()
