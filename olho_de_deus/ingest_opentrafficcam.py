#!/usr/bin/env python3
"""
Ingestão do dataset OpenTrafficCamMap (github.com/AidanWelch/OpenTrafficCamMap,
MIT) — 7029 câmeras de trânsito reais nos EUA com URL de stream direto
(.m3u8 majoritariamente), já rotuladas por estado/cidade/direção.

Por que essa fonte: pesquisa (2026-08-30) sobre "como conseguir mais
câmeras estáveis mundiais" mostrou que agregadores comerciais (Windy,
EarthCam) ou travam em embed ou são caros, e a maioria dos DOTs estaduais
com API real de vídeo (NY/GA/NC/WI/AZ/UT/LA) exige cadastro de chave que
só o usuário pode fazer. OpenTrafficCamMap é a única fonte grande, real,
sem cadastro nenhum, com stream direto de verdade — mesmo padrão de
confiabilidade que já validamos (infra de DOT, não YouTube).

Uso:
    git clone --depth 1 https://github.com/AidanWelch/OpenTrafficCamMap.git /tmp/OpenTrafficCamMap
    python3 ingest_opentrafficcam.py --repo /tmp/OpenTrafficCamMap [--apply]
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"


def make_id(url: str) -> str:
    return "otcm_" + hashlib.md5(url.encode()).hexdigest()[:12]


def load_repo_cameras(repo_path: Path) -> List[Dict[str, Any]]:
    cameras_dir = repo_path / "cameras"
    out = []
    for country_file in cameras_dir.glob("*.json"):
        country_code = country_file.stem
        with open(country_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for region, subregions in data.items():
            for subregion, cams in subregions.items():
                for cam in cams:
                    if cam.get("markedForReview"):
                        continue  # não confiar em entrada sinalizada como precisando revisão
                    url = cam.get("url")
                    if not url:
                        continue
                    out.append({
                        "id": make_id(url),
                        "nome": f"{region} / {subregion} - {cam.get('description', '')}".strip(" -"),
                        "local": f"{subregion}, {region}",
                        "cidade": subregion,
                        "uf": region,
                        "pais": country_code,
                        "setor": "GLOBAL",
                        "tipo_area": "TRAFFIC",
                        "lat": cam.get("latitude"),
                        "long": cam.get("longitude"),
                        "status": "LIVE",
                        "is_real_stream": True,
                        "thumbnail_url": "",
                        "url": url,
                        "video_id": None,
                        "source": "OpenTrafficCamMap",
                        "encoding": cam.get("encoding"),
                        "stream_format": cam.get("format"),
                    })
    return out


def run(repo_path: Path, apply_changes: bool) -> Dict[str, Any]:
    new_cameras = load_repo_cameras(repo_path)
    print(f"{len(new_cameras)} câmeras carregadas do dataset (sem markedForReview).")

    existing = json.load(open(CAMERAS_PATH, "r", encoding="utf-8")) if CAMERAS_PATH.exists() else []
    existing_urls = {c.get("url") for c in existing if c.get("url")}

    fresh = [c for c in new_cameras if c["url"] not in existing_urls]
    dup_count = len(new_cameras) - len(fresh)
    print(f"Duplicatas por URL contra o que já existe: {dup_count}. Novas de verdade: {len(fresh)}.")

    if apply_changes:
        merged = existing + fresh
        tmp = CAMERAS_PATH.with_suffix(".tmp")
        json.dump(merged, open(tmp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        tmp.replace(CAMERAS_PATH)
        print(f"Gravado: {len(existing)} -> {len(merged)} câmeras totais.")

    return {"loaded": len(new_cameras), "duplicates": dup_count, "new": len(fresh), "total_before": len(existing)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="caminho do clone local do OpenTrafficCamMap")
    parser.add_argument("--apply", action="store_true", help="grava de verdade em live_cameras.json")
    args = parser.parse_args()

    summary = run(Path(args.repo), apply_changes=args.apply)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
