#!/usr/bin/env python3
"""
Preenche lat/long real pras câmeras que não têm, usando o campo `local`
(cidade/estado real) já presente nos dados — nunca inventa coordenada.

Geocodificação via Nominatim (OpenStreetMap), API pública e gratuita.
Respeita a política de uso deles: 1 requisição/segundo, User-Agent
identificado — não é permitido bombardear o serviço.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CAMERAS_PATH = ROOT / "database" / "live_cameras.json"
GEOCODE_CACHE_PATH = ROOT / "database" / "geocode_cache.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GEOCODE] %(message)s")
log = logging.getLogger("geocode")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "dashboard-cam-olho-de-deus/1.0 (uso pessoal, geocodificacao de cameras publicas)"
RATE_LIMIT_SECONDS = 1.1  # Nominatim exige no máximo 1 req/s


# Nomes que não são um lugar físico com coordenada fixa — compilados,
# canais temáticos, ou a Estação Espacial Internacional (que literalmente
# não tem lat/long fixo). Forçar uma coordenada nesses seria inventar dado,
# não geocodificar. Ficam sem lat/long de propósito.
NOT_A_PLACE_MARKERS = (
    "earthcam global", "skylinewebcams global", "global live streams",
    "explore.org", "estação espacial internacional", "rede clima ao vivo",
    "ferrovias & trens", "railstream", "virtual railfan", "plane spotting",
    "aurora boreal ao vivo", "vulcões ativos ao vivo",
)


def is_not_a_real_place(query: str) -> bool:
    q = query.lower()
    return any(marker in q for marker in NOT_A_PLACE_MARKERS)


def _search_once(q: str) -> Optional[Tuple[float, float]]:
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    return None


def geocode(query: str) -> Optional[Tuple[float, float]]:
    """Tenta a query como veio; se vier vazio (não é erro, Nominatim só não
    achou), tenta variantes progressivamente mais simples. Achado real:
    'Madrid, Espanha, ES' falha (nome do país em português + sigla ISO
    juntos confunde o parser deles), mas 'Madrid' sozinho funciona — testado
    manualmente antes de generalizar isso pra todas as queries."""
    if not query.strip():
        return None

    candidates = [query]
    # Variante 2: só o primeiro segmento antes de vírgula/hífen (nome
    # principal do lugar, sem sufixo de país/região que pode atrapalhar).
    primary = query.split(",")[0].split(" - ")[0].strip()
    if primary and primary != query:
        candidates.append(primary)

    for i, q in enumerate(candidates):
        try:
            coords = _search_once(q)
            if coords:
                return coords
        except Exception as e:
            log.warning(f"Falha ao geocodificar '{q}': {e}")
        if i < len(candidates) - 1:
            time.sleep(RATE_LIMIT_SECONDS)
    return None


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def run(apply_changes: bool) -> Dict[str, Any]:
    cameras = load_json(CAMERAS_PATH, [])
    cache: Dict[str, Any] = load_json(GEOCODE_CACHE_PATH, {})

    missing = [c for c in cameras if c.get("lat") is None or c.get("long") is None]
    log.info(f"{len(missing)} câmeras sem lat/long de {len(cameras)} totais.")

    # Agrupa por local+país únicos pra minimizar chamadas reais ao serviço.
    unique_queries = {}
    for c in missing:
        local = (c.get("local") or "").strip()
        pais = (c.get("pais") or "").strip()
        query = f"{local}, {pais}" if pais and pais not in local else local
        if not query.strip(", "):
            query = c.get("cidade") or c.get("nome", "")
        unique_queries.setdefault(query, []).append(c)

    log.info(f"{len(unique_queries)} locais únicos a resolver (cache já tem {len(cache)}).")

    resolved_count = 0
    not_a_place_count = 0
    failed_queries = []
    for i, (query, cams) in enumerate(unique_queries.items()):
        if is_not_a_real_place(query):
            # Não tenta geocodificar — não existe coordenada real correta
            # pra "EarthCam Global" ou pra Estação Espacial Internacional.
            for c in cams:
                c["no_fixed_location"] = True
            not_a_place_count += len(cams)
            continue

        # Só confia no cache pra sucesso — falha anterior é sempre
        # reconsultada, porque a lógica de fallback (query simplificada)
        # pode ter mudado desde a última rodada (foi o caso aqui: cache
        # tinha 90 falsos-negativos por causa de um bug na query, não
        # porque o lugar não existe).
        if query in cache and cache[query]:
            coords = tuple(cache[query])
        else:
            coords = geocode(query)
            cache[query] = list(coords) if coords else None
            time.sleep(RATE_LIMIT_SECONDS)
            if (i + 1) % 20 == 0:
                log.info(f"  progresso: {i+1}/{len(unique_queries)} locais consultados...")

        if coords:
            for c in cams:
                c["lat"], c["long"] = coords
            resolved_count += len(cams)
        else:
            failed_queries.append(query)

    save_json(GEOCODE_CACHE_PATH, cache)

    still_missing = sum(1 for c in cameras if c.get("lat") is None or c.get("long") is None)
    log.info(f"Resolvidas {resolved_count} | sem local fixo (não tentado): {not_a_place_count} | ainda sem coordenada: {still_missing}.")
    if failed_queries:
        log.warning(f"Locais que não geocodificaram ({len(failed_queries)}): {failed_queries[:20]}")

    if apply_changes:
        save_json(CAMERAS_PATH, cameras)
        log.info(f"Gravado {CAMERAS_PATH.name} com as coordenadas novas.")

    return {
        "total_cameras": len(cameras),
        "missing_before": len(missing),
        "unique_locations": len(unique_queries),
        "resolved": resolved_count,
        "not_a_place": not_a_place_count,
        "still_missing": still_missing,
        "failed_queries": failed_queries,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="grava de verdade em live_cameras.json (sem isso, só simula e mostra o que resolveria)")
    args = parser.parse_args()

    summary = run(apply_changes=args.apply)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
