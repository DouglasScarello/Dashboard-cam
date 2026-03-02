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
from biometric_processor import BiometricProcessor

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
        self.biometric_processor = BiometricProcessor()
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

                # --- ANÁLISE BIOMÉTRICA (HUD TÁTICO) ---
                display_frame = frame.copy()
                h, w = display_frame.shape[:2]
                
                # Processar biometria
                biometric_results = self.biometric_processor.process_frame(frame)
                
                for res in biometric_results:
                    x1, y1, x2, y2 = res["box"]
                    match = res["match"]
                    
                    # Definir cor baseado no risco (Verde = Neutro, Amarelo = Baixo Risco, Vermelho = Match FBI)
                    color = (0, 255, 0) # Verde padrão
                    label = "DESCONHECIDO"
                    
                    if match:
                        color = (0, 0, 255) # Vermelho (Match)
                        label = f"ALERTA: {match['title']}"
                        # Overlay de metadados do Match
                        cv2.rectangle(display_frame, (x1, y2 + 5), (x1 + 300, y2 + 45), (0, 0, 0), -1)
                        cv2.putText(display_frame, label, (x1 + 5, y2 + 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                    # Bounding Box Estilizada (Canto)
                    length = 20
                    thickness = 2
                    # Top-Left
                    cv2.line(display_frame, (x1, y1), (x1 + length, y1), color, thickness)
                    cv2.line(display_frame, (x1, y1), (x1, y1 + length), color, thickness)
                    # Top-Right
                    cv2.line(display_frame, (x1 + (x2-x1), y1), (x1 + (x2-x1) - length, y1), color, thickness)
                    cv2.line(display_frame, (x1 + (x2-x1), y1), (x1 + (x2-x1), y1 + length), color, thickness)
                    # Bottom-Left
                    cv2.line(display_frame, (x1, y1 + (y2-y1)), (x1 + length, y1 + (y2-y1)), color, thickness)
                    cv2.line(display_frame, (x1, y1 + (y2-y1)), (x1, y1 + (y2-y1) - length), color, thickness)
                    # Bottom-Right
                    cv2.line(display_frame, (x1 + (x2-x1), y1 + (y2-y1)), (x1 + (x2-x1) - length, y1 + (y2-y1)), color, thickness)
                    cv2.line(display_frame, (x1 + (x2-x1), y1 + (y2-y1)), (x1 + (x2-x1), y1 + (y2-y1) - length), color, thickness)

                # Barra de Status Superior (Estilo FBI/OSS)
                cv2.rectangle(display_frame, (0, 0), (w, 40), (0, 0, 0), -1)
                monitor_label = self.youtube_id if self.youtube_id else "LOCAL"
                status_text = f"OSS v0.2-BIO | STATUS: ATIVO | ALVO: {monitor_label}"
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

    def play_forensic(self, step: float = 2.0):
        """
        Modo Forênsico com Player Netflix/YouTube:
          SPACE        — play/pause (auto-avança)
          → / D        — +step segundos
          ← / A        — -step segundos (buffer)
          Clique na barra de progresso — saltar para posição
          S            — salvar frame
          Q / ESC      — sair
        """
        if not self.cap:
            print("[error] Não foi possível iniciar.")
            return

        print(f"\n[forense] Player Netflix-style ativo (step={step}s)")
        print("[controle] SPACE=play/pause | ←→=navegar | CLICK na barra=seek | S=salvar | Q=sair\n")

        frame_buffer = {}
        buffer_idx = -1
        playing = False
        play_interval = step
        last_play_time = 0.0
        mouse_state = {"x": -1, "y": -1, "click": False}

        # --- Info do vídeo ---
        fps        = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        total_sec  = total_frames / fps if total_frames > 0 else 0
        is_stream  = (total_frames <= 0 or self.youtube_id is not None)

        def _fmt(sec):
            m, s = divmod(int(sec), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        BAR_H = 72
        SEEK_Y_rel = 18

        def _draw_player(df, cur_frame, is_playing):
            """Seek bar baseada na duração real do vídeo."""
            h, w = df.shape[:2]
            # Guard: frame muito pequeno causa QFont::setPointSizeF <= 0
            if h < 80 or w < 80:
                return df.copy(), (16, max(w-16, 17), 0, 0, 50, max(w//2, 1))
            out = df.copy()

            # Barra inferior semitransparente
            overlay = out.copy()
            cv2.rectangle(overlay, (0, h - BAR_H), (w, h), (10, 10, 10), -1)
            cv2.addWeighted(overlay, 0.85, out, 0.15, 0, out)

            bar_y  = h - BAR_H + SEEK_Y_rel
            bar_x0, bar_x1 = 16, w - 16

            # Progresso: frame atual vs total
            if is_stream or total_frames <= 0:
                # Stream ao vivo: usar buffer como referência
                buf_count = len(frame_buffer)
                progress = (buffer_idx / max(buf_count - 1, 1)) if buf_count > 1 else 0
            else:
                progress = min(cur_frame / max(total_frames - 1, 1), 1.0)

            dot_x = int(bar_x0 + progress * (bar_x1 - bar_x0))

            # Trilha
            cv2.line(out, (bar_x0, bar_y), (bar_x1, bar_y), (70, 70, 70), 3, cv2.LINE_AA)
            cv2.line(out, (bar_x0, bar_y), (dot_x, bar_y), (0, 60, 220), 4, cv2.LINE_AA)
            cv2.circle(out, (dot_x, bar_y), 8, (30, 100, 255), -1, cv2.LINE_AA)
            cv2.circle(out, (dot_x, bar_y), 8, (220, 220, 255), 1, cv2.LINE_AA)

            # Tempo atual / total
            _safe_fps = max(fps, 1.0)
            cur_sec   = max(0.0, cur_frame / _safe_fps)
            time_cur  = _fmt(cur_sec)
            time_tot  = _fmt(total_sec) if not is_stream else "AO VIVO"
            text_y    = max(14, bar_y - 6)  # nunca coordenada negativa
            cv2.putText(out, f"{time_cur} / {time_tot}",
                        (bar_x0, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180,180,180), 1)

            # Botões
            btn_y  = h - BAR_H + 52
            btn_col = (210, 210, 210)
            cx = w // 2

            # ⏮ Voltar
            cv2.rectangle(out, (bar_x0, btn_y-9), (bar_x0+3, btn_y+9), btn_col, -1)
            cv2.fillPoly(out, [np.array([[bar_x0+14,btn_y-9],[bar_x0+4,btn_y],[bar_x0+14,btn_y+9]],np.int32)], btn_col)

            # ▶ / ⏸
            if is_playing:
                cv2.rectangle(out, (cx-13, btn_y-10), (cx-5, btn_y+10), btn_col, -1)
                cv2.rectangle(out, (cx+5,  btn_y-10), (cx+13, btn_y+10), btn_col, -1)
            else:
                cv2.fillPoly(out, [np.array([[cx-10,btn_y-12],[cx+13,btn_y],[cx-10,btn_y+12]],np.int32)], btn_col)

            # ⏭ Avançar
            cv2.rectangle(out, (bar_x1-3, btn_y-9), (bar_x1, btn_y+9), btn_col, -1)
            cv2.fillPoly(out, [np.array([[bar_x1-14,btn_y-9],[bar_x1-4,btn_y],[bar_x1-14,btn_y+9]],np.int32)], btn_col)

            return out, (bar_x0, bar_x1, bar_y, h - BAR_H, btn_y, cx)

        def _on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                mouse_state["x"] = x
                mouse_state["y"] = y
                mouse_state["click"] = True

        cv2.setMouseCallback(self.window_name, _on_mouse)

        def _capture_and_analyze():
            if step > 0 and self.youtube_id is None:
                fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
                skip = int(fps * step)
                pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos + skip)
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            h, w = frame.shape[:2]
            df = frame.copy()
            bio = self.biometric_processor.process_frame(frame)
            alert_count = 0
            for res in bio:
                x1, y1, x2, y2 = res["box"]
                match = res.get("match")
                color = (0, 0, 255) if match else (0, 200, 60)
                ln, th = 18, 2
                for (px,py,dx,dy) in [(x1,y1,1,0),(x1,y1,0,1),(x2,y1,-1,0),(x2,y1,0,1),
                                       (x1,y2,1,0),(x1,y2,0,-1),(x2,y2,-1,0),(x2,y2,0,-1)]:
                    cv2.line(df,(px,py),(px+dx*ln,py+dy*ln),color,th,cv2.LINE_AA)
                if match:
                    alert_count += 1
                    cv2.rectangle(df,(x1,y2+4),(x1+260,y2+38),(0,0,0),-1)
                    cv2.putText(df,f"\u26a0 {match['title'][:28]}",(x1+5,y2+26),
                                cv2.FONT_HERSHEY_SIMPLEX,0.44,(0,230,230),1)
            # Top status bar
            cv2.rectangle(df,(0,0),(w,40),(10,10,10),-1)
            ts = time.strftime("%H:%M:%S")
            lbl = self.youtube_id or "LOCAL"
            cv2.putText(df,f"OSS FORENSE | {ts} | Faces:{len(bio)} Alertas:{alert_count} | {lbl}",
                        (10,26),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,90),1)
            ic = (0,30,200) if alert_count>0 else (0,180,0)
            cv2.circle(df,(w-18,20),7,ic,-1,cv2.LINE_AA)
            return df

        try:
            df = _capture_and_analyze()
            if df is not None:
                cur_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                frame_buffer[cur_frame] = df
                buffer_idx = cur_frame

            bx0, bx1, seek_y, bar_top, btn_y, cx = 16, 1264, 0, 0, 50, 640

            while True:
                current_time = time.time()

                # Auto-play
                if playing and (current_time - last_play_time) >= play_interval:
                    last_play_time = current_time
                    df = _capture_and_analyze()
                    if df is not None:
                        cur_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                        frame_buffer[cur_frame] = df
                        buffer_idx = cur_frame
                        # Limitar buffer a 60 entradas
                        if len(frame_buffer) > 60:
                            oldest = min(frame_buffer.keys())
                            del frame_buffer[oldest]
                    else:
                        playing = False

                # Renderizar
                if buffer_idx in frame_buffer:
                    nav, (bx0, bx1, seek_y, bar_top, btn_y, cx) = _draw_player(
                        frame_buffer[buffer_idx], buffer_idx, playing)
                    cv2.imshow(self.window_name, nav)

                # Mouse seek
                if mouse_state["click"]:
                    mx, my = mouse_state["x"], mouse_state["y"]
                    mouse_state["click"] = False

                    # Click na seek bar
                    if bar_top - 14 <= my <= bar_top + 14 and bx0 <= mx <= bx1:
                        ratio = (mx - bx0) / max(bx1 - bx0, 1)
                        if is_stream:
                            keys = sorted(frame_buffer.keys())
                            target_idx = min(int(ratio * len(keys)), len(keys)-1)
                            buffer_idx = keys[target_idx]
                        else:
                            target_frame = int(ratio * total_frames)
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                            df = _capture_and_analyze()
                            if df is not None:
                                cur_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                                frame_buffer[cur_frame] = df
                                buffer_idx = cur_frame

                    # Click no botão play/pause
                    if abs(my - btn_y) < 18 and abs(mx - cx) < 20:
                        playing = not playing
                        last_play_time = current_time

                key = cv2.waitKey(30) & 0xFF

                if key in (ord('q'), 27):
                    break
                elif key == ord(' '):
                    playing = not playing
                    last_play_time = current_time
                elif key in (83, ord('d')):  # →
                    playing = False
                    if not is_stream:
                        pos = buffer_idx + int(fps * step)
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                    df = _capture_and_analyze()
                    if df is not None:
                        cur_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                        frame_buffer[cur_frame] = df
                        buffer_idx = cur_frame
                elif key in (81, ord('a')):  # ←
                    playing = False
                    keys = sorted(frame_buffer.keys())
                    if keys:
                        i = keys.index(buffer_idx) if buffer_idx in keys else len(keys)-1
                        if i > 0:
                            buffer_idx = keys[i - 1]
                        elif not is_stream and buffer_idx > 0:
                            # Seek back no arquivo
                            pos = max(0, buffer_idx - int(fps * step))
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                            df = _capture_and_analyze()
                            if df is not None:
                                cur_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                                frame_buffer[cur_frame] = df
                                buffer_idx = cur_frame
                elif key == ord('s'):
                    if buffer_idx in frame_buffer:
                        fname = f"forense_{int(time.time())}.jpg"
                        cv2.imwrite(fname, frame_buffer[buffer_idx])
                        print(f"[forense] Salvo: {fname}")

        except KeyboardInterrupt:
            print("[info] Encerrando player...")
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
    parser.add_argument("--forensic", action="store_true", help="Modo forense: frame-a-frame com navegação por teclado")
    parser.add_argument("--step", type=float, default=2.0, help="Segundos a pular no modo forense (padrão: 2s)")
    
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

    # Iniciar monitoramento
    monitor = VideoMonitor(video_source, youtube_id=stream_id)
    if args.forensic:
        monitor.play_forensic(step=args.step)
    else:
        monitor.play(interval=args.interval)

if __name__ == "__main__":
    main()
