#!/usr/bin/env python3
"""
interpol_ingestion.py — Olho de Deus
Foco: Global 🌍 (Interpol - Red & Yellow Notices)
Utiliza a API pública oficial ws-public.interpol.int.
"""
import requests
import os
import time
import sys
from tqdm import tqdm
from typing import Dict, List, Optional

# Injetar caminho para intelligence_db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "intelligence")))

from core.ingestor import BaseIngestor
from playwright.sync_api import sync_playwright

class InterpolIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="Interpol", db=db)
        self.api_base = "https://ws-public.interpol.int/notices/v1"
        self.output_dir = "intelligence/data/images/interpol"
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_data(self, max_pages: int = 5):
        """Busca Red e Yellow Notices da Interpol via scraping da galeria pública (bypass 403 API)."""
        # URLs de galeria pública
        types = {
            "red": "https://www.interpol.int/How-we-work/Notices/Red-Notices/View-Red-Notices",
            "yellow": "https://www.interpol.int/How-we-work/Notices/Yellow-Notices/View-Yellow-Notices"
        }
        
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = context.new_page()
            
            for n_type, base_url in types.items():
                self.logger.info(f"Iniciando scraping galeria Interpol {n_type.upper()}.")
                
                for pg_num in range(1, max_pages + 1):
                    url = f"{base_url}?page={pg_num}"
                    try:
                        page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        # Esperar um dos cartões aparecer
                        try:
                            page.wait_for_selector(".redNoticeItem", timeout=15000)
                        except:
                            self.logger.warning(f"Nenhum cartão encontrado na página {pg_num} (Interpol {n_type})")
                            break
                        
                        # Rolagem suave para garantir carregamento de imagens
                        page.evaluate("window.scrollBy(0, 500)")
                        page.wait_for_timeout(1000)

                        # Cartões da galeria
                        cards = page.query_selector_all(".redNoticeItem")
                        if not cards:
                            break
                            
                        for card in tqdm(cards, desc=f"Interpol {n_type.upper()} Pg {pg_num}"):
                            self._process_card(card, n_type)
                            
                    except Exception as e:
                        self.logger.error(f"Erro na página {pg_num} ({n_type}): {e}")
            
            browser.close()

    def _process_card(self, card, n_type):
        """Processa um card HTML da Interpol."""
        try:
            name_el  = card.query_selector(".redNoticeItem__labelLink")
            img_el   = card.query_selector(".redNoticeItem__img")
            
            name    = name_el.inner_text().strip().replace("\n", " ") if name_el else "N/A"
            img_url = img_el.get_attribute("src") if img_el else None
            
            if name == "N/A": return

            # Resolver URL relativa se necessário
            if img_url and img_url.startswith("/"):
                img_url = "https://www.interpol.int" + img_url

            uid = f"INTERPOL_{n_type.upper()}_{abs(hash(name))}"
            
            normalized = {
                "id": uid,
                "name": name.upper(),
                "category": "wanted" if n_type == "red" else "missing",
                "source": f"Interpol/{n_type.capitalize()}",
                "description": f"Interpol {n_type.capitalize()} Notice extraído da galeria pública."
            }

            if img_url:
                img_name = f"{uid}.jpg"
                # Salvar na pasta correta
                img_path = os.path.join(self.output_dir, img_name)
                if self.download_image(img_url, img_path):
                    normalized["img_url"] = img_url
                    normalized["img_path"] = f"data/images/interpol/{img_name}"

            self.process_individual(normalized)
        except Exception as e:
            self.logger.error(f"Erro ao processar card Interpol: {e}")

    def _process_item(self, item: Dict, n_type: str):
        """Normaliza os dados da Interpol para o formato Olho de Deus."""
        # A Interpol fornece um links -> self -> href que contém o ID único
        entity_id = item.get("entity_id", "UNKNOWN").replace("/", "_")
        uid = f"INTERPOL_{n_type.upper()}_{entity_id}"
        
        normalized = {
            "id": uid,
            "name": f"{item.get('forename', '')} {item.get('name', '')}".strip().upper(),
            "category": "wanted" if n_type == "red" else "missing",
            "source": f"Interpol/{n_type.capitalize()}",
            "sex": item.get("sex_id"),
            "birth_date": item.get("date_of_birth"),
            "nationalities": item.get("nationalities", []),
            "description": f"Interpol {n_type.capitalize()} Notice\nEntity ID: {entity_id}"
        }

        # Imagem - a Interpol fornece via links -> images e links -> thumbnail
        img_links = item.get("_links", {})
        photo_url = None
        if "thumbnail" in img_links:
            photo_url = img_links["thumbnail"]["href"]
        
        if photo_url:
            img_name = f"{uid}.jpg"
            img_path = os.path.join(self.output_dir, img_name)
            
            if self.download_image(photo_url, img_path):
                normalized["img_url"] = photo_url
                normalized["img_path"] = f"data/images/interpol/{img_name}"

        self.process_individual(normalized)

if __name__ == "__main__":
    from intelligence_db import DB
    db = DB()
    ingestor = InterpolIngestor(db=db)
    # Coleta inicial
    ingestor.fetch_data()
    ingestor.close()
