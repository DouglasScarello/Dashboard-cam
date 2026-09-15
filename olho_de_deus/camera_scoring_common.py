"""
camera_scoring_common.py — Olho de Deus

Infra compartilhada entre a triagem de aptidão de câmera pra ALPR (placa,
`score_camera_alpr.py`) e pra reconhecimento facial (rosto,
`score_camera_face.py`), e o lote que roda isso no catálogo inteiro
(`camera_scoring_batch.py`).

Por que existe (2026-09-15): rodar os dois scorers completos (N frames, 2
estágios de detecção cada) em todas as ~8038 câmeras do catálogo levaria
dezenas de horas — a maior parte gasta em câmeras óbvias (nunca aparece
gente nem veículo, câmera de fachada/paisagem/estacionamento vazio). Este
módulo dá o pré-filtro barato (Estágio A do lote): 1 chamada YOLO por
frame com pessoa+veículo juntos na mesma lista de classes, em vez de 2
chamadas separadas — só pra saber se vale a pena gastar o score completo
(Estágio B) numa câmera. O Estágio B em si reaproveita `avalia_camera` de
`score_camera_alpr.py`/`score_camera_face.py` sem modificação — cada um
continua rodando sua própria detecção de 2 estágios exatamente como já
validado, só que agora limitado à fração do catálogo que passou pelo
pré-filtro.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from liveness_common import DB_PATH, status_de_liveness

PESSOA_CLASSE = 0
VEICULO_CLASSES = [2, 3, 5, 7]
CLASSES_COMBINADAS = [PESSOA_CLASSE] + VEICULO_CLASSES

# Achado (2026-09-15, testando o Estágio A pela primeira vez com
# concorrência real): um singleton global com "if None: cria" não é
# thread-safe — em `camera_scoring_batch.py` (ThreadPoolExecutor), 3
# threads chegaram simultaneamente antes da primeira terminar de atribuir
# a variável global, e cada uma carregou sua própria cópia do modelo
# (visto no log: "Loading ... for OpenVINO inference" 3x). Thread-local
# resolve isso sem lock: cada thread carrega e reusa a SUA própria
# instância, sem estado compartilhado — também evita qualquer dúvida sobre
# segurança de chamadas concorrentes no mesmo objeto YOLO/OpenVINO.
_thread_local = threading.local()


def _get_detector_combinado():
    detector = getattr(_thread_local, "detector", None)
    if detector is None:
        from ultralytics import YOLO
        modelo = str(Path(__file__).resolve().parent / "yolov8n_openvino_model")
        detector = YOLO(modelo, task="detect")
        _thread_local.detector = detector
    return detector


def detecta_pessoas_e_veiculos(frame: np.ndarray) -> Tuple[List[Tuple[int, int, int, int]],
                                                             List[Tuple[int, int, int, int]]]:
    """1 chamada YOLO só (classes pessoa+veículo juntas) em vez de 2 — só
    faz sentido pro Estágio A do lote, onde o volume (catálogo inteiro)
    torna o custo de 2 inferências por frame significativo. Retorna
    (caixas_pessoa, caixas_veiculo) em coordenadas do frame original.
    conf=0.4 é deliberadamente mais permissivo que os 0.5 (rosto) / 0.3
    (placa) dos scorers completos — aqui o objetivo é só "tem algo aqui
    que vale a pena investigar de verdade no Estágio B", não uma decisão
    final; falso positivo custa 1 câmera a mais no Estágio B, falso
    negativo custa a câmera inteira descartada sem chance."""
    altura, largura = frame.shape[:2]
    pequeno = cv2.resize(frame, (320, 320))
    sx, sy = largura / 320.0, altura / 320.0
    deteccoes = _get_detector_combinado()(pequeno, verbose=False, conf=0.4, iou=0.45,
                                           classes=CLASSES_COMBINADAS)[0]
    pessoas: List[Tuple[int, int, int, int]] = []
    veiculos: List[Tuple[int, int, int, int]] = []
    for b in deteccoes.boxes:
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        caixa = (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))
        classe = int(b.cls[0])
        if classe == PESSOA_CLASSE:
            pessoas.append(caixa)
        else:
            veiculos.append(caixa)
    return pessoas, veiculos


def garante_schema_scoring(conn: sqlite3.Connection) -> None:
    """Colunas do veredito FINAL de aptidão (resultado do Estágio B).
    O resultado intermediário do Estágio A fica em tabela própria (ver
    `garante_tabela_estagio_a`) — misturar "ainda não avaliado a fundo" com
    "confirmado sem gente/veículo" na mesma coluna criaria a mesma
    ambiguidade que já causou bug em `confirmed_dead` (ver
    liveness_common.py) — vale a lição, mesmo padrão evitado aqui de
    propósito."""
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(cameras)")}
    novas = {
        "alpr_veredito": "TEXT",
        "alpr_largura_placa_media": "REAL",
        "face_veredito": "TEXT",
        "face_interocular_medio": "REAL",
        "scored_at": "TEXT",
    }
    for nome, tipo in novas.items():
        if nome not in colunas:
            conn.execute(f"ALTER TABLE cameras ADD COLUMN {nome} {tipo}")


def garante_tabela_estagio_a(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS camera_scoring_estagio_a (
            camera_id TEXT PRIMARY KEY,
            frames_checados INTEGER,
            frames_com_pessoa INTEGER,
            frames_com_veiculo INTEGER,
            promissora_placa INTEGER,
            promissora_rosto INTEGER,
            checked_at TEXT
        )
    """)


def buscar_candidatas_scoring(conn: sqlite3.Connection, apenas_nao_pontuadas: bool = True,
                               limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Câmeras elegíveis pra triagem de aptidão: precisam estar
    genuinamente VIVAS (reaproveita `status_de_liveness` — a MESMA regra
    usada pra decidir online/offline na API pública, ver
    liveness_common.py, não uma cópia) — gastar minutos de captura+YOLO
    numa câmera confirmada morta ou nunca checada é desperdício certo.
    Exclui candidatas de teste (`is_test_candidate`), que já têm seu
    próprio fluxo manual via `--camera-id` nos dois scorers.

    O filtro de liveness é aplicado em Python (não dá pra fazer via SQL —
    `status_de_liveness` depende do gate de streak, não é uma coluna
    crua), então o LIMIT também é aplicado em Python, depois do filtro —
    aplicar LIMIT antes no SQL devolveria menos que `limit` candidatas
    reais sempre que a amostra pegar câmera não-viva no meio."""
    query = """
        SELECT * FROM cameras
        WHERE (is_test_candidate IS NULL OR is_test_candidate = 0)
          AND url IS NOT NULL AND url != ''
    """
    if apenas_nao_pontuadas:
        query += " AND scored_at IS NULL"
    cameras = [dict(r) for r in conn.execute(query).fetchall()]
    vivas = [c for c in cameras if status_de_liveness(c) == "LIVE"]
    return vivas[:limit] if limit else vivas


def salvar_resultado_scoring(conn: sqlite3.Connection, camera_id: str,
                              alpr_veredito: Optional[str], alpr_largura: Optional[float],
                              face_veredito: Optional[str], face_interocular: Optional[float]) -> None:
    with conn:
        conn.execute(
            """UPDATE cameras
               SET alpr_veredito = ?, alpr_largura_placa_media = ?,
                   face_veredito = ?, face_interocular_medio = ?,
                   scored_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (alpr_veredito, alpr_largura, face_veredito, face_interocular, camera_id),
        )
