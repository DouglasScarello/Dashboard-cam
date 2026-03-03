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
DB_FILE = os.getenv("DB_FILE", "intelligence/data/intelligence.db")

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

if __name__ == "__main__":
    init_db()
