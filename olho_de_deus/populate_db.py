#!/usr/bin/env python3
"""
populate_db.py — Olho de Deus
Carrega todas as fontes de inteligência no banco SQLite local.

Fontes:
  1. FBI Wanted API        → dados ricos (físico, crimes, recompensa, fotos)
  2. OpenSanctions CSV     → Interpol Red (6437), Europol, NCA UK (sem foto)
  3. Banco FAISS existente → reutiliza embeddings já calculados em fbi_ingestion.py
  
Uso:
  poetry run python populate_db.py                 # tudo
  poetry run python populate_db.py --fbi-only       # só FBI
  poetry run python populate_db.py --os-only        # só OpenSanctions
  poetry run python populate_db.py --load-faiss     # carrega embeddings existentes
"""
import os
import io
import csv
import json
import time
import struct
import requests
import faiss
import numpy as np
import logging
import sys
from tqdm import tqdm
from typing import Optional
from datetime import datetime

# Injetar o caminho da pasta intelligence para encontrar o intelligence_db
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "intelligence")))

from intelligence_db import (
    init_db, get_connection,
    upsert_individual, insert_crimes, insert_location,
    save_embedding, stats
)

# ─────────────────────────────────────────────────────────────────
# FONTE 1: FBI WANTED API  (dados ricos com campo a campo)
# ─────────────────────────────────────────────────────────────────
def load_fbi(limit_pages: Optional[int] = None):
    """Carrega FBI Wanted API completo no banco SQLite."""
    conn = get_connection()
    base = "https://api.fbi.gov/wanted/v1/list"

    r = requests.get(base, params={"page": 1}, timeout=10)
    total = r.json().get("total", 0)
    pages = (total // 20) + 1
    if limit_pages:
        pages = min(pages, limit_pages)

    print(f"\n[FBI] Carregando {total} registros em {pages} páginas...")
    loaded = 0

    for page in range(1, pages + 1):
        data = requests.get(base, params={"page": page}, timeout=15).json()
        for item in data.get("items", []):
            uid   = item.get("uid", "")
            title = item.get("title", "N/A")

            # Determinar categoria
            subjects = item.get("subjects", [])
            cat = "missing" if any("missing" in s.lower() for s in subjects) else "wanted"

            # Imagem
            imgs = item.get("images", [])
            img_url = None
            if imgs:
                img_url = imgs[0].get("large") or imgs[0].get("thumb") or imgs[0].get("original")

            # Dados físicos
            details = item.get("details", "") or ""
            desc    = item.get("description", "") or item.get("caution", "") or ""

            # Verificar se imagem já existe localmente
            img_path_local = f"data/fbi_faces/{uid}.jpg"
            if not os.path.exists(img_path_local):
                img_path_local = None

            upsert_individual(conn, {
                "id":           uid,
                "name":         title,
                "aliases":      item.get("aliases", []) or [],
                "category":     cat,
                "source":       "FBI",
                "birth_date":   (item.get("dates_of_birth_used") or [""])[0] if item.get("dates_of_birth_used") else None,
                "sex":          item.get("sex"),
                "height_cm":    _parse_num(item.get("height")),
                "weight_kg":    _parse_num(item.get("weight")),
                "eye_color":    item.get("eyes"),
                "hair_color":   item.get("hair"),
                "nationalities": item.get("nationality", []) if isinstance(item.get("nationality"), list) else [item.get("nationality")] if item.get("nationality") else [],
                "occupation":   item.get("occupations", [None])[0] if item.get("occupations") else None,
                "description":  (desc + "\n" + details).strip()[:2000],
                "reward":       item.get("reward_text") or str(item.get("reward", "")),
                "url":          item.get("url"),
                "img_url":      img_url,
                "img_path":     img_path_local,
                "first_seen":   item.get("publication"),
                "last_seen":    item.get("modified"),
            })

            # Crimes → tabela crimes
            crime_list = []
            for charge in (item.get("charges") or []):
                crime_list.append(charge)
            for subj in (item.get("subjects") or []):
                crime_list.append(subj)
            if desc:
                crime_list.append(desc[:300])
            insert_crimes(conn, uid, crime_list)

            # Locais → tabela locations
            for fo in (item.get("field_offices") or []):
                insert_location(conn, uid, "operation", country="US", state=fo)

            loaded += 1

        conn.commit()
        time.sleep(0.25)

    conn.close()
    print(f"[FBI] ✓ {loaded} registros carregados")


def _parse_num(val) -> Optional[float]:
    """Converte altura/peso para número."""
    if val is None:
        return None
    try:
        return float(str(val).replace("\"", "").replace("'", "").split()[0])
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# FONTE 2: OPENSANCTIONS BULK CSV
# ─────────────────────────────────────────────────────────────────
DATASETS = {
    "interpol_red_notices": ("Interpol Red Notices",  "wanted"),
    "eu_most_wanted":       ("Europol EU Most Wanted", "wanted"),
    "gb_nca_most_wanted":   ("UK NCA Most Wanted",     "wanted"),
    "interpol_yellow_notices": ("Interpol Yellow Notices", "missing"),
}

def load_opensanctions():
    """Carrega todos os datasets OpenSanctions CSV."""
    conn = get_connection()

    for ds_key, (label, category) in DATASETS.items():
        url = f"https://data.opensanctions.org/datasets/latest/{ds_key}/targets.simple.csv"
        print(f"\n[OpenSanctions] {label}...")
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200:
                print(f"  [skip] HTTP {resp.status_code}")
                continue

            content = resp.content.decode("utf-8")
            reader  = csv.DictReader(io.StringIO(content))
            rows    = list(reader)
            loaded  = 0

            for row in tqdm(rows, desc=f"  {label}"):
                name = row.get("name", "").strip()
                if not name:
                    continue

                uid = f"os_{ds_key}_{row.get('id','')}"

                # Países
                countries = [c.strip() for c in (row.get("countries") or "").split(";") if c.strip()]

                # Crimes/sanctions
                sanctions = row.get("sanctions", "").strip()

                upsert_individual(conn, {
                    "id":           uid,
                    "name":         name,
                    "aliases":      [a.strip() for a in (row.get("aliases","")).split(";") if a.strip()],
                    "category":     category,
                    "source":       f"OpenSanctions/{label}",
                    "birth_date":   row.get("birth_date"),
                    "nationalities": countries,
                    "description":  sanctions[:2000] if sanctions else "",
                    "url":          "",
                    "first_seen":   row.get("first_seen"),
                    "last_seen":    row.get("last_seen"),
                })

                if sanctions:
                    insert_crimes(conn, uid, [sanctions[:500]])

                for country in countries[:3]:
                    insert_location(conn, uid, "nationality", country=country)

                loaded += 1

            conn.commit()
            print(f"  ✓ {loaded} registros de {label}")

        except Exception as e:
            print(f"  [erro] {e}")

    conn.close()


# ─────────────────────────────────────────────────────────────────
# FONTE 3: EMBEDDINGS DO FAISS EXISTENTE
# ─────────────────────────────────────────────────────────────────
def load_faiss_embeddings(faiss_path: str = "data/vector_db.faiss",
                          meta_path:  str = "data/vector_metadata.json"):
    """Importa embeddings já calculados do banco FAISS para o SQLite."""
    if not os.path.exists(faiss_path) or not os.path.exists(meta_path):
        print(f"[faiss] Arquivos não encontrados: {faiss_path}")
        return

    index = faiss.read_index(faiss_path)
    with open(meta_path, "r") as f:
        metadata = json.load(f)

    print(f"\n[FAISS] Importando {len(metadata)} embeddings...")
    conn = get_connection()

    for i, meta in enumerate(tqdm(metadata, desc="[FAISS] Embeddings")):
        uid = meta.get("uid", "")
        if not uid:
            continue
        emb_np = index.reconstruct(i)
        emb    = emb_np.tolist()
        save_embedding(conn, uid, emb)

    conn.commit()
    conn.close()
    print(f"[FAISS] ✓ {len(metadata)} embeddings importados")


# ─────────────────────────────────────────────────────────────────
# RELATÓRIO FINAL
# ─────────────────────────────────────────────────────────────────
def print_stats():
    conn = get_connection()
    s = stats(conn)
    conn.close()

    print("\n" + "═" * 60)
    print("  BANCO DE INTELIGÊNCIA — STATUS FINAL")
    print("═" * 60)
    print(f"  🔴 Procurados:         {s['wanted']:>7}")
    print(f"  🟡 Desaparecidos:      {s['missing']:>7}")
    print(f"  📊 Total de registros: {s['total']:>7}")
    print(f"  🧬 Com biometria:      {s['with_biometrics']:>7}")
    print("\n  Por fonte:")
    for src in s["by_source"]:
        print(f"    {src['source']:<44} {src['cnt']:>6}")
    print("═" * 60)
    print("\n  Para buscar:")
    print("  poetry run python intelligence_db.py search")


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Olho de Deus — Popular banco de inteligência")
    parser.add_argument("--fbi-only",   action="store_true")
    parser.add_argument("--os-only",    action="store_true")
    parser.add_argument("--load-faiss", action="store_true", help="Importar embeddings FAISS existentes")
    parser.add_argument("--fbi-pages",  type=int, default=None)
    args = parser.parse_args()

    init_db()

    if args.load_faiss:
        load_faiss_embeddings()
    elif args.fbi_only:
        load_fbi(limit_pages=args.fbi_pages)
    elif args.os_only:
        load_opensanctions()
    else:
        # Carregar tudo
        load_fbi(limit_pages=args.fbi_pages)
        load_opensanctions()
        load_faiss_embeddings()

    print_stats()
