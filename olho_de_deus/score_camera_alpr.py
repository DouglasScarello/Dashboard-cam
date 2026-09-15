"""
score_camera_alpr.py — Olho de Deus

Mede, com número em vez de palpite, se uma câmera serve pra leitura de placa.

Motivo (2026-09-14): a câmera de Tubarão foi descartada pra ALPR depois de eu
comparar ela no olho com a de Davao, que funciona. Deu pra concluir que o
problema era geometria (poste alto, ângulo oblíquo) e não resolução — o recorte
da placa em Tubarão tem 120x65px, MAIOR que os 102x47 de Davao que leem bem.
Mas fazer isso câmera por câmera, no olho, não escala e vira chute. Este script
faz a mesma comparação de forma reproduzível: captura N frames ao vivo, roda o
mesmo YOLO do pipeline de produção, e reporta as taxas cruas.

A métrica que separa as águas é a TAXA DE DETECÇÃO: o detector achou uma placa
em quantos por cento dos frames? Em Tubarão dá perto de zero mesmo com carro
passando na frente. Nitidez e contraste vêm junto porque explicam o *porquê*
quando a taxa é baixa.

Não escreve no banco. Só lê câmeras e cospe relatório — promover câmera pro
pipeline de produção é decisão humana.

Uso:
    poetry run python3 score_camera_alpr.py --all-candidates --json /tmp/triagem.json
    poetry run python3 score_camera_alpr.py --camera-id globetv_davao_leongarcia --frames 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import cv2
import numpy as np

import db_manager
from camera_grid_server import _capture_real_frame_jpeg
from forensic_sr_engine import alpr_engine, quality_assessor
from plate_processor import VEHICLE_CLASSES

# Caminho e limiares COPIADOS do pipeline de produção (monitor_plates.py:49 e
# plate_processor.py:_attempt_read). Não inventar número aqui: a triagem só vale
# alguma coisa se ela mede exatamente o que o serviço 24/7 vai enfrentar.
YOLO_VEICULO = str(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "yolov8n_openvino_model"))
CONF_VEICULO = 0.3
CONF_PLACA = 0.25

# Uma placa precisa de ~70px de largura pra o OCR ter chance. Abaixo disso o
# detector pode até achar, mas não sobra caractere pra ler. Número vindo da
# medição real: Davao lê com recortes de 77-102px de largura, e no log de
# produção os recortes abaixo de 60px saem todos como leu=None.
LARGURA_MINIMA_UTIL = 70

_detector_veiculo = None


def _get_detector_veiculo():
    global _detector_veiculo
    if _detector_veiculo is None:
        from ultralytics import YOLO
        _detector_veiculo = YOLO(YOLO_VEICULO, task="detect")
    return _detector_veiculo


def _analisa_frame(jpeg_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Replica o pipeline de PRODUÇÃO num frame: YOLO acha o veículo, e só
    dentro do recorte do veículo é que procura a placa.

    Achado (2026-09-14): a primeira versão disto rodava o detector de placa no
    frame 1920x1080 inteiro e dava 0% de detecção até em Davao, que funciona em
    produção há dias. Uma placa ocupa ~0,03% de um frame desses — o YOLO
    simplesmente não a enxerga nessa escala. Medir diferente da produção não
    mede nada.
    """
    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    altura, largura = frame.shape[:2]
    resultado: Dict[str, Any] = {
        "resolucao": f"{largura}x{altura}",
        "veiculos": 0,
        "detectou": False,
        "conf_bbox": None,
        "bbox_largura": None,
        "bbox_altura": None,
        "nitidez": None,
        "contraste": None,
        "leitura": None,
        "formato": None,
    }

    # Estágio 1 — veículos (mesmo downscale 320x320 da produção)
    pequeno = cv2.resize(frame, (320, 320))
    sx, sy = largura / 320.0, altura / 320.0
    deteccoes = _get_detector_veiculo()(pequeno, verbose=False, conf=CONF_VEICULO,
                                        iou=0.45, classes=VEHICLE_CLASSES)[0]
    caixas = []
    for b in deteccoes.boxes:
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        caixas.append((int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)))
    resultado["veiculos"] = len(caixas)

    # Estágio 2 — placa dentro de cada veículo. Fica com a de maior confiança.
    melhor = None
    for (x1, y1, x2, y2) in caixas:
        recorte_veiculo = frame[max(0, y1):min(altura, y2), max(0, x1):min(largura, x2)]
        if recorte_veiculo.size == 0:
            continue
        bbox, conf = alpr_engine.detect_plate_bbox(recorte_veiculo, conf_threshold=CONF_PLACA)
        if bbox is None:
            continue
        if melhor is None or conf > melhor[1]:
            melhor = (bbox, conf, recorte_veiculo)

    if melhor is None:
        return resultado

    (px1, py1, px2, py2), conf, recorte_veiculo = melhor
    recorte = recorte_veiculo[py1:py2, px1:px2]
    if recorte.size == 0:
        return resultado

    resultado["detectou"] = True
    resultado["conf_bbox"] = round(float(conf), 3)
    resultado["bbox_largura"] = int(px2 - px1)
    resultado["bbox_altura"] = int(py2 - py1)

    metricas = quality_assessor.evaluate(recorte)
    cinza = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY)
    resultado["nitidez"] = metricas["laplacian_variance"]
    resultado["contraste"] = round(float(cinza.std()), 1)

    # OCR só faz sentido se houver pixel suficiente. Rodar EasyOCR num recorte
    # de 30px de largura queima segundos pra devolver ruído.
    if resultado["bbox_largura"] >= LARGURA_MINIMA_UTIL:
        try:
            texto, formato, _conf_ocr = alpr_engine.read_plate(recorte)
            resultado["leitura"] = texto
            resultado["formato"] = formato
        except Exception as e:  # OCR quebrado não pode derrubar a triagem inteira
            resultado["leitura"] = f"<erro: {e}>"

    return resultado


def _veredito(res: Dict[str, Any]) -> str:
    """Traduz os números crus numa recomendação.

    Os cortes saem da comparação medida entre Davao (funciona em produção há
    dias) e Tubarão (não funciona): o que separa as duas é detectar de forma
    consistente, com recorte grande o bastante pra ter caractere.
    """
    taxa = res["taxa_deteccao"]
    largura = res["bbox_largura_media"] or 0

    # Sem carro nenhum na tela o teste não concluiu nada sobre a câmera — pode
    # ser madrugada, rua fechada, ou a câmera apontada pro céu. Não confundir
    # "não tem trânsito agora" com "não serve".
    if res["total_veiculos"] == 0:
        return "INCONCLUSIVO (nenhum veículo apareceu — repetir em horário de movimento)"

    if taxa >= 0.5 and largura >= LARGURA_MINIMA_UTIL and res["leituras_formato_valido"] > 0:
        return "SERVE"
    if taxa >= 0.25 and largura >= 50:
        return "MARGINAL"
    if taxa > 0:
        return "NAO SERVE (acha a placa, mas o recorte é pequeno demais pra ler)"
    return "NAO SERVE (vê o carro, nunca acha a placa)"


def avalia_camera(cam: Dict[str, Any], n_frames: int, intervalo: float) -> Dict[str, Any]:
    cam_id = cam["id"]
    nome = cam.get("nome") or cam_id
    url = cam.get("url") or ""
    print(f"\n── {nome}  ({cam_id})", file=sys.stderr, flush=True)

    frames: List[Dict[str, Any]] = []
    falhas_captura = 0

    for i in range(n_frames):
        jpeg = _capture_real_frame_jpeg(cam_id, url, timeout_s=20.0)
        if not jpeg:
            falhas_captura += 1
            print(f"   frame {i+1}/{n_frames}: captura falhou", file=sys.stderr, flush=True)
        else:
            analise = _analisa_frame(jpeg)
            if analise is None:
                falhas_captura += 1
                print(f"   frame {i+1}/{n_frames}: JPEG ilegível", file=sys.stderr, flush=True)
            else:
                frames.append(analise)
                marca = "PLACA" if analise["detectou"] else "  —  "
                extra = ""
                if analise["detectou"]:
                    extra = (f" conf={analise['conf_bbox']} "
                             f"{analise['bbox_largura']}x{analise['bbox_altura']}px "
                             f"nitidez={analise['nitidez']} leitura={analise['leitura']}")
                print(f"   frame {i+1}/{n_frames}: {analise['veiculos']} veíc  {marca}{extra}",
                      file=sys.stderr, flush=True)
        if i < n_frames - 1:
            time.sleep(intervalo)

    com_deteccao = [f for f in frames if f["detectou"]]
    n_ok = len(frames)

    def _media(campo: str) -> Optional[float]:
        vals = [f[campo] for f in com_deteccao if f[campo] is not None]
        return round(float(np.mean(vals)), 1) if vals else None

    res: Dict[str, Any] = {
        "camera_id": cam_id,
        "nome": nome,
        "local": cam.get("local") or cam.get("cidade") or "",
        "frames_pedidos": n_frames,
        "frames_capturados": n_ok,
        "falhas_captura": falhas_captura,
        "resolucao": frames[0]["resolucao"] if frames else None,
        "total_veiculos": sum(f["veiculos"] for f in frames),
        "frames_com_veiculo": sum(1 for f in frames if f["veiculos"] > 0),
        "frames_com_placa": len(com_deteccao),
        # Denominador = frames COM veículo, não todos. Punir a câmera por um
        # frame de rua vazia mediria o trânsito, não a câmera.
        "taxa_deteccao": (round(len(com_deteccao) / sum(1 for f in frames if f["veiculos"] > 0), 3)
                          if any(f["veiculos"] > 0 for f in frames) else 0.0),
        "conf_bbox_media": _media("conf_bbox"),
        "bbox_largura_media": _media("bbox_largura"),
        "bbox_altura_media": _media("bbox_altura"),
        "nitidez_media": _media("nitidez"),
        "contraste_medio": _media("contraste"),
        "leituras": [f["leitura"] for f in com_deteccao if f["leitura"]],
        "leituras_formato_valido": sum(
            1 for f in com_deteccao if f["formato"] in ("MERCOSUL", "ANTIGO")
        ),
        "frames": frames,
    }
    res["veredito"] = _veredito(res)
    return res


def _tabela(resultados: List[Dict[str, Any]]) -> str:
    cab = (f"{'CÂMERA':<32} {'VEÍC':>5} {'DET':>6} {'CONF':>6} {'PX':>9} "
           f"{'NITIDEZ':>8}  VEREDITO")
    linhas = [cab, "─" * 110]
    for r in sorted(resultados, key=lambda x: (-x["taxa_deteccao"], -(x["bbox_largura_media"] or 0))):
        px = f"{r['bbox_largura_media']:.0f}x{r['bbox_altura_media']:.0f}" if r["bbox_largura_media"] else "—"
        linhas.append(
            f"{r['nome'][:31]:<32} "
            f"{r['total_veiculos']:>5} "
            f"{r['taxa_deteccao']*100:>5.0f}% "
            f"{(r['conf_bbox_media'] or 0):>6.2f} "
            f"{px:>9} "
            f"{(r['nitidez_media'] or 0):>8.0f}  "
            f"{r['veredito']}"
        )
    return "\n".join(linhas)


def main() -> int:
    p = argparse.ArgumentParser(description="Mede se uma câmera serve pra leitura de placa.")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--all-candidates", action="store_true",
                       help="Avalia todas as câmeras marcadas como candidatas a teste")
    grupo.add_argument("--camera-id", action="append",
                       help="ID de câmera específica (pode repetir)")
    p.add_argument("--frames", type=int, default=12, help="Frames por câmera (padrão 12)")
    p.add_argument("--interval", type=float, default=10.0,
                   help="Segundos entre frames — precisa dar tempo de passar carro (padrão 10)")
    p.add_argument("--json", dest="json_out", help="Arquivo pra gravar o relatório completo")
    args = p.parse_args()

    if args.all_candidates:
        cams = db_manager.get_test_candidates()
    else:
        cams = []
        for cid in args.camera_id:
            cam = db_manager.get_camera_by_id(cid)
            if not cam:
                print(f"Câmera '{cid}' não existe em live_cameras.db", file=sys.stderr)
                return 1
            cams.append(cam)

    if not cams:
        print("Nenhuma câmera pra avaliar.", file=sys.stderr)
        return 1

    print(f"Avaliando {len(cams)} câmera(s) × {args.frames} frames "
          f"(~{len(cams) * args.frames * (args.interval + 8) / 60:.0f} min)",
          file=sys.stderr, flush=True)

    resultados = [avalia_camera(cam, args.frames, args.interval) for cam in cams]

    print("\n" + _tabela(resultados))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(resultados, fh, ensure_ascii=False, indent=2)
        print(f"\nRelatório completo: {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
