#!/usr/bin/env python3
"""
us_local_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: EUA Local — Phoenix Open Data + NamUs + marshals.gov
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

MARSHALS_API = "https://www.usmarshals.gov/api/wanted"


class USLocalIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="US_Local_Police", db=db)
        self.output_dir = str(ROOT / "intelligence" / "data" / "images" / "us_local")
        os.makedirs(self.output_dir, exist_ok=True)

    async def run(self, session: aiohttp.ClientSession, **kwargs) -> Dict:
        self.logger.info("[USLocal] Iniciando captura")

        await asyncio.gather(
            self._fetch_marshals(session),
            self._fetch_namus_stub(),
            return_exceptions=True,
        )

        self.logger.info(self.report())
        return self.stats

    async def _fetch_marshals(self, session: aiohttp.ClientSession):
        """US Marshals Service Wanted — api pública (se disponível)."""
        self.logger.info("[USLocal/Marshals] Tentando US Marshals API")
        try:
            data = await self.get_json(session, MARSHALS_API)
            items = data if isinstance(data, list) else data.get("items", data.get("wanted", []))
            self.logger.info(f"[USLocal/Marshals] {len(items)} registros")
            
            tasks = [self._process_marshal_item(session, item) for item in items]
            await asyncio.gather(*tasks)

        except Exception as e:
            # Marshals API pode não estar pública — fallback para Phoenix Open Data CKAN
            self.logger.warning(f"[USLocal/Marshals] {e} — pode exigir autenticação")
            await self._fetch_phoenix_fallback(session)

    async def _process_marshal_item(self, session: aiohttp.ClientSession, item: Dict):
        """Processa um registro individual do US Marshals Service."""
        uid = f"US_MARSHAL_{item.get('id', 'UNK')}"
        normalized = {
            "id":       uid,
            "name":     f"{item.get('first_name', '')} {item.get('last_name', '')}".strip().upper() or "UNKNOWN",
            "category": "wanted",
            "source":   "US Marshals",
            "description": item.get("description", ""),
            "sex":      item.get("sex"),
            "height_cm": self._parse_num(item.get("height")),
            "weight_kg": self._parse_num(item.get("weight")),
        }

        photo_url = item.get("photo_url")
        if photo_url:
            img_dest = os.path.join(self.output_dir, f"{uid}.jpg")
            await self.download_image(session, photo_url, img_dest, individual_id=uid)
            normalized["img_url"] = photo_url
            normalized["img_path"] = f"data/images/us_local/{uid}.jpg"

        self.save(normalized)

    def _parse_num(self, val) -> Optional[float]:
        try:
            return float(val)
        except (ValueError, TypeError):
            return None


    async def _fetch_phoenix_fallback(self, session: aiohttp.ClientSession):
        """Phoenix Open Data (CKAN) — cold cases / wanted persons."""
        url = "https://www.phoenixopendata.com/api/3/action/package_search?q=wanted&rows=20"
        try:
            data = await self.get_json(session, url)
            results = data.get("result", {}).get("results", [])
            self.logger.info(f"[USLocal/Phoenix] {len(results)} datasets encontrados")
            # Registra os datasets encontrados como referências
            for pkg in results[:5]:
                uid = f"US_PHX_{abs(hash(pkg.get('name', '')))}"
                self.save({
                    "id":       uid,
                    "name":     pkg.get("title", "UNKNOWN").upper(),
                    "category": "info",
                    "source":   "Phoenix Open Data",
                    "description": pkg.get("notes", "")[:500],
                    "nationalities": ["EUA"],
                })
        except Exception as e:
            self.logger.error(f"[USLocal/Phoenix] Falha: {e}")
            self.stats["errors"] += 1

    async def _fetch_namus_stub(self):
        """NamUs — requer registro oficial para API completa."""
        self.logger.warning("[USLocal/NamUs] namus.nij.ojp.gov requer registro — registrando stub")
        self.save({
            "id":       "NAMUS_REFERENCE",
            "name":     "NAMUS SYSTEM — US MISSING PERSONS",
            "category": "info",
            "source":   "NamUs EUA",
            "description": "Banco nacional de desaparecidos (namus.gov) — requer registro para acesso via API",
        })


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = USLocalIngestor(db=db)
        async with aiohttp.ClientSession() as session:
            await ingestor.run(session)
        ingestor.close()
    asyncio.run(_main())
