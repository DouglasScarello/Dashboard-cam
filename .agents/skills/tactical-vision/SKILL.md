---
name: tactical-vision
description: >-
  Protocolos de visão computacional tática, captura de streams RTSP/HLS,
  inferência YOLOv8 para detecção de armas e posturas anômalas, e extração biométrica ArcFace.
---

# Tactical Vision Skill

Esta skill fornece diretrizes e runbooks operacionais para manutenção e expansão do pipeline de visão tática:

## 1. Pipelines Suportados
- **live_pipeline.py**: Processamento em tempo real com buffer atômico de frames (`AtomicFrameRing`).
- **behavior_pipeline.py**: Detecção de armas e comportamento com YOLOv8n-pose e modelo de armas.
- **biometric_processor.py**: Rastreamento com IoU tracker e extração de embeddings faciais via ArcFace.
- **camera_grid_server.py**: Gateway FastAPI de streaming para go2rtc e thumbnails JPEG com cache TTL.

## 2. Padrões de Qualidade
- Sempre garantir que o frame entregue à inferência seja independente do frame desenhado pelo HUD.
- Ao adicionar novas câmeras ao grid, mapear resoluções de streaming no `config/go2rtc.yaml` e atualizar `farm_cams.py` ou endpoints REST.
