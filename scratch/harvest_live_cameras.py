#!/usr/bin/env python3
"""
===============================================================================
HARVESTER & VALIDATOR DE CÂMERAS AO VIVO DO YOUTUBE (50 SETORES EM PARALELO)
Busca, valida status de transmissão ao vivo (is_live: True) e salva em
database/live_cameras.json para alimentar o grid de 100+ câmeras.
===============================================================================
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "database" / "live_cameras.json"

SEARCH_QUERIES = [
    # ─── BRASIL - PRAIAS & CIDADES ───
    {"query": "camera ao vivo florianopolis live", "setor": "BR", "pais": "BR", "local": "Florianópolis, SC"},
    {"query": "camera ao vivo balneario camboriu live", "setor": "BR", "pais": "BR", "local": "Balneário Camboriú, SC"},
    {"query": "camera ao vivo santos praia 4k live", "setor": "BR", "pais": "BR", "local": "Santos, SP"},
    {"query": "camera ao vivo copacabana rio de janeiro live", "setor": "BR", "pais": "BR", "local": "Rio de Janeiro, RJ"},
    {"query": "camera ao vivo sao paulo transito avenida paulista live", "setor": "BR", "pais": "BR", "local": "São Paulo, SP"},
    {"query": "camera ao vivo curitiba pr live", "setor": "BR", "pais": "BR", "local": "Curitiba, PR"},
    {"query": "camera ao vivo porto alegre guaiba live", "setor": "BR", "pais": "BR", "local": "Porto Alegre, RS"},
    {"query": "camera ao vivo salvador barra bahia live", "setor": "BR", "pais": "BR", "local": "Salvador, BA"},
    {"query": "camera ao vivo fortaleza beira mar live", "setor": "BR", "pais": "BR", "local": "Fortaleza, CE"},
    {"query": "camera ao vivo recife boa viagem live", "setor": "BR", "pais": "BR", "local": "Recife, PE"},
    {"query": "camera ao vivo ubatuba caraguatatuba live", "setor": "BR", "pais": "BR", "local": "Litoral Norte, SP"},
    {"query": "camera ao vivo foz do iguacu ponte da amizade live", "setor": "BR", "pais": "BR", "local": "Foz do Iguaçu, PR"},
    {"query": "camera ao vivo ilhabela praia live", "setor": "BR", "pais": "BR", "local": "Ilhabela, SP"},
    {"query": "camera ao vivo bertioga riviera live", "setor": "BR", "pais": "BR", "local": "Bertioga, SP"},
    {"query": "camera ao vivo guaruja enseada live", "setor": "BR", "pais": "BR", "local": "Guarujá, SP"},
    {"query": "camera ao vivo bombinhas sc live", "setor": "BR", "pais": "BR", "local": "Bombinhas, SC"},
    {"query": "camera ao vivo gramado canela rs live", "setor": "BR", "pais": "BR", "local": "Gramado, RS"},

    # ─── BRASIL - AEROPORTOS & INFRAESTRUTURA ───
    {"query": "camera ao vivo aeroporto guarulhos gru live", "setor": "BR", "pais": "BR", "local": "Aeroporto GRU, SP"},
    {"query": "camera ao vivo aeroporto congonhas live", "setor": "BR", "pais": "BR", "local": "Aeroporto CGH, SP"},
    {"query": "camera ao vivo aeroporto viracopos live", "setor": "BR", "pais": "BR", "local": "Aeroporto VCP, SP"},
    {"query": "camera ao vivo aeroporto santos dumont galeao rj live", "setor": "BR", "pais": "BR", "local": "Aeroporto SDU/GIG, RJ"},
    {"query": "camera ao vivo aeroporto navegantes nvt live", "setor": "BR", "pais": "BR", "local": "Aeroporto NVT, SC"},
    {"query": "camera ao vivo aeroporto curitiba afonso pena live", "setor": "BR", "pais": "BR", "local": "Aeroporto CWB, PR"},
    {"query": "camera ao vivo porto de santos canal live", "setor": "BR", "pais": "BR", "local": "Porto de Santos, SP"},
    {"query": "camera ao vivo ponte hercilio luz florianopolis live", "setor": "BR", "pais": "BR", "local": "Ponte Hercílio Luz, SC"},

    # ─── AMÉRICA DO NORTE (EUA & CANADÁ) ───
    {"query": "times square new york live camera 4k", "setor": "US", "pais": "US", "local": "New York City, NY"},
    {"query": "las vegas strip live camera bellagio earthcam", "setor": "US", "pais": "US", "local": "Las Vegas, NV"},
    {"query": "miami beach live cam ocean drive earthcam", "setor": "US", "pais": "US", "local": "Miami Beach, FL"},
    {"query": "venice beach live camera los angeles", "setor": "US", "pais": "US", "local": "Los Angeles, CA"},
    {"query": "hollywood boulevard live camera", "setor": "US", "pais": "US", "local": "Hollywood, CA"},
    {"query": "jackson hole town square live cam wyoming", "setor": "US", "pais": "US", "local": "Jackson Hole, WY"},
    {"query": "chicago skyline live camera earthcam", "setor": "US", "pais": "US", "local": "Chicago, IL"},
    {"query": "san francisco golden gate live camera", "setor": "US", "pais": "US", "local": "San Francisco, CA"},
    {"query": "waikiki beach honolulu hawaii live cam", "setor": "US", "pais": "US", "local": "Honolulu, HI"},
    {"query": "niagara falls live camera earthcam", "setor": "CA", "pais": "CA", "local": "Niagara Falls, ON"},

    # ─── EUROPA ───
    {"query": "london abbey road live cam earthcam", "setor": "EU", "pais": "GB", "local": "London, UK"},
    {"query": "london tower bridge live camera 4k", "setor": "EU", "pais": "GB", "local": "London, UK"},
    {"query": "paris eiffel tower live camera 4k", "setor": "EU", "pais": "FR", "local": "Paris, França"},
    {"query": "venice rialto bridge live cam skylinewebcams", "setor": "EU", "pais": "IT", "local": "Veneza, Itália"},
    {"query": "venice st mark square piazza san marco live", "setor": "EU", "pais": "IT", "local": "Veneza, Itália"},
    {"query": "rome colosseum live camera skylinewebcams", "setor": "EU", "pais": "IT", "local": "Roma, Itália"},
    {"query": "prague old town square live camera 4k", "setor": "EU", "pais": "CZ", "local": "Praga, República Tcheca"},
    {"query": "madrid puerta del sol live camera", "setor": "EU", "pais": "ES", "local": "Madrid, Espanha"},
    {"query": "amsterdam canal live camera", "setor": "EU", "pais": "NL", "local": "Amsterdã, Holanda"},
    {"query": "barcelona sagrada familia live camera", "setor": "EU", "pais": "ES", "local": "Barcelona, Espanha"},

    # ─── BRASIL - EXPANSÃO ADICIONAL ───
    {"query": "camera ao vivo cabo frio arraial do cabo rj live", "setor": "BR", "pais": "BR", "local": "Região dos Lagos, RJ"},
    {"query": "camera ao vivo jericoacoara ceara live", "setor": "BR", "pais": "BR", "local": "Jericoacoara, CE"},
    {"query": "camera ao vivo maragogi alagoas live", "setor": "BR", "pais": "BR", "local": "Maragogi, AL"},
    {"query": "camera ao vivo itajai praia brava sc live", "setor": "BR", "pais": "BR", "local": "Itajaí / Praia Brava, SC"},
    {"query": "camera ao vivo ilheus bahia live", "setor": "BR", "pais": "BR", "local": "Ilhéus, BA"},
    {"query": "camera ao vivo rodovia dos imigrantes anchieta live", "setor": "BR", "pais": "BR", "local": "Sistema Anchieta-Imigrantes, SP"},
    {"query": "camera ao vivo rodovia presidente dutra ccr live", "setor": "BR", "pais": "BR", "local": "Rodovia Pres. Dutra, SP/RJ"},
    {"query": "camera ao vivo joinville sc live", "setor": "BR", "pais": "BR", "local": "Joinville, SC"},
    {"query": "camera ao vivo campos do jordao sp live", "setor": "BR", "pais": "BR", "local": "Campos do Jordão, SP"},

    # ─── INTERNACIONAL EXPANSÃO ───
    {"query": "mount fuji live camera japan 4k", "setor": "AS", "pais": "JP", "local": "Monte Fuji, Japão"},
    {"query": "akihabara tokyo live camera 4k", "setor": "AS", "pais": "JP", "local": "Akihabara, Japão"},
    {"query": "key west duval street live camera earthcam", "setor": "US", "pais": "US", "local": "Key West, FL"},
    {"query": "seattle space needle live camera 4k", "setor": "US", "pais": "US", "local": "Seattle, WA"},
    {"query": "santorini greece caldera live cam 4k", "setor": "EU", "pais": "GR", "local": "Santorini, Grécia"},
    {"query": "munich marienplatz live camera germany", "setor": "EU", "pais": "DE", "local": "Munique, Alemanha"},
    {"query": "swiss alps zermatt matterhorn live cam 4k", "setor": "EU", "pais": "CH", "local": "Alpes Suíços, Suíça"},
    {"query": "dublin temple bar live camera ireland", "setor": "EU", "pais": "IE", "local": "Dublin, Irlanda"},
    {"query": "lisbon praca do comercio live cam portugal", "setor": "EU", "pais": "PT", "local": "Lisboa, Portugal"},
    {"query": "singapore marina bay sands live cam 4k", "setor": "AS", "pais": "SG", "local": "Singapura, Singapura"},
    {"query": "panama canal miraflores locks live camera", "setor": "AM", "pais": "PA", "local": "Canal do Panamá, Panamá"}
]

def search_query_worker(item: Dict[str, str]) -> List[Dict[str, Any]]:
    """Executa busca com yt-dlp para extrair streams ao vivo com is_live=True."""
    query = item["query"]
    cmd = [
        "yt-dlp",
        f"ytsearch5:{query}",
        "--print", "%(title)s ### %(id)s ### %(webpage_url)s ### %(is_live)s",
        "--no-warnings",
        "--quiet"
    ]
    results = []
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        if proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.strip().split("\n"):
                if "###" in line:
                    parts = [p.strip() for p in line.split("###")]
                    if len(parts) >= 4:
                        title, vid_id, url, is_live_str = parts[0], parts[1], parts[2], parts[3]
                        if is_live_str.lower() == "true":
                            results.append({
                                "nome": title.upper(),
                                "url": url,
                                "local": item["local"],
                                "setor": item["setor"],
                                "pais": item["pais"],
                                "tipo": "youtube",
                                "status": "ACTIVE",
                                "video_id": vid_id,
                                "res": "1920x1080"
                            })
    except Exception as e:
        pass
    return results

def main():
    print(f"🚀 Iniciando colheita de câmeras ao vivo em {len(SEARCH_QUERIES)} setores...")
    t0 = time.time()
    
    unique_streams: Dict[str, Dict[str, Any]] = {}
    
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(search_query_worker, q): q for q in SEARCH_QUERIES}
        for future in as_completed(futures):
            res_list = future.result()
            for cam in res_list:
                vid_id = cam.get("video_id")
                if vid_id and vid_id not in unique_streams:
                    unique_streams[vid_id] = cam
            print(f"  [+] Coletadas até agora: {len(unique_streams)} câmeras únicas ativas.")

    # Atribuir IDs sequenciais a partir de 1000
    final_list = []
    for idx, cam in enumerate(unique_streams.values()):
        cam["id"] = 1000 + idx
        final_list.append(cam)

    print(f"\n✅ Colheita finalizada em {time.time() - t0:.2f}s!")
    print(f"📊 Total de Câmeras Ao Vivo Ativas Validadas: {len(final_list)}")

    # Salvar em database/live_cameras.json
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)

    print(f"💾 Base gravada com sucesso em: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
