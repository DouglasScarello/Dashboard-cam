#!/usr/bin/env python3
"""
Olho de Deus - Módulo Central de Monitoramento
Suporta: Arquivos Locais, Streams de YouTube e Estrutura Geográfica.
"""

import time
import argparse
import sys
import os
import json
from typing import Optional, Tuple, List, Dict

import cv2
import yt_dlp
import numpy as np

# Importar o módulo de stream se estiver no mesmo diretório
try:
    from youtube_stream import get_live_url, check_stream_health
except ImportError:
    # Fallback se rodar de outro lugar
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from youtube_stream import get_live_url, check_stream_health

class CameraLoader:
    """Gerencia a hierarquia de câmeras do arquivo JSON."""
    def __init__(self, json_path: str):
        if not os.path.exists(json_path):
            self.data = {}
        else:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)

    def find_camera(self, name: str) -> Optional[dict]:
        """Busca câmera pelo nome em toda a hierarquia."""
        for country in self.data.values():
            for state in country.get("states", {}).values():
                for city in state.get("cities", {}).values():
                    for cam in city.get("cameras", []):
                        if name.lower() in cam["name"].lower():
                            return cam
        return None

    def list_locations(self):
        """Lista a estrutura disponível."""
        print("\n[info] Localizações disponíveis:")
        for country_code, country in self.data.items():
            print(f"  - {country['name']} ({country_code})")
            for state_code, state in country.get("states", {}).items():
                print(f"    - {state['name']} ({state_code})")
                for city_name in state.get("cities", {}).keys():
                    print(f"      - {city_name}")

class VideoMonitor:
    """Gerencia a captura e exibição de vídeo com auto-healing."""
    def __init__(self, source: str, youtube_id: Optional[str] = None):
        self.source = source
        self.youtube_id = youtube_id
        self.cap = self._init_capture()
        self.window_name = "Olho de Deus - OSS"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 1280, 720)

    def _init_capture(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"[error] Falha ao abrir fonte: {self.source}")
            return None
        return cap

    def play(self, interval: float = 2.0):
        """Inicia o loop de captura e processamento."""
        if not self.cap:
            print("[error] Não foi possível iniciar o monitoramento devido a falha na fonte.")
            return

        print(f"\n[sistema] Iniciando monitoramento (Intervalo: {interval}s)")
        print("[controle] 'q' para sair | 's' para salvar frame\n")

        last_time = 0
        consecutive_failures = 0
        
        try:
            while True:
                current_time = time.time()
                
                # Controle de intervalo de processamento
                if (current_time - last_time) < interval:
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                    continue

                ret, frame = self.cap.read()

                # --- AUTO-HEALING LOGIC ---
                is_healthy = check_stream_health(frame) if ret else False
                
                if not ret or not is_healthy:
                    consecutive_failures += 1
                    status_msg = "ERRO DE CAPTURA" if not ret else "STREAM INVÁLIDA (TELA PRETA)"
                    print(f"[warning] {status_msg} ({consecutive_failures}/3)") # Changed to 3 for consistency with snippet
                    
                    if consecutive_failures >= 3: # Changed to 3 for consistency with snippet
                        print("[auto-healing] Tentando re-sincronizar stream...")
                        # Se for YouTube, tentar pegar nova URL
                        if self.youtube_id:
                            new_url = get_live_url(self.youtube_id)
                            if new_url:
                                self.source = new_url
                            else:
                                print("[error] Não foi possível obter nova URL do stream. Encerrando.")
                                break
                        
                        self.cap.release()
                        self.cap = self._init_capture()
                        if not self.cap:
                            print("[error] Falha ao re-inicializar a captura. Encerrando.")
                            break
                        consecutive_failures = 0
                        time.sleep(2)
                    
                    last_time = current_time
                    continue
                
                consecutive_failures = 0 # Reset se o frame for bom
                last_time = current_time

                # Exibição e Interface
                display_frame = frame.copy()
                
                # Barra de Status Superior (Estilo FBI/OSS)
                h, w = display_frame.shape[:2]
                cv2.rectangle(display_frame, (0, 0), (w, 40), (0, 0, 0), -1)
                monitor_label = self.youtube_id if self.youtube_id else "LOCAL"
                status_text = f"OSS v0.1 | STATUS: AO VIVO | MONITOR: {monitor_label}"
                cv2.putText(display_frame, status_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                # Health Indicator
                cv2.circle(display_frame, (w - 20, 20), 8, (0, 255, 0), -1)

                cv2.imshow(self.window_name, display_frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    timestamp = int(time.time())
                    filename = f"capture_{timestamp}.jpg"
                    cv2.imwrite(filename, frame)
                    print(f"[info] Frame salvo: {filename}")

        except KeyboardInterrupt:
            print("[info] Encerrando...")
        finally:
            if self.cap:
                self.cap.release()
            cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description="Olho de Deus - Monitoramento Inteligente")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source", help="Caminho do arquivo de vídeo local")
    group.add_argument("--cam", help="Nome da câmera no registro (ex: 'Koxixos', 'Ponte')")
    group.add_argument("--id", help="ID direto do YouTube")
    
    parser.add_argument("--mode", default="auto", choices=["file", "auto"], help="Modo de operação")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo em segundos (Vivobook: 2-5s)")
    parser.add_argument("--list", action="store_true", help="Listar câmeras e locais disponíveis")
    
    args = parser.parse_args()

    loader = CameraLoader("cameras.json")

    if args.list:
        loader.list_locations()
        sys.exit(0)

    video_source = None
    stream_id = None

    if args.source:
        video_source = args.source
    elif args.cam:
        cam_data = loader.find_camera(args.cam)
        if cam_data:
            print(f"[info] Câmera encontrada: {cam_data['name']} ({cam_data['description']})")
            stream_id = cam_data["id"]
        else:
            print(f"[error] Câmera '{args.cam}' não encontrada.")
            sys.exit(1)
    elif args.id:
        stream_id = args.id
    else:
        print("[warning] Nenhuma fonte especificada. Use --source, --cam, --id ou --list.")
        sys.exit(1)

    # Se for stream do YouTube, obter a URL real
    if stream_id:
        video_source = get_live_url(stream_id)
        if not video_source:
            print("[error] Não foi possível obter URL do stream.")
            sys.exit(1)

    # Iniciar monitoramento usando a nova classe VideoMonitor (Auto-Healing)
    monitor = VideoMonitor(video_source, youtube_id=stream_id)
    monitor.play(interval=args.interval)

if __name__ == "__main__":
    main()
