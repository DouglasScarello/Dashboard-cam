"""
test_biometric_pipeline.py — Olho de Deus

Testes de regressão pros bugs reais encontrados e corrigidos na sessão de
2026-09-09/10 (ver NOITE_AUTONOMA_2026-09-10.md pro relato completo de
cada achado). Roda contra o banco/índice REAIS do projeto — não são testes
unitários isolados com mocks, são testes de integração que confirmam que
o sistema de verdade funciona, não só que o código compila.

Uso:
    poetry run pytest tests/ -v
"""
import os
import sys
import sqlite3
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))
sys.path.insert(0, str(ROOT / "olho_de_deus"))

import numpy as np
import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_conn():
    db_path = ROOT / "intelligence" / "data" / "intelligence.db"
    if not db_path.exists():
        pytest.skip("intelligence.db não existe — rodar pipeline_ingestao.py primeiro")
    con = sqlite3.connect(str(db_path))
    yield con
    con.close()


@pytest.fixture(scope="module")
def sample_mugshot_path(db_conn):
    """Um caminho de foto real (mugshot classificado pelo CLIP) pra testar contra."""
    row = db_conn.execute(
        "SELECT img_path FROM individuals WHERE image_content_type = 'a mugshot photo of one person' "
        "AND img_path IS NOT NULL LIMIT 1"
    ).fetchone()
    if not row:
        pytest.skip("nenhum mugshot classificado disponível")
    path = ROOT / "intelligence" / "data" / row[0]
    if not path.exists():
        pytest.skip(f"arquivo não existe: {path}")
    return path


# ─── Bug 1: register_match_log faltando (quebrava import de live_pipeline.py) ──

def test_register_match_log_exists_and_works(db_conn, tmp_path):
    from intelligence_db import DB, register_match_log

    db = DB()
    # Não usa individual_id real de propósito — só confirma que a função roda
    # sem lançar exceção e que o INSERT realmente aconteceu.
    register_match_log(db, "test-uid-regressao", 0.5, 0.8, "MEDIUM", camera_id="test-cam")
    row = db_conn.execute(
        "SELECT distance, probability, confidence, camera_id FROM match_logs "
        "WHERE individual_id = 'test-uid-regressao' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row == (0.5, 0.8, "MEDIUM", "test-cam")
    db_conn.execute("DELETE FROM match_logs WHERE individual_id = 'test-uid-regressao'")
    db_conn.commit()
    db.close()


# ─── Bug 2: FAISS IndexIDMap x metadata (lista vs dict) fora de sincronia ──────

def test_vector_metadata_is_dict_keyed_by_faiss_id():
    import json
    meta_path = ROOT / "intelligence" / "data" / "vector_metadata.json"
    if not meta_path.exists():
        pytest.skip("vector_metadata.json não existe ainda")
    with open(meta_path) as f:
        meta = json.load(f)
    assert isinstance(meta, dict), "metadata precisa ser dict (chave = id do FAISS), não lista posicional"
    assert len(meta) > 0
    sample_key, sample_val = next(iter(meta.items()))
    assert "uid" in sample_val and "title" in sample_val


# ─── Bug 3 (o mais grave): embeddings nunca eram L2-normalizados ───────────────

def test_faiss_upsert_normalizes_before_indexing():
    """
    O índice real usa faiss.IndexIDMap (não IndexIDMap2), que não suporta
    reconstruct() por ID arbitrário pra inspecionar vetores já salvos — então
    testamos o comportamento de normalização direto no ponto onde ele acontece
    (FaissIDMap.upsert(), delta_embedder.py), com um índice descartável.
    """
    from delta_embedder import FaissIDMap

    fidx = FaissIDMap()
    fidx.index = __import__("faiss").IndexIDMap(__import__("faiss").IndexFlatL2(FaissIDMap.DIM))

    # Embedding propositalmente NÃO normalizado (norma bem longe de 1.0) — é
    # exatamente essa condição que o bug original deixava passar direto pro
    # FAISS sem normalizar, dando distância crua de match ~2-3 em vez de <1.
    fake_embedding = np.random.RandomState(42).normal(size=FaissIDMap.DIM).astype("float32") * 5.0
    assert not np.isclose(np.linalg.norm(fake_embedding), 1.0, atol=0.1)

    fidx.upsert("uid-teste-normalizacao", fake_embedding, "Nome Teste")

    int_id = fidx._id_to_uid.__class__ and list(fidx._id_to_uid.keys())[0]
    stored_vec = fidx.index.index.reconstruct(0)  # índice interno (IndexFlatL2) é sequencial
    norm = np.linalg.norm(stored_vec)
    assert abs(norm - 1.0) < 1e-3, (
        f"vetor salvo no índice tem norma {norm:.3f}, deveria ser ~1.0 — "
        "sem normalizar, distância de match nunca cai dentro de nenhum threshold "
        "razoável (achado crítico da sessão, ver NOITE_AUTONOMA_2026-09-10.md)"
    )


# ─── Bug: opencv/Haar Cascade dava falso positivo de múltiplos rostos ──────────

def test_retinaface_used_not_opencv_haar():
    """Confere que delta_embedder.py não voltou a usar o detector_backend='opencv'
    (Haar Cascade) — regressão fácil de reintroduzir sem querer numa limpeza futura."""
    src = (ROOT / "olho_de_deus" / "delta_embedder.py").read_text()
    assert 'detector_backend="retinaface"' in src
    assert 'detector_backend="opencv"' not in src


# ─── YuNet: detecção + alinhamento na pipeline ao vivo ─────────────────────────

def test_yunet_detects_and_aligns_real_face(sample_mugshot_path):
    import cv2
    from biometric_processor import _detect_and_align_face

    model_path = ROOT / "olho_de_deus" / "models" / "face_detection_yunet_2023mar.onnx"
    if not model_path.exists():
        pytest.skip("modelo YuNet não baixado — ver comando em NOITE_AUTONOMA_2026-09-10.md")

    fd = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), score_threshold=0.6)
    img = cv2.imread(str(sample_mugshot_path))
    aligned = _detect_and_align_face(fd, img)

    assert aligned is not None, "YuNet não achou rosto num mugshot real — regressão de detecção"
    assert aligned.shape == (112, 112, 3), "saída tem que ser 112x112 (template ArcFace padrão)"


def test_download_validator_rejects_non_image_bytes():
    """Bug real: Accept header pedia webp, servidor mandava WebP disfarçado de
    .jpg — ~150 arquivos corrompidos silenciosamente até a validação existir."""
    sys.path.insert(0, str(ROOT / "intelligence"))
    from download_fbi_photos import _is_real_image

    real_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    real_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    fake_html = b"<!DOCTYPE html><html>"
    fake_webp = b"RIFF" + b"\x00" * 4 + b"WEBPVP8 "

    assert _is_real_image(real_jpeg) is True
    assert _is_real_image(real_png) is True
    assert _is_real_image(fake_html) is False
    assert _is_real_image(fake_webp) is False


# ─── Person ReID: pesos reais, não fallback ImageNet ───────────────────────────

def test_person_reid_loads_real_market1501_weights():
    from person_reid import PersonReID, DEFAULT_WEIGHTS

    if not DEFAULT_WEIGHTS.exists():
        pytest.skip(f"pesos não baixados — ver comando gdown em NOITE_AUTONOMA_2026-09-10.md")

    reid = PersonReID()
    vec = reid.extract(np.zeros((256, 128, 3), dtype=np.uint8))
    assert vec.shape == (512,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-3


def test_person_reid_same_image_scores_higher_than_different(sample_mugshot_path, db_conn):
    import cv2
    from person_reid import PersonReID, DEFAULT_WEIGHTS

    if not DEFAULT_WEIGHTS.exists():
        pytest.skip("pesos Market-1501 não baixados")

    other_row = db_conn.execute(
        "SELECT img_path FROM individuals WHERE image_content_type = 'a mugshot photo of one person' "
        "AND img_path IS NOT NULL LIMIT 1 OFFSET 5"
    ).fetchone()
    if not other_row:
        pytest.skip("não há uma segunda foto pra comparar")

    reid = PersonReID()
    img_a = cv2.imread(str(sample_mugshot_path))
    img_b = cv2.imread(str(ROOT / "intelligence" / "data" / other_row[0]))

    vec_a1 = reid.extract(img_a)
    vec_a2 = reid.extract(img_a)  # mesma imagem de novo
    vec_b = reid.extract(img_b)

    sim_same = PersonReID.cosine_similarity(vec_a1, vec_a2)
    sim_diff = PersonReID.cosine_similarity(vec_a1, vec_b)

    assert sim_same > 0.99, "mesma imagem deveria dar similaridade ~1.0"
    assert sim_same > sim_diff, "mesma imagem tem que ser mais parecida consigo mesma que com outra pessoa"


# ─── Smoke test — health_check.py roda e não acusa problema ────────────────────

def test_health_check_reports_no_problems():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "olho_de_deus" / "health_check.py")],
        capture_output=True, text=True, timeout=120,
    )
    assert "TUDO FUNCIONAL" in result.stdout, (
        f"health_check.py encontrou problema(s):\n{result.stdout[-2000:]}"
    )
