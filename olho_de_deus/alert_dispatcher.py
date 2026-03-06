#!/usr/bin/env python3
"""
alert_dispatcher.py — Olho de Deus  [Fase 21: Alert Multichannel System]

Sistema de alertas pub/sub leve e assíncrono.
Publica eventos para múltiplos canais (Telegram, Webhook, Email, Pushover)
com roteamento declarativo via alert_config.yaml.

Design:
  - Fire-and-forget: chamada assíncrona não bloqueia o chamador
  - Rate limiting: sliding window por tipo de evento + canal
  - Isolamento: falha em um canal não afeta os outros
  - Ghost Protocol: sem brokers externos — chamadas HTTP diretas às APIs

Uso:
    from alert_dispatcher import dispatch

    await dispatch("INGESTION_SUCCESS", source="FBI", loaded=120, errors=2, elapsed=8.3)
    await dispatch("MATCH_DETECTED", name="OMAR KHAN", uid="fbi_abc123",
                   camera_id="CAM_001", confidence=0.97, threat_score=9)
"""
import asyncio
import logging
import smtplib
import time
import yaml
import aiohttp
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import os
import base64
from dotenv import load_dotenv

# ─── Ghost Proxy / Network Stealth (Fase 24) ─────────────────────────────────
try:
    from aiohttp_socks import ProxyConnector
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False
    ProxyConnector = None  # type: ignore

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

load_dotenv()

log = logging.getLogger("alert_dispatcher")
# Auditoria de Alertas (Fase 17)
audit_log = logging.getLogger("alert_audit")
_audit_path = Path(__file__).parent / "logs" / "audit.log"
os.makedirs(_audit_path.parent, exist_ok=True)
if not audit_log.handlers:
    ah = logging.FileHandler(_audit_path, encoding="utf-8")
    ah.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    audit_log.addHandler(ah)
    audit_log.setLevel(logging.INFO)

# ─── Config ──────────────────────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).parent / "alert_config.yaml"
_config: Optional[Dict] = None
_rate_tracker: Dict[str, List[float]] = defaultdict(list)  # key → timestamps
_dedup_tracker: Dict[str, Dict] = {} # uid → {"last_seen": t, "cameras": set()} (Fase 31)


def _load_config() -> Dict:
    global _config
    if _config is None:
        if not _CONFIG_PATH.exists():
            log.warning(f"alert_config.yaml não encontrado em {_CONFIG_PATH}")
            return {}
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
    return _config


# ─── Ghost Connector (Fase 24) ────────────────────────────────────────────────

def _build_connector() -> aiohttp.BaseConnector:
    """
    Retorna um ProxyConnector SOCKS5 se GHOST_PROXY_URL estiver definida,
    ou um TCPConnector padrão caso contrário.

    Configurar no .env:
        GHOST_PROXY_URL=socks5://127.0.0.1:9050   # Tor local
        GHOST_PROXY_URL=socks5://user:pass@proxy:1080
    """
    proxy_url = os.getenv("GHOST_PROXY_URL", "").strip()
    if proxy_url and HAS_SOCKS:
        try:
            connector = ProxyConnector.from_url(proxy_url, ssl=True)
            log.info(f"[NetStealth] Tráfego roteado via proxy: {proxy_url.split('@')[-1]}")
            return connector
        except Exception as e:
            log.error(f"[NetStealth] Falha ao criar ProxyConnector: {e} — usando conexão direta.")
    elif proxy_url and not HAS_SOCKS:
        log.warning("[NetStealth] GHOST_PROXY_URL definida mas aiohttp-socks não instalado. "
                    "Execute: poetry add aiohttp-socks")
    return aiohttp.TCPConnector(ssl=True)


# ─── Rate limiting ────────────────────────────────────────────────────────────

def _is_rate_limited(event_type: str, channel: str, max_per_min: int, cooldown: float) -> bool:
    key = f"{event_type}:{channel}"
    now = time.monotonic()
    window = 60.0

    # Limpar timestamps fora da janela
    _rate_tracker[key] = [t for t in _rate_tracker[key] if now - t < window]

    if len(_rate_tracker[key]) >= max_per_min:
        return True

    # Cooldown entre mensagens do mesmo tipo
    if _rate_tracker[key] and (now - _rate_tracker[key][-1]) < cooldown:
        return True

    _rate_tracker[key].append(now)
    return False


# ─── Template rendering ───────────────────────────────────────────────────────

def _render(template: str, **kwargs) -> str:
    kwargs.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Lógica de Destaque para High-Score (Fase 12)
    score = kwargs.get("threat_score")
    prefix = ""
    if score is not None:
        try:
            s_val = float(score)
            if s_val >= 9.0:
                prefix = "🚨🚨🚨 [CRITICAL TARGET] 🚨🚨🚨\n"
            elif s_val >= 8.0:
                prefix = "⚠️ [HIGH THREAT] ⚠️\n"
        except (ValueError, TypeError):
            pass

    try:
        rendered = template.format(**kwargs)
        return prefix + rendered
    except KeyError as e:
        return prefix + template + f"\n[template key missing: {e}]"


# ─── Criptografia E2E (Fase 25) ───────────────────────────────────────────────

def _maybe_encrypt(message: str) -> str:
    """Cifra a mensagem se GHOST_MASTER_KEY estiver definida e HAS_CRYPTO for True."""
    key_str = os.getenv("GHOST_MASTER_KEY")
    enabled = os.getenv("GHOST_ENCRYPTION_ENABLED", "false").lower() == "true"
    
    if not key_str or not enabled or not HAS_CRYPTO:
        return message

    try:
        # Garantir 32 bytes para AES-256
        key = key_str.encode("utf-8")[:32].ljust(32, b"\0")
        cipher = AES.new(key, AES.MODE_EAX)
        ciphertext, tag = cipher.encrypt_and_digest(message.encode("utf-8"))
        
        # Payload comprimido: nonce (16) + tag (16) + ciphertext
        blob = cipher.nonce + tag + ciphertext
        encoded = base64.b64encode(blob).decode("utf-8")
        return f"[GHOST_V1]{encoded}"
    except Exception as e:
        log.error(f"[Crypto] Erro na cifragem: {e}")
        return f"[CRYPTO_ERROR] {message}"


# ─── Canais ───────────────────────────────────────────────────────────────────

async def _send_telegram(cfg: Dict, message: str, session: aiohttp.ClientSession) -> bool:
    token   = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or not chat_id:
        log.debug("[Telegram] bot_token ou chat_id não configurados — pulando")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": cfg.get("parse_mode", "Markdown"),
        }
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                log.info("[Telegram] ✓ Alerta enviado")
                return True
            body = await resp.text()
            log.warning(f"[Telegram] HTTP {resp.status}: {body[:200]}")
    except Exception as e:
        log.error(f"[Telegram] Falha: {e}")
    return False


async def _send_webhook(cfg: Dict, event_type: str, message: str,
                        raw_kwargs: Dict, session: aiohttp.ClientSession) -> bool:
    url = cfg.get("url", "")
    if not url:
        return False
    try:
        payload = {
            "event":     event_type,
            "message":   message,
            "timestamp": datetime.utcnow().isoformat(),
            "data":      raw_kwargs,
        }
        headers = cfg.get("headers", {})
        method  = cfg.get("method", "POST").upper()
        send_fn = session.post if method == "POST" else session.put
        async with send_fn(url, json=payload, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status in (200, 201, 204):
                log.info("[Webhook] ✓ Alerta enviado")
                return True
            log.warning(f"[Webhook] HTTP {resp.status}")
    except Exception as e:
        log.error(f"[Webhook] Falha: {e}")
    return False


async def _send_email(cfg: Dict, event_type: str, message: str) -> bool:
    """Email via aiosmtplib se disponível, senão fallback stdlib síncrono."""
    host     = cfg.get("smtp_host", "smtp.gmail.com")
    port     = cfg.get("smtp_port", 587)
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    from_    = cfg.get("from_addr", username)
    to_list  = cfg.get("to_addrs", [])

    if not username or not password or not to_list:
        log.debug("[Email] Credenciais SMTP não configuradas — pulando")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Olho de Deus] {event_type}"
    msg["From"]    = from_
    msg["To"]      = ", ".join(to_list)
    msg.attach(MIMEText(message, "plain", "utf-8"))

    try:
        try:
            import aiosmtplib
            await aiosmtplib.send(
                msg, hostname=host, port=port,
                username=username, password=password,
                use_tls=cfg.get("use_tls", True),
            )
        except ImportError:
            # Fallback síncrono executado em thread pool
            loop = asyncio.get_event_loop()
            def _sync_send():
                with smtplib.SMTP(host, port) as s:
                    if cfg.get("use_tls", True):
                        s.starttls()
                    s.login(username, password)
                    s.sendmail(from_, to_list, msg.as_string())
            await loop.run_in_executor(None, _sync_send)

        log.info("[Email] ✓ Alerta enviado")
        return True
    except Exception as e:
        log.error(f"[Email] Falha: {e}")
    return False


async def _send_pushover(cfg: Dict, event_type: str, message: str,
                          severity: str, session: aiohttp.ClientSession) -> bool:
    app_token = cfg.get("app_token", "")
    user_key  = cfg.get("user_key", "")
    if not app_token or not user_key:
        log.debug("[Pushover] Credenciais não configuradas — pulando")
        return False

    # Mapear severidade para prioridade Pushover
    priority_map = {"DEBUG": -2, "INFO": -1, "WARNING": 0, "ERROR": 1, "CRITICAL": 2}
    priority = priority_map.get(severity, 0)

    try:
        payload = {
            "token":    app_token,
            "user":     user_key,
            "title":    f"Olho de Deus — {event_type}",
            "message":  message,
            "priority": priority,
        }
        if priority == 2:  # CRITICAL: requer acknowledge
            payload.update({"retry": 60, "expire": 3600})

        async with session.post(
            "https://api.pushover.net/1/messages.json",
            data=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 200:
                log.info("[Pushover] ✓ Alerta enviado")
                return True
            log.warning(f"[Pushover] HTTP {resp.status}")
    except Exception as e:
        log.error(f"[Pushover] Falha: {e}")
    return False


# ─── Dispatcher principal ─────────────────────────────────────────────────────

async def dispatch(event_type: str, **kwargs) -> None:
    """
    Publica um evento para todos os canais configurados para aquele tipo.
    Fire-and-forget — não bloqueia o chamador.

    Args:
        event_type: Tipo do evento (deve corresponder a uma entrada em routing: no YAML).
        **kwargs:   Variáveis para o template do evento.
    """
    cfg = _load_config()
    if not cfg:
        return

    routes       = cfg.get("routing", [])
    channels_cfg = cfg.get("channels", {})
    rl           = cfg.get("rate_limit", {})
    max_per_min  = rl.get("max_per_minute", 10)
    cooldown     = rl.get("cooldown_seconds", 5)

    # Encontrar rota para este evento
    route = next((r for r in routes if r["event"] == event_type), None)
    if not route:
        log.debug(f"Nenhuma rota para evento: {event_type}")
        return

    severity  = route.get("severity", "INFO")
    template  = route.get("template", "{event_type}: {kwargs}")
    target_ch = route.get("channels", [])
    message   = _render(template, event_type=event_type, **kwargs)

    # Aplicar Criptografia E2E se configurado (Fase 25)
    message = _maybe_encrypt(message)

    connector = _build_connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for ch_name in target_ch:
            ch_cfg = channels_cfg.get(ch_name, {})
            if not ch_cfg.get("enabled", False):
                continue
            
            # Suporte a bypass para emergências (Fase 30)
            bypass = kwargs.get("bypass_rate_limit", False)
            if not bypass and _is_rate_limited(event_type, ch_name, max_per_min, cooldown):
                log.debug(f"[{ch_name}] Rate-limited para {event_type}")
                continue

            if ch_name == "telegram":
                tasks.append(_send_telegram(ch_cfg, message, session))
            elif ch_name == "webhook":
                tasks.append(_send_webhook(ch_cfg, event_type, message, kwargs, session))
            elif ch_name == "email":
                tasks.append(_send_email(ch_cfg, event_type, message))
            elif ch_name == "pushover":
                tasks.append(_send_pushover(ch_cfg, event_type, message, severity, session))

        if tasks:
            # Lógica de Deduplicação / Agrupamento Espacial (Fase 31)
            uid = kwargs.get("uid")
            if event_type == "MATCH_DETECTED" and uid:
                now = time.time()
                entry = _dedup_tracker.get(uid, {"last_seen": 0, "cameras": set()})
                
                # Se visto recentemente em outra câmera, podemos transformar o alerta
                if now - entry["last_seen"] < 600: # 10 minutos
                    entry["cameras"].add(kwargs.get("camera_id", "UNK"))
                    if len(entry["cameras"]) > 1:
                        message = f"🗺️ **MOVIMENTAÇÃO SUSPEITA: {kwargs.get('name', 'ALVO')}**\n"
                        message += f"Detectado em {len(entry['cameras'])} locais (Última: {kwargs.get('camera_id')})\n"
                        message += f"Histórico Recente: {', '.join(entry['cameras'])}"
                
                entry["last_seen"] = now
                entry["cameras"].add(kwargs.get("camera_id", "UNK"))
                _dedup_tracker[uid] = entry

            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Registrar na Auditoria (Fase 17)
            audit_log.info(f"EVENT: {event_type} | CHANNELS: {', '.join(target_ch)} | STATUS: {'SUCCESS' if all(r is True for r in results) else 'PARTIAL_FAILURE'}")
            
            failed = sum(1 for r in results if isinstance(r, Exception) or r is False)
            if failed:
                log.warning(f"[dispatch] {failed}/{len(tasks)} canais falharam para {event_type}")


def dispatch_sync(event_type: str, **kwargs) -> None:
    """
    Versão síncrona do dispatch para uso em contextos não-async.
    Cria um event loop temporário se necessário.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(dispatch(event_type, **kwargs))
        else:
            loop.run_until_complete(dispatch(event_type, **kwargs))
    except RuntimeError:
        asyncio.run(dispatch(event_type, **kwargs))


# ─── CLI de teste ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    parser = argparse.ArgumentParser(description="Olho de Deus — Alert Dispatcher Test")
    parser.add_argument("--event", default="SYSTEM_ONLINE", help="Tipo do evento a testar")
    parser.add_argument("--mode",  default="TEST",          help="Modo do sistema")
    args = parser.parse_args()

    print(f"Testando evento: {args.event}")
    asyncio.run(dispatch(args.event, mode=args.mode, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("Teste concluído.")
