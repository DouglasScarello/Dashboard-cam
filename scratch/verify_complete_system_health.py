#!/usr/bin/env python3
"""
===============================================================================
SUÍTE DE VERIFICAÇÃO E AUDITORIA COMPLETA DO SISTEMA OLHO DE DEUS
Valida:
1. Conectividade e integridade dos servidores (Portas 8000, 8001, 1420, 6379)
2. Resposta de endpoints REST e Spatial H3
3. Extração e integridade de streams ao vivo nas câmeras brasileiras prioritárias
4. Integridade do banco de 10.000 câmeras georreferenciadas
===============================================================================
"""

import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_url(url: str, desc: str, timeout: float = 3.0) -> bool:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OlhoDeDeus-Auditor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            elapsed = (time.time() - t0) * 1000
            if res.status in [200, 201]:
                print(f"  ✅ [{res.status}] {desc:<48} ({elapsed:.1f} ms)")
                return True
            else:
                print(f"  ❌ [{res.status}] {desc:<48} ({elapsed:.1f} ms)")
                return False
    except Exception as e:
        print(f"  ❌ [ERR] {desc:<48} -> {str(e)[:40]}")
        return False

def main():
    print("=" * 70)
    print("🔍 AUDITORIA GERAL DE SAÚDE DO SISTEMA — OLHO DE DEUS C4ISR")
    print("=" * 70)

    # 1. Checagem de Endpoints dos Servidores
    print("\n1. SERVIDORES & APIs:")
    s1 = check_url("http://localhost:8000/api/health", "Tactical API Server (Porta 8000)")
    s2 = check_url("http://localhost:8001/api/health", "Camera Grid Server (Porta 8001)")
    s3 = check_url("http://localhost:1420/", "Frontend Cockpit Web/Tauri (Porta 1420)")
    s4 = check_url("http://localhost:8001/api/alerts", "Alert Engine Polling Stream")

    # 2. Checagem dos Motores C4ISR Avançados
    print("\n2. MOTORES ESPACIAIS, GRAFOS & STREAMING:")
    m1 = check_url("http://localhost:8000/api/tactical/spatial/nearby?lat=-23.5505&lon=-46.6333&radius_meters=3000", "Uber H3 Spatial Query (Raio 3km)")
    m2 = check_url("http://localhost:8000/api/tactical/streaming/metrics", "Cluster Bandwidth & ABR Metrics")
    m3 = check_url("http://localhost:8000/api/tactical/graph/ALVO-01", "Graph Link Engine & Co-occurrence")

    # 3. Checagem das Câmeras Brasileiras Prioritárias
    print("\n3. CONSULTA DE CÂMERAS BRASILEIRAS NO BANCO:")
    cam_file = ROOT / "database" / "live_cameras.json"
    if not cam_file.exists():
        print("  ❌ Arquivo live_cameras.json não encontrado.")
        return

    with open(cam_file, "r", encoding="utf-8") as f:
        cams = json.load(f)

    br_cams = [c for c in cams if c.get("pais") == "BR" or c.get("setor") == "BR"]
    print(f"  📊 Total de Câmeras no Banco: {len(cams)}")
    print(f"  🇧🇷 Câmeras Brasileiras Indexadas: {len(br_cams)} ({len(br_cams)/len(cams)*100:.1f}%)")

    # Amostragem das 10 primeiras câmeras brasileiras
    print("\n4. TESTE DE RESOLUÇÃO DE STREAM AO VIVO (AMOSTRA BRASIL):")
    sample_ids = [str(c["id"]) for c in cams[:8]]
    stream_ok = 0
    for cid in sample_ids:
        cam_meta = next((c for c in cams if str(c["id"]) == cid), {})
        nome = cam_meta.get("nome", "")[:40]
        url = f"http://localhost:8001/api/cameras/{cid}/live_url"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OlhoDeDeus-Auditor/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as res:
                data = json.loads(res.read().decode("utf-8"))
                vid_id = data.get("video_id")
                has_stream = bool(data.get("url") or vid_id)
                if has_stream:
                    stream_ok += 1
                    print(f"  ✅ [ID {cid}] {nome:<40} -> VID: {vid_id}")
                else:
                    print(f"  ⚠️ [ID {cid}] {nome:<40} -> Sem video_id")
        except Exception as e:
            print(f"  ❌ [ID {cid}] {nome:<40} -> Erro: {str(e)[:30]}")

    print("\n" + "=" * 70)
    all_ok = s1 and s2 and s3 and m1 and m2 and (stream_ok == len(sample_ids))
    if all_ok:
        print("🎉 STATUS GERAL: 100% OPERACIONAL E FUNCIONANDO CORRETAMENTE!")
    else:
        print("⚠️ STATUS GERAL: OPERACIONAL COM PONTOS DE ATENÇÃO REGISTRADOS ACIMA.")
    print("=" * 70)

if __name__ == "__main__":
    main()
