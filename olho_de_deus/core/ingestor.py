#!/usr/bin/env python3
"""
core/ingestor.py — Olho de Deus
BaseIngestor: Classe base para normalizar a ingestão de inteligência.
Fulfill: Muni's Tip #3 (Modularization)
"""
import os
import requests
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from intelligence_db import DB, upsert_individual, insert_crimes, insert_image

class BaseIngestor(ABC):
    def __init__(self, source_name: str, db: Optional[DB] = None):
        self.source_name = source_name
        self.db = db or DB()
        self.logger = logging.getLogger(f"ingestor.{source_name}")
        
    @abstractmethod
    def fetch_data(self, limit: Optional[int] = None):
        """Busca dados da fonte remota."""
        pass

    def process_individual(self, data: Dict):
        """Normaliza e salva um indivíduo no banco."""
        try:
            # 1. Upsert dos dados básicos
            upsert_individual(self.db, data)
            
            # 2. Inserir Crimes
            if "crimes" in data:
                insert_crimes(self.db, data["id"], data["crimes"])
                
            # 3. Registrar Imagens (Galeria)
            if "img_url" in data and data["img_url"]:
                insert_image(self.db, data["id"], img_url=data["img_url"], is_primary=True)
                
            if "gallery" in data:
                for img_url in data["gallery"]:
                    insert_image(self.db, data["id"], img_url=img_url, is_primary=False)
            
            self.db.commit()
            return True
        except Exception as e:
            self.logger.error(f"Erro ao processar {data.get('id')}: {e}")
            return False

    def download_image(self, url: str, target_path: str):
        """Utilitário para download seguro de evidências visuais."""
        if os.path.exists(target_path):
            return True
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            r = requests.get(url, timeout=20, stream=True)
            if r.status_code == 200:
                with open(target_path, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
                return True
        except Exception as e:
            self.logger.error(f"Falha no download {url}: {e}")
        return False

    def close(self):
        self.db.close()
