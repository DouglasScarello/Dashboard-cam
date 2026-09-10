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

def test_multiface_recovers_dominant_face_when_size_disparity_is_large(db_conn):
    """
    Revisão manual de 9 casos reais (2026-09-10, ver NOITE_AUTONOMA_2026-09-10.md):
    quando há 2+ rostos na imagem mas um é >=10x maior em área, sempre era o
    assunto principal + artefato pequeno (pessoa ao fundo, foto de carteira na
    mão) — nunca uma foto genuína de 2 pessoas (essas ficam em 1x-2.3x). Esse
    caso (Thomas Crane Wales) tem razão ~59x — tem que recuperar e reconhecer
    ele mesmo, não ficar de fora.
    """
    row = db_conn.execute(
        "SELECT has_embedding FROM individuals WHERE id = '3a3ec6ff4ecd1c5aac9a7f2380eccd47'"
    ).fetchone()
    if row is None:
        pytest.skip("indivíduo de teste não está no banco (FBI não ingerido ainda)")
    if row[0] != 1:
        pytest.skip("ainda não reprocessado com a lógica de recuperação — rodar extract_embeddings.py")

    import cv2
    from biometric_processor import BiometricProcessor, _detect_and_align_face

    img_path = ROOT / "intelligence" / "data" / "fbi_faces" / "3a3ec6ff4ecd1c5aac9a7f2380eccd47.jpg"
    if not img_path.exists():
        pytest.skip("foto de teste não baixada")

    bp = BiometricProcessor()
    img = cv2.imread(str(img_path))
    aligned = _detect_and_align_face(bp.face_detector, img)
    assert aligned is not None
    _, match = bp._identify(aligned)
    assert match is not None and match["uid"] == "3a3ec6ff4ecd1c5aac9a7f2380eccd47"


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


# ─── Bug real: CAP_FFMPEG não abre webcam nesse sistema (silenciosamente) ──────

def test_webcam_capture_uses_correct_backend():
    """
    monitor_camera.py --webcam N é a via de teste recomendada ao usuário quando
    não há câmera real de catálogo à mão. Achado em auto-revisão: _capture_loop
    usava cv2.CAP_FFMPEG pra TODAS as fontes, inclusive webcam — mas FFMPEG
    precisa de libavdevice (esse build do OpenCV não tem) e falha silenciosamente
    (isOpened()=False) pra dispositivo de câmera local. Testado que precisa do
    backend padrão (auto-detect/V4L2) e do índice como int, não string.
    """
    import cv2
    if not Path("/dev/video0").exists():
        pytest.skip("sem dispositivo de webcam nesse ambiente")

    cap_ffmpeg = cv2.VideoCapture(0, cv2.CAP_FFMPEG)
    ffmpeg_works = cap_ffmpeg.isOpened()
    cap_ffmpeg.release()

    cap_default = cv2.VideoCapture(0)
    default_works = cap_default.isOpened()
    cap_default.release()

    assert default_works, "backend padrão deveria conseguir abrir a webcam"
    # Documenta a limitação real do ambiente (não é bug do nosso código, é do
    # build do OpenCV) — se algum dia isso passar a True, tudo bem, só significa
    # que o ambiente ganhou libavdevice; o importante é que _capture_loop já
    # trata os dois casos corretamente (ver source_type == "webcam" em live_pipeline.py).
    src = (ROOT / "olho_de_deus" / "live_pipeline.py").read_text()
    assert 'if self.source_type == "webcam"' in src, (
        "live_pipeline.py precisa branch especial pra webcam — sem isso, "
        f"CAP_FFMPEG falha silenciosamente nesse ambiente (funciona={ffmpeg_works})"
    )


# ─── Score de periculosidade: selo "ARMED AND DANGEROUS" força piso alto ──────
# (score_engine.py, mexido nesta sessão pra ligar o badge no frontend —
# AlertCenter.tsx — mas nunca tinha teste de regressão. Roda contra o banco
# real: um caso que a FBI marcou como "armed and dangerous" de verdade, e um
# caso de fraude não-violenta como contraste, pra confirmar que o piso de 9.0
# não vira "todo mundo tira nota alta".)

def test_armed_and_dangerous_forces_high_score(db_conn):
    from intelligence_db import DB
    from score_engine import ThreatScorer

    row = db_conn.execute(
        "SELECT id FROM individuals WHERE description LIKE '%ARMED AND DANGEROUS%' LIMIT 1"
    ).fetchone()
    if not row:
        pytest.skip("nenhum indivíduo com selo 'ARMED AND DANGEROUS' no banco atual")

    db = DB()
    score = ThreatScorer(db).calculate_individual_score(row[0])
    db.close()

    assert score >= 9.0, f"selo ARMED AND DANGEROUS deveria forçar score >= 9.0, veio {score}"


def test_non_violent_fraud_does_not_get_armed_dangerous_score(db_conn):
    from intelligence_db import DB
    from score_engine import ThreatScorer

    row = db_conn.execute(
        "SELECT id FROM individuals WHERE description NOT LIKE '%ARMED AND DANGEROUS%' "
        "AND description NOT LIKE '%CONSIDERED DANGEROUS%' "
        "AND (description LIKE '%FRAUD%' OR description LIKE '%FURTO%' OR description LIKE '%THEFT%') "
        "LIMIT 1"
    ).fetchone()
    if not row:
        pytest.skip("nenhum indivíduo de fraude/furto sem selo armado no banco atual")

    db = DB()
    score = ThreatScorer(db).calculate_individual_score(row[0])
    db.close()

    assert score < 9.0, (
        f"caso de fraude/furto sem selo 'armed and dangerous' não deveria bater o piso "
        f"de 9.0 reservado pra ameaça física confirmada pela fonte, veio {score}"
    )


# ─── Catálogo real de câmeras: seleção de modo de captura (Workstream 2) ──────
# monitor_camera.py liga o LivePipeline numa câmera de database/live_cameras.db
# (8198 câmeras reais) mas nunca tinha teste — só foi verificado manualmente
# uma vez, contra 1 câmera HLS da Caltrans (ver plano/log). Testa contra o
# catálogo de verdade: uma câmera SNAPSHOT_JPEG real (ex: 511 Ontario) e uma
# M3U8/HLS real (ex: Caltrans), confirmando que db_manager.get_camera_by_id +
# resolve_source_type escolhem o modo certo pras duas.

def test_camera_catalog_resolves_snapshot_and_direct_modes():
    import db_manager
    from monitor_camera import resolve_source_type

    conn = db_manager.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM cameras WHERE stream_format = 'SNAPSHOT_JPEG' LIMIT 1")
    snapshot_row = cur.fetchone()
    cur.execute(
        "SELECT id FROM cameras WHERE stream_format != 'SNAPSHOT_JPEG' AND url LIKE '%.m3u8%' LIMIT 1"
    )
    hls_row = cur.fetchone()
    conn.close()

    if not snapshot_row or not hls_row:
        pytest.skip("catálogo de câmeras não tem os dois tipos de amostra esperados")

    snapshot_cam = db_manager.get_camera_by_id(snapshot_row["id"])
    hls_cam = db_manager.get_camera_by_id(hls_row["id"])

    assert snapshot_cam is not None and "url" in snapshot_cam and "nome" in snapshot_cam
    assert hls_cam is not None and "url" in hls_cam

    assert resolve_source_type(snapshot_cam) == "snapshot_jpeg", (
        "câmera SNAPSHOT_JPEG real do catálogo precisa cair no modo de polling HTTP, "
        "senão cv2.VideoCapture tenta ler uma URL de foto única como se fosse stream de vídeo"
    )
    assert resolve_source_type(hls_cam) == "direct", (
        "câmera M3U8/HLS real do catálogo precisa cair no modo de captura contínua"
    )


# ─── Cadastro manual da watchlist pessoal (Workstream 1) ───────────────────────
# enroll_person.py foi o pedido ORIGINAL do usuário (antes de pivotar pra usar
# a lista do FBI) — cadastro manual de gente autorizada, category="watchlist".
# Nunca teve teste de regressão nenhum, apesar de ser um caminho de código
# real e ainda disponível (poetry run python3 enroll_person.py --name ...).

def test_enroll_person_creates_watchlist_entry_and_copies_photo(sample_mugshot_path):
    import shutil
    from intelligence_db import DB, init_db
    import enroll_person

    init_db()
    test_name = "Teste Regressão Watchlist Pessoal"
    uid = enroll_person.generate_deterministic_uid(test_name)
    dest_photo = enroll_person.PHOTO_DIR / f"{uid}.jpg"

    try:
        enroll_person.enroll(test_name, [str(sample_mugshot_path)], relationship="teste automatizado")

        assert dest_photo.exists(), "enroll_person.py deveria copiar a foto pra watchlist_photos/"

        db = DB()
        row = db.execute(
            "SELECT category, source, img_path FROM individuals WHERE id = ?", (uid,)
        ).fetchone()
        db.close()
        assert row is not None, "cadastro não gravou o indivíduo no banco"
        assert row["category"] == "watchlist"
        assert row["source"] == "manual"
        assert row["img_path"] == f"watchlist_photos/{uid}.jpg"
    finally:
        db = DB()
        db.execute("DELETE FROM individuals WHERE id = ?", (uid,))
        db.execute("DELETE FROM individual_images WHERE individual_id = ?", (uid,))
        db.commit()
        db.close()
        if dest_photo.exists():
            dest_photo.unlink()


def test_enroll_person_rejects_reserved_fbi_categories():
    import enroll_person

    for reserved in enroll_person.RESERVED_CATEGORIES:
        with pytest.raises(SystemExit):
            enroll_person.enroll("Teste Categoria Reservada", ["/nao/importa.jpg"], category=reserved)
