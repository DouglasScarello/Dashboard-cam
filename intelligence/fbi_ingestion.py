#!/usr/bin/env python3
import requests
import os
import json
import time
import numpy as np
import faiss
from tqdm import tqdm
from typing import List, Dict, Optional
from deepface import DeepFace
from playwright.sync_api import sync_playwright

# Configuração de Logs p/ DeepFace (evitar ruído)
import logging
logging.getLogger("deepface").setLevel(logging.ERROR)

def _playwright_download(url: str, dest_path: str, page) -> bool:
    """Usa uma página Playwright existente para baixar uma imagem."""
    try:
        response = page.goto(url, timeout=20000, wait_until="domcontentloaded")
        if response and response.ok:
            content_type = response.headers.get("content-type", "")
            if "image" in content_type:
                with open(dest_path, 'wb') as f:
                    f.write(response.body())
                return True
            else:
                # Fallback: screenshot da área de imagem visible na página
                page.screenshot(path=dest_path, type="jpeg", clip={"x": 0, "y": 0, "width": 400, "height": 500})
                return True
    except Exception as e:
        print(f"[warning] playwright_download falhou: {e}")
    return False

class FBIIngestor:
    def __init__(self, base_url: str = "https://api.fbi.gov/wanted/v1/list"):
        self.base_url = base_url
        self.output_dir = "data/fbi_faces"
        os.makedirs(self.output_dir, exist_ok=True)
        self.db_path = "data/fbi_intelligence.json"
        self.delay = 0.25  # 4 requisições por segundo (rate limit balanceado)

    def fetch_page(self, page: int = 1) -> Dict:
        """Busca uma página específica da API."""
        params = {"page": page}
        response = requests.get(self.base_url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[error] Falha na página {page}: {response.status_code}")
            return {}

    def sync(self, limit_pages: Optional[int] = None):
        """Sincroniza a base local com a API do FBI."""
        print("[sistema] Iniciando sincronização com FBI Wanted API...")
        
        first_page = self.fetch_page(1)
        total_items = first_page.get("total", 0)
        items_per_page = 20
        total_pages = (total_items // items_per_page) + 1
        
        if limit_pages:
            total_pages = min(total_pages, limit_pages)

        intelligence_base = []

        for page in tqdm(range(1, total_pages + 1), desc="Baixando metadados"):
            data = self.fetch_page(page)
            for item in data.get("items", []):
                intelligence_base.append({
                    "uid": item.get("uid"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "images": item.get("images", []),
                    "files": item.get("files", []),
                })
            time.sleep(self.delay)

        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(intelligence_base, f, indent=4, ensure_ascii=False)
            
        print(f"[sucesso] {len(intelligence_base)} registros sincronizados em {self.db_path}")
        self.process_biometrics(intelligence_base)

    def process_biometrics(self, intelligence_base: List[Dict]):
        """Baixa imagens e gera embeddings para cada registro."""
        print("\n[sistema] Iniciando extração biométrica (ArcFace)...")
        
        embeddings_list = []
        metadata_list = []
        
        # Garantir que o diretório de dados existe
        os.makedirs("data", exist_ok=True)

        # Abrir UMA sessão de browser compartilhada p/ todos os downloads
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0.0.0 Safari/537.36",
                extra_http_headers={"Referer": "https://www.fbi.gov/"}
            )
            page = context.new_page()
            # Bloquear recursos desnecessários p/ acelerar
            page.route("**/*.{css,woff,woff2,ttf,eot,js}", lambda route: route.abort())

            self._process_loop(intelligence_base, page, embeddings_list, metadata_list)
            browser.close()

        if embeddings_list:
            self.save_vector_db(embeddings_list, metadata_list)

    def _process_loop(self, intelligence_base, page, embeddings_list, metadata_list):
        """Loop interno de biometria com sessão Playwright compartilhada."""
        for person in tqdm(intelligence_base, desc="Processando Biometria"):
            uid = person["uid"]
            images = person.get("images", [])
            if not images:
                continue
                
            # Buscar a imagem original/maior
            img_url = (
                images[0].get("large") or
                images[0].get("thumb") or
                images[0].get("original")
            )
            if not img_url:
                continue

            img_path = os.path.join(self.output_dir, f"{uid}.jpg")

            # Download via Playwright (bypassa 403 do CDN do FBI)
            if not os.path.exists(img_path):
                ok = _playwright_download(img_url, img_path, page)
                if not ok:
                    continue

            # Extração de Embedding
            try:
                # Usando ArcFace via DeepFace
                objs = DeepFace.represent(
                    img_path = img_path, 
                    model_name = "ArcFace", 
                    enforce_detection = False,
                    detector_backend = "opencv"
                )
                
                if objs:
                    embedding = objs[0]["embedding"]
                    embeddings_list.append(embedding)
                    metadata_list.append({
                        "uid": uid,
                        "title": person["title"],
                        "description": person["description"]
                    })
            except Exception as e:
                print(f"[warning] Falha ao processar {uid}: {type(e).__name__}: {e}")
                continue

    def save_vector_db(self, embeddings: List[List[float]], metadata: List[Dict]):
        """Cria e salva o índice FAISS e metadados associados."""
        embeddings_np = np.array(embeddings).astype('float32')
        dimension = embeddings_np.shape[1]
        
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings_np)
        
        faiss.write_index(index, "data/vector_db.faiss")
        with open("data/vector_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
            
        print(f"[sucesso] Base vetorial criada: {len(metadata)} faces mapeadas.")

if __name__ == "__main__":
    ingestor = FBIIngestor()
    # Para teste, limitamos a 2 páginas
    ingestor.sync(limit_pages=2)
