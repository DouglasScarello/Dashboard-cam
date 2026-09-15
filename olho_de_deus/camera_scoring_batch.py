"""
camera_scoring_batch.py — Olho de Deus

Roda a triagem de aptidão (ALPR + reconhecimento facial) no catálogo
inteiro, em 2 estágios — pra não gastar N frames × 2 pipelines completos
em milhares de câmeras óbvias (sem gente nem veículo visível). Ver plano
aprovado em 2026-09-15 ("triagem de aptidão das câmeras pra ALPR e
reconhecimento facial").

Estágio A (barato, catálogo inteiro): 1-2 frames por câmera, 1 chamada
YOLO combinada (pessoa+veículo — ver camera_scoring_common.py), só grava
"apareceu gente/veículo alguma vez" numa tabela auxiliar
(`camera_scoring_estagio_a`). Não decide veredito final.

Estágio B (completo, só nas promissoras do Estágio A): reaproveita
`avalia_camera()` de `score_camera_alpr.py`/`score_camera_face.py` SEM
MODIFICAÇÃO — cada um roda a própria detecção de 2 estágios exatamente
como já validado manualmente, agora só limitado à fração do catálogo que
vale a pena. Escreve o veredito final nas colunas de `cameras`
(`alpr_veredito`, `face_veredito`, etc. — ver garante_schema_scoring).

Escreve incrementalmente, câmera por câmera — uma varredura de horas
rodando em background precisa sobreviver a uma interrupção (suspensão do
notebook, queda de wifi) sem perder o trabalho já feito. Por padrão só
processa quem ainda não tem `scored_at` (resume automático); `--forcar`
ignora isso.

Uso:
    # Estágio A — barato, teste numa amostra pequena antes do catálogo inteiro
    poetry run python3 camera_scoring_batch.py estagio-a --limit 50 --dry-run
    poetry run python3 camera_scoring_batch.py estagio-a --limit 50
    poetry run python3 camera_scoring_batch.py estagio-a          # catálogo inteiro

    # Estágio B — completo, só nas promissoras do Estágio A
    poetry run python3 camera_scoring_batch.py estagio-b --limit 10 --dry-run
    poetry run python3 camera_scoring_batch.py estagio-b          # promissoras inteiras
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import cv2
import numpy as np

from camera_grid_server import _capture_real_frame_jpeg
from camera_scoring_common import (
    DB_PATH,
    buscar_candidatas_scoring,
    detecta_pessoas_e_veiculos,
    garante_schema_scoring,
    garante_tabela_estagio_a,
    salvar_resultado_scoring,
)

FRAMES_ESTAGIO_A = 2
INTERVALO_ESTAGIO_A = 5.0
CONCURRENCY_CAPTURA = 15  # I/O-bound (ffmpeg) — mesma ordem de grandeza usada em hls_liveness.py/snapshot_liveness.py

# YOLO/YuNet são CPU-bound (Ryzen sem NPU, OpenVINO FP32 — ver
# hw_douglas_book_igpu_only) — deixar as 15 threads de captura rodando
# inferência ao mesmo tempo satura a CPU sem ganhar nada (o gargalo vira
# fila de CPU, não mais a rede). Um semáforo à parte, mais apertado,
# limita quantas inferências rodam ao mesmo tempo, sem limitar quantas
# capturas de rede podem estar em voo simultaneamente.
ML_SEMAFORO = threading.Semaphore(3)

PROGRESSO_A_CADA = 200

FRAMES_ESTAGIO_B_PADRAO = 8
INTERVALO_ESTAGIO_B_PADRAO = 10.0
# Achado (2026-09-15): rodar as 2378 promissoras do Estágio A serial (uma
# câmera de cada vez) levaria dias. 4 é deliberadamente baixo — Estágio B
# usa modelo de verdade (YOLO+OCR/ArcFace) por frame, CPU sem GPU dedicada,
# não I/O puro como o Estágio A (que aguenta 15+ threads).
CONCURRENCY_ESTAGIO_B_PADRAO = 4


def _estagio_a_uma_camera(cam: Dict[str, Any]) -> Dict[str, Any]:
    cam_id = cam["id"]
    url = cam.get("url") or ""
    frames_ok = 0
    frames_com_pessoa = 0
    frames_com_veiculo = 0

    for i in range(FRAMES_ESTAGIO_A):
        jpeg = _capture_real_frame_jpeg(cam_id, url, timeout_s=15.0)
        if jpeg:
            buf = np.frombuffer(jpeg, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is not None:
                frames_ok += 1
                with ML_SEMAFORO:
                    pessoas, veiculos = detecta_pessoas_e_veiculos(frame)
                if pessoas:
                    frames_com_pessoa += 1
                if veiculos:
                    frames_com_veiculo += 1
        if i < FRAMES_ESTAGIO_A - 1:
            time.sleep(INTERVALO_ESTAGIO_A)

    return {
        "camera_id": cam_id,
        "frames_checados": frames_ok,
        "frames_com_pessoa": frames_com_pessoa,
        "frames_com_veiculo": frames_com_veiculo,
        "promissora_placa": 1 if frames_com_veiculo > 0 else 0,
        "promissora_rosto": 1 if frames_com_pessoa > 0 else 0,
    }


def _progresso(i: int, total: int, t0: float) -> None:
    if i % PROGRESSO_A_CADA != 0 and i != total:
        return
    decorrido = time.time() - t0
    ritmo = i / decorrido if decorrido > 0 else 0
    restante = (total - i) / ritmo if ritmo > 0 else 0
    print(f"[{i}/{total}] {decorrido/60:.1f}min decorridos, ~{restante/60:.1f}min restantes",
          file=sys.stderr, flush=True)


def _buscar_falhas_de_captura(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Câmeras que já passaram pelo Estágio A mas tiveram falha TOTAL de
    captura (`frames_checados = 0`) — não foram avaliadas de verdade,
    "sem pessoa nem veículo" pra elas é um artefato de rede/rate-limit, não
    uma conclusão real. Achado (2026-09-15): rodando o catálogo inteiro,
    750 caíram nessa categoria, 694 delas do mesmo host (digitraffic.fi,
    câmeras da Finlândia) que já tinha dado rate-limit (HTTP 429) no
    checador de liveness — sintoma de bater rápido demais nesse host com
    concorrência alta, não de câmera ruim."""
    linhas = conn.execute("""
        SELECT c.* FROM camera_scoring_estagio_a e
        JOIN cameras c ON c.id = e.camera_id
        WHERE e.frames_checados = 0
    """).fetchall()
    return [dict(r) for r in linhas]


def rodar_estagio_a(limit: Optional[int], dry_run: bool, forcar: bool,
                     concorrencia: int, retry_falhas: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    garante_schema_scoring(conn)
    garante_tabela_estagio_a(conn)
    conn.commit()

    if retry_falhas:
        cams = _buscar_falhas_de_captura(conn)
        if limit:
            cams = cams[:limit]
    else:
        cams = buscar_candidatas_scoring(conn, apenas_nao_pontuadas=not forcar, limit=limit)
    conn.close()

    if retry_falhas:
        print(f"Estágio A [retry]: {len(cams)} câmeras com falha total de captura na rodada anterior "
              f"— reprocessando com concorrência={concorrencia}", file=sys.stderr)
    else:
        print(f"Estágio A: {len(cams)} câmeras candidatas (vivas, fora da aba de teste)"
              f"{' — incluindo já pontuadas (--forcar)' if forcar else ' — só as ainda não pontuadas'}",
              file=sys.stderr)
    if not cams:
        print("Nada pra fazer.", file=sys.stderr)
        return

    resultados: List[Dict[str, Any]] = []
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concorrencia) as ex:
        for i, res in enumerate(ex.map(_estagio_a_uma_camera, cams), start=1):
            resultados.append(res)
            _progresso(i, len(cams), t0)

    promissoras_placa = sum(1 for r in resultados if r["promissora_placa"])
    promissoras_rosto = sum(1 for r in resultados if r["promissora_rosto"])
    nenhuma = sum(1 for r in resultados if not r["promissora_placa"] and not r["promissora_rosto"])
    print(f"\nResumo Estágio A: {promissoras_placa} promissoras p/ placa, "
          f"{promissoras_rosto} promissoras p/ rosto, "
          f"{nenhuma} sem pessoa nem veículo em nenhum frame (descartadas do Estágio B)",
          file=sys.stderr)

    if dry_run:
        print("[DRY-RUN] Nada foi escrito no banco.", file=sys.stderr)
        return

    conn = sqlite3.connect(DB_PATH)
    with conn:
        for r in resultados:
            conn.execute(
                """INSERT INTO camera_scoring_estagio_a
                       (camera_id, frames_checados, frames_com_pessoa, frames_com_veiculo,
                        promissora_placa, promissora_rosto, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(camera_id) DO UPDATE SET
                       frames_checados=excluded.frames_checados,
                       frames_com_pessoa=excluded.frames_com_pessoa,
                       frames_com_veiculo=excluded.frames_com_veiculo,
                       promissora_placa=excluded.promissora_placa,
                       promissora_rosto=excluded.promissora_rosto,
                       checked_at=excluded.checked_at""",
                (r["camera_id"], r["frames_checados"], r["frames_com_pessoa"],
                 r["frames_com_veiculo"], r["promissora_placa"], r["promissora_rosto"]),
            )
    conn.close()
    print("Gravado em camera_scoring_estagio_a.", file=sys.stderr)


def _estagio_b_uma_camera(item):
    """Roda o(s) scorer(s) completo(s) pra UMA câmera — unidade de trabalho
    do ThreadPoolExecutor. Import tardio de score_camera_alpr/
    score_camera_face aqui dentro (não no topo do módulo) porque essas duas
    libs puxam ultralytics/deepface/faiss — pesado, só vale pagar por
    thread que efetivamente processa uma câmera."""
    import score_camera_alpr
    import score_camera_face

    cam, info, frames, interval = item
    alpr_veredito = alpr_largura = face_veredito = face_interocular = None

    if info.get("promissora_placa"):
        r = score_camera_alpr.avalia_camera(cam, frames, interval)
        alpr_veredito = r["veredito"]
        alpr_largura = r["bbox_largura_media"]

    if info.get("promissora_rosto"):
        r = score_camera_face.avalia_camera(cam, frames, interval)
        face_veredito = r["veredito"]
        face_interocular = r["interocular_medio"]

    return cam, alpr_veredito, alpr_largura, face_veredito, face_interocular


def rodar_estagio_b(limit: Optional[int], dry_run: bool, forcar_todas: bool,
                     frames: int, interval: float, concorrencia: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    garante_schema_scoring(conn)
    conn.commit()

    if forcar_todas:
        cams = buscar_candidatas_scoring(conn, apenas_nao_pontuadas=True, limit=limit)
        promissoras = {c["id"]: {"promissora_placa": 1, "promissora_rosto": 1} for c in cams}
    else:
        linhas = conn.execute(
            "SELECT camera_id, promissora_placa, promissora_rosto FROM camera_scoring_estagio_a "
            "WHERE promissora_placa = 1 OR promissora_rosto = 1"
        ).fetchall()
        promissoras = {r["camera_id"]: dict(r) for r in linhas}
        todas_vivas = {c["id"]: c for c in buscar_candidatas_scoring(conn, apenas_nao_pontuadas=True, limit=None)}
        cams = [todas_vivas[cid] for cid in promissoras if cid in todas_vivas]
        if limit:
            cams = cams[:limit]
    conn.close()

    print(f"Estágio B: {len(cams)} câmeras "
          f"{'(--forcar-todas, ignorando o filtro do Estágio A)' if forcar_todas else '(promissoras do Estágio A)'} "
          f"— concorrência={concorrencia}",
          file=sys.stderr)
    if not cams:
        print("Nada pra fazer — rode o Estágio A primeiro, ou use --forcar-todas.", file=sys.stderr)
        return

    # Achado (2026-09-15, ver score_camera_alpr.py/score_camera_face.py):
    # concorrência aqui limita ao mesmo tempo I/O (captura de frame) e CPU
    # (YOLO+OCR) — diferente do Estágio A, que separa os dois com um
    # semáforo à parte, aqui não dá (avalia_camera() intercala captura e
    # inferência frame a frame, sem gancho pra separar). Por isso o valor
    # de concorrência já É o limite de inferência simultânea — mantido
    # baixo de propósito (CPU sem GPU dedicada).
    itens = [(cam, promissoras.get(cam["id"], {"promissora_placa": 1, "promissora_rosto": 1}), frames, interval)
             for cam in cams]

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concorrencia) as ex:
        for i, (cam, alpr_veredito, alpr_largura, face_veredito, face_interocular) in enumerate(
                ex.map(_estagio_b_uma_camera, itens), start=1):
            print(f"[{i}/{len(cams)}] {cam.get('nome') or cam['id']}: "
                  f"placa={alpr_veredito or '—'} rosto={face_veredito or '—'}", file=sys.stderr, flush=True)

            if not dry_run:
                conn = sqlite3.connect(DB_PATH)
                salvar_resultado_scoring(conn, cam["id"], alpr_veredito, alpr_largura,
                                          face_veredito, face_interocular)
                conn.close()

            _progresso(i, len(cams), t0)

    print("Estágio B concluído." + (" [DRY-RUN, nada gravado]" if dry_run else ""), file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    pa = sub.add_parser("estagio-a", help="Triagem barata (1-2 frames) — pré-filtro pro Estágio B")
    pa.add_argument("--limit", type=int, default=None)
    pa.add_argument("--dry-run", action="store_true", help="Só relatório, não escreve no banco")
    pa.add_argument("--forcar", action="store_true", help="Reavalia mesmo quem já tem scored_at")
    pa.add_argument("--concurrency", type=int, default=CONCURRENCY_CAPTURA,
                     help=f"Threads de captura simultâneas (padrão {CONCURRENCY_CAPTURA})")
    pa.add_argument("--retry-falhas", action="store_true",
                     help="Reprocessa só quem teve falha TOTAL de captura (frames_checados=0) "
                          "na rodada anterior — use com --concurrency baixo se a causa for rate-limit")

    pb = sub.add_parser("estagio-b", help="Score completo (ALPR+rosto) nas promissoras do Estágio A")
    pb.add_argument("--limit", type=int, default=None)
    pb.add_argument("--dry-run", action="store_true", help="Só relatório, não escreve no banco")
    pb.add_argument("--forcar-todas", action="store_true",
                     help="Ignora o filtro do Estágio A — roda em todas as câmeras vivas ainda não pontuadas")
    pb.add_argument("--frames", type=int, default=FRAMES_ESTAGIO_B_PADRAO)
    pb.add_argument("--interval", type=float, default=INTERVALO_ESTAGIO_B_PADRAO)
    pb.add_argument("--concurrency", type=int, default=CONCURRENCY_ESTAGIO_B_PADRAO,
                     help=f"Câmeras processadas em paralelo (padrão {CONCURRENCY_ESTAGIO_B_PADRAO} — "
                          "CPU-bound, não subir sem medir antes)")

    args = p.parse_args()

    if args.comando == "estagio-a":
        rodar_estagio_a(args.limit, args.dry_run, args.forcar, args.concurrency, args.retry_falhas)
    else:
        rodar_estagio_b(args.limit, args.dry_run, args.forcar_todas, args.frames, args.interval, args.concurrency)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
