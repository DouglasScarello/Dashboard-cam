#!/usr/bin/env python3
"""
interpol_ingestion.py — Olho de Deus  [Fase 10: Async Migration]
Fonte: Interpol Red & Yellow Notices (galeria pública)
Usa Playwright async via run_in_executor para não bloquear o event loop.
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


NOTICE_TYPES = {
    "red":    ("wanted",  "https://www.interpol.int/How-we-work/Notices/Red-Notices/View-Red-Notices"),
    "yellow": ("missing", "https://www.interpol.int/How-we-work/Notices/Yellow-Notices/View-Yellow-Notices"),
}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


class InterpolIngestor(BaseIngestor):
    def __init__(self, db=None):
        super().__init__(source_name="Interpol", db=db)
        self.output_dir = str(ROOT / "intelligence" / "data" / "images" / "interpol")
        os.makedirs(self.output_dir, exist_ok=True)

    async def run(self, session: aiohttp.ClientSession, max_pages: int = 5, **kwargs) -> Dict:
        self.logger.info(f"[Interpol] Iniciando scraping — {max_pages} páginas por tipo")

        # Playwright é síncrono — executamos em thread pool para não bloquear
        await self.run_playwright_sync(self._scrape_all, max_pages)

        self.logger.info(self.report())
        return self.stats

    def _scrape_all(self, max_pages: int):
        """Scraping síncrono executado em executor thread."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA)
            page = ctx.new_page()
            page.route("**/*.{css,woff2,woff}", lambda r: r.abort())

            for n_type, (category, base_url) in NOTICE_TYPES.items():
                for pg_num in range(1, max_pages + 1):
                    url = f"{base_url}?page={pg_num}"
                    try:
                        page.goto(url, timeout=30_000, wait_until="domcontentloaded")
                        page.wait_for_selector(".redNoticeItem", timeout=12_000)
                        page.evaluate("window.scrollBy(0, 600)")
                        page.wait_for_timeout(800)

                        cards = page.query_selector_all(".redNoticeItem")
                        if not cards:
                            break

                        for card in cards:
                            self._process_card(card, n_type, category)

                    except Exception as e:
                        self.logger.warning(f"[Interpol] {n_type} pg {pg_num}: {e}")
                        break

            browser.close()

    def _process_card(self, card, n_type: str, category: str):
        try:
            name_el = card.query_selector(".redNoticeItem__labelLink")
            img_el  = card.query_selector(".redNoticeItem__img")

            name = name_el.inner_text().strip().replace("\n", " ") if name_el else None
            if not name:
                self.stats["skipped"] += 1
                return

            img_url = img_el.get_attribute("src") if img_el else None
            if img_url and img_url.startswith("/"):
                img_url = "https://www.interpol.int" + img_url

            uid = f"INTERPOL_{n_type.upper()}_{abs(hash(name))}"

            normalized = {
                "id":          uid,
                "name":        name.upper(),
                "category":    category,
                "source":      f"Interpol/{n_type.capitalize()}",
                "description": f"Interpol {n_type.capitalize()} Notice — galeria pública.",
            }

            if img_url:
                img_dest = os.path.join(self.output_dir, f"{uid}.jpg")
                # Download síncrono (estamos no executor)
                import requests
                try:
                    r = requests.get(img_url, timeout=15, stream=True)
                    if r.status_code == 200 and not os.path.exists(img_dest):
                        import hashlib
                        hasher = hashlib.sha256()
                        with open(img_dest, "wb") as f:
                            for chunk in r.iter_content(16384):
                                hasher.update(chunk)
                                f.write(chunk)
                        
                        file_hash = hasher.hexdigest()
                        self._register_custody_sync(uid, file_hash, img_dest)

                        normalized["img_url"]  = img_url
                        normalized["img_path"] = f"data/images/interpol/{uid}.jpg"
                except Exception as e:
                    self.logger.warning(f"[Interpol] Falha download {img_url}: {e}")


            self.save(normalized)
        except Exception as e:
            self.logger.error(f"[Interpol] Erro card: {e}")
            self.stats["errors"] += 1


if __name__ == "__main__":
    from intelligence_db import DB
    async def _main():
        db = DB()
        ingestor = InterpolIngestor(db=db)
        async with aiohttp.ClientSession() as session:
            await ingestor.run(session, max_pages=3)
        ingestor.close()
    asyncio.run(_main())
