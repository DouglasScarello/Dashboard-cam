#!/usr/bin/env python3
import json
import cv2
import yt_dlp
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "omni_cams.json"

def filter_elite():
    print("💎 Refinando Banco de Dados para Modo ELITE (HD/4K)...")
    
    if not DB_PATH.exists():
        print("Erro: Banco de dados não encontrado.")
        return

    with open(DB_PATH, 'r', encoding='utf-8') as f:
        cams = json.load(f)

    elite_cams = []
    ydl_opts = {'quiet': True, 'no_warnings': True}

    for cam in cams:
        print(f"Auditando: {cam['nome'][:40]}...", end="\r")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(cam['url'], download=False)
                width = info.get('width', 0)
                height = info.get('height', 0)
                
                # Critério Elite: Pelo menos 720p (HD)
                if height >= 720:
                    cam['res'] = f"{width}x{height}"
                    elite_cams.append(cam)
        except:
            continue

    print(f"\n✅ Concluído! {len(elite_cams)} unidades de elite preservadas.")
    
    # Salva o novo banco de dados filtrado
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(elite_cams, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    filter_elite()
