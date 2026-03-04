#!/usr/bin/env python3
"""
opensanctions_ingestion.py — Olho de Deus
Foco: Agregação Global 🌍 (OpenSanctions Targets CSV)
Cobre: Europol, UK NCA, Holanda, Polônia, Espanha, etc.
"""
import requests
import os
import csv
import io
import sys
from tqdm import tqdm
from typing import Dict, List, Optional

# Injetar caminho para intelligence_db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "intelligence")))

from core.ingestor import BaseIngestor

class OpenSanctionsIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="OpenSanctions", db=db)
        self.base_url = "https://data.opensanctions.org/datasets/latest/{dataset}/targets.simple.csv"
        # Datasets solicitados pelo usuário
        self.datasets = {
            "eu_europol_wanted": "Europol (União Europeia)",
            "gb_nca_most_wanted": "NCA (Reino Unido)",
            "nl_most_wanted": "Holanda (Países Baixos)",
            "pl_wanted": "Polônia",
            "es_most_wanted": "Espanha"
        }

    def fetch_data(self, specific_dataset: Optional[str] = None):
        """Baixa e processa datasets do OpenSanctions."""
        target_datasets = {specific_dataset: self.datasets[specific_dataset]} if specific_dataset else self.datasets
        
        for ds_key, ds_label in target_datasets.items():
            self.logger.info(f"Iniciando captura OpenSanctions: {ds_label}")
            url = self.base_url.format(dataset=ds_key)
            
            try:
                resp = requests.get(url, timeout=60, stream=True)
                resp.raise_for_status()
                
                # Processar stream CSV para não carregar tudo na RAM
                content = resp.content.decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                
                rows = list(reader)
                for row in tqdm(rows, desc=f"OS {ds_key}"):
                    self._process_row(row, ds_key, ds_label)
                    
            except Exception as e:
                self.logger.error(f"Erro ao processar dataset {ds_key}: {e}")

    def _process_row(self, row: Dict, ds_key: str, ds_label: str):
        """Normaliza uma linha do CSV para o formato Olho de Deus."""
        uid = f"OS_{ds_key.upper()}_{row.get('id', '')}"
        name = row.get("name", "DESCONHECIDO").strip().upper()
        if not name or name == "N/A": return

        normalized = {
            "id": uid,
            "name": name,
            "category": "wanted",
            "source": f"OpenSanctions/{ds_label}",
            "description": f"Fonte Original: {ds_label}\nSanções/Motivo: {row.get('sanctions', 'Não especificado')}",
            "birth_date": row.get("birth_date"),
            "nationalities": row.get("countries", "").split(";"),
        }

        # OpenSanctions Simple CSV geralmente não tem URLs de imagem diretamente.
        # Imagens para estas fontes exigiriam scraping tático dos sites originais,
        # mas por hora indexamos os metadados para busca textual e futura biometria.
        
        self.process_individual(normalized)

if __name__ == "__main__":
    from intelligence_db import DB
    db = DB()
    ingestor = OpenSanctionsIngestor(db=db)
    # Baixar todos os datasets configurados
    ingestor.fetch_data()
    ingestor.close()
