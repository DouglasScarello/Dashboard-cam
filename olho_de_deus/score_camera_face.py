"""
score_camera_face.py — Olho de Deus

Mede, com número em vez de palpite, se uma câmera serve pra reconhecimento
facial — espelha `score_camera_alpr.py`, mesma disciplina: captura N frames
ao vivo, roda o MESMO pipeline de 2 estágios da produção (YOLO acha a
pessoa, YuNet acha o rosto dentro do recorte da pessoa — nunca no frame
inteiro, mesma lição já aprendida com placa: um rosto ocupa uma fração
minúscula de um frame 1920x1080, rodar o detector nele direto não acha
nada), e aplica o MESMO gate de qualidade que decide se um rosto vira
embedding em produção (`biometric_processor._face_quality_ok`) — a
triagem só vale alguma coisa se medir exatamente o que o serviço 24/7 vai
enfrentar, não uma aproximação.

Achado que já estava pesquisado e calibrado ANTES deste script (ver
biometric_processor.py:62-115, pesquisa citada lá: NIST FRVT Part 3/2019 +
pipeline de limpeza do InsightFace WebFace42M): o corte que separa rosto
"reconhecível" de "longe/pequeno demais" é a distância interocular em
pixels — `MIN_INTEROCULAR_PX=40`, com ~48px sendo a referência da
literatura pra "condição difícil". Reaproveitado aqui, não reinventado.

Não escreve no banco. Só lê câmeras e cospe relatório — promover câmera
pro pipeline de produção é decisão humana.

Uso:
    poetry run python3 score_camera_face.py --all-candidates --json /tmp/triagem_face.json
    poetry run python3 score_camera_face.py --camera-id globetv_davao_leongarcia --frames 6
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
from biometric_processor import (
    _ARCFACE_112_TEMPLATE,
    _face_quality_ok,
    YUNET_MODEL_PATH,
)

# Caminho e limiares COPIADOS do pipeline de produção
# (biometric_processor.py:274-316, _process_frame_bytetrack:339-349). Não
# inventar número aqui: a triagem só vale alguma coisa se medir exatamente o
# que o serviço 24/7 vai enfrentar.
YOLO_PESSOA = str(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "yolov8n_openvino_model"))
CONF_PESSOA = 0.5
IOU_PESSOA = 0.45
CLASSE_PESSOA = [0]  # COCO "person"

# Abaixo de ~25px o YuNet até acha um blob de rosto, mas não sobra geometria
# nenhuma pra confiar — nem "MARGINAL" é justo chamar. Entre 25 e
# MIN_INTEROCULAR_PX(=40) é a faixa "vê gente, mas longe demais pra
# reconhecimento confiável" (mesmo espírito do "MARGINAL" do scorer de
# placa: detecta, mas não dá pra confiar no resultado).
INTEROCULAR_MARGINAL_MIN = 25

_detector_pessoa = None
_face_detector = None


def _get_detector_pessoa():
    global _detector_pessoa
    if _detector_pessoa is None:
        from ultralytics import YOLO
        _detector_pessoa = YOLO(YOLO_PESSOA, task="detect")
    return _detector_pessoa


def _get_face_detector():
    global _face_detector
    if _face_detector is None:
        _face_detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL_PATH), "", (320, 320), score_threshold=0.6
        )
    return _face_detector


def _detecta_melhor_rosto(recorte_pessoa: np.ndarray) -> Optional[Dict[str, Any]]:
    """Roda YuNet dentro do recorte de PESSOA (não do frame inteiro) e
    reporta os números CRUS (interocular, confiança, pose, nitidez do
    alinhado) — não só um booleano — pra dar pra medir a distribuição por
    câmera. O veredito de aceite/rejeição roda `_face_quality_ok()` de
    verdade (importada de biometric_processor.py), garantindo que bate com
    o que a produção decidiria."""
    h, w = recorte_pessoa.shape[:2]
    if h < 10 or w < 10:
        return None

    detector = _get_face_detector()
    detector.setInputSize((w, h))
    _, faces = detector.detect(recorte_pessoa)
    if faces is None or len(faces) == 0:
        return None

    best = max(faces, key=lambda f: f[14])
    landmarks = best[4:14].reshape(5, 2).astype(np.float32)
    det_score = float(best[14])

    right_eye, left_eye, nose = landmarks[0], landmarks[1], landmarks[2]
    interocular = float(np.linalg.norm(right_eye - left_eye))
    d_r = abs(nose[0] - right_eye[0])
    d_l = abs(nose[0] - left_eye[0])
    yaw_ratio = d_r / max(d_r + d_l, 1e-6)

    resultado: Dict[str, Any] = {
        "det_confidence": round(det_score, 3),
        "interocular_px": round(interocular, 1),
        "yaw_ratio": round(yaw_ratio, 3),
        "blur": None,
        "gate_passou": False,
        "gate_motivo": "falha no alinhamento",
    }

    transform, _ = cv2.estimateAffinePartial2D(landmarks, _ARCFACE_112_TEMPLATE, method=cv2.LMEDS)
    if transform is None:
        return resultado

    aligned = cv2.warpAffine(recorte_pessoa, transform, (112, 112), borderValue=0.0)
    gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
    resultado["blur"] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)

    gate_ok, motivo = _face_quality_ok(landmarks, det_score, aligned)
    resultado["gate_passou"] = gate_ok
    resultado["gate_motivo"] = motivo
    return resultado


def _analisa_frame(jpeg_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Replica o pipeline de PRODUÇÃO num frame: YOLO acha a pessoa, e só
    dentro do recorte da pessoa é que procura o rosto (mesma razão do
    scorer de placa: um rosto ocupa uma fração minúscula do frame inteiro
    — rodar o detector direto no frame não acha nada)."""
    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return None

    altura, largura = frame.shape[:2]
    resultado: Dict[str, Any] = {
        "resolucao": f"{largura}x{altura}",
        "pessoas": 0,
        "detectou_rosto": False,
        "rosto": None,
    }

    # Downscale 320x320 com escala X/Y independente — mesmo padrão de
    # biometric_processor.py:333-336.
    pequeno = cv2.resize(frame, (320, 320))
    sx, sy = largura / 320.0, altura / 320.0
    deteccoes = _get_detector_pessoa()(pequeno, verbose=False, conf=CONF_PESSOA,
                                        iou=IOU_PESSOA, classes=CLASSE_PESSOA)[0]
    caixas = []
    for b in deteccoes.boxes:
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        caixas.append((int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy)))
    resultado["pessoas"] = len(caixas)

    # Fica com o rosto de maior confiança entre todas as pessoas do frame.
    melhor = None
    for (x1, y1, x2, y2) in caixas:
        recorte_pessoa = frame[max(0, y1):min(altura, y2), max(0, x1):min(largura, x2)]
        if recorte_pessoa.size == 0:
            continue
        rosto = _detecta_melhor_rosto(recorte_pessoa)
        if rosto is None:
            continue
        if melhor is None or rosto["det_confidence"] > melhor["det_confidence"]:
            melhor = rosto

    if melhor is not None:
        resultado["detectou_rosto"] = True
        resultado["rosto"] = melhor

    return resultado


def _veredito(res: Dict[str, Any]) -> str:
    """Traduz os números crus numa recomendação — mesmo espírito de
    `score_camera_alpr.py::_veredito`, adaptado aos números de rosto."""
    if res["total_pessoas"] == 0:
        return "INCONCLUSIVO (nenhuma pessoa apareceu — repetir em horário de movimento)"

    if res["frames_com_rosto"] == 0:
        return "NAO SERVE (vê gente, nunca acha rosto no recorte)"

    taxa = res["taxa_deteccao_rosto"]
    interocular = res["interocular_medio"] or 0

    if taxa >= 0.5 and res["frames_gate_passou"] > 0:
        return "SERVE"
    if taxa >= 0.25 and interocular >= INTEROCULAR_MARGINAL_MIN:
        return "MARGINAL"
    return "NAO SERVE (rosto pequeno demais pra reconhecimento)"


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
                marca = "ROSTO" if analise["detectou_rosto"] else "  —  "
                extra = ""
                if analise["detectou_rosto"]:
                    r = analise["rosto"]
                    gate = "PASSOU" if r["gate_passou"] else f"REJEITADO({r['gate_motivo']})"
                    extra = (f" conf={r['det_confidence']} interocular={r['interocular_px']}px "
                             f"blur={r['blur']} gate={gate}")
                print(f"   frame {i+1}/{n_frames}: {analise['pessoas']} pessoa(s)  {marca}{extra}",
                      file=sys.stderr, flush=True)
        if i < n_frames - 1:
            time.sleep(intervalo)

    com_rosto = [f for f in frames if f["detectou_rosto"]]
    n_ok = len(frames)

    def _media(campo: str) -> Optional[float]:
        vals = [f["rosto"][campo] for f in com_rosto if f["rosto"][campo] is not None]
        return round(float(np.mean(vals)), 1) if vals else None

    res: Dict[str, Any] = {
        "camera_id": cam_id,
        "nome": nome,
        "local": cam.get("local") or cam.get("cidade") or "",
        "frames_pedidos": n_frames,
        "frames_capturados": n_ok,
        "falhas_captura": falhas_captura,
        "resolucao": frames[0]["resolucao"] if frames else None,
        "total_pessoas": sum(f["pessoas"] for f in frames),
        "frames_com_pessoa": sum(1 for f in frames if f["pessoas"] > 0),
        "frames_com_rosto": len(com_rosto),
        # Denominador = frames COM pessoa, não todos — mesma razão do
        # scorer de placa: punir a câmera por um frame de rua vazia mediria
        # o movimento, não a câmera.
        "taxa_deteccao_rosto": (round(len(com_rosto) / sum(1 for f in frames if f["pessoas"] > 0), 3)
                                 if any(f["pessoas"] > 0 for f in frames) else 0.0),
        "frames_gate_passou": sum(1 for f in com_rosto if f["rosto"]["gate_passou"]),
        "det_confidence_media": _media("det_confidence"),
        "interocular_medio": _media("interocular_px"),
        "blur_medio": _media("blur"),
        "motivos_rejeicao": [f["rosto"]["gate_motivo"] for f in com_rosto if not f["rosto"]["gate_passou"]],
        "frames": frames,
    }
    res["veredito"] = _veredito(res)
    return res


def _tabela(resultados: List[Dict[str, Any]]) -> str:
    cab = (f"{'CÂMERA':<32} {'PESS':>5} {'DET%':>6} {'CONF':>6} {'INTEROC':>8} "
           f"{'GATE':>5}  VEREDITO")
    linhas = [cab, "─" * 110]
    for r in sorted(resultados, key=lambda x: (-x["taxa_deteccao_rosto"], -(x["interocular_medio"] or 0))):
        interoc = f"{r['interocular_medio']:.0f}px" if r["interocular_medio"] else "—"
        linhas.append(
            f"{r['nome'][:31]:<32} "
            f"{r['total_pessoas']:>5} "
            f"{r['taxa_deteccao_rosto']*100:>5.0f}% "
            f"{(r['det_confidence_media'] or 0):>6.2f} "
            f"{interoc:>8} "
            f"{r['frames_gate_passou']:>5}  "
            f"{r['veredito']}"
        )
    return "\n".join(linhas)


def main() -> int:
    p = argparse.ArgumentParser(description="Mede se uma câmera serve pra reconhecimento facial.")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--all-candidates", action="store_true",
                       help="Avalia todas as câmeras marcadas como candidatas a teste")
    grupo.add_argument("--camera-id", action="append",
                       help="ID de câmera específica (pode repetir)")
    p.add_argument("--frames", type=int, default=12, help="Frames por câmera (padrão 12)")
    p.add_argument("--interval", type=float, default=10.0,
                   help="Segundos entre frames — precisa dar tempo de passar gente (padrão 10)")
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
