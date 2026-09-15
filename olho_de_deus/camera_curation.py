#!/usr/bin/env python3
"""
Curadoria real da lista de câmeras: remove mortas e duplicatas.

Contexto: `database/live_cameras.json` acumula câmeras ao longo do tempo
sem nenhuma limpeza — muitas já saíram do ar (ver `camera_liveness.py`) e
há entradas duplicadas (mesmo vídeo do YouTube catalogado mais de uma vez,
ou o mesmo ponto físico reingerido com nome ligeiramente diferente).

Este script NUNCA apaga silenciosamente:
- Roda (ou reaproveita) a checagem de liveness real via `camera_liveness.py`
  (YouTube), `hls_liveness.py` (streams .m3u8 diretos) e `snapshot_liveness.py`
  (câmeras de imagem única) — os três checadores do catálogo.
- Detecta duplicatas por `video_id` idêntico e por nome+coordenada quase
  idêntica (mesmo ponto físico reingerido).
- Escreve a lista curada em `live_cameras.json` só com `--apply` — sem essa
  flag, roda em modo dry-run e só imprime o que faria.
- TUDO que seria removido vai pra `live_cameras_removed_archive.json` com
  motivo e timestamp — nada é descartado de verdade, dá pra auditar/reverter.
- Faz backup do arquivo atual antes de sobrescrever (`.bak-<timestamp>`).

Uso:
  python3 camera_curation.py                    # dry-run, só relatório
  python3 camera_curation.py --refresh-liveness  # roda camera_liveness.py de novo antes
  python3 camera_curation.py --apply             # aplica de verdade (com backup)
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from liveness_common import STREAK_MINIMO_PRA_CONFIRMAR_MORTA, status_de_liveness

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database" / "live_cameras.db"
REMOVED_ARCHIVE_PATH = ROOT / "database" / "live_cameras_removed_archive.json"

# Os dois JSON abaixo eram a fonte de dados deste script. Ficaram pra trás numa
# migração pela metade: camera_liveness.py passou a ler E escrever o SQLite,
# enquanto este script continuou lendo o JSON — congelado em 2026-08-31 — e
# escrevendo por cima dele, enquanto o resto do sistema (db_manager,
# camera_grid_server, monitor_plates) lê o .db com 8.221 linhas.
#
# Ou seja: consertar só o SELECT quebrado do liveness transformaria uma falha
# barulhenta diária numa decisão silenciosa tomada em cima de dado de um mês
# atrás. Por isso a leitura foi portada junto. Mantidos aqui só como
# documentação de onde estava a fonte antiga.
LEGADO_CAMERAS_JSON = ROOT / "database" / "live_cameras.json"
LEGADO_LIVENESS_JSON = ROOT / "database" / "camera_liveness_state.json"

# Coordenadas dentro desta distância (graus) E mesmo nome normalizado =
# considerado o mesmo ponto físico reingerido. ~0.0005° ≈ 55m no equador —
# suficiente pra pegar reingestão do mesmo local, não câmeras vizinhas reais.
DUPLICATE_COORD_TOLERANCE = 0.0005


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def carrega_cameras_do_db() -> List[Dict[str, Any]]:
    """Catálogo vivo, direto do SQLite que o resto do sistema usa."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM cameras")]
    finally:
        conn.close()


# Streak/status agora vêm de liveness_common.py — usado também por
# hls_liveness.py, snapshot_liveness.py e camera_grid_server.py. Achado
# (2026-09-15): esta função e a constante de streak viviam duplicadas aqui
# desde a correção do incidente de 693/823 câmeras falso-mortas; ter a MESMA
# regra de segurança escrita em mais de um lugar é como esse tipo de buraco
# reabre (uma cópia diverge da outra numa correção futura). Ver
# `STREAK_MINIMO_PRA_CONFIRMAR_MORTA`/`status_de_liveness` em
# liveness_common.py — o valor do streak (2) e o comportamento são
# idênticos aos de antes, só a definição saiu daqui.
STREAK_MINIMO_PRA_REMOVER = STREAK_MINIMO_PRA_CONFIRMAR_MORTA


def normalize_name(name: str) -> str:
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum())


def find_duplicates(cameras: List[Dict[str, Any]]) -> Dict[str, str]:
    """Retorna {camera_id_duplicado: camera_id_original_mantido}."""
    duplicate_of: Dict[str, str] = {}

    # 1. Duplicata exata por video_id — mesma live catalogada 2+ vezes.
    seen_by_video_id: Dict[str, str] = {}
    for cam in cameras:
        vid = cam.get("video_id")
        cid = str(cam["id"])
        if not vid:
            continue
        if vid in seen_by_video_id:
            duplicate_of[cid] = seen_by_video_id[vid]
        else:
            seen_by_video_id[vid] = cid

    # 2. Duplicata por nome normalizado + coordenada muito próxima — mesmo
    # ponto físico reingerido com video_id diferente (ex: canal reiniciou
    # a live e o pipeline de ingestão catalogou como câmera "nova").
    by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cam in cameras:
        cid = str(cam["id"])
        if cid in duplicate_of:
            continue
        name_key = normalize_name(cam.get("nome", ""))
        if name_key:
            by_name[name_key].append(cam)

    for name_key, group in by_name.items():
        if len(group) < 2:
            continue
        kept = group[0]
        for other in group[1:]:
            # URL de stream diferente = câmera FÍSICA diferente, ponto final.
            #
            # Achado (2026-09-14), pego rodando o dry-run antes de aplicar: a
            # regra nome+coordenada sozinha marcava 366 câmeras como duplicata,
            # e 363 delas eram falso positivo. O caso que denunciou foi a malha
            # de rodovia de SP, onde o mesmo quilômetro tem duas câmeras —
            # SP055-KM211A e SP055-KM211B, os dois sentidos da pista. Mesmo
            # nome, mesma coordenada, streams distintos. Com --apply isso teria
            # apagado metade da malha de SP de uma vez.
            url1 = (kept.get("url") or "").strip()
            url2 = (other.get("url") or "").strip()
            if url1 and url2 and url1 != url2:
                continue

            lat1, lon1 = kept.get("lat"), kept.get("long")
            lat2, lon2 = other.get("lat"), other.get("long")
            if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
                continue
            if abs(lat1 - lat2) <= DUPLICATE_COORD_TOLERANCE and abs(lon1 - lon2) <= DUPLICATE_COORD_TOLERANCE:
                duplicate_of[str(other["id"])] = str(kept["id"])

    return duplicate_of


def curate(refresh_liveness: bool, concurrency: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    if refresh_liveness:
        # Achado (2026-09-15): só camera_liveness.py (canal YouTube, 15 de
        # 8218 câmeras) era chamado aqui. hls_liveness.py e
        # snapshot_liveness.py — que cobrem os outros 99,8% do catálogo —
        # não tinham NENHUM agendamento (sem cron, sem timer, sem chamada
        # de dentro deste script). O único timer real do projeto
        # (olho-de-deus-curadoria.timer, diário) passa a acionar os três,
        # em vez de precisar de um timer novo por checador.
        script_dir = Path(__file__).resolve().parent
        for script in ("camera_liveness.py", "hls_liveness.py", "snapshot_liveness.py"):
            print(f"Rodando {script} --concurrency {concurrency} (pode levar alguns minutos)...", file=sys.stderr)
            subprocess.run(
                [sys.executable, str(script_dir / script), "--concurrency", str(concurrency)],
                check=True,
            )

    cameras = carrega_cameras_do_db()
    # O status de liveness agora mora na própria linha da câmera (colunas
    # confirmed_dead / live_status), escritas por camera_liveness.py.
    liveness = {
        str(c["id"]): {"status": status_de_liveness(c)} for c in cameras
    }
    now = datetime.now(timezone.utc).isoformat()

    duplicate_of = find_duplicates(cameras)

    kept: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []

    for cam in cameras:
        cid = str(cam["id"])
        entry = {**cam}

        if cid in duplicate_of:
            entry["_removed_reason"] = f"DUPLICATE_OF:{duplicate_of[cid]}"
            entry["_removed_at"] = now
            removed.append(entry)
            continue

        status = liveness.get(cid, {}).get("status")
        # Achado (2026-09-15): "ENDED_BUT_EXISTS" nunca é retornado por
        # status_de_liveness() (só "DEAD"/"LIVE"/"AGUARDANDO_CONFIRMACAO"/
        # None) — era um branch morto que dava a falsa impressão de que
        # streams HLS encerrados eram tratados aqui. A normalização de
        # verdade agora acontece em hls_liveness.py antes da escrita.
        if status == "DEAD":
            entry["_removed_reason"] = f"DEAD ({status})"
            entry["_removed_at"] = now
            removed.append(entry)
            continue

        if status is None:
            # Nunca checada — não remove sem evidência, só sinaliza.
            entry["_liveness_status"] = "NUNCA_CHECADA"
        elif status == "AGUARDANDO_CONFIRMACAO":
            # Morta na checagem mais recente, mas ainda sem streak suficiente
            # pra confiar que não é bloqueio anti-bot pontual — mantém e
            # espera a próxima rodada confirmar.
            entry["_liveness_status"] = (
                f"AGUARDANDO_CONFIRMACAO (streak={cam.get('dead_streak') or 0}"
                f"/{STREAK_MINIMO_PRA_REMOVER})"
            )

        # `entry`, não `cam` — bug pré-existente pego rodando o teste desta
        # sessão: guardar `cam` descartava a anotação de status posta acima
        # em `entry`, então NUNCA_CHECADA/AGUARDANDO_CONFIRMACAO nunca
        # chegavam a aparecer pra quem lê a lista mantida.
        kept.append(entry)

    summary = {
        "total_original": len(cameras),
        "duplicatas_removidas": sum(1 for r in removed if r["_removed_reason"].startswith("DUPLICATE_OF")),
        "mortas_removidas": sum(1 for r in removed if r["_removed_reason"].startswith("DEAD")),
        "mantidas": len(kept),
        "nunca_checadas_mantidas": sum(1 for c in kept if liveness.get(str(c["id"]), {}).get("status") is None),
        "aguardando_confirmacao": sum(
            1 for c in kept
            if liveness.get(str(c["id"]), {}).get("status") == "AGUARDANDO_CONFIRMACAO"
        ),
    }
    return kept, removed, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Aplica de verdade (senão só relatório dry-run)")
    parser.add_argument("--refresh-liveness", action="store_true", help="Roda camera_liveness.py de novo antes de curar (recomendado — dados podem estar velhos)")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    kept, removed, summary = curate(args.refresh_liveness, args.concurrency)

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not args.apply:
        print("\n[DRY-RUN] Nada foi escrito. Rode com --apply pra aplicar de verdade.", file=sys.stderr)
        return

    # Backup do banco inteiro antes de apagar linha. O arquivo de catálogo já
    # foi truncado por acidente uma vez (ver PLANO_CONTINUACAO.md) — aqui a
    # cópia é do .db, que é o que vale agora.
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_path = DB_PATH.with_name(f"live_cameras.db.bak-{carimbo}")
    backup_path.write_bytes(DB_PATH.read_bytes())
    print(f"Backup do banco salvo em {backup_path}", file=sys.stderr)

    # Arquivo de remoções continua em JSON de propósito: é trilha de auditoria
    # append-only, com o registro inteiro e o motivo. Se uma remoção se provar
    # errada, dá pra reinserir a linha a partir daqui.
    existing_archive = load_json(REMOVED_ARCHIVE_PATH, [])
    save_json(REMOVED_ARCHIVE_PATH, existing_archive + removed)

    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.executemany("DELETE FROM cameras WHERE id = ?",
                         [(str(r["id"]),) for r in removed])
    conn.close()

    print(f"Aplicado: {summary['mantidas']} câmeras mantidas, {len(removed)} "
          f"removidas do banco e arquivadas em {REMOVED_ARCHIVE_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
