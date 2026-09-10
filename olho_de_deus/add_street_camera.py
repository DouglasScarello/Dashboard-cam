#!/usr/bin/env python3
"""
add_street_camera.py — Olho de Deus

Insere UMA câmera de rua verificada manualmente (visualmente, ao vivo) no
catálogo — usado pela sessão de curadoria de câmeras públicas de acesso
livre pra reconhecimento facial (ver SESSAO_CAMERAS_2026-09-10.md).

As 8.198 câmeras já existentes no catálogo (Digitraffic, Ontario511,
OpenTrafficCamMap, Vegagerdin, NZTA) são TODAS de rodovia/trânsito de DOT
— nenhuma serve pra reconhecimento facial (mostram carro, não pessoa).
Este script cadastra especificamente câmeras de RUA/CENTRO DE CIDADE,
com gente visível, verificadas uma a uma ao vivo antes de entrar aqui —
nunca em lote sem checagem visual.

source="GlobeTV-Rua-Verificada" e tipo_area="RUA_PEDESTRE" separam essas
das 8.198 antigas, pra dar pra filtrar só as úteis pra reconhecimento.

Uso (como função, chamado a partir do fluxo de verificação):
    from add_street_camera import add_verified_street_camera
    add_verified_street_camera(
        id="globetv_e515fc89da51", nome="...", cidade="...", pais="IE",
        url="https://...", stream_format="M3U8", lat=53.34, long=-6.26,
    )
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_FILE = Path(__file__).resolve().parent.parent / "database" / "live_cameras.db"


def add_verified_street_camera(
    id: str,
    nome: str,
    cidade: Optional[str] = None,
    pais: Optional[str] = None,
    url: str = "",
    stream_format: str = "M3U8",
    lat: Optional[float] = None,
    long: Optional[float] = None,
    video_id: Optional[str] = None,
) -> bool:
    """Retorna True se inseriu, False se o id já existia (idempotente)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM cameras WHERE id = ?", (id,))
    if cur.fetchone():
        conn.close()
        return False

    cur.execute(
        """INSERT INTO cameras
           (id, nome, local, cidade, pais, tipo_area, setor, url, video_id,
            lat, long, live_confirmed, live_status, stream_format, source)
           VALUES (?, ?, ?, ?, ?, 'RUA_PEDESTRE', 'RUA_PEDESTRE', ?, ?, ?, ?, 1, 'LIVE_VERIFIED', ?, 'GlobeTV-Rua-Verificada')""",
        (id, nome, cidade, cidade, pais, url, video_id, lat, long, stream_format),
    )
    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cadastra uma câmera de rua verificada")
    parser.add_argument("--id", required=True)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--cidade")
    parser.add_argument("--pais")
    parser.add_argument("--url", default="")
    parser.add_argument("--video-id")
    parser.add_argument("--stream-format", default="M3U8")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--long", type=float)
    args = parser.parse_args()

    added = add_verified_street_camera(
        id=args.id, nome=args.nome, cidade=args.cidade, pais=args.pais,
        url=args.url, stream_format=args.stream_format, lat=args.lat, long=args.long,
        video_id=args.video_id,
    )
    print(f"[add-street-camera] {'adicionada' if added else 'já existia, pulada'}: {args.id}")
