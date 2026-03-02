#!/usr/bin/env python3
"""
Intelligence Database — Olho de Deus
Banco SQLite local para catalogação completa de indivíduos procurados/desaparecidos.

Tabelas:
  individuals   — dados completos do indivíduo
  crimes        — crimes associados (many-to-one)
  locations     — locais associados (last seen, operação)
  face_embeddings — embeddings biométricos ArcFace (blob binário)
"""
import sqlite3
import json
import struct
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime

DB_FILE = "data/intelligence.db"


# ─────────────────────────────────────────────────────────────────
# SCHEMA SQL
# ─────────────────────────────────────────────────────────────────
SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS individuals (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    aliases         TEXT,               -- JSON array de nomes alternativos
    category        TEXT NOT NULL,      -- 'wanted' | 'missing' | 'sanction'
    source          TEXT NOT NULL,      -- 'FBI' | 'Interpol_RED' | 'OpenSanctions/...'
    birth_date      TEXT,
    sex             TEXT,
    height_cm       REAL,
    weight_kg       REAL,
    eye_color       TEXT,
    hair_color      TEXT,
    nationalities   TEXT,               -- JSON array ISO-2
    languages       TEXT,               -- JSON array
    occupation      TEXT,
    description     TEXT,               -- descrição completa original
    reward          TEXT,               -- valor de recompensa em texto
    url             TEXT,               -- link para perfil original
    img_url         TEXT,               -- URL da imagem na fonte
    img_path        TEXT,               -- caminho local da imagem baixada
    has_embedding   INTEGER DEFAULT 0,  -- 1 se embedding biométrico disponível
    first_seen      TEXT,               -- data de entrada no sistema fonte
    last_seen       TEXT,
    ingested_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crimes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    individual_id   TEXT NOT NULL,
    crime           TEXT NOT NULL,
    severity        TEXT,               -- 'high' | 'medium' | 'low'
    FOREIGN KEY (individual_id) REFERENCES individuals(id)
);

CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    individual_id   TEXT NOT NULL,
    type            TEXT NOT NULL,      -- 'last_seen' | 'operation' | 'nationality'
    country         TEXT,
    state           TEXT,
    city            TEXT,
    details         TEXT,
    FOREIGN KEY (individual_id) REFERENCES individuals(id)
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    individual_id   TEXT PRIMARY KEY,
    embedding_blob  BLOB NOT NULL,       -- 512 floats ArcFace (float32 LE)
    model           TEXT DEFAULT 'ArcFace',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (individual_id) REFERENCES individuals(id)
);

-- Índices para busca rápida
CREATE INDEX IF NOT EXISTS idx_name       ON individuals(name);
CREATE INDEX IF NOT EXISTS idx_category   ON individuals(category);
CREATE INDEX IF NOT EXISTS idx_source     ON individuals(source);
CREATE INDEX IF NOT EXISTS idx_embedding  ON individuals(has_embedding);
CREATE INDEX IF NOT EXISTS idx_crimes_id  ON crimes(individual_id);
CREATE INDEX IF NOT EXISTS idx_locs_id    ON locations(individual_id);
"""

# ─────────────────────────────────────────────────────────────────
# CONEXÃO
# ─────────────────────────────────────────────────────────────────
def get_connection(db_file: str = DB_FILE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_file: str = DB_FILE):
    """Cria o banco e aplica o schema."""
    conn = get_connection(db_file)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[db] Banco inicializado: {db_file}")


# ─────────────────────────────────────────────────────────────────
# INSERT / UPSERT
# ─────────────────────────────────────────────────────────────────
def upsert_individual(conn: sqlite3.Connection, data: Dict):
    """
    Insere ou atualiza um indivíduo no banco.
    
    Campos obrigatórios: id, name, category, source
    """
    conn.execute("""
        INSERT INTO individuals (
            id, name, aliases, category, source, birth_date, sex,
            height_cm, weight_kg, eye_color, hair_color,
            nationalities, languages, occupation, description,
            reward, url, img_url, img_path, has_embedding,
            first_seen, last_seen
        ) VALUES (
            :id, :name, :aliases, :category, :source, :birth_date, :sex,
            :height_cm, :weight_kg, :eye_color, :hair_color,
            :nationalities, :languages, :occupation, :description,
            :reward, :url, :img_url, :img_path, :has_embedding,
            :first_seen, :last_seen
        )
        ON CONFLICT(id) DO UPDATE SET
            name          = excluded.name,
            aliases       = excluded.aliases,
            birth_date    = excluded.birth_date,
            description   = excluded.description,
            img_url       = COALESCE(excluded.img_url, individuals.img_url),
            img_path      = COALESCE(excluded.img_path, individuals.img_path),
            has_embedding = MAX(individuals.has_embedding, excluded.has_embedding),
            last_seen     = excluded.last_seen
    """, {
        "id":           data.get("id") or data.get("uid") or "",
        "name":         data.get("name") or data.get("title") or "N/A",
        "aliases":      json.dumps(data.get("aliases", []), ensure_ascii=False),
        "category":     data.get("category", "wanted"),
        "source":       data.get("source", "unknown"),
        "birth_date":   data.get("birth_date") or data.get("dates_of_birth_used"),
        "sex":          data.get("sex"),
        "height_cm":    data.get("height_cm") or data.get("height"),
        "weight_kg":    data.get("weight_kg") or data.get("weight"),
        "eye_color":    data.get("eye_color") or data.get("eyes"),
        "hair_color":   data.get("hair_color") or data.get("hair"),
        "nationalities": json.dumps(data.get("nationalities", []), ensure_ascii=False),
        "languages":    json.dumps(data.get("languages", []), ensure_ascii=False),
        "occupation":   data.get("occupation"),
        "description":  data.get("description") or data.get("crime") or "",
        "reward":       data.get("reward") or data.get("reward_text"),
        "url":          data.get("url"),
        "img_url":      data.get("img_url"),
        "img_path":     data.get("img_path"),
        "has_embedding": 1 if data.get("has_embedding") else 0,
        "first_seen":   data.get("first_seen"),
        "last_seen":    data.get("last_seen"),
    })


def insert_crimes(conn: sqlite3.Connection, individual_id: str, crimes: List[str]):
    """Insere crimes associados a um indivíduo (ignora duplicatas)."""
    for crime in crimes:
        if crime.strip():
            conn.execute("""
                INSERT OR IGNORE INTO crimes (individual_id, crime)
                VALUES (?, ?)
            """, (individual_id, crime.strip()[:1000]))


def insert_location(conn: sqlite3.Connection, individual_id: str,
                    loc_type: str, country: str = None, 
                    state: str = None, city: str = None, details: str = None):
    conn.execute("""
        INSERT INTO locations (individual_id, type, country, state, city, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (individual_id, loc_type, country, state, city, details))


def save_embedding(conn: sqlite3.Connection, individual_id: str,
                   embedding: List[float]):
    """Salva embedding ArcFace como blob binário."""
    blob = struct.pack(f"{len(embedding)}f", *embedding)
    conn.execute("""
        INSERT INTO face_embeddings (individual_id, embedding_blob)
        VALUES (?, ?)
        ON CONFLICT(individual_id) DO UPDATE SET
            embedding_blob = excluded.embedding_blob,
            created_at = datetime('now')
    """, (individual_id, blob))
    conn.execute(
        "UPDATE individuals SET has_embedding=1 WHERE id=?", (individual_id,)
    )


def load_embedding(conn: sqlite3.Connection, individual_id: str) -> Optional[List[float]]:
    """Carrega embedding de uma pessoa específica."""
    row = conn.execute(
        "SELECT embedding_blob FROM face_embeddings WHERE individual_id=?",
        (individual_id,)
    ).fetchone()
    if row:
        n = len(row["embedding_blob"]) // 4
        return list(struct.unpack(f"{n}f", row["embedding_blob"]))
    return None


def load_all_embeddings(conn: sqlite3.Connection) -> Tuple[List[str], List[List[float]]]:
    """Carrega todos os embeddings. Retorna (ids, embeddings)."""
    rows = conn.execute(
        "SELECT individual_id, embedding_blob FROM face_embeddings"
    ).fetchall()
    ids, embeddings = [], []
    for row in rows:
        n = len(row["embedding_blob"]) // 4
        ids.append(row["individual_id"])
        embeddings.append(list(struct.unpack(f"{n}f", row["embedding_blob"])))
    return ids, embeddings


# ─────────────────────────────────────────────────────────────────
# BUSCA E CONSULTA
# ─────────────────────────────────────────────────────────────────
def search(conn: sqlite3.Connection,
           name: str = None,
           category: str = None,
           source: str = None,
           crime: str = None,
           country: str = None,
           has_embedding: bool = None,
           limit: int = 50) -> List[Dict]:
    """
    Busca de texto completo e filtros.
    
    Args:
        name:          Busca parcial no nome (LIKE %name%)
        category:      'wanted' | 'missing' | 'sanction'
        source:        Filtro por fonte (ex: 'FBI', 'Interpol')
        crime:         Busca parcial em crimes associados
        country:       Filtro por país (ISO-2 ou nome)
        has_embedding: True = só com biometria
        limit:         Máximo de resultados
    """
    where, params = ["1=1"], []

    if name:
        where.append("(i.name LIKE ? OR i.aliases LIKE ? OR i.description LIKE ?)")
        params += [f"%{name}%", f"%{name}%", f"%{name}%"]

    if category:
        where.append("i.category = ?")
        params.append(category)

    if source:
        where.append("i.source LIKE ?")
        params.append(f"%{source}%")

    if has_embedding is not None:
        where.append("i.has_embedding = ?")
        params.append(1 if has_embedding else 0)

    # Subquery para crimes
    crime_join = ""
    if crime:
        crime_join = "LEFT JOIN crimes c ON c.individual_id = i.id"
        where.append("c.crime LIKE ?")
        params.append(f"%{crime}%")

    # Subquery para países
    loc_join = ""
    if country:
        loc_join = "LEFT JOIN locations l ON l.individual_id = i.id"
        where.append("(l.country LIKE ? OR i.nationalities LIKE ?)")
        params += [f"%{country}%", f"%{country}%"]

    sql = f"""
        SELECT DISTINCT
            i.id, i.name, i.aliases, i.category, i.source,
            i.birth_date, i.nationalities, i.description,
            i.reward, i.url, i.img_path, i.has_embedding,
            i.ingested_at
        FROM individuals i
        {crime_join}
        {loc_join}
        WHERE {" AND ".join(where)}
        ORDER BY i.has_embedding DESC, i.name ASC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_individual(conn: sqlite3.Connection, individual_id: str) -> Optional[Dict]:
    """Retorna perfil completo com crimes e locais."""
    row = conn.execute(
        "SELECT * FROM individuals WHERE id=?", (individual_id,)
    ).fetchone()
    if not row:
        return None
    data = dict(row)

    # Crimes
    crimes = conn.execute(
        "SELECT crime, severity FROM crimes WHERE individual_id=?", (individual_id,)
    ).fetchall()
    data["crimes"] = [c["crime"] for c in crimes]

    # Locais
    locs = conn.execute(
        "SELECT type, country, state, city, details FROM locations WHERE individual_id=?",
        (individual_id,)
    ).fetchall()
    data["locations"] = [dict(l) for l in locs]

    return data


def stats(conn: sqlite3.Connection) -> Dict:
    """Estatísticas gerais do banco."""
    total       = conn.execute("SELECT COUNT(*) FROM individuals").fetchone()[0]
    wanted      = conn.execute("SELECT COUNT(*) FROM individuals WHERE category='wanted'").fetchone()[0]
    missing     = conn.execute("SELECT COUNT(*) FROM individuals WHERE category='missing'").fetchone()[0]
    with_bio    = conn.execute("SELECT COUNT(*) FROM individuals WHERE has_embedding=1").fetchone()[0]
    by_source   = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM individuals GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    return {
        "total":      total,
        "wanted":     wanted,
        "missing":    missing,
        "with_biometrics": with_bio,
        "by_source":  [dict(r) for r in by_source],
    }


def export_csv(conn: sqlite3.Connection, output_path: str):
    """Exporta o banco completo para CSV."""
    import csv
    rows = conn.execute("""
        SELECT i.id, i.name, i.category, i.source, i.birth_date,
               i.nationalities, i.description, i.reward, i.url,
               i.has_embedding, i.ingested_at,
               GROUP_CONCAT(DISTINCT c.crime, ' | ') as crimes,
               GROUP_CONCAT(DISTINCT l.country, ', ') as countries
        FROM individuals i
        LEFT JOIN crimes c ON c.individual_id = i.id
        LEFT JOIN locations l ON l.individual_id = i.id
        GROUP BY i.id
        ORDER BY i.category, i.name
    """).fetchall()
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])
    print(f"[db] Exportado: {output_path} ({len(rows)} registros)")


# ─────────────────────────────────────────────────────────────────
# CLI INTERATIVO DE BUSCA
# ─────────────────────────────────────────────────────────────────
def interactive_search():
    """Terminal de busca interativo."""
    conn = get_connection()
    s = stats(conn)

    print("\n" + "═" * 60)
    print("  OLHO DE DEUS — Intelligence Database")
    print("═" * 60)
    print(f"  Total: {s['total']} | Procurados: {s['wanted']} | Desaparecidos: {s['missing']}")
    print(f"  Com biometria: {s['with_biometrics']}")
    print("\n  Fontes:")
    for src in s["by_source"][:8]:
        print(f"    {src['source']:<40} {src['cnt']:>6}")
    print("═" * 60)

    while True:
        print("\nComandos: [b]uscar | [d]etalhe <id> | [e]xportar | [s]tats | [q]sair")
        cmd = input("> ").strip().lower()

        if cmd.startswith("q"):
            break

        elif cmd.startswith("s"):
            s2 = stats(conn)
            print(f"Total: {s2['total']} | Procurados: {s2['wanted']} | Desapar: {s2['missing']}")

        elif cmd.startswith("e"):
            path = "data/intelligence_export.csv"
            export_csv(conn, path)

        elif cmd.startswith("d "):
            uid = cmd[2:].strip()
            person = get_individual(conn, uid)
            if person:
                print(f"\n{'─'*50}")
                print(f"  Nome:       {person['name']}")
                print(f"  Categoria:  {person['category']}")
                print(f"  Fonte:      {person['source']}")
                print(f"  Nascimento: {person['birth_date'] or 'N/A'}")
                print(f"  Países:     {person['nationalities']}")
                print(f"  Recompensa: {person['reward'] or 'N/A'}")
                print(f"  Crimes:     {' | '.join(person['crimes']) or 'N/A'}")
                print(f"  Descrição:  {(person['description'] or '')[:200]}")
                print(f"  Biometria:  {'✓ SIM' if person['has_embedding'] else '✗ NÃO'}")
                print(f"  URL:        {person['url'] or 'N/A'}")
                print(f"{'─'*50}")
            else:
                print(f"  ID não encontrado: {uid}")

        elif cmd.startswith("b"):
            print("  Nome (enter=todos): ", end=""); nome    = input().strip()
            print("  Categoria [wanted/missing/]: ", end=""); cat  = input().strip() or None
            print("  Crime (enter=todos): ", end=""); crime  = input().strip() or None
            print("  País (ex: br, ru): ", end=""); pais    = input().strip() or None
            print("  Só com biometria? [s/N]: ", end=""); bio = input().strip().lower() == "s"

            results = search(conn,
                name=nome or None, category=cat,
                crime=crime, country=pais,
                has_embedding=True if bio else None,
                limit=20)

            print(f"\n  {len(results)} resultado(s):\n")
            for r in results:
                bio_mark = "🟢" if r["has_embedding"] else "⚪"
                cat_mark = "🔴" if r["category"] == "wanted" else "🟡"
                print(f"  {cat_mark}{bio_mark} [{r['id'][:20]:<22}] {r['name']:<35} {r['source']}")
        else:
            print("  Comando inválido.")

    conn.close()


# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        interactive_search()
    else:
        init_db()
        print("Banco criado. Use 'poetry run python intelligence_db.py search' para buscar.")
