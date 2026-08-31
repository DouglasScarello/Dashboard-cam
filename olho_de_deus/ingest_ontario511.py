#!/usr/bin/env python3
"""
Ingestão do Ontario 511 (511on.ca) — 940 câmeras de trânsito reais,
API pública SEM CADASTRO (`https://511on.ca/api/v2/get/cameras`).

Achado real (2026-08-30, sessão noturna autônoma): a pesquisa anterior
supôs que `https://511on.ca/map/Cctv/{id}` fosse uma página de embed que
precisaria de mais um passo de scraping pra achar a URL real. Testado
direto: essa URL JÁ É uma imagem JPEG real, atualizada a cada request
(câmeras Axis Q6054-E-MkIII/Q6052-E reais, timestamp EXIF batendo com o
horário real da requisição). Não precisa de scraping nenhum.

Diferença importante de tipo: isso é uma câmera de SNAPSHOT (imagem única
que atualiza a cada pedido), não um stream de vídeo contínuo HLS como as
outras fontes deste projeto. Fica marcado com `stream_format: "SNAPSHOT_JPEG"`
pra quem for tratar isso na UI diferenciar dos players HLS.
"""

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
API_URL = "https://511on.ca/api/v2/get/cameras"
USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; ingestao de cameras publicas)"


def make_id(url: str) -> str:
    return "on511_" + hashlib.md5(url.encode()).hexdigest()[:12]


def fetch_source() -> List[Dict[str, Any]]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def build_cameras(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for cam in raw:
        lat, lon = cam.get("Latitude"), cam.get("Longitude")
        roadway = cam.get("Roadway", "")
        location = cam.get("Location", "")
        for view in cam.get("Views", []):
            if view.get("Status") != "Enabled":
                continue
            url = view.get("Url")
            if not url:
                continue
            desc = view.get("Description", "")
            out.append({
                "id": make_id(url),
                "nome": f"ON - {roadway} - {location} ({desc})".strip(" -()"),
                "local": location,
                "cidade": location,
                "uf": "ON",
                "pais": "CA",
                "setor": "GLOBAL",
                "tipo_area": "TRAFFIC",
                "lat": lat,
                "long": lon,
                "status": "LIVE",
                "is_real_stream": True,
                "thumbnail_url": "",
                "url": url,
                "video_id": None,
                "source": "Ontario511",
                "stream_format": "SNAPSHOT_JPEG",
            })
    return out


def run(apply_changes: bool) -> Dict[str, Any]:
    raw = fetch_source()
    new_cameras = build_cameras(raw)
    print(f"{len(new_cameras)} views de câmera carregadas da API (de {len(raw)} pontos).")

    existing = json.load(open(CAMERAS_PATH, "r", encoding="utf-8")) if CAMERAS_PATH.exists() else []
    existing_urls = {c.get("url") for c in existing if c.get("url")}
    fresh = [c for c in new_cameras if c["url"] not in existing_urls]
    print(f"Novas de verdade (sem duplicar URL já existente): {len(fresh)}.")

    if apply_changes:
        merged = existing + fresh
        tmp = CAMERAS_PATH.with_suffix(".tmp")
        json.dump(merged, open(tmp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        tmp.replace(CAMERAS_PATH)
        print(f"Gravado: {len(existing)} -> {len(merged)} câmeras totais.")

    return {"loaded": len(new_cameras), "new": len(fresh), "total_before": len(existing)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(apply_changes=args.apply), indent=2, ensure_ascii=False))
