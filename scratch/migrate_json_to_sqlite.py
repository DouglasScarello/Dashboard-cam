import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "database" / "live_cameras.db"
JSON_FILE = ROOT / "database" / "live_cameras.json"
SCHEMA_FILE = ROOT / "database" / "schema.sql"

def migrate():
    print(f"Lendo {JSON_FILE}...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        cameras = json.load(f)
        
    print(f"Criando banco SQLite em {DB_FILE}...")
    conn = sqlite3.connect(DB_FILE)

    # DROP explícito antes do schema: `CREATE TABLE IF NOT EXISTS` não
    # altera uma tabela já existente — se o schema.sql ganhar uma coluna
    # nova (aconteceu aqui: stream_format), a tabela antiga no disco fica
    # desatualizada e todo INSERT subsequente quebra. Como o banco é
    # sempre reconstruído do zero a partir do JSON mesmo, recriar do zero
    # é seguro e não perde nada.
    with conn:
        conn.execute("DROP TABLE IF EXISTS cameras")

    with open(SCHEMA_FILE, "r") as f:
        conn.executescript(f.read())
        
    print(f"Inserindo {len(cameras)} registros...")

    # Prepara os dados
    def to_bool(val):
        if val is None: return False
        return bool(val)

    # Achado real (2026-08-31): esse script só fazia INSERT OR REPLACE,
    # nunca removia do banco o que sumiu do JSON. Resultado: depois de
    # limpar câmeras mortas/zumbi/duplicadas no live_cameras.json (curadoria
    # de várias rodadas), o banco continuava servindo 9374 câmeras via API
    # enquanto o JSON já tinha só 4002 — a limpeza nunca chegava no usuário
    # final. Agora apaga tudo antes de reinserir, pra live_cameras.json
    # continuar sendo a fonte de verdade única e o banco sempre espelhar
    # exatamente o que está nele, nunca acumular lixo de rodadas antigas.
    with conn:
        conn.execute("DELETE FROM cameras")

    count = 0
    with conn:
        for c in cameras:
            conn.execute('''
                INSERT OR REPLACE INTO cameras
                (id, nome, local, endereco, cidade, uf, tipo_area, setor, pais, thumbnail_url, url, video_id, lat, long, confirmed_dead, live_confirmed, live_status, stream_format, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                c.get("id"),
                c.get("nome"),
                c.get("local"),
                c.get("endereco"),
                c.get("cidade"),
                c.get("uf"),
                c.get("tipo_area"),
                c.get("setor"),
                c.get("pais"),
                c.get("thumbnail_url"),
                c.get("url"),
                c.get("video_id"),
                c.get("lat"),
                c.get("long"),
                to_bool(c.get("confirmed_dead")),
                to_bool(c.get("live_confirmed")),
                c.get("live_status"),
                c.get("stream_format"),
                c.get("source")
            ))
            count += 1
            
    print(f"Migração completa! {count} câmeras gravadas no SQLite.")
    conn.close()

if __name__ == "__main__":
    migrate()
