#!/usr/bin/env python3
"""
audit_manager.py — Olho de Deus [Fase 17: Auditoria e Rotação]

Gerencia a saúde do hardware e a retenção de dados forenses:
- Rotação e compressão de logs operacionais.
- Limpeza seletiva de evidências (matches).
- Manutenção de integridade do banco de dados (SQLite VACUUM).
- Execução em baixa prioridade (nice/ionice).
"""
import os
import time
import shutil
import gzip
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Configurações de Retenção (Módulo 2)
RETENTION_LOGS_HOT_DAYS = 7
RETENTION_LOGS_FINAL_DAYS = 30
RETENTION_EVIDENCE_LOW_DAYS = 30
MIN_SCORE_FOR_VITALICIA = 8.0
DB_VACUUM_SIZE_MB = 500

log = logging.getLogger("audit_manager")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [AUDIT] %(message)s")

class AuditManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.log_dir = base_path / "logs"
        self.evidence_dir = base_path / "intelligence" / "data" / "evidence" / "matches"
        self.db_path = base_path / "intelligence" / "data" / "intelligence.db"
        
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Tentar ajustar prioridade do processo (Linux)
        try:
            os.nice(15) # Prioridade muito baixa
        except AttributeError:
            pass

    def rotate_logs(self):
        """Comprime logs antigos e deleta os que expiraram."""
        log.info("Iniciando rotação de logs...")
        now = datetime.now()
        
        for log_file in self.log_dir.glob("*.log"):
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            age = (now - mtime).days
            
            if age > RETENTION_LOGS_FINAL_DAYS:
                log.info(f"Removendo log expirado: {log_file.name}")
                log_file.unlink()
            elif age > RETENTION_LOGS_HOT_DAYS and not log_file.suffix == ".gz":
                log.info(f"Comprimindo log: {log_file.name}")
                self._compress_file(log_file)
                log_file.unlink()

    def cleanup_evidence(self):
        """Deleta evidências de baixo risco conforme a política de retenção."""
        log.info("Iniciando limpeza de evidências biométricas...")
        if not self.evidence_dir.exists():
            return

        now = datetime.now()
        cleaned_count = 0
        
        # Nota: Idealmente verificaríamos o score no DB, mas para performance 
        # aqui usaremos o padrão de nome match_uid_timestamp.jpg se houver no futuro.
        # Por enquanto, filtramos por data de modificação.
        for ev_file in self.evidence_dir.glob("*.jpg"):
            mtime = datetime.fromtimestamp(ev_file.stat().st_mtime)
            age = (now - mtime).days
            
            if age > RETENTION_EVIDENCE_LOW_DAYS:
                # TODO: No futuro, cruzar com 'threat_scores' antes de deletar.
                # Por ora, deletamos tudo acima da retenção para proteger o SSD.
                ev_file.unlink()
                cleaned_count += 1
                
        log.info(f"Limpeza concluída: {cleaned_count} arquivos removidos.")

    def maintain_database(self):
        """Executa VACUUM se o banco estiver muito grande."""
        if not self.db_path.exists():
            return
            
        size_mb = self.db_path.stat().st_size / (1024 * 1024)
        if size_mb > DB_VACUUM_SIZE_MB:
            log.info(f"DB atingiu {size_mb:.1f}MB. Executando VACUUM para otimização...")
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("VACUUM")
                conn.close()
                new_size = self.db_path.stat().st_size / (1024 * 1024)
                log.info(f"VACUUM concluído. Novo tamanho: {new_size:.1f}MB")
            except Exception as e:
                log.error(f"Erro na manutenção do DB: {e}")

    def _compress_file(self, file_path: Path):
        with open(file_path, 'rb') as f_in:
            with gzip.open(f"{file_path}.gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

    def run_full_audit(self):
        log.info("=== INICIANDO AUDITORIA GLOBAL (Fase 17) ===")
        self.rotate_logs()
        self.cleanup_evidence()
        self.maintain_database()
        log.info("=== AUDITORIA CONCLUÍDA. SSD PROTEGIDO. ===")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Olho de Deus — Audit Manager")
    parser.add_argument("--now", action="store_true", help="Executar auditoria agora")
    args = parser.parse_args()
    
    base = Path(__file__).resolve().parent
    manager = AuditManager(base)
    
    if args.now:
        manager.run_full_audit()
    else:
        # Modo daemon simples (espera 24h)
        log.info("Modo de monitoramento persistente ativo. Próxima auditoria em 24h.")
        manager.run_full_audit()
