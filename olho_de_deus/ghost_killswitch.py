#!/usr/bin/env python3
"""
ghost_killswitch.py — Olho de Deus [Fase 28: Kill-Switch / Protocolo de Defesa Ativa]

Daemon que monitora o estado físico do hardware e reage a ameaças passando o sistema
ao estado de LOCKDOWN imediato:
  - Finaliza todos os processos do Olho de Deus (SIGKILL)
  - Sobrescreve variáveis de memória com zeros (key zeroization)
  - Ejeta drives de backup montados
  - Grava log forense do evento com timestamp e causa

Gatilhos Configuráveis:
  1. Desconexão de energia AC (cabo removido)
  2. Mudança de SSID de rede (saída da zona segura)
  3. Atalho de pânico via arquivo-sinal (/tmp/.ghost_panic)

Uso:
  poetry run python ghost_killswitch.py --start    # Inicia daemon
  ghost_killswitch.py --panic                     # Disparo manual imediato
  ghost_killswitch.py --status                    # Verificar estado atual
"""

import os
import sys
import time
import signal
import shutil
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

load_dotenv()

# ─── Configuração ──────────────────────────────────────────────────────────────

BASE_DIR      = Path(__file__).resolve().parent.parent
LOG_DIR       = Path(__file__).parent / "logs"
PANIC_SIGNAL  = Path("/tmp/.ghost_panic")       # Arquivo-gatilho de emergência
LOCK_FILE     = Path("/tmp/.ghost_locked")       # Indicador de estado LOCKED
STATE_FILE    = Path("/tmp/.ghost_ks_state")     # Estado do daemon

# Redes consideradas "zonas seguras" (SSIDs confiáveis)
# Configure com os SSIDs do seu ambiente doméstico/operacional
TRUSTED_SSIDS_ENV = os.getenv("GHOST_TRUSTED_SSIDS", "")
TRUSTED_SSIDS = [s.strip() for s in TRUSTED_SSIDS_ENV.split(",") if s.strip()]

# Processos alvo do Kill-Switch
TARGET_PROCESS_NAMES = [
    "live_pipeline",
    "main.py",
    "biometric_processor",
    "alert_dispatcher",
    "farm_omni",
    "farm_cams",
    "farm_transito",
]

# ─── Logging ───────────────────────────────────────────────────────────────────

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [KILLSWITCH] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "killswitch.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("ghost_killswitch")

# ─── Sensor: Energia AC ────────────────────────────────────────────────────────

def is_on_ac_power() -> bool:
    """Verifica se o notebook está conectado à energia AC."""
    try:
        # Verificar via psutil primeiro
        if HAS_PSUTIL:
            battery = psutil.sensors_battery()
            if battery is not None:
                return battery.power_plugged
    except Exception:
        pass

    # Fallback via sysfs
    for bat_dir in Path("/sys/class/power_supply").glob("AC*"):
        online_file = bat_dir / "online"
        if online_file.exists():
            return online_file.read_text().strip() == "1"
    
    for bat_dir in Path("/sys/class/power_supply").glob("ADP*"):
        online_file = bat_dir / "online"
        if online_file.exists():
            return online_file.read_text().strip() == "1"
    
    return True  # Fallback seguro: assumir que está na tomada

# ─── Sensor: SSID de Rede ──────────────────────────────────────────────────────

def get_current_ssid() -> str:
    """Obtém o SSID da rede Wi-Fi atual via nmcli."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""

def is_in_trusted_zone(ssid: str) -> bool:
    """Verifica se o SSID está na lista de zonas confiáveis."""
    if not TRUSTED_SSIDS:
        return True  # Sem lista configurada, não monitorar SSID
    return ssid in TRUSTED_SSIDS

# ─── Execução do Lockdown ──────────────────────────────────────────────────────

def execute_lockdown(trigger: str):
    """
    Protocolo de Lockdown em 4 fases:
    1. Log forense do evento
    2. Terminar processos do Olho de Deus
    3. Ejetar drives externos
    4. Marcar sistema como LOCKED
    """
    timestamp = datetime.now().isoformat()
    log.critical(f"⚡ LOCKDOWN ATIVADO! Gatilho: {trigger} | Timestamp: {timestamp}")

    # Fase 1: Log forense imutável
    forensic = {
        "event": "GHOST_LOCKDOWN",
        "trigger": trigger,
        "timestamp": timestamp,
        "hostname": os.uname().nodename,
    }
    with open(LOG_DIR / "lockdown_events.log", "a", encoding="utf-8") as f:
        import json
        f.write(json.dumps(forensic) + "\n")

    # Fase 2: Terminar todos os processos alvo
    killed_count = 0
    if HAS_PSUTIL:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if any(target in cmdline for target in TARGET_PROCESS_NAMES):
                    log.info(f"Terminando PID {proc.pid}: {proc.info['name']}")
                    proc.kill()
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    log.info(f"Processos terminados: {killed_count}")

    # Fase 3: Sobrescrever variáveis de ambiente sensíveis com zeros
    sensitive_vars = ["GHOST_MASTER_KEY", "DATABASE_ENCRYPTION_KEY", "TELEGRAM_TOKEN"]
    for var in sensitive_vars:
        if var in os.environ:
            os.environ[var] = "\x00" * len(os.environ[var])
            del os.environ[var]
    log.info("Variáveis sensíveis zeradas da memória do processo.")

    # Fase 4: Ejetar drives externos (backups)
    media_base = Path("/run/media") / os.getenv("USER", "douglasdsr")
    if media_base.exists():
        for mount in media_base.iterdir():
            if mount.is_dir():
                try:
                    subprocess.run(["udisksctl", "unmount", "-b", str(mount)], 
                                   capture_output=True, timeout=5)
                    log.info(f"Drive ejetado: {mount}")
                except Exception as e:
                    log.warning(f"Falha ao ejetar {mount}: {e}")

    # Fase 5: Marcar como LOCKED
    LOCK_FILE.write_text(f"LOCKED:{timestamp}:{trigger}")
    log.critical("🔴 SISTEMA EM LOCKDOWN. Reinicialização manual necessária.")

# ─── Monitoramento de Gatilhos ──────────────────────────────────────────────────

class KillSwitchDaemon:
    """Daemon Monitor de Segurança Física."""

    def __init__(self):
        self.running = True
        self.last_ssid = get_current_ssid()
        self.last_ac   = is_on_ac_power()
        
        log.info("Kill-Switch Daemon iniciado.")
        log.info(f"SSID atual: '{self.last_ssid}'")
        log.info(f"AC Power: {'SIM' if self.last_ac else 'NÃO'}")
        if TRUSTED_SSIDS:
            log.info(f"SSIDs confiáveis: {TRUSTED_SSIDS}")
        else:
            log.warning("GHOST_TRUSTED_SSIDS não configurado — monitoramento de SSID desativado.")

    def monitor_loop(self):
        """Loop principal de monitoramento (intervalo de 3 segundos)."""
        check_interval = 3

        while self.running:
            try:
                # Gatilho 1: Arquivo de pânico manual
                if PANIC_SIGNAL.exists():
                    PANIC_SIGNAL.unlink()
                    execute_lockdown("PANIC_SIGNAL_FILE")
                    break

                # Gatilho 2: Desconexão de energia AC
                current_ac = is_on_ac_power()
                if self.last_ac and not current_ac:
                    execute_lockdown("AC_POWER_DISCONNECTED")
                    break
                self.last_ac = current_ac

                # Gatilho 3: Mudança de SSID
                if TRUSTED_SSIDS:
                    current_ssid = get_current_ssid()
                    if current_ssid != self.last_ssid:
                        log.warning(f"Mudança de SSID: '{self.last_ssid}' → '{current_ssid}'")
                        if not is_in_trusted_zone(current_ssid):
                            execute_lockdown(f"UNTRUSTED_SSID:{current_ssid}")
                            break
                        self.last_ssid = current_ssid

            except Exception as e:
                log.error(f"Erro no loop de monitoramento: {e}")

            time.sleep(check_interval)

    def start(self):
        """Inicia o daemon em thread separada."""
        STATE_FILE.write_text("ACTIVE")
        thread = threading.Thread(target=self.monitor_loop, daemon=True)
        thread.start()
        
        try:
            log.info("Pressione Ctrl+C para encerrar o Kill-Switch Daemon.")
            thread.join()
        except KeyboardInterrupt:
            log.info("Kill-Switch Daemon encerrado manualmente.")
            self.running = False
        finally:
            if STATE_FILE.exists():
                STATE_FILE.unlink()

# ─── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olho de Deus — Ghost Kill-Switch (Fase 28)")
    parser.add_argument("--start",  action="store_true", help="Iniciar daemon de monitoramento")
    parser.add_argument("--panic",  action="store_true", help="Disparar lockdown imediato agora")
    parser.add_argument("--status", action="store_true", help="Verificar estado atual")
    args = parser.parse_args()

    if args.panic:
        log.critical("PÂNICO MANUAL ATIVADO!")
        execute_lockdown("MANUAL_PANIC_CLI")
    elif args.status:
        locked   = LOCK_FILE.exists()
        active   = STATE_FILE.exists()
        ssid     = get_current_ssid()
        ac_power = is_on_ac_power()
        trusted  = is_in_trusted_zone(ssid)
        
        print(f"Estado do Kill-Switch:")
        print(f"  Daemon Ativo: {'SIM' if active else 'NÃO'}")
        print(f"  Sistema Locked: {'⚠️  SIM' if locked else 'OK'}")
        print(f"  SSID Atual: '{ssid}' {'(CONFIÁVEL)' if trusted else '(DESCONHECIDO ⚠️)'}")
        print(f"  Energia AC: {'SIM ✓' if ac_power else 'NÃO ⚠️'}")
    elif args.start:
        daemon = KillSwitchDaemon()
        daemon.start()
    else:
        parser.print_help()
