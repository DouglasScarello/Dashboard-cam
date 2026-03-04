#!/usr/bin/env python3
"""
Digital DNA - Mass Biometric Embedding Extraction
Extrai vetores ArcFace (512-d) de todas as imagens na base de inteligência.
"""
import os
import sys
import sqlite3
import json
import numpy as np
import faiss
from tqdm import tqdm
from deepface import DeepFace
from pathlib import Path

# Configurações de Caminho (Relativos à raiz do projeto ou absolutos)
ROOT_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = ROOT_DIR / "intelligence" / "data" / "intelligence.db"
FAISS_PATH = ROOT_DIR / "intelligence" / "data" / "vector_db.faiss"
METADATA_PATH = ROOT_DIR / "intelligence" / "data" / "vector_metadata.json"

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

def extract_embeddings():
    if not DB_PATH.exists():
        print(f"[erro] Banco de dados não encontrado em {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Buscar indivíduos sem biometria processada
    cursor.execute("SELECT id, name, img_path FROM individuals WHERE has_embedding = 0 AND img_path IS NOT NULL")
    targets = cursor.fetchall()
    
    if not targets:
        print("[info] Todos os perfis já possuem biometria processada.")
        return

    print(f"[🛰️] Iniciando extração de DNA Digital para {len(targets)} perfis...")

    # Preparar FAISS e metadados
    embeddings_list = []
    metadata_list = []
    
    # Se já existir FAISS, carregar para anexar (ou podemos reconstruir do zero para garantir integridade)
    # Para simplificar e evitar duplicatas em lote, vamos ler o que já existe no SQLite first
    cursor.execute("SELECT individual_id, embedding_blob FROM face_embeddings")
    existing = cursor.fetchall()
    for row in existing:
        # Converter blob de volta para array
        import struct
        emb = np.array(struct.unpack(f"{len(row['embedding_blob'])//4}f", row['embedding_blob'])).astype('float32')
        embeddings_list.append(emb)
        
        # Buscar nome para o metadata
        c2 = conn.cursor()
        c2.execute("SELECT name FROM individuals WHERE id = ?", (row['individual_id'],))
        p = c2.fetchone()
        metadata_list.append({"uid": row['individual_id'], "title": p['name'] if p else "Desconhecido"})

    processed_count = 0
    errors_count = 0

    for target in tqdm(targets, desc="Processando Biometria"):
        uid = target['id']
        name = target['name']
        img_rel_path = target['img_path']
        
        # O img_path no banco costuma ser relativo à raiz do projeto ou absoluto
        # Testar as duas possibilidades
        full_img_path = ROOT_DIR / img_rel_path
        if not full_img_path.exists():
            # Tentar relativo a intelligence/data
            full_img_path = ROOT_DIR / "intelligence" / "data" / img_rel_path
            if not full_img_path.exists():
                # Tentar se o path já for absoluto (caso comece com /home)
                full_img_path = Path(img_rel_path)
                if not full_img_path.exists():
                    # print(f"[warning] Imagem não encontrada para {name}: {img_rel_path}")
                    errors_count += 1
                    continue

        try:
            # Extração ArcFace
            objs = DeepFace.represent(
                img_path=str(full_img_path),
                model_name="ArcFace",
                enforce_detection=True, # Garantir que há um rosto
                detector_backend="opencv" # Mais rápido para CPU
            )
            
            if not objs:
                errors_count += 1
                continue

            embedding = objs[0]["embedding"]
            emb_array = np.array(embedding).astype('float32')

            # Salvar no Banco (SQLite)
            import struct
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            cursor.execute("INSERT OR REPLACE INTO face_embeddings (individual_id, embedding_blob) VALUES (?, ?)", (uid, blob))
            cursor.execute("UPDATE individuals SET has_embedding = 1 WHERE id = ?", (uid,))
            
            # Adicionar às listas do FAISS
            embeddings_list.append(emb_array)
            metadata_list.append({"uid": uid, "title": name})
            
            processed_count += 1
            
            # Commit a cada 50 para segurança
            if processed_count % 50 == 0:
                conn.commit()

        except Exception as e:
            # print(f"[erro] Falha ao processar {name}: {e}")
            errors_count += 1
            continue

    conn.commit()
    conn.close()

    # --- ATUALIZAR FAISS ---
    if embeddings_list:
        print(f"\n[📦] Indexando {len(embeddings_list)} vetores no FAISS...")
        dim = len(embeddings_list[0])
        index = faiss.IndexFlatL2(dim)
        index.add(np.array(embeddings_list).astype('float32'))
        
        faiss.write_index(index, str(FAISS_PATH))
        with open(METADATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(metadata_list, f, ensure_ascii=False, indent=2)

    print(f"\n[✅] Finalizado!")
    print(f"    - Processados: {processed_count}")
    print(f"    - Falhas: {errors_count}")
    print(f"    - Índice FAISS atualizado em: {FAISS_PATH}")

if __name__ == "__main__":
    extract_embeddings()
