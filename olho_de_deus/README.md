# 👁️ Módulo Olho de Deus — Análise Biométrica em Tempo Real

Motor de visão computacional para detecção e identificação facial em feeds de vídeo.

## Estrutura

```
olho_de_deus/
├── main.py                 # Entrada principal: player forense + HUD tático
├── biometric_processor.py  # YOLO + ArcFace + REID tracker (IoU)
├── youtube_stream.py       # Extração de stream YouTube (yt-dlp)
├── cameras.json            # Configuração de câmeras monitoradas
├── farm_cams.py            # Farm de câmeras públicas
├── farm_omni.py            # Monitoramento onipresente
├── farm_transito.py        # Câmeras de trânsito
├── filter_elite.py         # Filtros de detecção elite
├── audit_network.py        # Auditoria de rede
├── yolov8n.pt              # Modelo YOLO (detecção de faces)
└── pyproject.toml
```

## Comandos

```bash
# Stream YouTube (modo forensic)
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic --step 10

# Arquivo de vídeo local
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --source /caminho/video.mp4 --forensic

# Modo automático (sem pausa por frame)
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID
```

## Controles do Player Forense

| Tecla | Ação |
|-------|------|
| `SPACE` | Play / Pause |
| `→` / `D` | Próximo frame |
| `←` / `A` | Frame anterior |
| `S` | Salvar frame atual em JPEG |
| `Q` / `ESC` | Sair |
| Click na barra | Seek para posição |

## Integração com Intelligence

Aponte o banco de dados:
```python
# em biometric_processor.py, altere os caminhos:
index_path    = "../intelligence/data/global_vector_db.faiss"
metadata_path = "../intelligence/data/global_metadata.json"
```
