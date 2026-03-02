#!/usr/bin/env python3
"""
farm_cams.py - Crawler de Câmeras ao Vivo (YouTube)
Gera feeds formatados para a Importação Bulk do Dashboard OSS.
"""

import time
import sys
import yt_dlp
from typing import List, Dict

# Configuração de Alvos (Customizável pelo usuário)
ALVOS = [
    {"termo": "live cam florianópolis", "local": "Florianópolis, SC", "setor": "BR"},
    {"termo": "live cam balneário camboriú", "local": "Balneário Camboriú, SC", "setor": "BR"},
    {"termo": "live cam são paulo", "local": "São Paulo, SP", "setor": "BR"},
    {"termo": "live cam rio de janeiro", "local": "Rio de Janeiro, RJ", "setor": "BR"},
    {"termo": "live cam times square nyc", "local": "Times Square, NY", "setor": "US"},
    {"termo": "live cam shibuya tokyo crossing", "local": "Shibuya, Tokyo", "setor": "JP"},
    {"termo": "live cam london abbey road", "local": "London, UK", "setor": "UK"},
]

class YouTubeFarmer:
    def __init__(self, limit_per_term: int = 3):
        self.limit = limit_per_term
        self.ydl_opts = {
            'extract_flat': True,       # Extração rápida (não pega stream real, apenas metadados)
            'quiet': True,              # Silencioso
            'no_warnings': True,
            'skip_download': True,
        }

    def farm(self, targets: List[Dict]):
        print(f"\n{'='*60}")
        print(f" OSS v0.1 - CRAWLER DE CÂMERAS - DATA: {time.strftime('%d/%m/%Y')}")
        print(f"{'='*60}")
        print("COPIE E COLE AS LINHAS ABAIXO NA IMPORTAÇÃO BULK DO DASHBOARD:\n")

        for target in targets:
            termo = target.get("termo")
            local = target.get("local")
            setor = target.get("setor")

            # Prefixo 'ytsearch:' diz para o yt-dlp fazer a busca no YouTube
            search_query = f"ytsearch{self.limit}:{termo}"
            
            try:
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    result = ydl.extract_info(search_query, download=False)
                    
                    if 'entries' in result:
                        for entry in result['entries']:
                            if not entry: continue
                            
                            video_id = entry.get('id')
                            title = entry.get('title', 'Câmera Sem Título')
                            
                            # Higienização do Nome (Regras do Sênior)
                            # 1. Tudo em Maiúsculo
                            # 2. Trocar | por - (para não quebrar o parser)
                            safe_name = title.replace('|', '-').upper().strip()
                            url = f"https://www.youtube.com/watch?v={video_id}"
                            
                            # Formatação Final: NOME | URL | LOCAL | SETOR
                            print(f"{safe_name} | {url} | {local} | {setor}")

                # Delay anti-bloqueio (Gargalo identificado)
                time.sleep(2)

            except Exception as e:
                # Silencioso para não quebrar o output formatado, mas loga no stderr
                sys.stderr.write(f"[ERRO] Falha ao farmar '{termo}': {str(e)}\n")

        print(f"\n{'='*60}")
        print(" FIM DO PROCESSO DE EXTRAÇÃO")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    farmer = YouTubeFarmer(limit_per_term=3)
    farmer.farm(ALVOS)
