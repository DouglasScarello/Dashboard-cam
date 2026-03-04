#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Injetar caminhos
ROOT_DIR = Path(__file__).parent.parent.resolve()
sys.path.append(str(ROOT_DIR / "intelligence"))

from intelligence_db import DB

def check():
    print("═" * 40)
    print("  RELATÓRIO DE INTELIGÊNCIA GLOBAL")
    print("═" * 40)
    
    try:
        db = DB()
        # Estatísticas por Fonte
        cur = db.execute("SELECT source, COUNT(*) as cnt FROM individuals GROUP BY source ORDER BY cnt DESC")
        rows = cur.fetchall()
        
        total = 0
        for row in rows:
            print(f"  [🛰️] {row['source']:<25} : {row['cnt']} registros")
            total += row['cnt']
            
        print("-" * 40)
        print(f"  📊 TOTAL GLOBAL NO BANCO: {total}")
        
        # Verificar Biometria
        cur = db.execute("SELECT COUNT(*) as cnt FROM individuals WHERE has_embedding = 1")
        bio_cnt = cur.fetchone()[0]
        print(f"  🧬 PERFIS COM BIOMETRIA:   {bio_cnt}")
        
        # Amostra de nomes recentes
        print("\n  [👁️] ÚLTIMOS ALVOS ADICIONADOS:")
        cur = db.execute("SELECT name, source FROM individuals ORDER BY ingested_at DESC LIMIT 5")
        for row in cur.fetchall():
            print(f"    - {row['name']} ({row['source']})")
            
        db.close()
    except Exception as e:
        print(f"[erro] Falha ao ler banco: {e}")
    print("═" * 40)

if __name__ == "__main__":
    check()
