#!/usr/bin/env python3
"""
Curadoria real da lista de câmeras: remove mortas e duplicatas.

Contexto: `database/live_cameras.json` acumula câmeras ao longo do tempo
sem nenhuma limpeza — muitas já saíram do ar (ver `camera_liveness.py`) e
há entradas duplicadas (mesmo vídeo do YouTube catalogado mais de uma vez,
ou o mesmo ponto físico reingerido com nome ligeiramente diferente).

Este script NUNCA apaga silenciosamente:
- Roda (ou reaproveita) a checagem de liveness real via `camera_liveness.py`.
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
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
LIVENESS_STATE_PATH = ROOT / "database" / "camera_liveness_state.json"
REMOVED_ARCHIVE_PATH = ROOT / "database" / "live_cameras_removed_archive.json"

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
            lat1, lon1 = kept.get("lat"), kept.get("long")
            lat2, lon2 = other.get("lat"), other.get("long")
            if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
                continue
            if abs(lat1 - lat2) <= DUPLICATE_COORD_TOLERANCE and abs(lon1 - lon2) <= DUPLICATE_COORD_TOLERANCE:
                duplicate_of[str(other["id"])] = str(kept["id"])

    return duplicate_of


def curate(refresh_liveness: bool, concurrency: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    if refresh_liveness:
        print(f"Rodando camera_liveness.py --concurrency {concurrency} (pode levar alguns minutos)...", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "camera_liveness.py"), "--concurrency", str(concurrency)],
            check=True,
        )

    cameras = load_json(CAMERAS_PATH, [])
    liveness = load_json(LIVENESS_STATE_PATH, {})
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
        if status in ("DEAD", "ENDED_BUT_EXISTS"):
            entry["_removed_reason"] = f"DEAD ({status})"
            entry["_removed_at"] = now
            removed.append(entry)
            continue

        if status is None:
            # Nunca checada — não remove sem evidência, só sinaliza.
            entry["_liveness_status"] = "NUNCA_CHECADA"

        kept.append(cam)

    summary = {
        "total_original": len(cameras),
        "duplicatas_removidas": sum(1 for r in removed if r["_removed_reason"].startswith("DUPLICATE_OF")),
        "mortas_removidas": sum(1 for r in removed if r["_removed_reason"].startswith("DEAD")),
        "mantidas": len(kept),
        "nunca_checadas_mantidas": sum(1 for c in kept if liveness.get(str(c["id"]), {}).get("status") is None),
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

    # Backup antes de sobrescrever — mesmo arquivo que já foi acidentalmente
    # truncado uma vez nesta mesma sessão (ver PLANO_CONTINUACAO.md).
    if CAMERAS_PATH.exists():
        backup_path = CAMERAS_PATH.with_name(f"live_cameras.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}")
        backup_path.write_bytes(CAMERAS_PATH.read_bytes())
        print(f"Backup salvo em {backup_path}", file=sys.stderr)

    save_json(CAMERAS_PATH, kept)

    existing_archive = load_json(REMOVED_ARCHIVE_PATH, [])
    save_json(REMOVED_ARCHIVE_PATH, existing_archive + removed)

    print(f"Aplicado: {summary['mantidas']} câmeras mantidas, {len(removed)} arquivadas em {REMOVED_ARCHIVE_PATH.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
