#!/usr/bin/env python3
"""
farm_omni.py - O Crawler Definitivo do OSS (Omniscient Surveillance System)
Suporta: YouTube (via yt-dlp) e Diretórios HLS Publicos (via requests/bs4).
Formato de Saída: NOME | URL | LOCAL | SETOR
"""

import time
import sys
import argparse
import json
import os
import requests
import yt_dlp
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from pathlib import Path

# Configuração de Caminhos
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "omni_cams.json"

# Desabilitar avisos de SSL (Para crawlers em sites com cert assinados/expirados)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAÇÃO DE ALVOS ---

ALVOS_YT = [
    {"termo": "live cam Florianópolis", "local": "Florianópolis, SC", "setor": "BR"},
    {"termo": "live cam Balneário Camboriú", "local": "Balneário Camboriú, SC", "setor": "BR"},
    {"termo": "live cam São Paulo", "local": "São Paulo, SP", "setor": "BR"},
    {"termo": "Times Square NYC live", "local": "New York, NY", "setor": "US"},
    {"termo": "Shibuya Crossing live", "local": "Tokyo, Japan", "setor": "JP"},
    {"termo": "Kensington Ave Philadelphia live", "local": "Philadelphia, PA", "setor": "US"},
]

# Exemplo de diretórios HLS públicos (Agregadores de Câmeras de Trânsito/Tempo)
ALVOS_HLS = [
    {"url": "https://www.skylinewebcams.com/en/webcam/brazil/santa-catarina/florianopolis.html", "local": "Florianópolis, SC", "setor": "BR"},
    {"url": "https://www.insecam.org/en/bycountry/BR/", "local": "Brasil (CCTV)", "setor": "BR"},
]

class OmniFarmer:
    def __init__(self, headers: Optional[Dict] = None):
        self.headers = headers or {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def clean_name(self, name: str) -> str:
        """Higieniza o nome para o padrão Dashboard."""
        return name.replace('|', '-').upper().strip()

    def load_db(self) -> List[Dict]:
        """Carrega o banco de dados JSON."""
        if not DB_PATH.exists():
            return []
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def save_db(self, data: List[Dict]):
        """Salva o banco de dados JSON."""
        # Garante o diretório
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def add_camera_to_db(self, camera: Dict, db: List[Dict]) -> bool:
        """Adiciona câmera se não for duplicada (baseada na URL)."""
        if any(c['url'] == camera['url'] for c in db):
            return False
        
        # Gera ID incremental se necessário
        if not db:
            camera['id'] = 1000
        else:
            camera['id'] = max(c.get('id', 999) for c in db) + 1
            
        db.append(camera)
        return True

    def farm_youtube(self, limit_per_term: int = 15):
        """Engine YouTube: Pesquisa apenas transmissões AO VIVO reais."""
        print(f"\n[ENGINE] YouTube Search - Limite: {limit_per_term} resultados/alvo")
        
        db = self.load_db()
        new_count = 0
        
        ydl_opts = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
        }

        for target in ALVOS_YT:
            termo = target["termo"]
            search_query = f"ytsearch{limit_per_term}:{termo} live"
            
            try:
                print(f"[SEARCH] {termo}...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    result = ydl.extract_info(search_query, download=False)
                    
                    if 'entries' in result:
                        for entry in result['entries']:
                            if not entry: continue
                            
                            duration = entry.get('duration')
                            live_status = entry.get('live_status') or entry.get('is_live')
                            title = entry.get('title', 'NO NAME')

                            if duration is None or live_status == 'is_live' or 'LIVE' in title.upper():
                                camera = {
                                    "nome": self.clean_name(title),
                                    "url": f"https://www.youtube.com/watch?v={entry['id']}",
                                    "local": target["local"],
                                    "setor": target["setor"],
                                    "pais": target["setor"], # Simplificação para o dashboard
                                    "tipo": "youtube",
                                    "status": "AO VIVO"
                                }
                                
                                if self.add_camera_to_db(camera, db):
                                    print(f"[NEW] {camera['nome']}")
                                    new_count += 1

                time.sleep(3)

            except Exception as e:
                sys.stderr.write(f"[ERROR YT] {termo}: {e}\n")
        
        self.save_db(db)
        print(f"\n[FINISH] {new_count} novas câmeras adicionadas ao banco.")

    def farm_hls(self):
        """Engine HLS: Scraper de diretórios públicos em busca de .m3u8 ativos."""
        print("\n[ENGINE] HLS Scraper - Analisando diretórios públicos...")

        for target in ALVOS_HLS:
            url_dir = target["url"]
            try:
                print(f"[SCRAPE] {url_dir}...")
                response = requests.get(url_dir, headers=self.headers, timeout=10, verify=False)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Procura links .m3u8 em tags <source>, scripts ou atributos data
                links_encontrados = []
                
                # Busca bruta no texto do HTML (comum em scripts de stream)
                import re
                m3u8_links = re.findall(r'https?://[^\s\'"]+\.m3u8', response.text)
                links_encontrados.extend(m3u8_links)

                for link in set(links_encontrados):
                    # Validação de sinal (Head 200) com bypass de SSL
                    try:
                        check = requests.head(link, timeout=3, headers=self.headers, verify=False)
                        if check.status_code == 200:
                            # Nome baseado em pedaço da URL ou título da página
                            name_part = link.split('/')[-1].replace('.m3u8', '').replace('_', ' ')
                            doc_title = soup.title.string if soup.title else "HLS UNIT"
                            safe_name = self.clean_name(f"{doc_title} - {name_part}")
                            
                            print(f"{safe_name} | {link} | {target['local']} | {target['setor']}")
                    except:
                        continue

            except Exception as e:
                sys.stderr.write(f"[ERROR HLS] {url_dir}: {e}\n")

def main():
    parser = argparse.ArgumentParser(description="OSS Omni-Farmer v15.0")
    parser.add_argument("--source", choices=["youtube", "hls", "all"], default="all",
                        help="Escolha o motor de busca (youtube, hls ou all)")
    args = parser.parse_args()

    farmer = OmniFarmer()
    
    print(f"\n{'='*70}")
    print(f" OMNI-FARMER v15.0 - MONITORAMENTO GLOBAL")
    print(f" DATA: {time.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*70}")
    print("COPIE O OUTPUT PARA A IMPORTAÇÃO BULK NO DASHBOARD\n")

    if args.source in ["youtube", "all"]:
        farmer.farm_youtube()
    
    if args.source in ["hls", "all"]:
        farmer.farm_hls()

    print(f"\n{'='*70}")
    print(" FIM DO PROCESSO DE BUSCA")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
