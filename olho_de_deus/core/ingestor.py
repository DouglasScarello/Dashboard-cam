#!/usr/bin/env python3
"""
core/ingestor.py — Olho de Deus
BaseIngestor ASYNC: Contrato base para ingestão paralela de inteligência.

Fase 10: Migração de sync → async com aiohttp + tenacity.
Ingestores que dependem de Playwright mantêm o padrão sync
via executor para não bloquear o event loop.
"""
import os
import sys
import asyncio
import logging
import aiohttp
import aiofiles
import hashlib
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log
)

# Path resolução para intelligence_db
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from intelligence_db import DB, upsert_individual, insert_crimes, insert_image

logger_root = logging.getLogger("ingestor")


class BaseIngestor(ABC):
    """
    Classe base assíncrona para todos os ingestores do Olho de Deus.

    Contrato:
        - Implementar `run(session, **kwargs)` como coroutine principal.
        - Chamar `self.save(data)` para persistir cada indivíduo.
        - Resultados acumulados em `self.stats` para relatório final.
    """

    def __init__(self, source_name: str, db: Optional[DB] = None):
        self.source_name = source_name
        self.db = db or DB()
        self.logger = logging.getLogger(f"ingestor.{source_name}")
        self.stats = {"loaded": 0, "skipped": 0, "errors": 0}

    @abstractmethod
    async def run(self, session: aiohttp.ClientSession, **kwargs) -> Dict[str, int]:
        """
        Coroutine principal de ingestão.
        Deve retornar self.stats ao final.
        """

    # ─── Persistência ────────────────────────────────────────────────────────

    def save(self, data: Dict) -> bool:
        """Normaliza e persiste um indivíduo no banco de forma síncrona."""
        try:
            upsert_individual(self.db, data)

            if data.get("crimes"):
                insert_crimes(self.db, data["id"], data["crimes"])

            if data.get("img_url"):
                insert_image(self.db, data["id"], img_url=data["img_url"], is_primary=True)

            for extra_url in (data.get("gallery") or []):
                insert_image(self.db, data["id"], img_url=extra_url, is_primary=False)

            self.db.commit()
            self.stats["loaded"] += 1
            return True
        except Exception as e:
            self.logger.error(f"[{self.source_name}] Erro ao salvar {data.get('id')}: {e}")
            self.stats["errors"] += 1
            return False

    # ─── HTTP helpers (com retry automático) ─────────────────────────────────

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(logger_root, logging.WARNING),
        reraise=True,
    )
    async def get_json(self, session: aiohttp.ClientSession, url: str, **kwargs) -> Any:
        """GET com retry exponencial. Retorna JSON parseado."""
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), **kwargs) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        before_sleep=before_sleep_log(logger_root, logging.WARNING),
        reraise=True,
    )
    async def get_text(self, session: aiohttp.ClientSession, url: str, **kwargs) -> str:
        """GET com retry exponencial. Retorna texto."""
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), **kwargs) as resp:
            resp.raise_for_status()
            return await resp.text(encoding="utf-8")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=3, max=20),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=False,
    )
    async def download_image(
        self, session: aiohttp.ClientSession, url: str, dest: str,
        individual_id: Optional[str] = None
    ) -> bool:
        """
        Download assíncrono de imagem com cálculo de SHA-256 'no voo'.
        Se 'individual_id' for fornecido, registra automaticamente na Cadeia de Custódia.
        """
        hasher = hashlib.sha256()
        
        # Se já existe, apenas calculamos o hash para registro/verificação
        if os.path.exists(dest):
            try:
                async with aiofiles.open(dest, "rb") as f:
                    while chunk := await f.read(65536):
                        hasher.update(chunk)
                file_hash = hasher.hexdigest()
                if individual_id:
                    self._register_custody(individual_id, file_hash, dest)
                return True
            except Exception:
                return False

        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(16384):
                            hasher.update(chunk)
                            await f.write(chunk)
                    
                    file_hash = hasher.hexdigest()
                    if individual_id:
                        self._register_custody(individual_id, file_hash, dest)
                    return True
        except Exception as e:
            self.logger.warning(f"[{self.source_name}] Falha download {url}: {e}")
        return False

    def _register_custody(self, individual_id: str, file_hash: str, file_path: str):
        """Helper interno para registro na Cadeia de Custódia."""
        from intelligence_db import register_evidence
        try:
            # Usar um ID de evidência derivado ou aleatório
            # Para rastreabilidade, podemos usar UUID v4
            ev_id = str(uuid.uuid4())
            register_evidence(self.db, ev_id, individual_id, file_hash, file_path)
            self.logger.debug(f"[custódia] Evidência registrada: {ev_id[:8]}")
        except Exception as e:
            # Se for violação de imutabilidade (ID repetido), o dispatch cuidará de gritar
            if "Violação de Imutabilidade" in str(e):
                from alert_dispatcher import dispatch_sync
                dispatch_sync("INTEGRITY_VIOLATION", 
                    evidence_id="DuplicateID", 
                    expected_hash="N/A", 
                    actual_hash=file_hash,
                    detected_at=datetime.now().isoformat()
                )
            self.logger.error(f"[custódia] Falha ao registrar evidência: {e}")

    def _register_custody_sync(self, individual_id: str, file_hash: str, file_path: str):
        """Versão síncrona do registro de custódia (para uso em executores)."""
        from intelligence_db import register_evidence
        try:
            ev_id = str(uuid.uuid4())
            register_evidence(self.db, ev_id, individual_id, file_hash, file_path)
            self.logger.debug(f"[custódia-sync] Evidência registrada: {ev_id[:8]}")
        except Exception as e:
            self.logger.error(f"[custódia-sync] Falha ao registrar evidência: {e}")

    # ─── Playwright helper (bloqueia em executor para não travar o loop) ─────


    async def run_playwright_sync(self, func, *args):
        """
        Executa uma função Playwright síncrona em thread pool,
        sem bloquear o event loop principal do asyncio.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    # ─── Relatório ────────────────────────────────────────────────────────────

    def report(self) -> str:
        s = self.stats
        return (
            f"[{self.source_name}] "
            f"✓ {s['loaded']} carregados | "
            f"⚠ {s['skipped']} ignorados | "
            f"✗ {s['errors']} erros"
        )

    def close(self):
        self.db.close()
