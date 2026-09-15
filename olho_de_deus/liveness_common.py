"""
liveness_common.py — Olho de Deus

Regra de streak/persistência compartilhada entre os três checadores de
liveness de câmera (camera_liveness.py p/ YouTube, hls_liveness.py p/ M3U8,
snapshot_liveness.py p/ SNAPSHOT_JPEG) e o consumidor público
(camera_grid_server.py).

Por que existe (2026-09-15): até aqui cada checador tinha sua própria cópia
da regra de segurança, ou nem tinha nenhuma — hls_liveness.py e
snapshot_liveness.py escreviam direto num JSON sem retry nem streak.
`camera_liveness.py` (canal YouTube) já tinha sido corrigido com streak de 2
confirmações depois de um incidente real (uma varredura marcou 693/823
câmeras como mortas de uma vez só por bloqueio anti-bot, não por estarem
mortas). Ter a MESMA regra escrita em 3 lugares diferentes é exatamente como
esse tipo de buraco reabre — uma cópia esquece o streak numa correção futura
e a proteção vira ilusória só ali. Centralizado aqui, cada checador só
decide "está viva, morta, ou inconclusiva nesta rodada" — a lógica de
streak e a escrita no banco são uma função só, usada também pela leitura
pública (`camera_grid_server.get_camera_liveness`), pra "confirmado morto"
significar exatamente a mesma coisa em todo o sistema.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database" / "live_cameras.db"

# Confirmações MORTAS em execuções SEPARADAS necessárias antes de uma câmera
# virar autoridade pra remoção (camera_curation.py) OU aparecer como
# confirmada morta pra quem consome a API pública (camera_grid_server.py).
# Um evento correlacionado tipo o incidente de 693/823 não se repete
# idêntico em rodadas separadas sem ser um problema real que merece olho
# humano — por isso o mesmo número vale pras duas pontas, não só pra remoção.
STREAK_MINIMO_PRA_CONFIRMAR_MORTA = 2


def garante_schema_liveness(conn: sqlite3.Connection) -> None:
    """`dead_streak` pode não existir ainda num banco recém-copiado/restaurado
    de antes de 2026-09-14 — ALTER TABLE idempotente, mesmo padrão usado pra
    `is_test_candidate`/`test_notes`/`channel_url`."""
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(cameras)")}
    if "dead_streak" not in colunas:
        conn.execute("ALTER TABLE cameras ADD COLUMN dead_streak INTEGER DEFAULT 0")


def buscar_candidatas(conn: sqlite3.Connection, stream_formats: Iterable[str],
                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Câmeras de um ou mais `stream_format` ainda não confirmadas mortas.

    Câmeras já confirmadas mortas (`confirmed_dead=1`) saem da varredura —
    quem quiser reavaliar uma morta precisa de outro caminho (ex: a
    recuperação por canal do YouTube), não da checagem de rotina, senão o
    custo de varrer o catálogo cresce sem necessidade."""
    formatos = list(stream_formats)
    placeholders = ",".join("?" for _ in formatos)
    query = (
        f"SELECT id, url, video_id, dead_streak FROM cameras "
        f"WHERE stream_format IN ({placeholders}) AND confirmed_dead = 0"
    )
    params: List[Any] = list(formatos)
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


def status_de_liveness(cam: Dict[str, Any]) -> Optional[str]:
    """Traduz as colunas cruas do banco num veredito único, usado tanto por
    quem decide remoção (camera_curation.py) quanto por quem decide
    online/offline pra API pública (camera_grid_server.py) — mesma regra,
    um lugar só.

    Retorna "DEAD" (confirmada morta, streak suficiente), "LIVE" (última
    checagem foi positiva), "AGUARDANDO_CONFIRMACAO" (morta na checagem mais
    recente mas streak ainda insuficiente pra confiar) ou None (nunca
    checada)."""
    if cam.get("confirmed_dead"):
        if (cam.get("dead_streak") or 0) < STREAK_MINIMO_PRA_CONFIRMAR_MORTA:
            return "AGUARDANDO_CONFIRMACAO"
        return "DEAD"
    if cam.get("live_confirmed"):
        return "LIVE"
    return None


def aplicar_resultados(conn: sqlite3.Connection, resultados: Dict[str, Dict[str, Any]]) -> None:
    """Grava o resultado de uma rodada de checagem no SQLite, aplicando o
    gate de streak. Chamado depois de `buscar_candidatas` + a checagem real
    de cada checador específico (yt-dlp, HTTP HLS, HTTP snapshot).

    `resultados[cam_id]` precisa conter:
      - "status": "LIVE" | "DEAD" | qualquer outra string = "sem voto"
      - "live_status": texto livre pra guardar em `cameras.live_status`
      - "dead_streak_anterior": int (valor já lido de `buscar_candidatas`)

    Qualquer status fora de LIVE/DEAD (ex: RATE_LIMITED do checador de
    snapshot, pra HTTP 429) NÃO conta como voto — não incrementa nem zera o
    streak, não muda `confirmed_dead`/`live_confirmed`. É a mesma proteção
    que `snapshot_liveness.py` já tinha contra confundir rate-limit com
    câmera morta, agora estendida pra também respeitar o streak."""
    with conn:
        for cam_id, r in resultados.items():
            status = r.get("status")
            if status not in ("LIVE", "DEAD"):
                continue

            esta_morta = status == "DEAD"
            confirmed_dead = 1 if esta_morta else 0
            live_confirmed = 0 if esta_morta else 1
            # Streak soma enquanto continuar morta em execuções separadas;
            # zera assim que uma execução a encontrar viva.
            novo_streak = (r.get("dead_streak_anterior") or 0) + 1 if esta_morta else 0

            conn.execute(
                """UPDATE cameras
                   SET confirmed_dead = ?, live_confirmed = ?, live_status = ?,
                       dead_streak = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (confirmed_dead, live_confirmed, r.get("live_status"), novo_streak, cam_id),
            )
