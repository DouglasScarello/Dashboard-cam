#!/usr/bin/env python3
"""
bnmp_ingestion.py — Olho de Deus
Foco: Brasil 🇧🇷 (Banco Nacional de Mandados de Prisão - CNJ)
Utiliza endpoints públicos do portal BNMP 3.0.
"""
import requests
import os
import json
import sys
from tqdm import tqdm
from typing import Dict, List, Optional

# Injetar caminho para intelligence_db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "intelligence")))

from core.ingestor import BaseIngestor
from playwright.sync_api import sync_playwright

class BNMPIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="BNMP_Brasil", db=db)
        # Endpoint de busca do BNMP 3.0 (Simulado do portal público)
        self.api_url = "https://bnmp3.cnj.jus.br/api/ge-servico-pesquisar-mandado/v1/mandados/pesquisar"
        self.output_dir = "intelligence/data/images/bnmp"
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_data(self, limit: int = 50):
        """Busca mandados de prisão ativos no Brasil usando Playwright para bypass de 403."""
        self.logger.info(f"Iniciando captura BNMP Brasil via Playwright: limite {limit} registros.")
        
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            # Ir para a página principal para estabelecer cookies/sessão
            context = browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = context.new_page()
            page.goto("https://bnmp3.cnj.jus.br/", wait_until="networkidle")

            # Payload para busca
            payload = {
                "pagina": 1,
                "quantidadeRegistros": limit,
                "status": "ATIVO"
            }

            try:
                # Realizar o POST usando o contexto do Playwright
                response = page.request.post(
                    self.api_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://bnmp3.cnj.jus.br/"
                    }
                )

                if response.status != 200:
                    self.logger.error(f"Falha na API BNMP via Playwright: {response.status}")
                    return

                data = response.json()
                items = data.get("listaMandados", [])
                
                for item in tqdm(items, desc="Captura BNMP"):
                    self._process_item(item)
                    
            except Exception as e:
                self.logger.error(f"Erro ao buscar dados do BNMP: {e}")
            finally:
                browser.close()

    def _process_item(self, item: Dict):
        """Normaliza os dados do BNMP para o formato Olho de Deus."""
        # O BNMP usa o número do mandado ou CPF como identificador
        uid = f"BRA_BNMP_{item.get('numeroMandado', 'UNKNOWN')}"
        
        # O BNMP muitas vezes exige uma segunda chamada para pegar detalhes e foto
        # Aqui simulamos a normalização dos dados disponíveis na lista principal
        normalized = {
            "id": uid,
            "name": item.get("nomePessoa", "DESCONHECIDO").upper(),
            "category": "wanted",
            "source": "BNMP/CNJ",
            "description": f"Mandado de Prisão Nº {item.get('numeroMandado')}\nÓrgão Expedidor: {item.get('orgaoJudiciario')}",
            "sex": item.get("sexo"),
            "birth_date": item.get("dataNascimento"),
            "crimes": [item.get("assuntoCnj", "Crime não especificado")],
            "nationalities": ["Brasil"],
            "locations": [item.get("orgaoJudiciario", "")]
        }

        # No BNMP 3.0, a foto é servida por um endpoint de anexo específico
        # url_foto = f"https://bnmp3.cnj.jus.br/api/ge-servico-exibir-anexo/v1/anexos/{item.get('idAnexoFoto')}"
        # Como o acesso à foto pode exigir autenticação ou cookies específicos, 
        # marcamos para tentativa de download futuro se o id existir.
        
        if item.get("idAnexoFoto"):
            photo_url = f"https://bnmp3.cnj.jus.br/api/ge-servico-exibir-anexo/v1/anexos/{item['idAnexoFoto']}"
            img_name = f"{uid}.jpg"
            img_path = os.path.join(self.output_dir, img_name)
            
            # Nota: O download pode requerer Playwright se houver proteção de sessão
            if self.download_image(photo_url, img_path):
                normalized["img_url"] = photo_url
                normalized["img_path"] = f"data/images/bnmp/{img_name}"

        self.process_individual(normalized)

if __name__ == "__main__":
    from intelligence_db import DB
    db = DB()
    ingestor = BNMPIngestor(db=db)
    # Teste com pequena amostra
    ingestor.fetch_data(limit=20)
    ingestor.close()
