#!/usr/bin/env python3
"""
Ingestão do NZTA/Waka Kotahi (Nova Zelândia) — 319 câmeras de trânsito
reais, API pública SEM CADASTRO (`https://trafficnz.info/service/traffic/rest/4/cameras/all`).

Igual ao Ontario 511: é tipo SNAPSHOT_JPEG (imagem única por request via
`imageUrl`), não HLS contínuo.
"""

import argparse
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
API_URL = "https://trafficnz.info/service/traffic/rest/4/cameras/all"
BASE_URL = "https://trafficnz.info"
USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; ingestao de cameras publicas)"


def make_id(url: str) -> str:
    return "nzta_" + hashlib.md5(url.encode()).hexdigest()[:12]


def fetch_source() -> bytes:
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def build_cameras(xml_bytes: bytes) -> List[Dict[str, Any]]:
    root = ET.fromstring(xml_bytes)
    out = []
    for cam in root.findall("camera"):
        image_url = cam.findtext("imageUrl")
        if not image_url:
            continue
        full_url = BASE_URL + image_url if image_url.startswith("/") else image_url
        lat = cam.findtext("latitude")
        lon = cam.findtext("longitude")
        out.append({
            "id": make_id(full_url),
            "nome": f"NZ - {cam.findtext('highway','')} - {cam.findtext('name','')}".strip(" -"),
            "local": cam.findtext("description", ""),
            "cidade": cam.findtext("region/name", ""),
            "uf": "",
            "pais": "NZ",
            "setor": "GLOBAL",
            "tipo_area": "TRAFFIC",
            "lat": float(lat) if lat else None,
            "long": float(lon) if lon else None,
            "status": "LIVE",
            "is_real_stream": True,
            "thumbnail_url": "",
            "url": full_url,
            "video_id": None,
            "source": "NZTA",
            "stream_format": "SNAPSHOT_JPEG",
        })
    return out


def run(apply_changes: bool) -> Dict[str, Any]:
    xml_bytes = fetch_source()
    new_cameras = build_cameras(xml_bytes)
    print(f"{len(new_cameras)} câmeras carregadas da API.")

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
