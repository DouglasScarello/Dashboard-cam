#!/usr/bin/env python3
"""
===============================================================================
VERIFICADOR DE STATUS AO VIVO EM MASSA (120 CÂMERAS EM PARALELO)
Valida cada stream com yt-dlp para checar se is_live == True em tempo real.
Se alguma câmera estiver offline ou for VOD gravado, marca como DEAD ou
remove para garantir uma base 100% AO VIVO.
===============================================================================
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Tuple

ROOT = Path(__file__).resolve().parent.parent
CAM_FILE = ROOT / "database" / "live_cameras.json"

def verify_single_cam(cam: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
    """Verifica se uma câmera está ativamente transmitindo ao vivo."""
    vid_id = cam.get("video_id")
    url = cam.get("url")
    target = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else url
    
    cmd = [
        "yt-dlp",
        target,
        "--print", "%(is_live)s ### %(live_status)s ### %(title)s",
        "--extractor-args", "youtube:player_client=android,web,ios",
        "--no-warnings",
        "--quiet",
        "--socket-timeout", "6"
    ]
    
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
        if proc.returncode == 0 and proc.stdout.strip():
            line = proc.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split("###")]
            is_live_str = parts[0].lower() if len(parts) > 0 else "false"
            live_status = parts[1].lower() if len(parts) > 1 else ""
            
            if is_live_str == "true" or live_status == "is_live":
                return cam, True, "ONLINE (AO VIVO)"
            else:
                return cam, False, f"OFFLINE (Status: {live_status})"
        else:
            return cam, False, f"ERRO ({proc.stderr.strip()[:40]})"
    except Exception as e:
        return cam, False, f"TIMEOUT / ERRO ({str(e)[:30]})"

def main():
    if not CAM_FILE.exists():
        print("Arquivo de câmeras não encontrado.")
        sys.exit(1)

    with open(CAM_FILE, "r", encoding="utf-8") as f:
        cams = json.load(f)

    print(f"🔍 Verificando status de {len(cams)} câmeras em tempo real (16 threads)...")
    t0 = time.time()

    live_cams = []
    dead_cams = []

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(verify_single_cam, c): c for c in cams}
        for future in as_completed(futures):
            cam, is_live, msg = future.result()
            cid = cam.get("id")
            nome = cam.get("nome", "")[:45]
            if is_live:
                live_cams.append(cam)
                print(f"  ✅ [ID {cid}] {nome:<45} -> {msg}")
            else:
                dead_cams.append(cam)
                print(f"  ❌ [ID {cid}] {nome:<45} -> {msg}")

    print("\n" + "=" * 70)
    print(f"📊 RESULTADO DA AUDITORIA AO VIVO (Tempo: {time.time() - t0:.2f}s):")
    print(f"  - Câmeras Confirmadas AO VIVO (100% ONLINE): {len(live_cams)}")
    print(f"  - Câmeras Offline/Finalizadas: {len(dead_cams)}")
    print("=" * 70)

    # Reindexar IDs das câmeras 100% confirmadas ao vivo
    for idx, c in enumerate(live_cams):
        c["id"] = 1000 + idx
        c["status"] = "LIVE"

    with open(CAM_FILE, "w", encoding="utf-8") as f:
        json.dump(live_cams, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Base database/live_cameras.json atualizada com {len(live_cams)} câmeras rigorosamente AO VIVO!")

if __name__ == "__main__":
    main()
