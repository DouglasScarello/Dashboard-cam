#!/usr/bin/env python3
"""
enrich_geo.py — Olho de Deus [Fase 13: Geographic Intelligence]

Este script injeta coordenadas geográficas (lat/long) no omni_cams.json
usando o banco de referências curadas (cameras.json).
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMNI_PATH = ROOT / "database" / "omni_cams.json"
REFS_PATH = ROOT / "olho_de_deus" / "cameras.json"

def enrich():
    if not OMNI_PATH.exists() or not REFS_PATH.exists():
        print("[error] Arquivos não encontrados.")
        return

    with open(OMNI_PATH, 'r', encoding='utf-8') as f:
        main_data = json.load(f)

    with open(REFS_PATH, 'r', encoding='utf-8') as f:
        refs_raw = json.load(f)

    # Achata as referências por ID
    geo_map = {}
    for country in refs_raw.values():
        for state in country.get("states", {}).values():
            for city in state.get("cities", {}).values():
                for cam in city.get("cameras", []):
                    geo_map[cam["id"]] = {
                        "lat": cam.get("lat"),
                        "long": cam.get("long")
                    }

    # Enriquece o dataset principal
    enriched_count = 0
    for cam in main_data:
        # Tenta casar pelo ID extraído da URL do YouTube
        url = cam.get("url", "")
        if "v=" in url:
            y_id = url.split("v=")[1].split("&")[0]
            if y_id in geo_map:
                cam["lat"] = geo_map[y_id]["lat"]
                cam["long"] = geo_map[y_id]["long"]
                enriched_count += 1
        # Se não tiver ID de vídeo, mas tiver nome exato
        elif cam.get("name") in geo_map:
             cam["lat"] = geo_map[cam["name"]]["lat"]
             cam["long"] = geo_map[cam["name"]]["long"]
             enriched_count += 1

    with open(OMNI_PATH, 'w', encoding='utf-8') as f:
        json.dump(main_data, f, indent=4, ensure_ascii=False)

    print(f"[sucesso] {enriched_count} câmeras enriquecidas com coordenadas GPS.")

if __name__ == "__main__":
    enrich()
