import redis
import hashlib
import json
import logging

log = logging.getLogger("vector_cache")

class VectorCache:
    """
    Camada de Cache para Embeddings (Fase 31.2).
    Evita buscas exaustivas no FAISS para rostos vistos recentemente.
    """
    def __init__(self, host='localhost', port=6379, db=0, ttl=300):
        try:
            self.client = redis.Redis(host=host, port=port, db=db, socket_timeout=0.1)
            self.ttl = ttl
            self.online = self.client.ping()
            if self.online:
                log.info("🚀 Conectado ao Cache Redis (Ghost Protocol)")
        except Exception as e:
            log.warning(f"⚠️ Redis indisponível: {e}. Operando sem cache.")
            self.online = False

    def _hash_vector(self, vector):
        """Gera um hash SHA-256 único para o vetor de embedding."""
        return hashlib.sha256(vector.tobytes()).hexdigest()

    def get_match(self, embedding):
        """Busca um match no cache."""
        if not self.online: return None
        
        v_hash = self._hash_vector(embedding)
        try:
            cached = self.client.get(f"face_cache:{v_hash}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    def set_match(self, embedding, match_data):
        """Salva um match no cache com TTL."""
        if not self.online or not match_data: return
        
        v_hash = self._hash_vector(embedding)
        try:
            self.client.setex(
                f"face_cache:{v_hash}",
                self.ttl,
                json.dumps(match_data)
            )
        except Exception:
            pass
