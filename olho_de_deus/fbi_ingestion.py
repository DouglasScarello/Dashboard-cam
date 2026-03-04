#!/usr/bin/env python3
"""
fbi_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: FBI Wanted API (api.fbi.gov)
Usa aiohttp para requests + Playwright em executor para download de imagens.
"""
import os
import sys
import asyncio
import aiohttp
from pathlib import Path
from tqdm.asyncio import tqdm
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from core.ingestor import BaseIngestor

FBI_API = "https://api.fbi.gov/wanted/v1/list"


class FBIIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="FBI", db=db)
        self.output_dir = str(ROOT / "intelligence" / "data" / "images" / "fbi")
        os.makedirs(self.output_dir, exist_ok=True)

    async def run(self, session: aiohttp.ClientSession, limit_pages: int = 5, **kwargs) -> Dict:
        self.logger.info(f"[FBI] Iniciando captura — {limit_pages} páginas")

        # Descobre total de páginas
        try:
            meta = await self.get_json(session, FBI_API, params={"page": 1})
            total = meta.get("total", 0)
            pages = min((total // 20) + 1, limit_pages)
            self.logger.info(f"[FBI] {total} registros → {pages} páginas")
        except Exception as e:
            self.logger.error(f"[FBI] Falha ao obter metadados: {e}")
            self.stats["errors"] += 1
            return self.stats

        # Busca páginas em paralelo (max 5 concurrent para respeitar rate limit)
        semaphore = asyncio.Semaphore(5)
        tasks = [self._fetch_page(session, semaphore, p) for p in range(1, pages + 1)]
        await tqdm.gather(*tasks, desc="[FBI] Páginas")

        self.logger.info(self.report())
        return self.stats

    async def _fetch_page(self, session: aiohttp.ClientSession, sem: asyncio.Semaphore, page: int):
        async with sem:
            try:
                data = await self.get_json(session, FBI_API, params={"page": page})
                items = data.get("items", [])
                for item in items:
                    await self._process_item(session, item)
                await asyncio.sleep(0.2)  # Gentle rate limit
            except Exception as e:
                self.logger.error(f"[FBI] Erro página {page}: {e}")
                self.stats["errors"] += 1

    async def _process_item(self, session: aiohttp.ClientSession, item: Dict):
        uid = item.get("uid")
        if not uid:
            self.stats["skipped"] += 1
            return

        subjects = item.get("subjects", [])
        cat = "missing" if any("missing" in s.lower() for s in subjects) else "wanted"

        normalized = {
            "id": uid,
            "name": (item.get("title") or "DESCONHECIDO").upper(),
            "category": cat,
            "source": "FBI",
            "description": ((item.get("description") or "") + "\n" + (item.get("details") or "")).strip(),
            "sex": item.get("sex"),
            "birth_date": (item.get("dates_of_birth_used") or [None])[0],
            "occupation": (item.get("occupations") or [None])[0],
            "reward": item.get("reward_text"),
            "nationalities": item.get("nationality") if isinstance(item.get("nationality"), list) else [item.get("nationality")] if item.get("nationality") else [],
            "aliases": item.get("aliases") or [],
            "crimes": [c for c in (item.get("subjects") or [])],
            "eye_color": item.get("eyes"),
            "hair_color": item.get("hair"),
            "height_cm": self._parse_num(item.get("height")),
            "weight_kg": self._parse_num(item.get("weight")),
            "url": item.get("url"),
        }

        # Imagem principal
        imgs = item.get("images") or []
        if imgs and isinstance(imgs[0], dict):
            p_url = imgs[0].get("original") or imgs[0].get("large") or imgs[0].get("thumb")
            if p_url:
                img_dest = os.path.join(self.output_dir, f"{uid}.jpg")
                await self.download_image(session, p_url, img_dest, individual_id=uid)
                normalized["img_url"] = p_url
                normalized["img_path"] = f"data/images/fbi/{uid}.jpg"

        # Galeria extra
        normalized["gallery"] = [
            (img.get("original") or img.get("large"))
            for img in imgs[1:]
            if isinstance(img, dict) and (img.get("original") or img.get("large"))
        ]

        self.save(normalized)

    @staticmethod
    def _parse_num(val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(str(val).replace('"', '').replace("'", '').split()[0])
        except Exception:
            return None


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = FBIIngestor(db=db)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            await ingestor.run(session, limit_pages=10)
        ingestor.close()
    asyncio.run(_main())
