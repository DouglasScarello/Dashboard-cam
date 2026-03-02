#!/usr/bin/env python3
"""
Global Ingestion v2.0 — Olho de Deus
Agrega múltiplas fontes internacionais usando métodos CONFIRMADOS:

  FONTE 1 – FBI Wanted API
    endpoint: api.fbi.gov/wanted/v1/list
    acesso:   HTTP GET (sem auth, sem bloqueio)
    imagens:  Playwright (bypass CDN 403)

  FONTE 2 – OpenSanctions Bulk CSV (GRATUITO, sem key)
    endpoint: data.opensanctions.org/datasets/latest/{dataset}/targets.simple.csv
    datasets: interpol_red_notices, eu_most_wanted, gb_nca_most_wanted
    acesso:   HTTP direto (200 OK confirmado)
    imagens:  sem URL — metadados apenas (nome, crime, país)

  FONTE 3 – Interpol Red/Yellow via portal público (Playwright scraping)
    endpoint: interpol.int/How-we-work/Notices/Red-Notices/View-Red-Notices
    acesso:   Playwright (lista paginada da galeria pública)
    imagens:  extração via img tags na galeria

Saída: data/global_faces/  + FAISS global_vector_db.faiss + global_metadata.json
"""
import os
import io
import csv
import json
import time
import requests
import numpy as np
import faiss
import logging
from tqdm import tqdm
from typing import List, Dict, Optional, Iterator
from deepface import DeepFace
from playwright.sync_api import sync_playwright, Page

logging.getLogger("deepface").setLevel(logging.ERROR)
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ── Caminhos ────────────────────────────────────────────────────────────────
OUTPUT_DIR = "data/global_faces"
DB_PATH    = "data/global_intelligence.json"
FAISS_PATH = "data/global_vector_db.faiss"
META_PATH  = "data/global_metadata.json"

# ── Datastes OpenSanctions (CSV gratuito) ────────────────────────────────────
OPENSANCTIONS_DATASETS = {
    "interpol_red_notices": "Interpol Red Notices",
    "eu_most_wanted":       "Europol EU Most Wanted",
    "gb_nca_most_wanted":   "UK NCA Most Wanted",
}

# ────────────────────────────────────────────────────────────────────────────
# FONTE 1: FBI WANTED API
# ────────────────────────────────────────────────────────────────────────────
def fetch_fbi(limit_pages: Optional[int] = None) -> Iterator[Dict]:
    """FBI Wanted API – funciona sem auth."""
    base = "https://api.fbi.gov/wanted/v1/list"
    resp = requests.get(base, params={"page": 1}, timeout=10)
    total = resp.json().get("total", 0)
    pages = (total // 20) + 1
    if limit_pages:
        pages = min(pages, limit_pages)

    for page in tqdm(range(1, pages + 1), desc="[FBI] Paginação"):
        data = requests.get(base, params={"page": page}, timeout=10).json()
        for item in data.get("items", []):
            imgs = item.get("images", [])
            img_url = (
                imgs[0].get("large") or
                imgs[0].get("thumb") or
                imgs[0].get("original")
            ) if imgs else None
            yield {
                "uid":      item.get("uid"),
                "title":    item.get("title", "N/A"),
                "source":   "FBI",
                "category": "wanted",
                "img_url":  img_url,
                "img_method": "playwright" if img_url else None,
            }
        time.sleep(0.25)


# ────────────────────────────────────────────────────────────────────────────
# FONTE 2: OPENSANCTIONS BULK CSV (sem key, gratuito)
# ────────────────────────────────────────────────────────────────────────────
def fetch_opensanctions_csv(dataset_key: str, label: str) -> Iterator[Dict]:
    """
    Baixa o CSV bulk do OpenSanctions (HTTP 200 confirmado).
    Sem API key, sem bloqueio. Dados atualizados diariamente.
    """
    url = f"https://data.opensanctions.org/datasets/latest/{dataset_key}/targets.simple.csv"
    print(f"\n[OpenSanctions] Baixando {label}...")
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        content = resp.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        for row in tqdm(rows, desc=f"[OS] {label}"):
            name = row.get("name", "N/A").strip()
            if not name:
                continue
            yield {
                "uid":      f"os_{dataset_key}_{row.get('id', '')}",
                "title":    name,
                "source":   f"OpenSanctions/{label}",
                "category": "wanted",
                "img_url":  None,     # OpenSanctions CSV não tem URLs de imagem
                "img_method": None,
                "crime":    row.get("sanctions", "")[:200],
                "countries": row.get("countries", ""),
                "birth_date": row.get("birth_date", ""),
            }
    except Exception as e:
        print(f"[warning] OpenSanctions {dataset_key}: {e}")


def fetch_all_opensanctions() -> Iterator[Dict]:
    """Itera todos os datasets OpenSanctions configurados."""
    for ds_key, ds_label in OPENSANCTIONS_DATASETS.items():
        yield from fetch_opensanctions_csv(ds_key, ds_label)


# ────────────────────────────────────────────────────────────────────────────
# FONTE 3: INTERPOL GALERIA PÚBLICA (Playwright scraping)
# ────────────────────────────────────────────────────────────────────────────
def _interpol_scrape_page(page: Page, url: str) -> List[Dict]:
    """Extrai cartões de procurados de uma página da galeria Interpol."""
    results = []
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Cartões da galeria Interpol
        cards = page.query_selector_all(".nwa-notice-card, .wanted-notice-card, article.notice")
        for card in cards:
            name_el  = card.query_selector(".nwa-person-name, h3, .name")
            img_el   = card.query_selector("img")
            link_el  = card.query_selector("a")

            name    = name_el.inner_text().strip() if name_el else "N/A"
            img_url = img_el.get_attribute("src") if img_el else None
            profile = link_el.get_attribute("href") if link_el else ""

            if name and img_url:
                results.append({
                    "uid":      f"interpol_gallery_{abs(hash(name))}",
                    "title":    name,
                    "source":   "Interpol_Gallery",
                    "category": "wanted",
                    "img_url":  img_url,
                    "img_method": "direct",
                    "profile_url": profile,
                })
    except Exception as e:
        print(f"[warning] Interpol scrape: {e}")
    return results


def fetch_interpol_gallery(max_pages: int = 10) -> Iterator[Dict]:
    """
    Scraping da galeria pública da Interpol via Playwright.
    As páginas de lista são públicas e acessíveis.
    """
    base_url = "https://www.interpol.int/How-we-work/Notices/Red-Notices/View-Red-Notices"
    seen = set()

    print(f"\n[Interpol] Scraping galeria pública ({max_pages} páginas)...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = ctx.new_page()
        page.route("**/*.{css,woff,woff2,ttf,eot}", lambda r: r.abort())

        for pg_num in range(1, max_pages + 1):
            url = f"{base_url}?page={pg_num}"
            cards = _interpol_scrape_page(page, url)
            if not cards:
                print(f"[Interpol] Página {pg_num}: sem resultados, parando.")
                break
            for c in cards:
                if c["uid"] not in seen:
                    seen.add(c["uid"])
                    yield c
            time.sleep(1.0)

        browser.close()
    print(f"[Interpol] {len(seen)} procurados extraídos da galeria.")


# ────────────────────────────────────────────────────────────────────────────
# DOWNLOAD DE IMAGENS
# ────────────────────────────────────────────────────────────────────────────
def _playwright_download(url: str, dest: str, page: Page) -> bool:
    """Download via Playwright — bypassa CDN bloqueios (FBI, Interpol CDN)."""
    try:
        resp = page.goto(url, timeout=20000, wait_until="domcontentloaded")
        if resp and resp.ok:
            ct = resp.headers.get("content-type", "")
            if "image" in ct:
                with open(dest, "wb") as f:
                    f.write(resp.body())
                return True
            else:
                # Screenshot do conteúdo como fallback
                page.screenshot(path=dest, type="jpeg",
                                clip={"x": 0, "y": 0, "width": 400, "height": 500})
                return True
    except Exception:
        pass
    return False


def _requests_download(url: str, dest: str) -> bool:
    """Download simples com headers de browser."""
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0",
            "Accept": "image/*,*/*",
        })
        ct = resp.headers.get("Content-Type", "")
        if "image" in ct or resp.status_code == 200:
            with open(dest, "wb") as f:
                f.write(resp.content)
            return len(resp.content) > 1000  # rejeitar respostas vazias
    except Exception:
        pass
    return False


# ────────────────────────────────────────────────────────────────────────────
# BIOMETRIA
# ────────────────────────────────────────────────────────────────────────────
def extract_embedding(img_path: str) -> Optional[List[float]]:
    try:
        objs = DeepFace.represent(
            img_path=img_path,
            model_name="ArcFace",
            enforce_detection=False,
            detector_backend="opencv",
        )
        return objs[0]["embedding"] if objs else None
    except Exception:
        return None


def build_vector_db(embeddings: List[List[float]], metadata: List[Dict]):
    arr = np.array(embeddings, dtype="float32")
    idx = faiss.IndexFlatL2(arr.shape[1])
    idx.add(arr)
    faiss.write_index(idx, FAISS_PATH)
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[sucesso] Base vetorial global: {len(metadata)} faces → {FAISS_PATH}")


# ────────────────────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ────────────────────────────────────────────────────────────────────────────
def run(
    include_fbi:           bool = True,
    include_opensanctions: bool = True,
    include_interpol:      bool = True,
    fbi_pages:             Optional[int] = None,
    interpol_pages:        int = 10,
):
    """
    Executa ingestão completa de todas as fontes e constrói o banco vetorial global.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)

    intelligence_base: List[Dict] = []

    print("═" * 60)
    print("  OLHO DE DEUS — Ingestão Global v2.0")
    print("═" * 60)

    # ── Fase 1: Coleta de Metadados ──────────────────────────────────────────
    if include_fbi:
        print("\n[Fase 1/3] FBI Wanted API...")
        for r in fetch_fbi(limit_pages=fbi_pages):
            intelligence_base.append(r)
        print(f"  ✓ FBI: {sum(1 for r in intelligence_base if r['source']=='FBI')} registros")

    if include_opensanctions:
        print("\n[Fase 2/3] OpenSanctions Bulk CSV...")
        os_start = len(intelligence_base)
        for r in fetch_all_opensanctions():
            intelligence_base.append(r)
        print(f"  ✓ OpenSanctions: {len(intelligence_base) - os_start} registros")

    if include_interpol:
        print("\n[Fase 3/3] Interpol Galeria Pública...")
        ip_start = len(intelligence_base)
        for r in fetch_interpol_gallery(max_pages=interpol_pages):
            intelligence_base.append(r)
        print(f"  ✓ Interpol Gallery: {len(intelligence_base) - ip_start} registros")

    # Salvar base bruta
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(intelligence_base, f, indent=2, ensure_ascii=False)
    print(f"\n[global] {len(intelligence_base)} registros totais → {DB_PATH}")

    # ── Fase 2: Download de Imagens + Biometria ──────────────────────────────
    print("\n[Fase 4] Download de imagens + Extração biométrica...")
    embeddings: List[List[float]] = []
    metadata:   List[Dict]        = []

    # Separar por método de download
    playwright_records = [r for r in intelligence_base if r.get("img_method") == "playwright" and r.get("img_url")]
    direct_records     = [r for r in intelligence_base if r.get("img_method") == "direct" and r.get("img_url")]
    no_img_records     = [r for r in intelligence_base if not r.get("img_url")]

    print(f"  Playwright: {len(playwright_records)} | Direto: {len(direct_records)} | Sem imagem: {len(no_img_records)}")

    # Download via Playwright (FBI e afins)
    if playwright_records:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0",
                extra_http_headers={"Referer": "https://www.fbi.gov/"},
            )
            page = ctx.new_page()
            page.route("**/*.{css,woff,woff2,ttf,eot,js}", lambda r: r.abort())

            for rec in tqdm(playwright_records, desc="[Playwright] Download"):
                uid  = rec["uid"]
                dest = os.path.join(OUTPUT_DIR, f"{uid}.jpg")
                if not os.path.exists(dest):
                    _playwright_download(rec["img_url"], dest, page)
                if os.path.exists(dest):
                    emb = extract_embedding(dest)
                    if emb:
                        embeddings.append(emb)
                        metadata.append(_meta(rec))
            browser.close()

    # Download direto (Interpol galeria)
    for rec in tqdm(direct_records, desc="[Direto] Download"):
        uid  = rec["uid"]
        dest = os.path.join(OUTPUT_DIR, f"{uid}.jpg")
        if not os.path.exists(dest):
            _requests_download(rec["img_url"], dest)
        if os.path.exists(dest):
            emb = extract_embedding(dest)
            if emb:
                embeddings.append(emb)
                metadata.append(_meta(rec))

    # Registros sem imagem: indexar como metadados apenas (sem embedding)
    print(f"[info] {len(no_img_records)} registros sem imagem indexados apenas como metadados textuais")

    # ── Fase 3: Salvar FAISS ─────────────────────────────────────────────────
    if embeddings:
        build_vector_db(embeddings, metadata)
    else:
        print("[warning] Nenhum embedding extraído.")

    # ── Resumo ───────────────────────────────────────────────────────────────
    from collections import Counter
    print("\n" + "═" * 60)
    print("[RESUMO FINAL]")
    src_count = Counter(m["source"] for m in metadata)
    for src, cnt in src_count.most_common():
        print(f"  {src:<45} {cnt:>5} faces")
    print(f"\n  TOTAL DE FACES BIOMÉTRICAS: {len(embeddings)}")
    print(f"  TOTAL DE REGISTROS TEXTUAIS: {len(intelligence_base)}")
    print("═" * 60)


def _meta(rec: Dict) -> Dict:
    return {
        "uid":      rec["uid"],
        "title":    rec["title"],
        "source":   rec["source"],
        "category": rec.get("category", "wanted"),
        "crime":    rec.get("crime", ""),
    }


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Olho de Deus — Ingestão Global v2.0")
    parser.add_argument("--no-fbi",            action="store_true", help="Desativar FBI")
    parser.add_argument("--no-opensanctions",  action="store_true", help="Desativar OpenSanctions")
    parser.add_argument("--no-interpol",       action="store_true", help="Desativar Interpol Gallery")
    parser.add_argument("--fbi-pages",         type=int, default=None, help="Limitar páginas FBI")
    parser.add_argument("--interpol-pages",    type=int, default=10,   help="Páginas da galeria Interpol")
    args = parser.parse_args()

    run(
        include_fbi=           not args.no_fbi,
        include_opensanctions= not args.no_opensanctions,
        include_interpol=      not args.no_interpol,
        fbi_pages=             args.fbi_pages,
        interpol_pages=        args.interpol_pages,
    )
