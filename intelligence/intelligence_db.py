#!/usr/bin/env python3
"""
Intelligence Database — Olho de Deus
Suporte Dual: SQLite (Local) e PostgreSQL (Produção/Docker)
"""
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import json
import struct
import os
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configurações
DB_TYPE = os.getenv("DB_TYPE", "sqlite") # 'sqlite' ou 'postgres'
# Usar caminho absoluto para evitar bases fantasmas em subdiretórios
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.getenv("DB_FILE", os.path.join(BASE_DIR, "intelligence", "data", "intelligence.db"))

PG_HOST = os.getenv("DB_HOST", "localhost")
PG_NAME = os.getenv("DB_NAME", "intelligence")
PG_USER = os.getenv("DB_USER", "ghost")
PG_PASS = os.getenv("DB_PASS", "protocol")
PG_PORT = os.getenv("DB_PORT", "5432")

# ─────────────────────────────────────────────────────────────────
# CLASSE DE ABSTRAÇÃO DB
# ─────────────────────────────────────────────────────────────────

class DB:
    def __init__(self):
        self.type = DB_TYPE
        self.conn = None
        self._connect()

    def _connect(self):
        if self.type == "postgres":
            try:
                self.conn = psycopg2.connect(
                    host=PG_HOST, database=PG_NAME,
                    user=PG_USER, password=PG_PASS, port=PG_PORT
                )
            except Exception as e:
                print(f"[db] Erro ao conectar no Postgres: {e}. Caindo para SQLite...")
                self.type = "sqlite"
                self._connect_sqlite()
        else:
            self._connect_sqlite()

    def _connect_sqlite(self):
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        self.conn = sqlite3.connect(DB_FILE)
        self.conn.row_factory = sqlite3.Row

    def get_cursor(self):
        if self.type == "postgres":
            return self.conn.cursor(cursor_factory=RealDictCursor)
        return self.conn.cursor()

    def translate_query(self, query: str) -> str:
        """Converte placeholders '?' para '%s' se for Postgres."""
        if self.type == "postgres":
            return query.replace("?", "%s")
        return query

    def execute(self, query: str, params: Any = ()):
        cur = self.get_cursor()
        q = self.translate_query(query)
        cur.execute(q, params)
        return cur

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

# ─────────────────────────────────────────────────────────────────
# SCHEMA E INICIALIZAÇÃO
# ─────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS individuals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    aliases         TEXT,
    category        TEXT NOT NULL,
    source          TEXT NOT NULL,
    birth_date      TEXT,
    sex             TEXT,
    height_cm       REAL,
    weight_kg       REAL,
    eye_color       TEXT,
    hair_color      TEXT,
    nationalities   TEXT,
    languages       TEXT,
    occupation      TEXT,
    description     TEXT,
    reward          TEXT,
    url             TEXT,
    img_url         TEXT,
    img_path        TEXT,
    has_embedding   INTEGER DEFAULT 0,
    first_seen      TEXT,
    last_seen       TEXT,
    ingested_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crimes (
    id              SERIAL PRIMARY KEY,
    individual_id   TEXT REFERENCES individuals(id),
    crime           TEXT NOT NULL,
    severity        TEXT
);

CREATE TABLE IF NOT EXISTS locations (
    id              SERIAL PRIMARY KEY,
    individual_id   TEXT REFERENCES individuals(id),
    type            TEXT NOT NULL,
    country         TEXT,
    state           TEXT,
    city            TEXT,
    details         TEXT
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    individual_id   TEXT PRIMARY KEY REFERENCES individuals(id),
    embedding       vector(512), -- Postgres native vector
    embedding_blob  BYTEA,       -- SQLite fallback
    model           TEXT DEFAULT 'ArcFace',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS individual_images (
    id              SERIAL PRIMARY KEY,
    individual_id   TEXT REFERENCES individuals(id),
    img_url         TEXT,
    img_path        TEXT,
    caption         TEXT,
    is_primary      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evidence (
    id              TEXT PRIMARY KEY,
    individual_id   TEXT NOT NULL REFERENCES individuals(id),
    file_hash       TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    captured_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS threat_scores (
    individual_id   TEXT PRIMARY KEY REFERENCES individuals(id),
    score           FLOAT DEFAULT 1.0,
    factors_json    TEXT, -- Detalhes do cálculo (JSON)
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

"""

def init_db():
    db = DB()
    if db.type == "sqlite":
        # SQLite não suporta SERIAL ou BYTEA nativamente do mesmo jeito
        schema = SCHEMA_SQL.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        schema = schema.replace("BYTEA", "BLOB")
        schema = schema.replace("vector(512)", "BLOB") # Fallback simples
        db._connect_sqlite()
        db.conn.executescript(schema)
    else:
        # Habilitar pgvector no Postgres
        db.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        db.execute(SCHEMA_SQL)
    db.commit()
    db.close()
    print(f"[db] Banco inicializado ({db.type}) com suporte vetorial.")

# ─────────────────────────────────────────────────────────────────
# CRUD E BUSCA
# ─────────────────────────────────────────────────────────────────

def upsert_individual(db: DB, data: Dict):
    # Usando ON CONFLICT para Postgres e SQLite (ambos suportam agora)
    q = """
        INSERT INTO individuals (
            id, name, aliases, category, source, birth_date, sex,
            height_cm, weight_kg, eye_color, hair_color,
            nationalities, languages, occupation, description,
            reward, url, img_url, img_path, has_embedding,
            first_seen, last_seen
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = EXCLUDED.name,
            aliases = EXCLUDED.aliases,
            description = EXCLUDED.description,
            last_seen = EXCLUDED.last_seen,
            has_embedding = EXCLUDED.has_embedding
    """
    params = (
        data.get("id"), data.get("name"), json.dumps(data.get("aliases", []), ensure_ascii=False),
        data.get("category"), data.get("source"), data.get("birth_date"),
        data.get("sex"), data.get("height_cm"), data.get("weight_kg"),
        data.get("eye_color"), data.get("hair_color"), 
        json.dumps(data.get("nationalities", []) if isinstance(data.get("nationalities"), list) else [data.get("nationalities")] if data.get("nationalities") else [], ensure_ascii=False),
        json.dumps(data.get("languages", []) if isinstance(data.get("languages"), list) else [data.get("languages")] if data.get("languages") else [], ensure_ascii=False),
        json.dumps(data.get("occupation", []) if isinstance(data.get("occupation"), list) else [data.get("occupation")] if data.get("occupation") else [], ensure_ascii=False),
        data.get("description"), data.get("reward"),
        data.get("url"), data.get("img_url"), data.get("img_path"),
        1 if data.get("has_embedding") else 0,
        data.get("first_seen"), data.get("last_seen")
    )
    db.execute(q, params)
    db.commit()

def insert_crimes(db: DB, individual_id: str, crimes: List[str]):
    for crime in crimes:
        if crime.strip():
            # Postgres e SQLite tem sintaxes levemente diferentes para IGNORE duplicatas
            if db.type == "sqlite":
                db.execute("INSERT OR IGNORE INTO crimes (individual_id, crime) VALUES (?, ?)", (individual_id, crime.strip()))
            else:
                db.execute("INSERT INTO crimes (individual_id, crime) VALUES (?, ?) ON CONFLICT DO NOTHING", (individual_id, crime.strip()))
    db.commit()

def insert_image(db: DB, individual_id: str, **kwargs):
    q = "INSERT INTO individual_images (individual_id, img_url, img_path, caption, is_primary) VALUES (?, ?, ?, ?, ?)"
    db.execute(q, (individual_id, kwargs.get("img_url"), kwargs.get("img_path"), kwargs.get("caption"), 1 if kwargs.get("is_primary") else 0))
    db.commit()

def search(db: DB, **kwargs) -> List[Dict]:
    where, params = ["1=1"], []
    if kwargs.get("name"):
        where.append("(name LIKE ? OR aliases LIKE ? OR description LIKE ?)")
        p = f"%{kwargs['name']}%"
        params += [p, p, p]
    if kwargs.get("category"):
        where.append("category = ?")
        params.append(kwargs["category"])
    
    limit = kwargs.get("limit", 40)
    sql = f"SELECT * FROM individuals WHERE {' AND '.join(where)} LIMIT ?"
    params.append(limit)
    
    cur = db.execute(sql, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]

    return data

def save_embedding(db: DB, individual_id: str, embedding: List[float]):
    """Salva vetor biométrico no Postgres (pgvector) ou SQLite (BLOB)."""
    if db.type == "postgres":
        # Converte lista [0.1, 0.2...] para string formatada '[0.1, 0.2...]' para o pgvector
        emb_str = str(embedding).replace(" ", "")
        q = "INSERT INTO face_embeddings (individual_id, embedding) VALUES (?, ?) ON CONFLICT(individual_id) DO UPDATE SET embedding = EXCLUDED.embedding"
        db.execute(q, (individual_id, emb_str))
    else:
        # SQLite: fallback p/ BLOB (binário)
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        q = "INSERT OR REPLACE INTO face_embeddings (individual_id, embedding_blob) VALUES (?, ?)"
        db.execute(q, (individual_id, blob))
    db.commit()

def search_biometric(db: DB, target_embedding: List[float], limit: int = 10) -> List[Dict]:
    """Busca alvos similares usando similaridade de cosseno/L2 (via pgvector se disponível)."""
    if db.type == "postgres":
        emb_str = str(target_embedding).replace(" ", "")
        # Operador <-> é para distância L2
        q = """
            SELECT i.*, (f.embedding <-> ?) as distance
            FROM individuals i
            JOIN face_embeddings f ON i.id = f.individual_id
            ORDER BY distance ASC LIMIT ?
        """
        cur = db.execute(q, (emb_str, limit))
    else:
        # No SQLite fazemos uma busca simples ou via FAISS (externo).
        # Para Muni, vamos focar no Postgres como motor principal de performance.
        return []
        
    return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────────
# FASE 14 — DELTA EMBEDDING SUPPORT
# ─────────────────────────────────────────────────────────────────

def get_embedding_delta(db: DB, limit: Optional[int] = None) -> List[Dict]:
    """
    Retorna apenas os indivíduos que precisam de (re)processamento biométrico:
        1. Nunca tiveram embedding gerado (has_embedding = 0)
        2. Foram atualizados (last_seen) DEPOIS do último embedding calculado
    
    Usa LEFT JOIN para detectar ambos os casos numa única query eficiente.
    Exige img_path preenchido (sem imagem não há como gerar embedding).
    """
    q = """
        SELECT
            i.id,
            i.name,
            i.img_path,
            i.last_seen,
            fe.created_at AS emb_created_at
        FROM individuals i
        LEFT JOIN face_embeddings fe ON fe.individual_id = i.id
        WHERE i.img_path IS NOT NULL
          AND (
              i.has_embedding = 0
              OR fe.individual_id IS NULL
              OR (i.last_seen IS NOT NULL AND fe.created_at IS NOT NULL
                  AND i.last_seen > fe.created_at)
          )
        ORDER BY
            CASE WHEN i.has_embedding = 0 THEN 0 ELSE 1 END,  -- novos primeiro
            i.last_seen DESC
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    cur = db.execute(q)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def mark_embedded(db: DB, individual_id: str) -> None:
    """Marca um indivíduo como tendo embedding processado."""
    db.execute(
        "UPDATE individuals SET has_embedding = 1 WHERE id = ?",
        (individual_id,)
    )
    db.commit()


def get_all_embeddings_for_index(db: DB) -> List[Dict]:
    """
    Retorna todos os embeddings já calculados para reconstrução
    do IndexIDMap ao inicializar o delta_embedder.
    Retorna list de {individual_id, embedding_blob} ou {individual_id, embedding}.
    """
    cur = db.execute(
        "SELECT individual_id, embedding_blob FROM face_embeddings WHERE embedding_blob IS NOT NULL"
    )
    return [dict(r) for r in cur.fetchall()]


# ─────────────────────────────────────────────────────────────────
# FASE 16 — CADEIA DE CUSTÓDIA (SHA-256)
# ─────────────────────────────────────────────────────────────────

def register_evidence(db: DB, evidence_id: str, individual_id: str, file_hash: str, file_path: str):
    """
    Registra uma evidência (foto/frame) na Cadeia de Custódia.
    Design Append-Only: Rejeita se o ID já existir.
    """
    # Verificar se já existe (Proteção de Imutabilidade)
    cur = db.execute("SELECT 1 FROM evidence WHERE id = ?", (evidence_id,))
    if cur.fetchone():
        raise PermissionError(f"Violação de Imutabilidade: Evidência {evidence_id} já existe.")

    q = "INSERT INTO evidence (id, individual_id, file_hash, file_path) VALUES (?, ?, ?, ?)"
    db.execute(q, (evidence_id, individual_id, file_hash, file_path))
    db.commit()


def get_evidence(db: DB, individual_id: str) -> List[Dict]:
    """Retorna todas as evidências de um indivíduo."""
    cur = db.execute(
        "SELECT * FROM evidence WHERE individual_id = ? ORDER BY captured_at DESC",
        (individual_id,)
    )
    return [dict(r) for r in cur.fetchall()]


def get_all_evidence_hashes(db: DB) -> List[Dict]:
    """Retorna todos os registros de evidência para auditoria."""
    cur = db.execute("SELECT id, individual_id, file_hash, file_path FROM evidence")
    return [dict(row) for row in cur.fetchall()]

# ─────────────────────────────────────────────────────────────────
# THREAT SCORING (FASE 12)
# ─────────────────────────────────────────────────────────────────

def upsert_threat_score(db: DB, individual_id: str, score: float, factors: Dict):
    """Insere ou atualiza o score de ameaça de um indivíduo."""
    f_json = json.dumps(factors)
    q = """
    INSERT INTO threat_scores (individual_id, score, factors_json, updated_at)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(individual_id) DO UPDATE SET
        score = excluded.score,
        factors_json = excluded.factors_json,
        updated_at = CURRENT_TIMESTAMP
    """
    db.execute(q, (individual_id, score, f_json))
    db.commit()

def get_threat_score(db: DB, individual_id: str) -> Optional[Dict]:
    """Recupera o score e fatores de um indivíduo."""
    q = "SELECT score, factors_json, updated_at FROM threat_scores WHERE individual_id = ?"
    cur = db.execute(q, (individual_id,))
    row = cur.fetchone()
    if row:
        res = dict(row)
        res["factors"] = json.loads(res["factors_json"]) if res["factors_json"] else {}
        return res
    return None


def stats(db: DB) -> Dict:

    """Estatísticas gerais do banco."""
    def count(q):
        return db.execute(q).fetchone()[0]

    total   = count("SELECT COUNT(*) FROM individuals")
    wanted  = count("SELECT COUNT(*) FROM individuals WHERE category = 'wanted'")
    missing = count("SELECT COUNT(*) FROM individuals WHERE category = 'missing'")
    with_b  = count("SELECT COUNT(*) FROM individuals WHERE has_embedding = 1")

    cur = db.execute(
        "SELECT source, COUNT(*) as cnt FROM individuals GROUP BY source ORDER BY cnt DESC LIMIT 20"
    )
    by_source = [dict(r) for r in cur.fetchall()]

    return {
        "total":           total,
        "wanted":          wanted,
        "missing":         missing,
        "with_biometrics": with_b,
        "by_source":       by_source,
    }


if __name__ == "__main__":
    init_db()

