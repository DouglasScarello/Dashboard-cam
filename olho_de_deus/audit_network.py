#!/usr/bin/env python3
import json
import cv2
import yt_dlp
import numpy as np
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Configurações de Caminho
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "omni_cams.json"

class NetworkAuditor:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestvideo[height<=720]/best',
            'quiet': True,
            'no_warnings': True
        }

    def load_cams(self):
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def check_health(self, frame):
        """Avalia se o frame é 'saudável' (não preto, não cinza estático)."""
        if frame is None: return "DEAD"
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg_brightness = np.mean(gray)
        std_dev = np.std(gray)
        
        if avg_brightness < 10: return "BLACK_FRAME"
        if std_dev < 2: return "FROZEN/NOISE"
        
        return "HEALTHY"

    def audit_camera(self, cam):
        print(f"[AUDIT] Verificando: {cam['nome'][:40]}...")
        url = cam['url']
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                res_w = info.get('width', 0)
                res_h = info.get('height', 0)

            cap = cv2.VideoCapture(stream_url)
            ret, frame = cap.read()
            
            if not ret:
                status = "OFFLINE"
            else:
                status = self.check_health(frame)
            
            cap.release()
            
            return {
                "id": cam['id'],
                "nome": cam['nome'],
                "status": status,
                "res": f"{res_w}x{res_h}" if res_w else "N/A"
            }

        except Exception as e:
            return {
                "id": cam['id'],
                "nome": cam['nome'],
                "status": "ERROR",
                "res": "N/A"
            }

    def run_full_audit(self, workers=4):
        cams = self.load_cams()
        results = []
        
        print(f"\n🚀 Iniciando Auditoria Global em {len(cams)} câmeras...")
        print(f"Parallel Workers: {workers}\n")
        
        # Usamos threads para não travar no I/O de rede/yt-dlp
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(self.audit_camera, cams))
        
        self.report(results)

    def report(self, results):
        print(f"\n{'='*70}")
        print(f" RELATÓRIO DE QUALIDADE OSS - {time.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"{'='*70}")
        
        healthy = [r for r in results if r['status'] == "HEALTHY"]
        issues = [r for r in results if r['status'] != "HEALTHY"]
        
        print(f"✅ OPERACIONAIS: {len(healthy)}")
        print(f"⚠️ COM FALHA: {len(issues)}")
        print(f"{'='*70}\n")
        
        for r in results:
            indicator = "🟢" if r['status'] == "HEALTHY" else "🔴"
            print(f"{indicator} [{r['res']}] {r['nome'][:50]} -> {r['status']}")

if __name__ == "__main__":
    auditor = NetworkAuditor()
    auditor.run_full_audit()
