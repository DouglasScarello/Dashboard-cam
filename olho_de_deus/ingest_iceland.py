#!/usr/bin/env python3
"""
Ingestão da Vegagerðin (Administração de Estradas da Islândia) —
câmeras de trânsito reais, SEM CADASTRO.

Não existe uma API REST documentada pública; os dados vêm embutidos no
JSON de pré-renderização (Next.js `getStaticProps`) da página oficial
`umferdin.is/en/cameras`, em
`https://umferdin.is/_next/data/{buildId}/en/cameras.json`. O `buildId`
muda a cada deploy do site — se este script parar de funcionar, é o
primeiro lugar a checar (buscar `"buildId":"..."` no HTML de
`umferdin.is/en/cameras`).

165 estações, cada uma com 1+ imagens/ângulos reais (500 imagens no
total) servidas direto em `https://www.vegagerdin.is/vgdata/vefmyndavelar/
{slug}_{n}.jpg` — confirmado com curl real: JPEG genuíno.

Igual a Ontario 511 / NZTA / Digitraffic: tipo SNAPSHOT_JPEG.
"""

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
CAMERAS_PAGE_URL = "https://umferdin.is/en/cameras"
USER_AGENT = "Mozilla/5.0 (dashboard-cam-olho-de-deus; ingestao de cameras publicas)"


def fetch_build_id() -> str:
    req = urllib.request.Request(CAMERAS_PAGE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        raise RuntimeError("buildId não encontrado no HTML — site pode ter mudado de framework/formato.")
    return m.group(1)


def fetch_stations(build_id: str) -> List[Dict[str, Any]]:
    url = f"https://umferdin.is/_next/data/{build_id}/en/cameras.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    return data["pageProps"]["cameras"]


def make_id(url: str) -> str:
    return "iceland_" + hashlib.md5(url.encode()).hexdigest()[:12]


def build_cameras(stations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for st in stations:
        coords = st.get("coordinates") or {}
        lat, lon = coords.get("lat"), coords.get("lon")
        station_name = st.get("name", "")
        road = st.get("roadName", "")
        nome = f"IS - {station_name} ({road})" if road else f"IS - {station_name}"
        for img in st.get("images", []):
            url = img.get("url")
            if not url:
                continue
            desc = img.get("description", "")
            out.append({
                "id": make_id(url),
                "nome": nome,
                "local": desc or station_name,
                "cidade": "",
                "uf": "",
                "pais": "IS",
                "setor": "GLOBAL",
                "tipo_area": "TRAFFIC",
                "lat": lat,
                "long": lon,
                "status": "LIVE",
                "is_real_stream": True,
                "thumbnail_url": "",
                "url": url,
                "video_id": None,
                "source": "Vegagerdin",
                "stream_format": "SNAPSHOT_JPEG",
            })
    return out


def run(apply_changes: bool) -> Dict[str, Any]:
    build_id = fetch_build_id()
    stations = fetch_stations(build_id)
    new_cameras = build_cameras(stations)
    print(f"{len(stations)} estações, {len(new_cameras)} imagens/câmeras carregadas.")

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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(apply_changes=args.apply), indent=2, ensure_ascii=False))
