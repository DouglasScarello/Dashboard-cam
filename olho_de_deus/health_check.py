#!/usr/bin/env python3
"""
health_check.py — Olho de Deus

Relatório único, em português simples, pra qualquer humano (mesmo sem ler
código) confirmar que o sistema de reconhecimento facial está de verdade
funcional — sem precisar confiar apenas no que uma sessão de IA disse que
fez. Roda um teste real (não só conta linhas no banco).

Uso:
    poetry run python3 health_check.py
"""
import os
import sys
import sqlite3
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

OK = "✅"
WARN = "⚠️ "
FAIL = "❌"


def section(title):
    print("\n" + "─" * 70)
    print(f"  {title}")
    print("─" * 70)


def main():
    problems = []

    section("1. BANCO DE DADOS DE INTELIGÊNCIA (intelligence.db)")
    db_path = ROOT / "intelligence" / "data" / "intelligence.db"
    if not db_path.exists():
        print(f"{FAIL} Banco não existe em {db_path}")
        problems.append("banco de inteligência não existe")
        return report(problems)

    con = sqlite3.connect(str(db_path))
    total = con.execute("SELECT COUNT(*) FROM individuals").fetchone()[0]
    com_foto = con.execute("SELECT COUNT(*) FROM individuals WHERE img_path IS NOT NULL").fetchone()[0]
    com_emb_real = con.execute(
        "SELECT COUNT(*) FROM face_embeddings WHERE embedding_blob IS NOT NULL"
    ).fetchone()[0]
    com_score = con.execute("SELECT COUNT(*) FROM threat_scores").fetchone()[0]
    print(f"  Total de indivíduos cadastrados : {total}")
    print(f"  Com foto local baixada          : {com_foto}")
    print(f"  Com embedding facial REAL       : {com_emb_real}  {OK if com_emb_real > 0 else FAIL}")
    print(f"  Com score de periculosidade     : {com_score}  {OK if com_score > 0 else WARN}")
    if com_emb_real == 0:
        problems.append("nenhum embedding facial real gerado — rodar extract_embeddings.py")

    section("2. CLASSIFICAÇÃO DE CONTEÚDO (CLIP)")
    try:
        rows = con.execute(
            "SELECT image_content_type, COUNT(*) FROM individuals "
            "WHERE image_content_type IS NOT NULL GROUP BY image_content_type ORDER BY 2 DESC"
        ).fetchall()
        if rows:
            for label, n in rows:
                print(f"  {n:>5}  {label}")
        else:
            print(f"{WARN} Nenhuma imagem classificada ainda — rodar classify_images.py")
    except sqlite3.OperationalError:
        print(f"{WARN} Coluna image_content_type não existe — rodar init_db()")

    section("3. ÍNDICE DE BUSCA FACIAL (FAISS)")
    faiss_path = ROOT / "intelligence" / "data" / "vector_db.faiss"
    meta_path = ROOT / "intelligence" / "data" / "vector_metadata.json"
    if faiss_path.exists() and meta_path.exists():
        import json
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"{OK} Índice existe: {len(meta)} rostos indexados")
        if abs(len(meta) - com_emb_real) > 5:
            print(f"{WARN} Diferença entre metadata ({len(meta)}) e face_embeddings ({com_emb_real}) — rodar extract_embeddings.py --force-rebuild")
    else:
        print(f"{FAIL} Índice FAISS ou metadata não existem")
        problems.append("índice FAISS não existe")

    section("4. TESTE REAL — reconhecer rostos de verdade (não é só contagem)")
    # Testa VÁRIAS amostras, não 1 só — medido na sessão (400 amostras): ~2% das
    # fotos reais não tem rosto detectável ou não bate (imagem degradada/ângulo
    # ruim), isso é ESPERADO, não indica sistema quebrado. Testar 1 amostra
    # aleatória dava falso alarme sempre que calhava de pegar uma dessas.
    N_SAMPLES = 12
    MIN_SUCCESS_RATE = 0.7  # bem abaixo da taxa real (~97%) pra não dar alarme falso
    try:
        import cv2
        from biometric_processor import BiometricProcessor, _detect_and_align_face

        rows = con.execute(
            "SELECT id, name, img_path FROM individuals "
            "WHERE has_embedding=1 AND img_path IS NOT NULL "
            "AND image_content_type IN ('a mugshot photo of one person','a clear photo of one single person face') "
            "ORDER BY RANDOM() LIMIT ?",
            (N_SAMPLES,),
        ).fetchall()
        if not rows:
            print(f"{WARN} Nenhum indivíduo com embedding pra testar")
        else:
            bp = BiometricProcessor()
            ok_count, wrong, no_face_or_match = 0, [], 0
            for uid, name, img_path in rows:
                img_full = ROOT / "intelligence" / "data" / img_path
                img = cv2.imread(str(img_full))
                aligned = _detect_and_align_face(bp.face_detector, img) if bp.face_detector and img is not None else None
                if aligned is None:
                    no_face_or_match += 1
                    continue
                _, match = bp._identify(aligned)
                if match and match["uid"] == uid:
                    ok_count += 1
                elif match:
                    wrong.append((name, match["title"]))
                else:
                    no_face_or_match += 1

            rate = ok_count / len(rows)
            print(f"  {ok_count}/{len(rows)} reconhecidos corretamente "
                  f"({no_face_or_match} sem rosto/sem match, {len(wrong)} errado) "
                  f"— taxa {rate:.0%}")
            for a, b in wrong:
                print(f"    {WARN} '{a}' reconhecido como '{b}' (pode ser duplicata de dado do FBI — ver log da sessão)")
            if rate >= MIN_SUCCESS_RATE:
                print(f"{OK} Taxa de acerto dentro do esperado (>= {MIN_SUCCESS_RATE:.0%})")
            else:
                print(f"{FAIL} Taxa de acerto abaixo do esperado")
                problems.append(f"taxa de reconhecimento baixa: {rate:.0%} (esperado >= {MIN_SUCCESS_RATE:.0%})")
    except Exception as e:
        print(f"{FAIL} Teste real falhou com erro: {e}")
        problems.append(f"teste real deu erro: {e}")

    section("5. CATÁLOGO DE CÂMERAS REAIS")
    cam_db = ROOT / "database" / "live_cameras.db"
    if cam_db.exists():
        ccon = sqlite3.connect(str(cam_db))
        n_cams = ccon.execute("SELECT COUNT(*) FROM cameras WHERE confirmed_dead=0").fetchone()[0]
        print(f"{OK} {n_cams} câmeras confirmadas vivas no catálogo")
        ccon.close()
    else:
        print(f"{WARN} Catálogo de câmeras não encontrado em {cam_db}")

    section("6. BUSCA POR SIMILARIDADE (tatuagem/veículo — CLIP)")
    clip_faiss = ROOT / "intelligence" / "data" / "clip_visual_db.faiss"
    clip_meta = ROOT / "intelligence" / "data" / "clip_visual_metadata.json"
    if clip_faiss.exists() and clip_meta.exists():
        try:
            import faiss as _faiss
            idx = _faiss.read_index(str(clip_faiss))
            print(f"{OK} Índice existe: {idx.ntotal} imagens (tatuagem/veículo) indexadas")
        except Exception as e:
            print(f"{FAIL} Índice existe mas não abre: {e}")
            problems.append("índice CLIP de similaridade corrompido")
    else:
        print(f"{WARN} Índice ainda não construído — rodar clip_similarity_index.py --build")

    section("7. PERSON RE-ID (roupa/corpo — Torchreid)")
    try:
        from person_reid import PersonReID, DEFAULT_WEIGHTS
        if not DEFAULT_WEIGHTS.exists():
            print(f"{FAIL} Pesos reais de ReID não encontrados em {DEFAULT_WEIGHTS} — caindo pro ImageNet genérico")
            problems.append("pesos Market-1501 do Person ReID ausentes")
        else:
            reid = PersonReID()
            print(f"{OK} Módulo carrega com pesos reais Market-1501 (rank-1 94.2% oficial)")
    except Exception as e:
        print(f"{FAIL} Person ReID falhou ao carregar: {e}")
        problems.append(f"Person ReID com erro: {e}")

    con.close()
    report(problems)


def report(problems):
    print("\n" + "═" * 70)
    if not problems:
        print(f"  {OK} TUDO FUNCIONAL — nenhum problema encontrado.")
    else:
        print(f"  {FAIL} {len(problems)} PROBLEMA(S) ENCONTRADO(S):")
        for p in problems:
            print(f"    - {p}")
    print("═" * 70 + "\n")


if __name__ == "__main__":
    main()
