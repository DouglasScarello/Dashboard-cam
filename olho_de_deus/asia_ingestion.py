#!/usr/bin/env python3
"""
asia_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: Ásia (Hong Kong via OpenSanctions, Índia NCRB, Coreia do Sul)
"""
import os
import sys
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from core.ingestor import BaseIngestor


class AsiaIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="Asia_Intel", db=db)
        self.output_dir = str(ROOT / "intelligence" / "data" / "images" / "asia")
        os.makedirs(self.output_dir, exist_ok=True)

    async def run(self, session: aiohttp.ClientSession, **kwargs) -> Dict:
        self.logger.info("[Asia] Iniciando captura regional")

        await asyncio.gather(
            self._fetch_hong_kong(session),
            self._fetch_india(session),
            self._fetch_south_korea(session),
            return_exceptions=True,
        )

        self.logger.info(self.report())
        return self.stats

    async def _fetch_hong_kong(self, session: aiohttp.ClientSession):
        """Hong Kong Police via OpenSanctions dataset hk_police_wanted."""
        self.logger.info("[Asia/HK] Consultando via OpenSanctions 'hk_police_wanted'")
        try:
            url = "https://data.opensanctions.org/datasets/latest/hk_police_wanted/targets.simple.csv"
            import csv, io
            raw = await self.get_text(session, url)
            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                name = row.get("name", "").strip().upper()
                if not name:
                    continue
                uid = f"HK_POLICE_{abs(hash(name))}"
                self.save({
                    "id":       uid,
                    "name":     name,
                    "category": "wanted",
                    "source":   "HK Police / OpenSanctions",
                    "description": f"Sanções: {row.get('sanctions', 'N/E')}",
                    "birth_date": row.get("birth_date"),
                })
        except Exception as e:
            self.logger.warning(f"[Asia/HK] Falha: {e} — dataset pode não estar disponível")
            self.stats["errors"] += 1

    async def _fetch_india(self, session: aiohttp.ClientSession):
        """Índia — NCRB state portals via OpenSanctions indiansanctions"""
        self.logger.info("[Asia/India] Consultando via OpenSanctions 'in_mha_wanted'")
        try:
            url = "https://data.opensanctions.org/datasets/latest/in_mha_wanted/targets.simple.csv"
            import csv, io
            raw = await self.get_text(session, url)
            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                name = row.get("name", "").strip().upper()
                if not name:
                    continue
                uid = f"IN_MHA_{abs(hash(name))}"
                self.save({
                    "id":       uid,
                    "name":     name,
                    "category": "wanted",
                    "source":   "India MHA / OpenSanctions",
                    "description": f"Sanções: {row.get('sanctions', 'N/E')}",
                    "nationalities": ["India"],
                })
        except Exception as e:
            self.logger.warning(f"[Asia/India] Falha: {e} — dataset pode não estar disponível")
            self.stats["errors"] += 1

    async def _fetch_south_korea(self, session: aiohttp.ClientSession):
        """Coreia do Sul — Endpoint de API pública (requer ServiceKey para acesso completo)."""
        self.logger.warning("[Asia/KR] data.go.kr requer ServiceKey — registrando como stub")
        # Stub para futura integração quando chave API for configurada
        self.save({
            "id":       "KR_API_STUB",
            "name":     "KOREA API PENDING KEY",
            "category": "info",
            "source":   "Korea data.go.kr",
            "description": "Endpoint: apis.data.go.kr/1320000/SearchMissingPersonService — requer ServiceKey",
        })


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = AsiaIngestor(db=db)
        async with aiohttp.ClientSession() as session:
            await ingestor.run(session)
        ingestor.close()
    asyncio.run(_main())
