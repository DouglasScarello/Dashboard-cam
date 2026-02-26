#!/usr/bin/env python3
"""
Olho de Deus - Módulo de captura de frames de lives do YouTube

Objetivo:
- Conectar em uma live do YouTube usando apenas a URL
- Forçar captura em resolução reduzida (<= 480p) para economizar CPU/RAM
- Entregar 1 frame por segundo para futura análise de IA

Requisitos (já instalados no seu ambiente conda):
- vidgear[core]
- yt-dlp
- opencv-python

Como usar (exemplo):
$ python3 main.py --url "https://www.youtube.com/watch?v=u4UZ4UvZXrg" --interval 1

"""

import time
import argparse
import sys
from typing import Optional

import cv2
from vidgear.gears import CamGear
from yt_dlp import YoutubeDL


def get_stream_url(youtube_url: str, max_height: int = 480) -> Optional[str]:
    """Extrai a melhor URL de stream adaptada ao `max_height` usando yt-dlp.

    Retorna a URL direta do formato escolhido (geralmente m3u8 ou https) que
    pode ser consumida pelo ffmpeg/CamGear.
    """
    ydl_opts = {
        "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]",
        "quiet": True,
        "no_warnings": True,
        # minimiza logs; não baixa o vídeo (download=False quando extrair info)
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

    # Se for vida (live), 'formats' normalmente existe
    formats = info.get("formats") or []

    # Ordena por height desc e pega a primeira que tenha 'url'
    viable = [f for f in formats if f.get("url") and f.get("height")]
    viable = sorted(viable, key=lambda x: (x.get("height") or 0), reverse=True)

    for f in viable:
        if f.get("height") and f["height"] <= max_height:
            return f["url"]

    # Fallback: se não encontrou formatos com height, tenta usar webpage_url ou url principal
    return info.get("url") or info.get("webpage_url")


def init_camera(stream_url: str, logging: bool = False) -> CamGear:
    """Inicializa CamGear apontando para a URL do stream.

    Observação: passamos a stream_url direta para o CamGear/ffmpeg para maior controle.
    """
    cam = CamGear(source=stream_url, y_tube=False, logging=logging).start()
    return cam


def main():
    parser = argparse.ArgumentParser(description="Olho de Deus - captura reduzida de lives YouTube")
    parser.add_argument("--url", required=False, default="https://www.youtube.com/watch?v=u4UZ4UvZXrg",
                        help="URL da live do YouTube")
    parser.add_argument("--interval", required=False, type=float, default=1.0,
                        help="Intervalo em segundos entre frames que serão separados para processamento (padrão=1s)")
    parser.add_argument("--max-height", required=False, type=int, default=480,
                        help="Altura máxima do vídeo a ser solicitada via yt-dlp (ex: 360, 480)")
    args = parser.parse_args()

    youtube_url = args.url
    process_interval = max(0.001, args.interval)
    max_height = args.max_height

    print(f"[info] Extrair stream reduzido de: {youtube_url} (<= {max_height}p)")
    try:
        stream_url = get_stream_url(youtube_url, max_height=max_height)
    except Exception as e:
        print(f"[error] Falha ao obter stream: {e}")
        sys.exit(1)

    if not stream_url:
        print("[error] Não foi possível extrair uma URL de stream válida.")
        sys.exit(1)

    print(f"[info] Stream direta obtida: {stream_url[:120]}{'...' if len(stream_url) > 120 else ''}")
    print("[info] Iniciando captura via CamGear (ffmpeg)...")

    cam = None
    try:
        cam = init_camera(stream_url, logging=False)
    except Exception as e:
        print(f"[error] Falha ao iniciar CamGear: {e}")
        sys.exit(1)

    last_processed = 0.0
    window_name = "Olho de Deus - Frame para IA (pressione q para sair)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 960, 540)

    print("[info] Loop de captura iniciado. Pressione 'q' para encerrar.")

    try:
        while True:
            frame = cam.read()
            # CamGear retorna None quando stream momentaneamente não fornece frame
            if frame is None:
                # evita tight-loop muito pesado
                time.sleep(0.01)
                continue

            now = time.time()
            # Se passou o intervalo configurado, marca este frame para processamento
            if now - last_processed >= process_interval:
                last_processed = now

                # Aqui é o frame que será enviado para o pipeline de IA no futuro
                frame_for_processing = frame.copy()

                # Exibe o frame para debug
                cv2.imshow(window_name, frame_for_processing)

                # TODO: Inserir IA de reconhecimento facial aqui
                # - Ex: results = face_model.detect(frame_for_processing)
                # - Enviar resultados via IPC/REST/Queue para o painel (Tauri) se necessário

            # Mesmo quando não processamos, ainda permitimos fechar a janela
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("[info] Tecla 'q' detectada — encerrando...")
                break

            # pequena pausa para reduzir uso de CPU quando não processando
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("[info] Interrompido pelo usuário (KeyboardInterrupt)")

    finally:
        # Limpeza
        try:
            if cam is not None:
                cam.stop()
        except Exception:
            pass
        cv2.destroyAllWindows()
        print("[info] Encerrado com sucesso.")


if __name__ == "__main__":
    main()
