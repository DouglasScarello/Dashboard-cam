#!/usr/bin/env python3
"""
pipeline_control.py — Controle manual (ligar/desligar) dos pipelines de IA
pesados que antes rodavam 24/7 sozinhos via systemd.

2026-09-12: decisão explícita do usuário. Dois motivos:
1. Calibração ainda não está pronta — o diagnóstico ao vivo do gate de
   qualidade facial (ver biometric_processor.py `_report_gate_result`)
   mostrou que a câmera de Bangkok rejeita quase todo mundo (longe demais
   da lente pro ArcFace confiar), então rodar 24/7 sem supervisão hoje só
   queima CPU/RAM sem gerar dado útil.
2. Concorrência de recursos — os dois pipelines rodando ao mesmo tempo já
   causaram lag real num jogo local (RAM baixando a ~500MB livre + swap
   thrashing pesado).

Os serviços systemd continuam existindo e funcionando exatamente como
antes (mesmos arquivos .service) — só o auto-start no boot/login foi
desabilitado (`systemctl --user disable`). Esse módulo só chama
`systemctl --user start/stop/show`, sempre contra um allowlist FIXO de
nomes de serviço: nunca aceita nome vindo de fora, porque isso vira
argumento de linha de comando — aceitar um nome arbitrário seria execução
de comando arbitrário disfarçada de "start pipeline".
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

ROOT = Path(__file__).resolve().parent

CONTROLLABLE_PIPELINES: Dict[str, Dict[str, str]] = {
    "rosto": {
        "service": "olho-de-deus-rosto.service",
        "label": "Reconhecimento Facial",
        "location": "Bangkok, Tailândia",
        "log_file": "logs/monitor_camera.log",
    },
    "placas": {
        "service": "olho-de-deus-placas.service",
        "label": "Leitura de Placa",
        "location": "Davao, Filipinas",
        "log_file": "logs/monitor_plates.log",
    },
}


def _systemctl(*args: str, timeout: float = 10.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _tail_log(log_file: str, n: int = 1) -> List[str]:
    """Últimas `n` linhas não vazias — lê só os últimos 8KB do arquivo
    (pode ter dezenas de milhares de linhas, ver monitor_plates.log) em
    vez de carregar o arquivo inteiro só pra pegar a última linha."""
    path = ROOT / log_file
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            block = min(size, 8192)
            f.seek(size - block)
            data = f.read().decode("utf-8", errors="replace")
        lines = [l for l in data.splitlines() if l.strip()]
        return lines[-n:]
    except Exception:
        return []


def get_pipeline_status(pipeline_id: str) -> Optional[Dict[str, Any]]:
    cfg = CONTROLLABLE_PIPELINES.get(pipeline_id)
    if not cfg:
        return None

    # Sem --value de propósito: `systemctl show --value` com múltiplas
    # --property NÃO garante a ordem pedida (achado real testando isto —
    # saía ActiveState/SubState/Timestamp/PID mesmo pedindo
    # MainPID,ActiveState,SubState,ActiveEnterTimestamp nessa ordem).
    # A forma "Key=Value" é a única que dá pra parsear sem depender de
    # ordem nenhuma.
    res = _systemctl(
        "show", cfg["service"],
        "--property=MainPID,ActiveState,SubState,ActiveEnterTimestamp",
    )
    props: Dict[str, str] = {}
    for line in (res.stdout or "").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            props[key] = value

    active_state = props.get("ActiveState", "unknown")
    sub_state = props.get("SubState", "unknown")
    since = props.get("ActiveEnterTimestamp") or None
    main_pid_raw = props.get("MainPID", "")

    main_pid = int(main_pid_raw) if main_pid_raw.isdigit() and main_pid_raw != "0" else None

    cpu_percent = None
    memory_mb = None
    since_epoch = None
    if main_pid:
        try:
            proc = psutil.Process(main_pid)
            cpu_percent = proc.cpu_percent(interval=0.1)
            memory_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
            # Epoch de verdade do processo (psutil), em vez de tentar parsear
            # a string localizada do systemd ("Sat 2026-09-12 23:55:52 -03")
            # no frontend — evita depender do parser de Date do navegador
            # pra um formato que não é ISO 8601.
            since_epoch = proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return {
        "id": pipeline_id,
        "label": cfg["label"],
        "location": cfg["location"],
        "service": cfg["service"],
        # active | inactive | activating | deactivating | failed
        "active_state": active_state,
        "sub_state": sub_state,
        "since": since,
        "since_epoch": since_epoch,
        "cpu_percent": cpu_percent,
        "memory_mb": memory_mb,
        "last_log_line": (_tail_log(cfg["log_file"], 1) or [None])[0],
    }


def list_pipelines() -> List[Dict[str, Any]]:
    return [s for s in (get_pipeline_status(pid) for pid in CONTROLLABLE_PIPELINES) if s]


def start_pipeline(pipeline_id: str) -> Dict[str, Any]:
    if pipeline_id not in CONTROLLABLE_PIPELINES:
        return {"status": "ERROR", "message": "Pipeline desconhecido"}
    res = _systemctl("start", CONTROLLABLE_PIPELINES[pipeline_id]["service"])
    if res.returncode != 0:
        return {"status": "ERROR", "message": res.stderr.strip() or "Falha ao iniciar"}
    return {"status": "OK", "pipeline": get_pipeline_status(pipeline_id)}


def stop_pipeline(pipeline_id: str) -> Dict[str, Any]:
    if pipeline_id not in CONTROLLABLE_PIPELINES:
        return {"status": "ERROR", "message": "Pipeline desconhecido"}
    res = _systemctl("stop", CONTROLLABLE_PIPELINES[pipeline_id]["service"])
    if res.returncode != 0:
        return {"status": "ERROR", "message": res.stderr.strip() or "Falha ao parar"}
    return {"status": "OK", "pipeline": get_pipeline_status(pipeline_id)}
