#!/usr/bin/env python3
"""
backup_manager.py — Olho de Deus [Fase 26: Redundância e Backup]

Cria snapshots cifrados (AES-256-EAX) dos dados de inteligência.
- Auto-detecta destinos externos (USB/NAS) no Manjaro Linux.
- Verifica integridade via SHA-256 em cada operação.
- Opera com prioridade mínima de I/O (ionice) para não afetar o WebRTC.
- Registra auditoria completa em logs/backup_audit.log.
"""

import os
import sys
import time
import gzip
import json
import shutil
import hashlib
import tarfile
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

load_dotenv()

# ─── Configuração ──────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "intelligence" / "data"
LOG_DIR    = Path(__file__).parent / "logs"
BACKUP_VERSION = "v1"

# Destino local fallback (caso nenhum externo seja detectado)
BACKUP_LOCAL_PATH = Path(os.getenv("BACKUP_LOCAL_PATH", str(Path.home() / "ghost_backups")))

# ─── Logging ───────────────────────────────────────────────────────────────────

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKUP] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "backup_audit.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("backup_manager")

# ─── Criptografia (Ghost Protocol) ─────────────────────────────────────────────

def _get_key() -> bytes:
    key_str = os.getenv("GHOST_MASTER_KEY", "")
    if not key_str:
        raise ValueError("[BACKUP] GHOST_MASTER_KEY não configurada. Abortando.")
    return key_str.encode()[:32].ljust(32, b"\0")

def encrypt_file(src_path: Path, dest_path: Path) -> str:
    """Cifra um arquivo e retorna o SHA-256 do arquivo cifrado."""
    if not HAS_CRYPTO:
        raise ImportError("pycryptodome não instalado. Execute: poetry add pycryptodome")
    
    key = _get_key()
    cipher = AES.new(key, AES.MODE_EAX)
    
    with open(src_path, "rb") as f:
        data = f.read()
    
    ciphertext, tag = cipher.encrypt_and_digest(data)
    
    # Formato: [16B nonce] + [16B tag] + [ciphertext]
    blob = cipher.nonce + tag + ciphertext
    
    # Cabeçalho de metadados
    header = json.dumps({
        "version": BACKUP_VERSION,
        "source": str(src_path),
        "created_at": datetime.utcnow().isoformat(),
    }).encode() + b"\n---GHOST_PAYLOAD---\n"
    
    with open(dest_path, "wb") as f:
        f.write(header)
        f.write(blob)
    
    # SHA-256 do arquivo cifrado
    digest = hashlib.sha256(blob).hexdigest()
    return digest

def decrypt_file(src_path: Path, dest_path: Path, key_str: str = None) -> bool:
    """Decifra um arquivo .ghost. Retorna True se bem-sucedido."""
    if not HAS_CRYPTO:
        return False
    
    key_raw = key_str.encode()[:32].ljust(32, b"\0") if key_str else _get_key()
    
    with open(src_path, "rb") as f:
        content = f.read()
    
    # Separar cabeçalho do payload
    separator = b"\n---GHOST_PAYLOAD---\n"
    idx = content.find(separator)
    if idx == -1:
        log.error("Formato de arquivo inválido: sem separador Ghost.")
        return False
    
    blob = content[idx + len(separator):]
    nonce, tag, ciphertext = blob[:16], blob[16:32], blob[32:]
    
    try:
        cipher = AES.new(key_raw, AES.MODE_EAX, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        with open(dest_path, "wb") as f:
            f.write(plaintext)
        return True
    except Exception as e:
        log.error(f"Falha na decifragem: {e}")
        return False

# ─── Detecção de Destino ────────────────────────────────────────────────────────

def find_backup_destination() -> Path:
    """Detecta automaticamente HDs externos ou USB montados no Manjaro."""
    media_base = Path("/run/media") / os.getenv("USER", "douglasdsr")
    
    if media_base.exists():
        for mount in sorted(media_base.iterdir()):
            if mount.is_dir():
                free = shutil.disk_usage(mount).free
                free_gb = free / (1024 ** 3)
                if free_gb > 1.0:  # Exige pelo menos 1GB livre
                    log.info(f"📀 Destino externo detectado: {mount} ({free_gb:.1f}GB livre)")
                    backup_dir = mount / "ghost_backups"
                    os.makedirs(backup_dir, exist_ok=True)
                    return backup_dir
    
    # Fallback local
    log.warning("Nenhum dispositivo externo detectado. Usando destino local.")
    os.makedirs(BACKUP_LOCAL_PATH, exist_ok=True)
    return BACKUP_LOCAL_PATH

# ─── Criação do Snapshot ────────────────────────────────────────────────────────

def create_snapshot(dry_run: bool = False) -> dict:
    """
    Cria um snapshot tar.gz cifrado da pasta de inteligência.
    Retorna um dict com metadados do resultado.
    """
    # Ajustar prioridade de I/O para mínima (Idle = classe 3)
    try:
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True, capture_output=True)
        log.info("Prioridade de I/O ajustada para Idle (ionice -c 3)")
    except Exception:
        log.warning("ionice não disponível, prosseguindo sem ajuste de prioridade.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"snapshot_{timestamp}.ghost"
    dest_dir = find_backup_destination()
    dest_path = dest_dir / snapshot_name

    # Arquivo tar temporário (em memória via /tmp)
    tmp_tar = Path(f"/tmp/ghost_snapshot_{timestamp}.tar.gz")
    
    log.info(f"=== INICIANDO SNAPSHOT [{timestamp}] ===")
    log.info(f"Fonte: {DATA_DIR} ({_human_size(DATA_DIR)})")
    log.info(f"Destino: {dest_path}")
    
    if dry_run:
        log.info("[DRY-RUN] Simulando backup sem mover dados.")
        return {"status": "dry_run", "source": str(DATA_DIR), "dest": str(dest_path)}

    # 1. Compactar
    log.info("Compactando dados...")
    with tarfile.open(tmp_tar, "w:gz") as tar:
        tar.add(DATA_DIR, arcname="intelligence_data")
    
    tar_size = tmp_tar.stat().st_size
    log.info(f"Compactado: {_human_size_raw(tar_size)}")
    
    # 2. Cifrar
    log.info("Cifrando snapshot com AES-256-EAX...")
    sha256_digest = encrypt_file(tmp_tar, dest_path)
    
    # 3. Limpar temporário
    tmp_tar.unlink()
    
    final_size = dest_path.stat().st_size
    
    # 4. Registrar auditoria
    audit_entry = {
        "timestamp": timestamp,
        "snapshot": str(dest_path),
        "sha256": sha256_digest,
        "source_dir": str(DATA_DIR),
        "size_bytes": final_size,
    }
    _write_audit_log(audit_entry)
    
    log.info(f"✓ Snapshot concluído: {snapshot_name}")
    log.info(f"  SHA-256: {sha256_digest[:16]}...{sha256_digest[-8:]}")
    log.info(f"  Tamanho final: {_human_size_raw(final_size)}")
    log.info("=================================================")
    
    return audit_entry

# ─── Verificação de Integridade ─────────────────────────────────────────────────

def verify_latest() -> bool:
    """Verifica o SHA-256 do snapshot mais recente contra o log de auditoria."""
    audit_file = LOG_DIR / "backup_audit.log"
    index_file = LOG_DIR / "backup_index.json"
    
    if not index_file.exists():
        log.error("Nenhum índice de backup encontrado.")
        return False
    
    with open(index_file) as f:
        entries = json.load(f)
    
    if not entries:
        log.error("Índice de backup vazio.")
        return False
    
    latest = entries[-1]
    snapshot_path = Path(latest["snapshot"])
    
    if not snapshot_path.exists():
        log.error(f"Snapshot não encontrado: {snapshot_path}")
        return False
    
    log.info(f"Verificando: {snapshot_path.name}")
    
    with open(snapshot_path, "rb") as f:
        content = f.read()
    
    separator = b"\n---GHOST_PAYLOAD---\n"
    idx = content.find(separator)
    blob = content[idx + len(separator):]
    
    actual_sha = hashlib.sha256(blob).hexdigest()
    expected_sha = latest["sha256"]
    
    if actual_sha == expected_sha:
        log.info(f"✓ INTEGRIDADE CONFIRMADA: SHA-256 corresponde.")
        return True
    else:
        log.error(f"❌ VIOLAÇÃO DE INTEGRIDADE: SHA-256 não corresponde!")
        log.error(f"   Esperado: {expected_sha}")
        log.error(f"   Atual:    {actual_sha}")
        return False

# ─── Helpers ────────────────────────────────────────────────────────────────────

def _human_size(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return _human_size_raw(total)

def _human_size_raw(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def _write_audit_log(entry: dict):
    index_file = LOG_DIR / "backup_index.json"
    entries = []
    if index_file.exists():
        try:
            with open(index_file) as f:
                entries = json.load(f)
        except Exception:
            entries = []
    
    entries.append(entry)
    
    # Manter apenas os últimos 100 registros no índice
    if len(entries) > 100:
        entries = entries[-100:]
    
    with open(index_file, "w") as f:
        json.dump(entries, f, indent=2)

# ─── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olho de Deus — Backup Manager (Fase 26)")
    parser.add_argument("--now",      action="store_true", help="Executar backup agora")
    parser.add_argument("--dry-run",  action="store_true", help="Simular sem mover dados")
    parser.add_argument("--verify",   action="store_true", help="Verificar integridade do último snapshot")
    args = parser.parse_args()
    
    if args.verify:
        ok = verify_latest()
        sys.exit(0 if ok else 1)
    elif args.now or args.dry_run:
        result = create_snapshot(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
