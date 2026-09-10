"""
test_module_imports.py — Olho de Deus

Regressão pro bug encontrado em 2026-09-10: intelligence/pyproject.toml
declarava só 6 das ~10 dependências reais, e o venv do poetry tinha sido
criado em Python 3.14 (sem wheel pra torchvision/tensorflow/faiss-cpu
antigos) — então TODO script daqui, mesmo seguindo exatamente o
`poetry run python3 script.py` documentado no próprio docstring de cada
um, falhava na primeira linha com ModuleNotFoundError.

Este teste importa (não executa) cada entrypoint real da esteira de
ingestão (ver pipeline_ingestao.py) pra garantir que o ambiente poetry
consegue mesmo rodar o que promete.
"""
import importlib

import pytest

ENTRYPOINT_MODULES = [
    "intelligence_db",
    "populate_db",
    "download_fbi_photos",
    "classify_images",
    "ocr_documents",
    "clip_similarity_index",
    "pipeline_ingestao",
    "enroll_person",
]


@pytest.mark.parametrize("module_name", ENTRYPOINT_MODULES)
def test_entrypoint_imports_cleanly(module_name):
    importlib.import_module(module_name)


def test_db_connects_and_has_real_data():
    from intelligence_db import DB, init_db

    init_db()
    db = DB()
    try:
        cur = db.execute("SELECT COUNT(*) as c FROM individuals")
        count = cur.fetchone()["c"]
        assert count > 0, "banco de inteligência está vazio — ingestão nunca rodou"
    finally:
        db.close()
