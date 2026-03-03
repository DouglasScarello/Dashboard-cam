import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Configurações do PostgreSQL (via env ou fallback)
PG_HOST = os.getenv("DB_HOST", "localhost")
PG_NAME = os.getenv("DB_NAME", "intelligence")
PG_USER = os.getenv("DB_USER", "ghost")
PG_PASS = os.getenv("DB_PASS", "protocol")

SQLITE_DB = "intelligence/data/intelligence.db"

def migrate():
    print(f"🚀 Iniciando migração: {SQLITE_DB} -> PostgreSQL ({PG_HOST})")
    
    if not os.path.exists(SQLITE_DB):
        print(f"❌ Erro: Banco SQLite não encontrado em {SQLITE_DB}")
        return

    # Conectar ao SQLite
    sl_conn = sqlite3.connect(SQLITE_DB)
    sl_conn.row_factory = sqlite3.Row
    sl_cur = sl_conn.cursor()

    # Conectar ao PostgreSQL
    try:
        pg_conn = psycopg2.connect(
            host=PG_HOST,
            database=PG_NAME,
            user=PG_USER,
            password=PG_PASS
        )
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"❌ Erro ao conectar no PostgreSQL: {e}")
        return

    # 1. Criar Tabelas no PG (simplificado para a migração)
    # Nota: Em um sistema real, usaríamos um gerenciador de migrações como alembic
    print("[migração] Criando tabelas no PostgreSQL...")
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS individuals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            aliases TEXT,
            category TEXT NOT NULL,
            source TEXT NOT NULL,
            birth_date TEXT,
            sex TEXT,
            height_cm REAL,
            weight_kg REAL,
            eye_color TEXT,
            hair_color TEXT,
            nationalities TEXT,
            languages TEXT,
            occupation TEXT,
            description TEXT,
            reward TEXT,
            url TEXT,
            img_url TEXT,
            img_path TEXT,
            has_embedding INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS crimes (
            id SERIAL PRIMARY KEY,
            individual_id TEXT REFERENCES individuals(id),
            crime TEXT NOT NULL,
            severity TEXT
        );
        CREATE TABLE IF NOT EXISTS individual_images (
            id SERIAL PRIMARY KEY,
            individual_id TEXT REFERENCES individuals(id),
            img_url TEXT,
            img_path TEXT,
            caption TEXT,
            is_primary INTEGER DEFAULT 0
        );
    """)
    pg_conn.commit()

    # 2. Migrar Individuals
    print("[migração] Migrando 'individuals'...")
    sl_cur.execute("SELECT * FROM individuals")
    rows = [dict(r) for r in sl_cur.fetchall()]
    if rows:
        cols = rows[0].keys()
        query = f"INSERT INTO individuals ({', '.join(cols)}) VALUES %s ON CONFLICT (id) DO NOTHING"
        values = [[r[c] for c in cols] for r in rows]
        execute_values(pg_cur, query, values)
        print(f"✅ {len(rows)} indivíduos migrados.")

    # 3. Migrar Crimes
    print("[migração] Migrando 'crimes'...")
    sl_cur.execute("SELECT individual_id, crime, severity FROM crimes")
    rows = [tuple(r) for r in sl_cur.fetchall()]
    if rows:
        execute_values(pg_cur, "INSERT INTO crimes (individual_id, crime, severity) VALUES %s", rows)
        print(f"✅ {len(rows)} crimes migrados.")

    # 4. Migrar Imagens
    print("[migração] Migrando 'individual_images'...")
    sl_cur.execute("SELECT individual_id, img_url, img_path, caption, is_primary FROM individual_images")
    rows = [tuple(r) for r in sl_cur.fetchall()]
    if rows:
        execute_values(pg_cur, "INSERT INTO individual_images (individual_id, img_url, img_path, caption, is_primary) VALUES %s", rows)
        print(f"✅ {len(rows)} imagens migradas.")

    pg_conn.commit()
    sl_conn.close()
    pg_conn.close()
    print("✨ Migração concluída com sucesso!")

if __name__ == "__main__":
    migrate()
