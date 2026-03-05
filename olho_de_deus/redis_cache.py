#!/usr/bin/env python3
"""
redis_cache.py — Olho de Deus [Fase 31.1: Redis Cache Layer]

Camada de cache distribuído com fallback gracioso.
Se o Redis não estiver disponível, opera em modo degradado sem travar o pipeline.

Responsabilidades:
  - Cache de embeddings ArcFace (TTL 24h) — evita re-extração por track
  - Rate-limiting de alertas por UID + câmera (debounce 60s) — evita spam no Telegram
  - Cache de threat scores (TTL 15min) — evita recálculo frequente
"""

import json
import logging
import time
from typing import Any, List, Optional

log = logging.getLogger(__name__)

# ─── Importação com fallback ────────────────────────────────────────────────
try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    log.warning("[RedisCache] Biblioteca 'redis' não instalada. Operando em modo degradado.")

# ─── TTLs em segundos ───────────────────────────────────────────────────────
TTL_EMBEDDING    = 60 * 60 * 24      # 24 horas
TTL_THREAT_SCORE = 60 * 15           # 15 minutos
TTL_ALERT_DEBOUNCE = 60              # 60 segundos entre alertas do mesmo UID/câmera


class RedisCache:
    """
    Interface de cache Redis com fallback transparente.

    Em modo degradado (Redis indisponível):
      - Todos os gets retornam None
      - rate-limiting sempre retorna False (sem bloquear alertas)
      - Nenhuma exceção é propagada para o caller
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, db: int = 0, password: Optional[str] = None):
        self._client = None
        self._degraded = False

        if not HAS_REDIS:
            self._degraded = True
            log.warning("[RedisCache] Modo degradado: biblioteca redis ausente.")
            return

        try:
            client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            client.ping()
            self._client = client
            log.info(f"[RedisCache] ✅ Conectado ao Redis em {host}:{port}")
        except Exception as e:
            self._degraded = True
            log.warning(f"[RedisCache] ⚠️ Redis indisponível ({e}). Modo degradado ativado.")

    # ─────────────────────────────────────────────────────────────────────────
    # Métodos internos
    # ─────────────────────────────────────────────────────────────────────────

    def _get(self, key: str) -> Optional[str]:
        if self._degraded or not self._client:
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            log.debug(f"[RedisCache] get({key}) falhou: {e}")
            return None

    def _set(self, key: str, value: str, ttl: int) -> bool:
        if self._degraded or not self._client:
            return False
        try:
            self._client.setex(key, ttl, value)
            return True
        except Exception as e:
            log.debug(f"[RedisCache] set({key}) falhou: {e}")
            return False

    def _exists(self, key: str) -> bool:
        if self._degraded or not self._client:
            return False
        try:
            return bool(self._client.exists(key))
        except Exception as e:
            log.debug(f"[RedisCache] exists({key}) falhou: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # API Pública — Embeddings
    # ─────────────────────────────────────────────────────────────────────────

    def get_embedding(self, uid: str) -> Optional[List[float]]:
        """
        Recupera embedding ArcFace cacheado para um UID.
        Retorna lista de floats ou None se ausente/expirado.
        """
        raw = self._get(f"emb:{uid}")
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    def set_embedding(self, uid: str, embedding: List[float]) -> bool:
        """
        Salva embedding ArcFace no cache com TTL de 24h.
        embedding deve ser uma lista de 512 floats.
        """
        try:
            payload = json.dumps(embedding)
            return self._set(f"emb:{uid}", payload, TTL_EMBEDDING)
        except Exception:
            return False

    def invalidate_embedding(self, uid: str) -> None:
        """Remove embedding do cache (ex: banco atualizado)."""
        if self._degraded or not self._client:
            return
        try:
            self._client.delete(f"emb:{uid}")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # API Pública — Threat Score
    # ─────────────────────────────────────────────────────────────────────────

    def get_threat_score(self, uid: str) -> Optional[float]:
        """
        Recupera threat score cacheado (TTL 15min).
        """
        raw = self._get(f"score:{uid}")
        if raw is not None:
            try:
                return float(raw)
            except (ValueError, TypeError):
                return None
        return None

    def set_threat_score(self, uid: str, score: float) -> bool:
        """Salva threat score no cache."""
        return self._set(f"score:{uid}", str(score), TTL_THREAT_SCORE)

    # ─────────────────────────────────────────────────────────────────────────
    # API Pública — Rate-Limiting de Alertas
    # ─────────────────────────────────────────────────────────────────────────

    def alert_is_rate_limited(self, uid: str, camera_id: str = "default") -> bool:
        """
        Verifica se um alerta para este UID+câmera está em período de debounce.

        Returns:
            True  — alerta JÁ FOI enviado recentemente (suprimir)
            False — pode enviar o alerta
        """
        return self._exists(f"alert:{uid}:{camera_id}")

    def mark_alert_sent(self, uid: str, camera_id: str = "default") -> bool:
        """
        Registra que um alerta foi enviado para este UID+câmera.
        Próximos alertas do mesmo par serão suprimidos pelo TTL (60s).
        """
        return self._set(f"alert:{uid}:{camera_id}", "1", TTL_ALERT_DEBOUNCE)

    # ─────────────────────────────────────────────────────────────────────────
    # API Pública — Diagnóstico
    # ─────────────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """
        Retorna status do cache para uso no System Health (Fase 20).
        """
        if self._degraded or not self._client:
            return {
                "mode": "degraded",
                "connected": False,
                "ping_ms": None,
                "info": "Redis indisponível — pipeline operando sem cache."
            }
        try:
            t0 = time.perf_counter()
            self._client.ping()
            ping_ms = round((time.perf_counter() - t0) * 1000, 2)
            info = self._client.info("server")
            return {
                "mode": "active",
                "connected": True,
                "ping_ms": ping_ms,
                "redis_version": info.get("redis_version", "?"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "used_memory_human": info.get("used_memory_human", "?"),
            }
        except Exception as e:
            return {"mode": "error", "connected": False, "error": str(e)}

    def flush_all(self) -> None:
        """Limpa TODOS os dados. Usar apenas em testes."""
        if self._degraded or not self._client:
            return
        try:
            self._client.flushdb()
            log.warning("[RedisCache] ⚠️ Banco Redis limpo (flush_all).")
        except Exception:
            pass


# ─── Instância global padrão (lazy) ─────────────────────────────────────────
_default_cache: Optional[RedisCache] = None


def get_cache(host: str = "127.0.0.1", port: int = 6379) -> RedisCache:
    """
    Retorna instância global do RedisCache (singleton lazy).
    Útil para uso direto em scripts sem necessidade de gerenciar instância.
    """
    global _default_cache
    if _default_cache is None:
        _default_cache = RedisCache(host=host, port=port)
    return _default_cache


# ─── Teste rápido ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cache = get_cache()

    h = cache.health()
    print(f"\n[health] Modo: {h['mode']}")
    if h.get("redis_version"):
        print(f"[health] Redis {h['redis_version']} | Latência: {h['ping_ms']}ms | Mem: {h['used_memory_human']}")

    # Teste de embedding
    test_emb = [0.1] * 512
    cache.set_embedding("test_uid_31", test_emb)
    recovered = cache.get_embedding("test_uid_31")
    assert recovered is None or len(recovered) == 512, "Falha no cache de embedding"
    print(f"[embedding] Cache {'✅ OK' if recovered else '⚠️ degradado (sem Redis)'}")

    # Teste de threat score
    cache.set_threat_score("test_uid_31", 8.7)
    score = cache.get_threat_score("test_uid_31")
    print(f"[score]     Cache {'✅ OK: ' + str(score) if score else '⚠️ degradado'}")

    # Teste de rate-limiting
    print(f"[alert-1]   Limitado antes: {cache.alert_is_rate_limited('test_uid_31', 'cam_floripa')}")
    cache.mark_alert_sent("test_uid_31", "cam_floripa")
    print(f"[alert-2]   Limitado depois: {cache.alert_is_rate_limited('test_uid_31', 'cam_floripa')}")

    # Cleanup
    cache.invalidate_embedding("test_uid_31")
    print("\n✅ Fase 31.1 — RedisCache operacional.")
