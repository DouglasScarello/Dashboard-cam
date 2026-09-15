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


def buscar_candidatas(conn: sqlite3.Connection,
                       stream_formats: Optional[Iterable[str]] = None,
                       excluir_stream_formats: Optional[Iterable[str]] = None,
                       excluir_youtube_por_url: bool = False,
                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Câmeras elegíveis pra checagem de rotina, usada pelos 3 checadores.

    Achado (2026-09-15, revisado 2026-09-15): a versão anterior filtrava
    `confirmed_dead = 0` — mas essa coluna já vira 1 na PRIMEIRA checagem
    morta (`aplicar_resultados` grava otimista, é o que permite o streak
    contar), bem antes do streak de `STREAK_MINIMO_PRA_CONFIRMAR_MORTA`
    confirmações completar. Resultado real, confirmado no banco: 4912
    câmeras ficaram presas em `confirmed_dead=1, dead_streak=1` para
    sempre — excluídas de toda checagem futura antes de chegar à 2ª
    confirmação, sem chance de virar DEAD de verdade nem de provar que
    voltaram a ficar LIVE. O filtro certo é o mesmo veredito usado pra
    decidir remoção/exibição pública (`status_de_liveness`): só sai da
    varredura de rotina quem JÁ tem streak completo (confirmado morto de
    verdade); quem tem streak insuficiente (`AGUARDANDO_CONFIRMACAO`)
    PRECISA continuar sendo candidata, senão nunca sai do limbo.

    stream_formats: se dado, exige `stream_format IN (...)`.
    excluir_stream_formats: se dado, exige `stream_format` NULL ou fora
    dessa lista (usado pelo checador HLS, que herda tudo que não é
    SNAPSHOT_JPEG/YOUTUBE, incluindo o legado com stream_format vazio).
    excluir_youtube_por_url: filtra fora URLs de youtube.com/youtu.be
    mesmo quando stream_format não identifica isso (legado)."""
    condicoes = ["NOT (confirmed_dead = 1 AND dead_streak >= ?)", "url IS NOT NULL AND url != ''"]
    params: List[Any] = [STREAK_MINIMO_PRA_CONFIRMAR_MORTA]

    if stream_formats:
        formatos = list(stream_formats)
        placeholders = ",".join("?" for _ in formatos)
        condicoes.append(f"stream_format IN ({placeholders})")
        params.extend(formatos)

    if excluir_stream_formats:
        formatos = list(excluir_stream_formats)
        placeholders = ",".join("?" for _ in formatos)
        condicoes.append(f"(stream_format IS NULL OR stream_format NOT IN ({placeholders}))")
        params.extend(formatos)

    if excluir_youtube_por_url:
        condicoes.append("url NOT LIKE '%youtube.com%' AND url NOT LIKE '%youtu.be%'")

    query = (
        "SELECT id, url, video_id, channel_url, dead_streak FROM cameras WHERE "
        + " AND ".join(condicoes)
    )
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
