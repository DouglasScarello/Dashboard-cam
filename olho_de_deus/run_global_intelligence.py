#!/usr/bin/env python3
"""
run_global_intelligence.py — Olho de Deus
Orquestrador Central de Ingestão e Biometria Global.
Sincroniza FBI, Interpol, BNMP e Agregadores Europeus.
"""
import sys
import os
import argparse

# Injetar o caminho da pasta intelligence para encontrar o intelligence_db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "intelligence")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "core")))

from intelligence_db import DB

# Importar Ingestores
from fbi_ingestion import FBIIngestor
from bnmp_ingestion import BNMPIngestor
from interpol_ingestion import InterpolIngestor
from opensanctions_ingestion import OpenSanctionsIngestor
from asia_ingestion import AsiaIngestor
from us_local_ingestion import USLocalIngestor

def run_pipeline(limit=50):
    print("═" * 60)
    print("  OLHO DE DEUS — Sincronização de Inteligência Global")
    print("═" * 60)
    
    db = DB()
    
    # 1. Ingestão Brasil (BNMP)
    print("\n[🛰️] Sincronizando: BNMP Brasil...")
    try:
        bnmp = BNMPIngestor(db=db)
        bnmp.fetch_data(limit=limit)
    except Exception as e:
        print(f"[!] Erro BNMP: {e}")

    # 2. Ingestão Interpol
    print("\n[🛰️] Sincronizando: Interpol Red/Yellow Notices...")
    try:
        interpol = InterpolIngestor(db=db)
        # Interpol gallery has ~16 cards per page
        max_pages = max(1, limit // 16)
        interpol.fetch_data(max_pages=max_pages)
    except Exception as e:
        print(f"[!] Erro Interpol: {e}")
    
    # 3. Ingestão FBI (Expansão)
    print("\n[🛰️] Sincronizando: FBI Wanted (Expansão)...")
    fbi = FBIIngestor(db=db)
    fbi.fetch_data(limit_pages=max(1, limit // 20))
    
    # 4. Agregação Europeia (OpenSanctions)
    print("\n[🛰️] Sincronizando: Europol/UK/Espanha/Holanda...")
    os_ingest = OpenSanctionsIngestor(db=db)
    os_ingest.fetch_data()

    # 5. Ingestão Ásia
    print("\n[🛰️] Sincronizando: Hong Kong/Índia/Coreia...")
    asia = AsiaIngestor(db=db)
    asia.fetch_hong_kong()
    asia.fetch_india()
    asia.fetch_south_korea()

    # 6. Ingestão EUA Local
    print("\n[🛰️] Sincronizando: NamUs/Phoenix Police...")
    us_local = USLocalIngestor(db=db)
    us_local.fetch_phoenix_police()
    us_local.fetch_namus()
    
    db.close()
    
    print("\n" + "═" * 60)
    print("  Ingestão Concluída. Iniciando extração biométrica...")
    print("═" * 60)
    
    # 5. Disparar extração de biometria
    os.system("python extract_embeddings.py")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olho de Deus - Global Intelligence Sync")
    parser.add_argument("--limit", type=int, default=50, help="Limite de registros por fonte")
    args = parser.parse_args()
    
    run_pipeline(limit=args.limit)
