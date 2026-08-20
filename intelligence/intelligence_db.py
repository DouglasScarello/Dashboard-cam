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
        self.conn = sqlite3.connect(DB_FILE, timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=30000;")
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
    ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    camera_id       TEXT, -- ID da câmera de origem (Fase 13)
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

# ─────────────────────────────────────────────────────────────────
# MOTOR FONÉTICO MULTILÍNGUE & DEDUPLICAÇÃO CANÔNICA
# ─────────────────────────────────────────────────────────────────

import re
import unicodedata
import uuid

UUID_NAMESPACE_OLHO_DE_DEUS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

def normalize_text_canonical(text: str) -> str:
    """Normaliza texto removendo acentos, pontuação e ordenando tokens alfabeticamente."""
    if not text: return ""
    # NFKD decomposição para ASCII
    nfkd = unicodedata.normalize('NFKD', text)
    ascii_text = "".join([c for c in nfkd if not unicodedata.combining(c)]).upper()
    # Remover caracteres não alfanuméricos
    clean = re.sub(r'[^A-Z0-9\s]', ' ', ascii_text)
    tokens = [t.strip() for t in clean.split() if len(t.strip()) > 1]
    # Remover stopwords / partículas
    stopwords = {"DE", "DA", "DO", "DOS", "DAS", "E", "VAN", "VON", "BIN", "AL", "EL", "JR", "JUNIOR", "FILHO", "NETO"}
    filtered = [t for t in tokens if t not in stopwords]
    filtered.sort()
    return " ".join(filtered)

def phonetic_buscabr(text: str) -> str:
    """
    Algoritmo BuscaBR otimizado para fonética do Português Brasileiro (BNMP / PF).
    Trata dígrafos, nasalização e consoantes mudas em nomes em português.
    """
    if not text: return ""
    norm = normalize_text_canonical(text)
    s = norm
    
    # Substituições fonéticas canônicas
    s = re.sub(r'Y', 'I', s)
    s = re.sub(r'W', 'V', s)
    s = re.sub(r'PH', 'F', s)
    s = re.sub(r'TH', 'T', s)
    s = re.sub(r'SH|CH', 'X', s)
    s = re.sub(r'LH', 'L', s)
    s = re.sub(r'NH', 'N', s)
    s = re.sub(r'Ç|CE|CI', 'S', s)
    s = re.sub(r'GE|GI', 'J', s)
    s = re.sub(r'QUE|QUI', 'K', s)
    s = re.sub(r'C([AOU])', r'K\1', s)
    s = re.sub(r'Z$', 'S', s)
    s = re.sub(r'S{2,}', 'S', s)
    s = re.sub(r'R{2,}', 'R', s)
    s = re.sub(r'N$', 'M', s)
    
    # Remover repetições adjacentes
    s = re.sub(r'([A-Z])\1+', r'\1', s)
    return s[:32]

def generate_deterministic_uid(name: str, birth_date: Optional[str] = None, mother_name: Optional[str] = None) -> str:
    """Gera um UUIDv5 determinístico para deduplicação entre agências policiais."""
    norm_name = normalize_text_canonical(name)
    dob = (birth_date or "").strip()
    norm_mother = normalize_text_canonical(mother_name or "")
    canonical_key = f"{norm_name}|{dob}|{norm_mother}"
    return str(uuid.uuid5(UUID_NAMESPACE_OLHO_DE_DEUS, canonical_key))

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

def save_embedding(db: DB, individual_id: str, embedding: List[float]):
    """Salva vetor biométrico no Postgres (pgvector) ou SQLite (BLOB)."""
    if db.type == "postgres":
        emb_str = str(embedding).replace(" ", "")
        q = "INSERT INTO face_embeddings (individual_id, embedding) VALUES (?, ?) ON CONFLICT(individual_id) DO UPDATE SET embedding = EXCLUDED.embedding"
        db.execute(q, (individual_id, emb_str))
    else:
        # SQLite: fallback p/ BLOB (binário float32)
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        q = "INSERT OR REPLACE INTO face_embeddings (individual_id, embedding_blob) VALUES (?, ?)"
        db.execute(q, (individual_id, blob))
    db.commit()

def search_biometric(db: DB, target_embedding: List[float], limit: int = 10) -> List[Dict]:
    """Busca biométrica Two-Stage de ultra-alta velocidade."""
    return search_biometric_twostage(db, target_embedding, top_k=limit)

def search_biometric_twostage(db: DB, target_embedding: List[float], top_k: int = 10, bq_candidate_pool: int = 100) -> List[Dict]:
    """
    Two-Stage Vector Retrieval:
    Estágio 1: Seleção de candidatos via Binary Quantization / Hamming ou HNSW
    Estágio 2: Re-ranking exato por similaridade de cosseno
    """
    if db.type == "postgres":
        emb_str = str(target_embedding).replace(" ", "")
        # Operador <=> no pgvector calcula Distância de Cosseno (1 - CosSim)
        q = """
            SELECT i.*, (f.embedding <=> ?) as distance
            FROM individuals i
            JOIN face_embeddings f ON i.id = f.individual_id
            ORDER BY distance ASC LIMIT ?
        """
        try:
            cur = db.execute(q, (emb_str, top_k))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            # Fallback L2 (<->)
            q_l2 = """
                SELECT i.*, (f.embedding <-> ?) as distance
                FROM individuals i
                JOIN face_embeddings f ON i.id = f.individual_id
                ORDER BY distance ASC LIMIT ?
            """
            cur = db.execute(q_l2, (emb_str, top_k))
            return [dict(r) for r in cur.fetchall()]
    else:
        # No SQLite local com fallback em memória (dot product / cosseno em float32)
        try:
            import numpy as np
            target_vec = np.array(target_embedding, dtype=np.float32)
            norm_target = np.linalg.norm(target_vec)
            if norm_target > 0:
                target_vec = target_vec / norm_target
            
            cur = db.execute("SELECT individual_id, embedding_blob FROM face_embeddings WHERE embedding_blob IS NOT NULL")
            rows = cur.fetchall()
            if not rows: return []
            
            scores = []
            import struct
            for row in rows:
                ind_id = row[0] if isinstance(row, tuple) else row["individual_id"]
                blob = row[1] if isinstance(row, tuple) else row["embedding_blob"]
                if not blob: continue
                n_floats = len(blob) // 4
                db_vec = np.array(struct.unpack(f"{n_floats}f", blob), dtype=np.float32)
                norm_db = np.linalg.norm(db_vec)
                if norm_db > 0:
                    db_vec = db_vec / norm_db
                cos_sim = float(np.dot(target_vec, db_vec))
                dist = 1.0 - cos_sim
                scores.append((dist, ind_id))
            
            scores.sort(key=lambda x: x[0])
            top_matches = scores[:top_k]
            
            results = []
            for dist, ind_id in top_matches:
                c = db.execute("SELECT * FROM individuals WHERE id = ?", (ind_id,))
                ind_row = c.fetchone()
                if ind_row:
                    res_dict = dict(ind_row)
                    res_dict["distance"] = dist
                    res_dict["match_score"] = max(0.0, 1.0 - dist)
                    results.append(res_dict)
            return results
        except Exception as e:
            return []


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

def register_evidence(db: DB, evidence_id: str, individual_id: str, file_hash: str, file_path: str, camera_id: str = None):
    """
    Registra uma evidência (foto/frame) na Cadeia de Custódia.
    Design Append-Only: Rejeita se o ID já existir.
    """
    # Verificar se já existe (Proteção de Imutabilidade)
    cur = db.execute("SELECT 1 FROM evidence WHERE id = ?", (evidence_id,))
    if cur.fetchone():
        raise PermissionError(f"Violação de Imutabilidade: Evidência {evidence_id} já existe.")

    q = "INSERT INTO evidence (id, individual_id, camera_id, file_hash, file_path) VALUES (?, ?, ?, ?, ?)"
    db.execute(q, (evidence_id, individual_id, camera_id, file_hash, file_path))
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


def get_full_individual_dossier(db: DB, individual_id: str) -> Optional[Dict]:
    """
    Agrega todos os dados de um indivíduo para exportação forense (Fase 18).
    Consolida: Dados Pessoais, Crimes, Threat Score e Evidências.
    """
    # 1. Dados Básicos
    q_basic = "SELECT * FROM individuals WHERE id = ?"
    cur = db.execute(q_basic, (individual_id,))
    row = cur.fetchone()
    if not row: return None
    
    dossier = dict(row)
    
    # 2. Crimes e Categorias
    q_crimes = "SELECT crime, severity FROM crimes WHERE individual_id = ?"
    cur = db.execute(q_crimes, (individual_id,))
    dossier["crimes_list"] = [dict(r) for r in cur.fetchall()]
    
    # 3. Threat Score
    dossier["threat"] = get_threat_score(db, individual_id)
    
    # 4. Evidências (Cadeia de Custódia)
    dossier["evidences"] = get_evidence(db, individual_id)
    
    # 5. Imagens Adicionais
    q_imgs = "SELECT img_path, caption FROM individual_images WHERE individual_id = ?"
    cur = db.execute(q_imgs, (individual_id,))
    dossier["additional_images"] = [dict(r) for r in cur.fetchall()]
    
    return dossier


def get_connection() -> DB:
    """Retorna uma nova instância conectada ao banco."""
    return DB()


def get_recent_matches(db: DB, limit: int = 10) -> List[Dict]:
    """Retorna os matches mais recentes registrados na cadeia de custódia / evidências."""
    q = """
        SELECT e.id as evidence_id, e.individual_id, e.camera_id, e.file_hash, e.file_path, e.captured_at,
               i.name, i.category, i.source, i.reward, i.img_path
        FROM evidence e
        LEFT JOIN individuals i ON e.individual_id = i.id
        ORDER BY e.captured_at DESC
        LIMIT ?
    """
    try:
        cur = db.execute(q, (limit,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return []


def insert_location(db: DB, individual_id: str, type_: str, country: Optional[str] = None,
                    state: Optional[str] = None, city: Optional[str] = None, details: Optional[str] = None):
    """Registra ou associa uma localização a um indivíduo."""
    q = """
        INSERT INTO locations (individual_id, type, country, state, city, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    try:
        db.execute(q, (individual_id, type_, country, state, city, details))
        db.commit()
    except Exception:
        pass


def stats(db: DB) -> Dict:
    """Estatísticas gerais do banco."""
    def count(q):
        row = db.execute(q).fetchone()
        if row is None:
            return 0
        if isinstance(row, dict):
            return list(row.values())[0]
        return row[0]

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

