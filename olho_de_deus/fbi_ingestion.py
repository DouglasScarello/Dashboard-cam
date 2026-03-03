#!/usr/bin/env python3
"""
fbi_ingestion.py — Olho de Deus
Fulfill: Muni's Tip #3 (Modularization)
Inherits from BaseIngestor for standardized intelligence gathering.
"""
import requests
import os
import time
from tqdm import tqdm
from typing import List, Dict, Optional
from core.ingestor import BaseIngestor
from playwright.sync_api import sync_playwright

class FBIIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="FBI", db=db)
        self.api_url = "https://api.fbi.gov/wanted/v1/list"
        self.output_dir = "intelligence/data/images/fbi"
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_data(self, limit_pages: int = 1):
        """Busca dados da API do FBI e processa via BaseIngestor."""
        self.logger.info(f"Iniciando captura FBI: {limit_pages} páginas.")
        
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0")
            page = context.new_page()
            # Bloquear lixo para performance
            page.route("**/*.{css,woff,js}", lambda r: r.abort())

            for p in range(1, limit_pages + 1):
                try:
                    resp = requests.get(self.api_url, params={"page": p}, timeout=15)
                    if resp.status_code != 200: break
                    
                    data = resp.json()
                    if not data: break
                    items = data.get("items", [])
                    
                    for item in tqdm(items, desc=f"Página {p}"):
                        self._process_item(item, page)
                        
                except Exception as e:
                    self.logger.error(f"Erro na página {p}: {e}")
            
            browser.close()

    def _process_item(self, item: Dict, pw_page):
        """Traduz formato FBI para formato interno do Olho de Deus."""
        uid = item.get("uid")
        if not uid: return

        # Normalização de Campos
        normalized = {
            "id": uid,
            "name": (item.get("title") or "Desconhecido").upper(),
            "category": "wanted", 
            "source": "FBI",
            "description": (item.get("description") or "") + "\n\n" + (item.get("details") or ""),
            "sex": item.get("sex"),
            "birth_date": (item.get("dates_of_birth_used") or [None])[0],
            "occupation": item.get("occupations"),
            "reward": item.get("reward_text"),
            "nationalities": item.get("nationality"),
            "crimes": (item.get("caution") or "").split(",") if item.get("caution") else []
        }

        # Tratamento de Imagens
        images = item.get("images")
        if images and isinstance(images, list) and len(images) > 0:
            primary_img = images[0]
            if isinstance(primary_img, dict):
                p_url = primary_img.get("original") or primary_img.get("large") or primary_img.get("thumb")
                if p_url:
                    img_name = f"{uid}.jpg"
                    img_path = os.path.join(self.output_dir, img_name)
                    
                    if not os.path.exists(img_path):
                        self.download_image_pw(p_url, img_path, pw_page)
                    
                    normalized["img_url"] = p_url
                    normalized["img_path"] = f"data/images/fbi/{img_name}" 

            # Galeria extra
            normalized["gallery"] = [
                img.get("original") or img.get("large") 
                for img in images[1:] 
                if isinstance(img, dict) and (img.get("original") or img.get("large"))
            ]

        # Ingestão via Classe Base
        self.process_individual(normalized)

    def download_image_pw(self, url: str, dest: str, page):
        """Download especializado usando Playwright para evitar bloqueios de CDN."""
        try:
            resp = page.goto(url, timeout=30000)
            if resp and resp.ok:
                with open(dest, "wb") as f:
                    f.write(resp.body())
                return True
        except Exception as e:
            self.logger.warning(f"Falha PW download {url}: {e}")
        return False

if __name__ == "__main__":
    from intelligence_db import DB
    db = DB()
    ingestor = FBIIngestor(db=db)
    ingestor.fetch_data(limit_pages=20)
    ingestor.close()
