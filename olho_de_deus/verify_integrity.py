#!/usr/bin/env python3
"""
verify_integrity.py — Olho de Deus  [Fase 16: Cadeia de Custódia]

Auditoria forense: verifica se os arquivos em disco coincidem com os
hashes SHA-256 registrados no banco de dados 'evidence'.

Se uma divergência for encontrada, dispara um alerta CRITICAL via Telegram.
"""
import hashlib
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

# Garante que o diretório olho_de_deus também esteja no path para o alert_dispatcher
sys.path.insert(0, str(ROOT / "olho_de_deus"))

from intelligence_db import DB, get_all_evidence_hashes
from alert_dispatcher import dispatch_sync

log = logging.getLogger("integrity_checker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [audit] %(message)s")

def calculate_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def run_audit():
    db = DB()
    try:
        records = get_all_evidence_hashes(db)
    except Exception as e:
        log.error(f"Erro ao ler hashes do banco: {e}")
        return

    print(f"\n[🔍] Iniciando Auditoria Forense em {len(records)} evidências...")

    passed = 0
    failed = 0
    missing = 0

    for rec in records:
        ev_id    = rec["id"]
        uid      = rec["individual_id"]
        expected = rec["file_hash"]
        path     = rec["file_path"]

        # Resolver caminho (pode ser relativo ou absoluto)
        full_path = Path(path)
        if not full_path.is_absolute():
            # Tentar relativo à raiz do projeto ou intelligence/data
            candidates = [
                ROOT / path,
                ROOT / "olho_de_deus" / path,
                ROOT / "intelligence" / "data" / path
            ]
            for c in candidates:
                if c.exists():
                    full_path = c
                    break

        if not full_path.exists():
             log.warning(f"[MISSING] Evidência {ev_id} não encontrada no disco: {path}")
             missing += 1
             continue

        try:
            actual = calculate_sha256(str(full_path))
            if actual == expected:
                passed += 1
            else:
                log.error(f"[VIOLATION] Hash divergente para {ev_id} (Alvo: {uid})")
                log.error(f"  Esperado: {expected}")
                log.error(f"  Encontrado: {actual}")
                failed += 1

                # Alerta Crítico via Telegram (Fase 21)
                dispatch_sync("INTEGRITY_VIOLATION",
                    evidence_id=ev_id,
                    expected_hash=expected,
                    actual_hash=actual,
                    detected_at=datetime.now().isoformat()
                )
        except Exception as e:
            log.error(f"[ERROR] Falha ao ler {full_path}: {e}")
            failed += 1

    print("\n" + "="*45)
    print(f" RESULTADO DA AUDITORIA — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f" - Integridade OK : {passed:>5}")
    print(f" - VIOLAÇÕES      : {failed:>5} 🚨")
    print(f" - Não encontrados: {missing:>5} ⚠️")
    print("="*45 + "\n")

    db.close()

if __name__ == "__main__":
    run_audit()
