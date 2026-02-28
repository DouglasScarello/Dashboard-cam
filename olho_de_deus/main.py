#!/usr/bin/env python3
"""
Olho de Deus - Módulo de captura de frames com suporte a arquivos locais

Objetivo:
- Ler frames de arquivos de vídeo local (MP4, AVI, MKV, etc.)
- Suportar navegação por frame (próximo/anterior)
- Preparar frames para futura análise de IA de reconhecimento facial

Requisitos (já instalados):
- opencv-python

Como usar (arquivo local):
$ python3 main.py --source /caminho/para/video.mp4 --mode file

Controles:
- Espaço: Pause/Resume
- Seta Direita (→): Próximo frame
- Seta Esquerda (←): Frame anterior
- 'r': Resetar para o início
- 'q': Sair
- '+'/'-': Ajustar intervalo de processamento (em modo auto)

"""

import time
import argparse
import sys
import os
from typing import Optional, Tuple

import cv2


class VideoPlayer:
    """Leitor de vídeo com suporte a navegação por frame."""

    def __init__(self, video_path: str):
        """Inicializa o leitor de vídeo."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {video_path}")

        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)

        if not self.cap.isOpened():
            raise RuntimeError(f"Não foi possível abrir o vídeo: {video_path}")

        # Propriedades do vídeo
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.current_frame_idx = 0
        self.paused = False

        print(f"[info] Vídeo carregado: {video_path}")
        print(f"[info]   Frames: {self.frame_count} | FPS: {self.fps:.1f} | Resolução: {self.frame_width}x{self.frame_height}")

    def read_frame(self) -> Optional[Tuple[bool, any]]:
        """Lê o frame atual. Retorna (sucesso, frame)."""
        ret, frame = self.cap.read()
        if ret:
            self.current_frame_idx = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        return ret, frame

    def set_frame(self, frame_idx: int) -> bool:
        """Posiciona o vídeo em um frame específico."""
        frame_idx = max(0, min(frame_idx, self.frame_count - 1))
        ret = self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        if ret:
            self.current_frame_idx = frame_idx
        return ret

    def next_frame(self) -> bool:
        """Avança para o próximo frame."""
        return self.set_frame(self.current_frame_idx + 1)

    def prev_frame(self) -> bool:
        """Volta para o frame anterior."""
        return self.set_frame(self.current_frame_idx - 1)

    def reset(self) -> bool:
        """Volta para o início do vídeo."""
        return self.set_frame(0)

    def get_position_str(self) -> str:
        """Retorna string com frame atual / total."""
        return f"Frame {self.current_frame_idx + 1}/{self.frame_count}"

    def close(self):
        """Fecha o leitor de vídeo."""
        if self.cap:
            self.cap.release()


def main():
    parser = argparse.ArgumentParser(
        description="Olho de Deus - Leitor de vídeo com navegação por frame"
    )
    parser.add_argument(
        "--source", 
        required=False,
        default=None,
        help="Caminho do arquivo de vídeo local (MP4, AVI, MKV, etc.)"
    )
    parser.add_argument(
        "--mode",
        required=False,
        default="file",
        choices=["file", "auto"],
        help="Modo de operação: 'file' (manual) ou 'auto' (processamento automático)"
    )
    parser.add_argument(
        "--interval",
        required=False,
        type=float,
        default=1.0,
        help="Intervalo em segundos entre frames a processar (modo auto)"
    )
    args = parser.parse_args()

    # Se não forneceu arquivo, pedir interativamente
    if not args.source:
        args.source = input("[input] Caminho do arquivo de vídeo: ").strip()

    if not args.source:
        print("[error] Nenhum arquivo fornecido.")
        sys.exit(1)

    # Inicializar leitor de vídeo
    try:
        player = VideoPlayer(args.source)
    except Exception as e:
        print(f"[error] Falha ao carregar vídeo: {e}")
        sys.exit(1)

    window_name = "Olho de Deus - Frame (Espaço: Pause | Setas: Next/Prev | R: Reset | Q: Sair)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 960, 540)

    print("[info] Controles:")
    print("  - Espaço: Pause/Resume")
    print("  - Seta Direita (→): Próximo frame")
    print("  - Seta Esquerda (←): Frame anterior")
    print("  - 'r': Resetar para o início")
    print("  - '+'/'-': Ajustar intervalo (modo auto)")
    print("  - 'q': Sair")

    last_processed = 0.0
    process_interval = max(0.001, args.interval)
    auto_play = args.mode == "auto"

    try:
        while True:
            # Ler frame
            ret, frame = player.read_frame()
            if not ret:
                print("[info] Fim do vídeo alcançado.")
                break

            now = time.time()

            # Modo auto: processar frames em intervalo
            if auto_play and now - last_processed >= process_interval:
                last_processed = now
                frame_for_processing = frame.copy()
                # TODO: Inserir IA de reconhecimento facial aqui
                # - Ex: results = face_model.detect(frame_for_processing)
            else:
                frame_for_processing = frame.copy()

            # Adicionar info de posição ao frame (overlay)
            info_text = player.get_position_str()
            status_text = "[AUTO]" if auto_play else "[MANUAL]"
            if player.paused:
                status_text += " [PAUSADO]"
            
            cv2.putText(
                frame_for_processing,
                f"{info_text} {status_text}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            # Exibir frame
            cv2.imshow(window_name, frame_for_processing)

            # Capturar input de teclado
            key = cv2.waitKey(30) & 0xFF

            if key == ord("q"):
                print("[info] Encerrando...")
                break
            elif key == ord(" "):  # Espaço: Pause/Resume
                player.paused = not player.paused
                status = "PAUSADO" if player.paused else "RETOMADO"
                print(f"[info] {status}")
            elif key == 83 or key == 2555904:  # Seta Direita
                if player.paused or not auto_play:
                    player.next_frame()
                    print(f"[info] Próximo frame: {player.get_position_str()}")
            elif key == 81 or key == 2424832:  # Seta Esquerda
                if player.paused or not auto_play:
                    player.prev_frame()
                    print(f"[info] Frame anterior: {player.get_position_str()}")
            elif key == ord("r"):
                player.reset()
                print("[info] Vídeo resetado para o início.")
            elif key == ord("+") or key == ord("="):
                process_interval = max(0.1, process_interval - 0.1)
                print(f"[info] Intervalo: {process_interval:.1f}s")
            elif key == ord("-"):
                process_interval = min(5.0, process_interval + 0.1)
                print(f"[info] Intervalo: {process_interval:.1f}s")

            # Em modo manual ou pausado, ficar esperando input
            if (not auto_play or player.paused) and key == 255:
                time.sleep(0.05)

    except KeyboardInterrupt:
        print("[info] Interrompido pelo usuário (KeyboardInterrupt)")

    finally:
        player.close()
        cv2.destroyAllWindows()
        print("[info] Encerrado com sucesso.")


if __name__ == "__main__":
    main()
