#!/usr/bin/env python3
"""
bnmp_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: BNMP Brasil — Banco Nacional de Mandados de Prisão (CNJ)
Usa Playwright async via run_in_executor (necessário para bypass de 403 com cookies).
"""
import os
import sys
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from core.ingestor import BaseIngestor

BNMP_API  = "https://bnmp3.cnj.jus.br/api/ge-servico-pesquisar-mandado/v1/mandados/pesquisar"
BNMP_HOME = "https://bnmp3.cnj.jus.br/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


class BNMPIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="BNMP_Brasil", db=db)
        self.output_dir = str(ROOT / "intelligence" / "data" / "images" / "bnmp")
        os.makedirs(self.output_dir, exist_ok=True)
        self._limit = 50

    async def run(self, session: aiohttp.ClientSession, limit: int = 50, **kwargs) -> Dict:
        self._limit = limit
        self.logger.info(f"[BNMP] Iniciando captura via Playwright — limite: {limit}")

        # Playwright blocking → roda no executor
        await self.run_playwright_sync(self._scrape, limit)

        self.logger.info(self.report())
        return self.stats

    def _scrape(self, limit: int):
        """Scraping síncrono executado em thread pool."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA)
            page = ctx.new_page()

            # Estabelece sessão/cookies
            page.goto(BNMP_HOME, wait_until="networkidle", timeout=30_000)

            payload = {"pagina": 1, "quantidadeRegistros": limit, "status": "ATIVO"}
            try:
                resp = page.request.post(
                    BNMP_API,
                    data=payload,
                    headers={"Content-Type": "application/json", "Referer": BNMP_HOME},
                )
                if resp.status != 200:
                    self.logger.error(f"[BNMP] HTTP {resp.status}")
                    self.stats["errors"] += 1
                    return

                items = resp.json().get("listaMandados", [])
                self.logger.info(f"[BNMP] {len(items)} mandados recebidos")

                for item in items:
                    self._process_item(item, page)

            except Exception as e:
                self.logger.error(f"[BNMP] Erro ao buscar mandados: {e}")
                self.stats["errors"] += 1
            finally:
                browser.close()

    def _process_item(self, item: Dict, page):
        uid = f"BRA_BNMP_{item.get('numeroMandado', 'UNKNOWN')}"

        normalized = {
            "id":          uid,
            "name":        item.get("nomePessoa", "DESCONHECIDO").upper(),
            "category":    "wanted",
            "source":      "BNMP/CNJ",
            "description": (
                f"Mandado Nº {item.get('numeroMandado')}\n"
                f"Órgão: {item.get('orgaoJudiciario', 'N/E')}"
            ),
            "sex":         item.get("sexo"),
            "birth_date":  item.get("dataNascimento"),
            "crimes":      [item.get("assuntoCnj", "Crime não especificado")],
            "nationalities": ["Brasil"],
        }

        # Tenta download da foto via cookies de sessão
        if item.get("idAnexoFoto"):
            photo_url = f"https://bnmp3.cnj.jus.br/api/ge-servico-exibir-anexo/v1/anexos/{item['idAnexoFoto']}"
            img_dest  = os.path.join(self.output_dir, f"{uid}.jpg")
            try:
                import requests
                from requests.adapters import HTTPAdapter
                s = requests.Session()
                r = s.get(photo_url, timeout=15, stream=True)
                if r.status_code == 200 and not os.path.exists(img_dest):
                    import hashlib
                    hasher = hashlib.sha256()
                    with open(img_dest, "wb") as f:
                        for chunk in r.iter_content(16384):
                            hasher.update(chunk)
                            f.write(chunk)
                    
                    file_hash = hasher.hexdigest()
                    self._register_custody_sync(uid, file_hash, img_dest)

                    normalized["img_url"]  = photo_url
                    normalized["img_path"] = f"data/images/bnmp/{uid}.jpg"
            except Exception as e:
                self.logger.warning(f"[BNMP] Falha download {photo_url}: {e}")


        self.save(normalized)


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = BNMPIngestor(db=db)
        async with aiohttp.ClientSession() as session:
            await ingestor.run(session, limit=20)
        ingestor.close()
    asyncio.run(_main())
