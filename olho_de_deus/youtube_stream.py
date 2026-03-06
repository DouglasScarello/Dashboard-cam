#!/usr/bin/env python3
"""
Módulo de captura de stream do YouTube para o projeto Olho de Deus.
Utiliza yt-dlp para extrair a URL do stream e OpenCV para capturar frames.
"""

import os
import time
import argparse
import subprocess
import logging
import sys
import cv2
import numpy as np
from typing import Optional

log = logging.getLogger(__name__)

def get_live_url(
    video_id: str,
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Optional[str]:
    """Extrai a URL direta (.m3u8 ou .mp4) de um vídeo do YouTube.
    Para contornar 'Sign in to confirm you're not a bot', use cookies_browser (ex: firefox, chrome)
    ou cookies_file (caminho para arquivo Netscape/cookies.txt).
    Variáveis de ambiente: YT_DLP_COOKIES_FROM_BROWSER, YT_DLP_COOKIES_FILE.
    """
    if "youtube.com" in video_id or "youtu.be" in video_id:
        if "v=" in video_id:
            video_id = video_id.split("v=")[1].split("&")[0]
        elif "/live/" in video_id:
            # Formato: youtube.com/live/ID?si=...
            video_id = video_id.split("/live/")[1].split("?")[0]
        elif "youtu.be/" in video_id:
            video_id = video_id.split("youtu.be/")[1].split("?")[0]

    cookies_browser = cookies_browser or os.environ.get("YT_DLP_COOKIES_FROM_BROWSER")
    cookies_file = cookies_file or os.environ.get("YT_DLP_COOKIES_FILE")

    log.info(f"Extraindo stream para ID: {video_id}")
    cmd = [
        "yt-dlp",
        "-g",
        "--no-warnings",
        "-f", "best[ext=mp4]/best",
    ]
    if cookies_browser:
        cmd.extend(["--cookies-from-browser", cookies_browser])
    if cookies_file:
        cmd.extend(["--cookies", cookies_file])
    cmd.append(f"https://www.youtube.com/watch?v={video_id}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            log.error(f"Falha no yt-dlp: {result.stderr}")
            return None
        url = result.stdout.strip()
        return url
    except Exception as e:
        log.error(f"Exceção ao executar yt-dlp: {e}")
        return None

def check_stream_health(frame: np.ndarray) -> bool:
    """
    Analisa se o frame é válido.
    Retorna False se o frame for nulo ou tiver pixels insuficientes (tela preta/morta).
    """
    if frame is None:
        return False
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    non_zero = cv2.countNonZero(cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY)[1])
    total_pixels = gray.shape[0] * gray.shape[1]
    
    if (non_zero / total_pixels) < 0.02:
        log.warning("Detectada tela preta ou sem sinal.")
        return False
        
    return True

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [STREAM] %(message)s")
    
    parser = argparse.ArgumentParser(description="Captura de stream do YouTube para Olho de Deus")
    parser.add_argument("--id", required=True, help="ID do vídeo do YouTube")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo em segundos entre captures")
    args = parser.parse_args()

    stream_url = get_live_url(args.id)
    if not stream_url:
        sys.exit(1)

    log.info(f"Stream URL obtida: {stream_url[:50]}...")
    
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        log.error("Não foi possível abrir o stream de vídeo.")
        sys.exit(1)

    window_name = f"Olho de Deus - YouTube ({args.id})"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    log.info("Iniciando captura. Pressione 'q' para sair.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("Falha ao ler frame. Tentando reconectar...")
                cap.release()
                time.sleep(5)
                stream_url = get_live_url(args.id)
                cap = cv2.VideoCapture(stream_url)
                continue

            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(frame, f"LIVE: {timestamp} | ID: {args.id}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow(window_name, frame)
            
            start_time = time.time()
            while time.time() - start_time < args.interval:
                if cv2.waitKey(100) & 0xFF == ord('q'):
                    raise KeyboardInterrupt
            
    except KeyboardInterrupt:
        log.info("Encerrando...")
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
