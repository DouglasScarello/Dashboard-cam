#!/usr/bin/env python3
"""
opensanctions_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: OpenSanctions Bulk CSV (Europol, NCA UK, NL, PL, ES)
Usa aiohttp para download de CSVs em paralelo por dataset.
"""
import os
import sys
import csv
import io
import asyncio
import aiohttp
from pathlib import Path
from tqdm.asyncio import tqdm
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from core.ingestor import BaseIngestor

BASE_URL = "https://data.opensanctions.org/datasets/latest/{dataset}/targets.simple.csv"

DATASETS = {
    "eu_europol_wanted":   "Europol (União Europeia)",
    "gb_nca_most_wanted":  "NCA (Reino Unido)",
    "nl_most_wanted":      "Holanda (Países Baixos)",
    "pl_wanted":           "Polônia",
    "es_most_wanted":      "Espanha",
}


class OpenSanctionsIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="OpenSanctions", db=db)

    async def run(self, session: aiohttp.ClientSession, specific_dataset: Optional[str] = None, **kwargs) -> Dict:
        target = (
            {specific_dataset: DATASETS[specific_dataset]}
            if specific_dataset and specific_dataset in DATASETS
            else DATASETS
        )

        self.logger.info(f"[OpenSanctions] Baixando {len(target)} datasets em paralelo")

        # Todos os datasets disparam em paralelo
        tasks = [self._fetch_dataset(session, key, label) for key, label in target.items()]
        await tqdm.gather(*tasks, desc="[OpenSanctions] Datasets")

        self.logger.info(self.report())
        return self.stats

    async def _fetch_dataset(self, session: aiohttp.ClientSession, ds_key: str, ds_label: str):
        url = BASE_URL.format(dataset=ds_key)
        try:
            self.logger.info(f"[OS] Baixando {ds_label}...")
            raw = await self.get_text(session, url)
            reader = csv.DictReader(io.StringIO(raw))
            rows = list(reader)
            self.logger.info(f"[OS] {ds_label}: {len(rows)} registros")
            for row in rows:
                self._process_row(row, ds_key, ds_label)
        except Exception as e:
            self.logger.error(f"[OS] Falha dataset {ds_key}: {e}")
            self.stats["errors"] += 1

    def _process_row(self, row: Dict, ds_key: str, ds_label: str):
        uid  = f"OS_{ds_key.upper()}_{row.get('id', '')}"
        name = row.get("name", "").strip().upper()
        if not name:
            self.stats["skipped"] += 1
            return

        self.save({
            "id":           uid,
            "name":         name,
            "category":     "wanted",
            "source":       f"OpenSanctions/{ds_label}",
            "description":  f"Fonte: {ds_label}\nSanções: {row.get('sanctions', 'N/E')}",
            "birth_date":   row.get("birth_date"),
            "nationalities": [c.strip() for c in row.get("countries", "").split(";") if c.strip()],
            "crimes":       [row.get("sanctions", "")] if row.get("sanctions") else [],
            "first_seen":   row.get("first_seen"),
            "last_seen":    row.get("last_seen"),
        })


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = OpenSanctionsIngestor(db=db)
        async with aiohttp.ClientSession() as session:
            await ingestor.run(session)
        ingestor.close()
    asyncio.run(_main())
