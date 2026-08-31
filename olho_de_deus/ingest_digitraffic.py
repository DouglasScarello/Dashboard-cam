#!/usr/bin/env python3
"""
Ingestão do Fintraffic/Digitraffic (Finlândia) — câmeras de trânsito/tempo
reais, API pública SEM CADASTRO
(`https://tie.digitraffic.fi/api/weathercam/v1/stations`).

Achado: a API exige `Accept-Encoding: gzip` (responde HTTP 406 sem isso).
Cada "estação" tem 1+ "presets" (ângulos de câmera); a imagem de cada
preset é servida direto em `https://weathercam.digitraffic.fi/{presetId}.jpg`
(confirmado com curl real: JPEG 1280x720 genuíno, ~300KB).

Igual a Ontario 511 / NZTA: tipo SNAPSHOT_JPEG (imagem única por request).
"""

import argparse
import gzip
import json
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
STATIONS_URL = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
IMAGE_BASE = "https://weathercam.digitraffic.fi"
USER_AGENT = "dashboard-cam-olho-de-deus (ingestao de cameras publicas)"


def fetch_stations() -> Dict[str, Any]:
    req = urllib.request.Request(
        STATIONS_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Digitraffic-User": "dashboard-cam-olho-de-deus",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw)


def build_cameras(geojson: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for feat in geojson.get("features", []):
        props = feat.get("properties", {})
        if props.get("collectionStatus") not in ("GATHERING", None):
            continue
        coords = feat.get("geometry", {}).get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        station_name = props.get("name", "")
        for preset in props.get("presets", []):
            if not preset.get("inCollection", True):
                continue
            preset_id = preset.get("id")
            if not preset_id:
                continue
            image_url = f"{IMAGE_BASE}/{preset_id}.jpg"
            out.append({
                "id": f"digitraffic_{preset_id}",
                "nome": f"FI - {station_name} ({preset_id})",
                "local": station_name,
                "cidade": "",
                "uf": "",
                "pais": "FI",
                "setor": "GLOBAL",
                "tipo_area": "TRAFFIC",
                "lat": lat,
                "long": lon,
                "status": "LIVE",
                "is_real_stream": True,
                "thumbnail_url": "",
                "url": image_url,
                "video_id": None,
                "source": "Digitraffic",
                "stream_format": "SNAPSHOT_JPEG",
            })
    return out


def run(apply_changes: bool) -> Dict[str, Any]:
    geojson = fetch_stations()
    new_cameras = build_cameras(geojson)
    print(f"{len(new_cameras)} câmeras (presets) carregadas da API.")

    existing = json.load(open(CAMERAS_PATH, "r", encoding="utf-8")) if CAMERAS_PATH.exists() else []
    existing_urls = {c.get("url") for c in existing if c.get("url")}
    fresh = [c for c in new_cameras if c["url"] not in existing_urls]
    print(f"Novas de verdade: {len(fresh)}.")

    if apply_changes:
        merged = existing + fresh
        tmp = CAMERAS_PATH.with_suffix(".tmp")
        json.dump(merged, open(tmp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        tmp.replace(CAMERAS_PATH)
        print(f"Gravado: {len(existing)} -> {len(merged)} câmeras totais.")

    return {"loaded": len(new_cameras), "new": len(fresh), "total_before": len(existing)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(apply_changes=args.apply), indent=2, ensure_ascii=False))
