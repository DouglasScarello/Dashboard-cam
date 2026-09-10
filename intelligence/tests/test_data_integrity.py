"""
test_data_integrity.py — Olho de Deus

Regressão pro bug encontrado em 2026-09-10: `individuals.has_embedding` é
uma flag desnormalizada (só serve de atalho pra `stats()` não precisar de
JOIN) que deveria espelhar "existe uma linha real em face_embeddings pra
essa pessoa" — mas 19 indivíduos tinham embedding real e a flag continuava
0, fazendo `stats()['with_biometrics']` (usado pelo dashboard/API) contar
1023 quando o número real era 1042. Corrigido com um UPDATE de
reconciliação; este teste garante que não volta a divergir sem avisar.
"""
from intelligence_db import DB, init_db


def test_has_embedding_flag_matches_real_face_embeddings():
    init_db()
    db = DB()
    try:
        under_flagged = db.execute(
            """
            SELECT COUNT(*) as c FROM individuals i
            JOIN face_embeddings f ON f.individual_id = i.id
            WHERE f.embedding_blob IS NOT NULL
              AND (i.has_embedding IS NULL OR i.has_embedding != 1)
            """
        ).fetchone()["c"]
        over_flagged = db.execute(
            """
            SELECT COUNT(*) as c FROM individuals i
            WHERE i.has_embedding = 1
              AND NOT EXISTS (
                  SELECT 1 FROM face_embeddings f
                  WHERE f.individual_id = i.id AND f.embedding_blob IS NOT NULL
              )
            """
        ).fetchone()["c"]
    finally:
        db.close()

    assert under_flagged == 0, (
        f"{under_flagged} indivíduo(s) têm embedding facial real mas has_embedding != 1 — "
        "stats()['with_biometrics'] vai subestimar o total. Rodar a reconciliação: "
        "UPDATE individuals SET has_embedding = 1 WHERE id IN (SELECT i.id FROM individuals i "
        "JOIN face_embeddings f ON f.individual_id = i.id WHERE f.embedding_blob IS NOT NULL "
        "AND (i.has_embedding IS NULL OR i.has_embedding != 1))"
    )
    assert over_flagged == 0, (
        f"{over_flagged} indivíduo(s) têm has_embedding = 1 sem embedding facial real — "
        "stats()['with_biometrics'] vai superestimar o total (falso positivo, pior que subestimar)."
    )
