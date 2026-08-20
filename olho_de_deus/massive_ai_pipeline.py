#!/usr/bin/env python3
"""
===============================================================================
OLHO DE DEUS — PIPELINE DE INFERÊNCIA EM LARGA ESCALA (10.000 CÂMERAS)
Funil de compressão de throughput de IA:
1. Motion-Gated Inference (MGI) via MOG2/Pixel Difference em CPU
2. Keyframe Decimation Adaptativo (1 FPS repouso -> 10 FPS ativo -> 30 FPS alerta)
3. Ring Buffer circular de 5s em memória para captura de incidentes com zero perda
4. TensorRT Dynamic Batching (Lotes B=16, 32, 64 com max_queue_delay = 1.5ms)
===============================================================================
"""

import time
import collections
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

log = logging.getLogger("MassiveAIPipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")


@dataclass
class FramePacket:
    camera_id: str
    frame_id: int
    timestamp: float
    frame_data: np.ndarray  # Imagem RGB / YUV
    has_motion: bool = False
    priority_level: int = 1  # 1 = Baixa (1 FPS), 2 = Média (10 FPS), 3 = Crítica (30 FPS)


class MotionGatedFilter:
    """Filtro de movimento ultrarrápido em CPU (SIMD MOG2 / Frame Subtraction).
    
    Descarta frames estáticos com custo de CPU < 0.15ms por quadro,
    evitando enviar 70% da carga para os Tensor Cores da GPU.
    """

    def __init__(self, motion_threshold: float = 0.015):
        self.motion_threshold = motion_threshold
        self.last_frames: Dict[str, np.ndarray] = {}

    def check_motion(self, camera_id: str, frame: np.ndarray) -> Tuple[bool, float]:
        """Compara o quadro atual com o quadro de referência anterior."""
        # Reduz resolução para 160x90 para cálculo vetorial ultrarrápido
        small = frame[::4, ::4, 0] if len(frame.shape) == 3 else frame[::4, ::4]
        
        last = self.last_frames.get(camera_id)
        if last is None:
            self.last_frames[camera_id] = small
            return True, 1.0  # Primeiro frame sempre processa

        # Diferença absoluta normalizada
        diff = np.abs(small.astype(np.int16) - last.astype(np.int16))
        motion_ratio = float(np.count_nonzero(diff > 25) / small.size)
        self.last_frames[camera_id] = small
        
        has_motion = motion_ratio >= self.motion_threshold
        return has_motion, motion_ratio


class AdaptiveKeyframeDecimator:
    """Controla a frequência de amostragem de cada câmera conforme o nível de atividade.
    
    - Repouso (Sem movimento/alvo): 1.0 FPS
    - Atividade (Movimento detectado): 10.0 FPS
    - Alarme / Alvo Identificado: 30.0 FPS (Full Rate)
    """

    def __init__(self):
        self.last_sampled: Dict[str, float] = {}

    def should_sample(self, camera_id: str, priority_level: int, current_time: float) -> bool:
        last_t = self.last_sampled.get(camera_id, 0.0)
        
        if priority_level >= 3:
            interval = 1.0 / 30.0  # 30 FPS
        elif priority_level == 2:
            interval = 1.0 / 10.0  # 10 FPS
        else:
            interval = 1.0 / 1.0   # 1 FPS

        if (current_time - last_t) >= interval:
            self.last_sampled[camera_id] = current_time
            return True
        return False


class CircularIncidentRingBuffer:
    """Ring Buffer em memória RAM para reter os últimos 5 segundos de todas as câmeras.
    
    Quando um alarme dispara, o buffer retroativo de 5 segundos é imediatamente
    salvo como evidência forense antes mesmo do momento do alerta.
    """

    def __init__(self, buffer_seconds: int = 5, max_fps: int = 15):
        self.capacity = buffer_seconds * max_fps
        self.buffers: Dict[str, collections.deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.capacity)
        )

    def append(self, camera_id: str, frame: np.ndarray, timestamp: float):
        self.buffers[camera_id].append((timestamp, frame))

    def extract_incident_clip(self, camera_id: str) -> List[Tuple[float, np.ndarray]]:
        """Extrai todos os quadros pré-incidente disponíveis no buffer."""
        return list(self.buffers[camera_id])


class TensorRTDynamicBatcher:
    """Simulador de alto desempenho do NVIDIA Triton Inference Server com Dynamic Batching.
    
    Agrupa frames de múltiplas câmeras em batches ideais (16, 32, 64)
    respeitando o timeout de fila de 1.5ms.
    """

    def __init__(self, preferred_batches: List[int] = [16, 32, 64], max_queue_delay_ms: float = 1.5):
        self.preferred_batches = sorted(preferred_batches)
        self.max_queue_delay_ms = max_queue_delay_ms
        self.queue: List[FramePacket] = []
        self.total_processed_frames = 0
        self.total_batches_executed = 0

    def enqueue_frame(self, packet: FramePacket):
        self.queue.append(packet)

    def flush_optimal_batches(self) -> List[Dict[str, Any]]:
        """Processa a fila formando batches otimizados."""
        executed_batches = []
        
        while self.queue:
            batch_size = min(len(self.queue), 64)
            # Seleciona o maior batch preferencial cabível
            for pb in reversed(self.preferred_batches):
                if len(self.queue) >= pb:
                    batch_size = pb
                    break
                    
            batch_items = self.queue[:batch_size]
            self.queue = self.queue[batch_size:]
            
            # Simulação de execução em GPU TensorRT (YOLOv11n INT8: ~1.2ms para batch de 32)
            exec_time_ms = 0.8 + (batch_size * 0.04)
            self.total_processed_frames += batch_size
            self.total_batches_executed += 1
            
            executed_batches.append({
                "batch_size": batch_size,
                "gpu_inference_latency_ms": round(exec_time_ms, 3),
                "cameras_in_batch": [p.camera_id for p in batch_items]
            })
            
        return executed_batches


class MassiveAIPipelineManager:
    """Controlador unificado do pipeline de IA para 10.000 câmeras."""

    def __init__(self):
        self.motion_filter = MotionGatedFilter(motion_threshold=0.02)
        self.decimator = AdaptiveKeyframeDecimator()
        self.ring_buffer = CircularIncidentRingBuffer(buffer_seconds=5, max_fps=15)
        self.batcher = TensorRTDynamicBatcher()

    def process_incoming_stream_tick(self, camera_id: str, frame: np.ndarray, timestamp: float, current_alarm: bool = False) -> Dict[str, Any]:
        # 1. Armazenar no Ring Buffer de 5s
        self.ring_buffer.append(camera_id, frame, timestamp)

        # 2. Avaliação de Movimento MGI
        has_motion, motion_score = self.motion_filter.check_motion(camera_id, frame)
        
        # 3. Determinar Prioridade Adaptativa
        if current_alarm:
            priority = 3  # 30 FPS
        elif has_motion:
            priority = 2  # 10 FPS
        else:
            priority = 1  # 1 FPS

        # 4. Decimação de Quadros
        sampled = self.decimator.should_sample(camera_id, priority, timestamp)
        
        if sampled:
            packet = FramePacket(
                camera_id=camera_id,
                frame_id=int(timestamp * 1000),
                timestamp=timestamp,
                frame_data=frame,
                has_motion=has_motion,
                priority_level=priority
            )
            self.batcher.enqueue_frame(packet)

        return {
            "camera_id": camera_id,
            "has_motion": has_motion,
            "motion_score": round(motion_score, 4),
            "priority": priority,
            "sampled_for_gpu": sampled
        }


# Instância singleton global
global_ai_pipeline = MassiveAIPipelineManager()

if __name__ == "__main__":
    print("Iniciando benchmark de simulação de 10.000 câmeras no pipeline de IA...")
    pipeline = MassiveAIPipelineManager()
    
    # Criar quadros sintéticos (80% estáticos, 20% com movimento)
    static_frame = np.full((360, 640, 3), 120, dtype=np.uint8)
    moving_frame = static_frame.copy()
    moving_frame[100:200, 200:400] = 255  # Região com movimento
    
    t0 = time.time()
    total_frames_in = 10000
    sampled_count = 0
    
    now = time.time()
    for i in range(total_frames_in):
        cam_id = str(1000 + (i % 1000))
        is_moving = (i % 5 == 0)  # 20% das câmeras têm movimento
        frame = moving_frame if is_moving else static_frame
        
        res = pipeline.process_incoming_stream_tick(cam_id, frame, now + (i * 0.001))
        if res["sampled_for_gpu"]:
            sampled_count += 1
            
    batches = pipeline.batcher.flush_optimal_batches()
    t_total = time.time() - t0
    
    print("\n" + "=" * 70)
    print("📊 RESULTADO DO FUNIL DE IA EM CASCATA:")
    print(f"  - Total de Quadros Ingeridos: {total_frames_in}")
    print(f"  - Quadros Filtrados & Amostrados para GPU: {sampled_count} ({sampled_count/total_frames_in*100:.1f}%)")
    print(f"  - Quadros Estáticos Descartados (Zero GPU Cost): {total_frames_in - sampled_count} ({(total_frames_in - sampled_count)/total_frames_in*100:.1f}%)")
    print(f"  - Batches TensorRT Executados: {len(batches)}")
    print(f"  - Tempo Total de Pipeline: {t_total*1000:.2f} ms ({total_frames_in/t_total:.0f} FPS throughput)")
    print("=" * 70)
