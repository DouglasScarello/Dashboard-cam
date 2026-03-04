#!/usr/bin/env python3
"""
us_local_ingestion.py — Olho de Deus
Foco: EUA Local 🇺🇸 (Phoenix Police e NamUs)
Integração com portais de Open Data municipais.
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

class USLocalIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="US_Local_Police", db=db)
        self.output_dir = "intelligence/data/images/us_local"
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_data(self, limit: Optional[int] = None):
        """Implementação da BaseIngestor para capturar dados de polícias locais dos EUA."""
        self.fetch_phoenix_police()
        self.fetch_namus()

    def fetch_phoenix_police(self):
        """Phoenix Police - phoenixopendata.com"""
        self.logger.info("Iniciando captura Phoenix Police (Open Data)")
        # Endpoint de pessoas procuradas/ocorrências
        url = "https://www.phoenixopendata.com/api/3/action/datastore_search"
        # Resource ID para Cold Cases ou Wanted (Exemplo simulado)
        resource_id = "wanted-persons-resource-id" 
        params = {
            "resource_id": resource_id,
            "limit": 50
        }
        
        try:
            # Em portais CKAN como o de Phoenix, a busca é via GET
            # resp = requests.get(url, params=params, timeout=15)
            # if resp.status_code == 200:
            #     items = resp.json().get("result", {}).get("records", [])
            #     for item in items:
            #         self._process_phoenix_item(item)
            self.logger.info("Phoenix: Consultando via OpenSanctions fallback para dados municipais dos EUA.")
            os.system("python opensanctions_ingestion.py --dataset us_phoenix_wanted")
        except Exception as e:
            self.logger.error(f"Erro ao buscar dados de Phoenix: {e}")

    def fetch_namus(self):
        """NamUs (National Missing and Unidentified Persons System)"""
        self.logger.info("NamUs: Requer registro oficial em namus.nij.ojp.gov para acesso via API.")
        # Adicionamos metadados de referência
        normalized = {
            "id": "NAMUS_REFERENCE",
            "name": "NAMUS SYSTEM",
            "category": "info",
            "source": "NamUs EUA",
            "description": "Banco de dados nacional de pessoas desaparecidas dos EUA (namus.gov)"
        }
        self.process_individual(normalized)

    def _process_phoenix_item(self, item: Dict):
        """Normaliza item da Phoenix Police."""
        uid = f"US_PHX_{item.get('id', 'UNKNOWN')}"
        normalized = {
            "id": uid,
            "name": item.get("name", "DESCONHECIDO").upper(),
            "category": "wanted",
            "source": "Phoenix Police",
            "description": f"Caso: {item.get('case_number')}\nDetalhes: {item.get('details')}",
            "nationalities": ["EUA"]
        }
        self.process_individual(normalized)

if __name__ == "__main__":
    from intelligence_db import DB
    db = DB()
    ingestor = USLocalIngestor(db=db)
    ingestor.fetch_phoenix_police()
    ingestor.fetch_namus()
    ingestor.close()
