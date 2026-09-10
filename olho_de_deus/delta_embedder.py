#!/usr/bin/env python3
"""
delta_embedder.py — Olho de Deus  [Fase 14: Delta Embedding Updater]

Motor de extração biométrica incremental (delta).
Processa APENAS os indivíduos que:
  1. Nunca tiveram embedding gerado (has_embedding = 0)
  2. Foram atualizados (last_seen) depois do último embedding calculado

Usa FAISS IndexIDMap para upsert de vetores por ID numérico derivado do UID.
Isso permite sobrescrever o vetor antigo de um alvo já existente sem
reconstruir o índice completo.

Uso direto:
    poetry run python delta_embedder.py
    poetry run python delta_embedder.py --limit 500 --batch-size 32 --force-rebuild
"""
import os
import sys
import json
import struct
import hashlib
import logging
import argparse
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import numpy as np
import faiss
from tqdm import tqdm

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
INTEL_DB = ROOT / "intelligence" / "data" / "intelligence.db"
FAISS_PATH    = ROOT / "intelligence" / "data" / "vector_db.faiss"
FAISS_ID_PATH = ROOT / "intelligence" / "data" / "vector_ids.npy"   # mapa int64 → uid string
META_PATH     = ROOT / "intelligence" / "data" / "vector_metadata.json"

sys.path.insert(0, str(ROOT / "intelligence"))
from intelligence_db import (
    DB, get_embedding_delta, mark_embedded,
    get_all_embeddings_for_index, save_embedding,
)

log = logging.getLogger("delta_embedder")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [delta] %(message)s", datefmt="%H:%M:%S")


# ─── ID mapping: UID string → int64 estável ──────────────────────────────────

def uid_to_int64(uid: str) -> int:
    """
    Converte UID string para int64 estável via SHA-256 truncado.
    Colisões são astronomicamente improváveis em 16k registros.
    """
    h = hashlib.sha256(uid.encode()).digest()
    return int.from_bytes(h[:8], byteorder="big", signed=True)


# ─── Carregamento / Inicialização do índice ──────────────────────────────────

class FaissIDMap:
    """
    Wrapper sobre faiss.IndexIDMap2 para upsert de embeddings por UID.
    IndexIDMap2 (não IndexIDMap) suporta reconstruct() por ID — necessário
    para verificar se um vetor precisa ser removido antes de sobrescrever.
    """
    DIM = 512  # ArcFace

    def __init__(self):
        self.index: Optional[faiss.IndexIDMap] = None
        self._id_to_uid: Dict[int, str] = {}   # int64 → uid string
        self._id_to_meta: Dict[int, Dict] = {}  # int64 → {"uid", "title"} (persistido em vector_metadata.json)

    def load_or_create(self, db: DB) -> int:
        """
        Carrega o índice existente do disco ou cria um novo a partir do banco.
        Retorna o número de vetores já indexados.
        """
        if FAISS_PATH.exists() and FAISS_ID_PATH.exists():
            log.info(f"Carregando índice FAISS existente: {FAISS_PATH}")
            base = faiss.read_index(str(FAISS_PATH))
            self.index = base  # já é um IndexIDMap se salvo corretamente
            if FAISS_ID_PATH.exists():
                id_map_raw = np.load(str(FAISS_ID_PATH), allow_pickle=True).item()
                self._id_to_uid = id_map_raw
            if META_PATH.exists():
                with open(META_PATH, "r", encoding="utf-8") as f:
                    self._id_to_meta = {int(k): v for k, v in json.load(f).items()}
            else:
                # Índice existente de uma versão anterior sem metadata — reconstrói a partir do uid.
                self._id_to_meta = {int_id: {"uid": uid, "title": uid} for int_id, uid in self._id_to_uid.items()}
            return self.index.ntotal

        # Primeira vez — constrói o IndexIDMap do zero a partir do banco
        log.info("Índice FAISS não encontrado. Construindo do banco de dados...")
        flat = faiss.IndexFlatL2(self.DIM)
        self.index = faiss.IndexIDMap(flat)
        self._id_to_uid = {}
        self._id_to_meta = {}

        rows = get_all_embeddings_for_index(db)
        if not rows:
            log.info("Nenhum embedding existente no banco — índice vazio criado.")
            return 0

        vecs = []
        ids  = []
        for row in rows:
            uid = row["individual_id"]
            blob = row["embedding_blob"]
            if not blob:
                continue
            n = len(blob) // 4
            if n != self.DIM:
                continue
            emb = np.array(struct.unpack(f"{n}f", blob), dtype="float32")
            int_id = uid_to_int64(uid)
            vecs.append(emb)
            ids.append(int_id)
            self._id_to_uid[int_id] = uid
            self._id_to_meta[int_id] = {"uid": uid, "title": row.get("name") or uid}

        if vecs:
            vecs_np = np.array(vecs, dtype="float32")
            faiss.normalize_L2(vecs_np)  # ver nota em upsert() sobre por que isso é obrigatório
            self.index.add_with_ids(
                vecs_np,
                np.array(ids, dtype="int64"),
            )
        log.info(f"Índice construído com {len(vecs)} vetores existentes.")
        return len(vecs)

    def upsert(self, uid: str, embedding: np.ndarray, name: Optional[str] = None) -> None:
        """
        Insere ou atualiza o vetor de um indivíduo no índice.
        Se o ID já existir, remove o vetor antigo antes de inserir o novo.

        IMPORTANTE: o embedding é L2-normalizado antes de entrar no índice.
        O ArcFace do DeepFace NÃO devolve vetores unitários por padrão — em L2
        cru, a distância entre a MESMA pessoa fica na casa de 2-3 (medido:
        mesma foto exata deu distância 2.54), muito acima de qualquer
        match_threshold configurado (0.4-0.7) e da calibração de probabilidade
        em biometric_processor.py (exp(-d*1.2), pensada pra distância
        normalizada 0-2). Sem essa normalização, NENHUM match real dispara,
        mesmo com o rosto certo no índice. biometric_processor._identify()
        também precisa normalizar o embedding de busca do mesmo jeito.
        """
        int_id = uid_to_int64(uid)

        # Remove vetor antigo se existir (IndexIDMap suporta remove_ids)
        if int_id in self._id_to_uid:
            try:
                selector = faiss.IDSelectorBatch(
                    1, faiss.swig_ptr(np.array([int_id], dtype="int64"))
                )
                self.index.remove_ids(selector)
            except Exception:
                pass  # ignore se o ID não estava no índice

        vec = embedding.reshape(1, -1).astype("float32")
        faiss.normalize_L2(vec)
        self.index.add_with_ids(vec, np.array([int_id], dtype="int64"))
        self._id_to_uid[int_id] = uid
        self._id_to_meta[int_id] = {"uid": uid, "title": name or uid}

    def save(self) -> None:
        """Persiste o índice, o mapa de IDs e a metadata (nome exibido no match) no disco."""
        FAISS_PATH.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(FAISS_PATH))
        np.save(str(FAISS_ID_PATH), self._id_to_uid)
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self._id_to_meta.items()}, f, ensure_ascii=False)
        log.info(f"Índice salvo: {self.index.ntotal} vetores → {FAISS_PATH}")

    @property
    def total(self) -> int:
        return self.index.ntotal if self.index else 0


# ─── Resolução de caminhos de imagem ─────────────────────────────────────────

def resolve_img_path(img_path: str) -> Optional[Path]:
    """Tenta múltiplas estratégias de resolução de caminho de imagem."""
    candidates = [
        ROOT / img_path,
        ROOT / "intelligence" / "data" / img_path,
        ROOT / "olho_de_deus" / img_path,
        Path(img_path),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ─── Pipeline principal ───────────────────────────────────────────────────────

def run_delta(
    limit: Optional[int] = None,
    batch_size: int = 32,
    force_rebuild: bool = False,
) -> Dict[str, int]:
    """
    Executa o pipeline de embedding delta.

    Args:
        limit:         Máximo de indivíduos a processar nesta execução.
        batch_size:    Commit interval no banco (evita WAL excessivo).
        force_rebuild: Reconstrói o índice FAISS do zero mesmo se existir.
    Returns:
        Dict com estatísticas: {processed, skipped, errors, already_indexed, total_indexed}
    """
    from deepface import DeepFace

    db = DB()
    t0 = time.monotonic()

    print("\n" + "═" * 60)
    print("  🧬 OLHO DE DEUS — Delta Embedding Updater  [Fase 14]")
    print("═" * 60)

    # ── 1. Carregar / construir índice ────────────────────────────────────────
    if force_rebuild and FAISS_PATH.exists():
        FAISS_PATH.unlink()
        if FAISS_ID_PATH.exists():
            FAISS_ID_PATH.unlink()
        log.info("Force rebuild: índice anterior removido.")

    fidx = FaissIDMap()
    already_indexed = fidx.load_or_create(db)
    print(f"\n  Vetores já indexados : {already_indexed:>6}")

    # ── 2. Identificar delta ───────────────────────────────────────────────────
    delta = get_embedding_delta(db, limit=limit)
    print(f"  Registros no delta   : {len(delta):>6}")
    print(f"  (novos sem embedding + atualizados desde último embed)\n")

    if not delta:
        print("  ✅ Banco 100% atualizado — nenhum embedding pendente.\n")
        db.close()
        return {"processed": 0, "skipped": 0, "errors": 0,
                "already_indexed": already_indexed, "total_indexed": fidx.total}

    # ── 3. Processar delta ────────────────────────────────────────────────────
    try:
        from classify_images import USABLE_LABELS
    except ImportError:
        USABLE_LABELS = None  # classify_images.py não rodou ainda — não filtra por conteúdo

    processed = 0
    skipped   = 0
    errors    = 0
    not_a_face = 0
    multi_face = 0
    multi_face_uids = []
    commit_buf = 0

    for row in tqdm(delta, desc="  ArcFace Embeddings", unit="face"):
        uid      = row["id"]
        img_path = row.get("img_path", "")
        content_type = row.get("image_content_type")

        # Triagem CLIP (classify_images.py) — pula direto imagens que já sabemos não
        # serem foto de rosto único (cartaz com várias pessoas, esboço, tatuagem,
        # documento etc), sem gastar tempo do RetinaFace nelas.
        if USABLE_LABELS is not None and content_type is not None and content_type not in USABLE_LABELS:
            not_a_face += 1
            continue

        # Resolve caminho da imagem
        full_path = resolve_img_path(img_path)
        if not full_path:
            skipped += 1
            continue

        try:
            objs = DeepFace.represent(
                img_path=str(full_path),
                model_name="ArcFace",
                enforce_detection=True,
                detector_backend="retinaface",  # mais preciso que Haar Cascade/opencv — evita falso positivo em fundo complexo
            )
            if not objs:
                skipped += 1
                continue

            if len(objs) > 1:
                # Mais de um rosto na imagem — na maioria das vezes é o assunto principal
                # da foto + um artefato (pessoa ao fundo, ou uma carteira/RG que a própria
                # pessoa segura na mão com a foto dela impressa). Revisei manualmente 9
                # casos reais (2026-09-10): quando o maior rosto é MUITO maior que o
                # segundo (>=10x em área), sempre era exatamente esse padrão — nunca uma
                # foto genuína de 2 pessoas (essas ficam em torno de 1x-2.3x de razão,
                # tamanho comparável, porque as duas são de fato o assunto da foto).
                # Ver NOITE_AUTONOMA_2026-09-10.md pros 9 casos e imagens conferidas.
                areas = sorted(
                    ((o["facial_area"]["w"] * o["facial_area"]["h"], o) for o in objs),
                    key=lambda t: t[0], reverse=True,
                )
                largest_area, largest_obj = areas[0]
                second_area = areas[1][0]
                if second_area > 0 and largest_area / second_area >= 10:
                    objs = [largest_obj]
                    log.info(f"[{uid}] {len(areas)} rostos detectados, mas o maior é "
                             f"{largest_area/second_area:.0f}x maior — usando só ele "
                             "(padrão: assunto principal + artefato pequeno).")
                else:
                    # Tamanhos comparáveis — provavelmente 2+ pessoas de verdade na foto,
                    # não dá pra saber qual rosto é o nome cadastrado sem revisão manual.
                    multi_face += 1
                    multi_face_uids.append(uid)
                    log.warning(f"[{uid}] {len(objs)} rostos de tamanho comparável — pulando, revisar manualmente.")
                    continue

            raw_emb  = objs[0]["embedding"]
            emb_np   = np.array(raw_emb, dtype="float32")

            # Upsert no IndexIDMap
            fidx.upsert(uid, emb_np, row.get("name"))

            # Salva blob no banco relacional
            save_embedding(db, uid, raw_emb)
            mark_embedded(db, uid)

            processed  += 1
            commit_buf += 1

            # Checkpoint periódico
            if commit_buf >= batch_size:
                fidx.save()
                commit_buf = 0

        except Exception as e:
            log.debug(f"[{uid}] Falha ArcFace: {e}")
            errors += 1

    # ── 4. Salvar índice final ────────────────────────────────────────────────
    # Salva sempre que há algo pra salvar — não só quando processed > 0. Sem isso,
    # um --force-rebuild que reconstrói do banco mas não processa nada de NOVO no
    # delta (ex: só sobraram erros/múltiplos rostos) nunca persistia o índice
    # recém-reconstruído no disco, apagando o arquivo antigo e não escrevendo um novo.
    if fidx.total > 0:
        fidx.save()

    db.close()
    elapsed = time.monotonic() - t0

    # ── 5. Relatório ──────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print(f"  ✅ Processados       : {processed}")
    print(f"  ⚠  Sem imagem        : {skipped}")
    print(f"  🚫 Não é rosto (CLIP): {not_a_face} (cartaz/esboço/tatuagem/documento — pulados sem gastar RetinaFace)")
    print(f"  ✗  Erros ArcFace     : {errors}")
    print(f"  🖼️  Múltiplos rostos  : {multi_face} (pulados — revisar manualmente)")
    print(f"  📦 Total no FAISS    : {fidx.total}")
    print(f"  ⏱  Tempo total       : {elapsed:.1f}s")
    print("═" * 60 + "\n")
    if multi_face_uids:
        print(f"  UIDs com múltiplos rostos (não indexados): {', '.join(multi_face_uids)}\n")

    return {
        "processed": processed,
        "skipped":   skipped,
        "not_a_face": not_a_face,
        "errors":    errors,
        "multi_face": multi_face,
        "multi_face_uids": multi_face_uids,
        "already_indexed": already_indexed,
        "total_indexed":   fidx.total,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Olho de Deus — Delta Embedding Updater")
    parser.add_argument("--limit",         type=int, default=None, help="Máximo de registros a processar")
    parser.add_argument("--batch-size",    type=int, default=32,   help="Checkpoint interval (default: 32)")
    parser.add_argument("--force-rebuild", action="store_true",    help="Reconstrói o índice FAISS do zero")
    args = parser.parse_args()

    run_delta(
        limit=args.limit,
        batch_size=args.batch_size,
        force_rebuild=args.force_rebuild,
    )
