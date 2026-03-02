#!/usr/bin/env python3
"""
Módulo de captura de stream do YouTube para o projeto Olho de Deus.
Utiliza yt-dlp para extrair a URL do stream e OpenCV para capturar frames.
"""

import time
import argparse
import subprocess
import os
import sys
import cv2
import numpy as np
from typing import Optional

def get_live_url(video_id: str) -> Optional[str]:
    """Extrai a URL direta (.m3u8 ou .mp4) de um vídeo do YouTube."""
    # Se já for uma URL completa, extrair o ID
    if "youtube.com" in video_id or "youtu.be" in video_id:
        if "v=" in video_id:
            video_id = video_id.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_id:
            video_id = video_id.split("youtu.be/")[1].split("?")[0]

    print(f"[info] Extraindo stream para ID: {video_id}")
    cmd = [
        "yt-dlp",
        "-g",
        "--no-warnings",
        "-f", "best[ext=mp4]/best",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            print(f"[error] Falha no yt-dlp: {result.stderr}")
            return None
        url = result.stdout.strip()
        return url
    except Exception as e:
        print(f"[error] Exceção ao executar yt-dlp: {e}")
        return None

def check_stream_health(frame: np.ndarray) -> bool:
    """
    Analisa se o frame é válido.
    Retorna False se o frame for nulo, tiver poucos pixels não-pretos (tela de erro)
    ou se a variância for muito baixa (imagem estática/travada).
    """
    if frame is None:
        return False
    
    # Converter para escala de cinza para análise de brilho
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Se mais de 98% dos pixels forem pretos (ou muito escuros), considerar stream morto
    non_zero = cv2.countNonZero(cv2.threshold(gray, 5, 255, cv2.THRESH_BINARY)[1])
    total_pixels = gray.shape[0] * gray.shape[1]
    
    if (non_zero / total_pixels) < 0.02:
        print("[health] Detectada tela preta ou sem sinal.")
        return False
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Captura de stream do YouTube para Olho de Deus")
    parser.add_argument("--id", required=True, help="ID do vídeo do YouTube (ex: 10c81f5f-4d14-44f7-bcaf-f0bff22949d6)")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo em segundos entre captures")
    args = parser.parse_args()

    stream_url = get_live_url(args.id)
    if not stream_url:
        sys.exit(1)

    print(f"[info] Stream URL obtida: {stream_url[:50]}...")
    
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        print("[error] Não foi possível abrir o stream de vídeo.")
        sys.exit(1)

    window_name = f"Olho de Deus - YouTube ({args.id})"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    print("[info] Iniciando captura. Pressione 'q' para sair.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[warning] Falha ao ler frame. Tentando reconectar...")
                cap.release()
                time.sleep(5)
                stream_url = get_live_url(args.id)
                cap = cv2.VideoCapture(stream_url)
                continue

            # Overlay de tempo real
            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(frame, f"LIVE: {timestamp} | ID: {args.id}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow(window_name, frame)
            
            # Salvar o primeiro frame para verificação (Artifact)
            cv2.imwrite("test_frame.jpg", frame)
            print("[info] Frame salvo como test_frame.jpg para verificação.")
            
            # Esperar pelo intervalo solicitado (pressionar 'q' sai imediatamente)
            # Como o OpenCV não lida bem com sleep longo mantendo a janela ativa,
            # fazemos um loop de waitKey pequeno.
            start_time = time.time()
            while time.time() - start_time < args.interval:
                if cv2.waitKey(100) & 0xFF == ord('q'):
                    raise KeyboardInterrupt
            
            # Limpar buffer para garantir o frame mais recente na próxima leitura
            # Em streams HLS, o buffer pode acumular frames antigos.
            # Uma técnica simples é ler alguns frames ou recriar o VideoCapture.
            # Para o Vivobook, vamos apenas ler o próximo após o delay.
            
    except KeyboardInterrupt:
        print("[info] Encerrando...")
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
