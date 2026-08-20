<!-- INÍCIO DO PROTOCOLO DE REGISTRO CONTÍNUO DE MUDANÇAS -->
# 📜 PROTOCOLO DE REGISTRO CONTÍNUO DE MUDANÇAS (CHANGE-LOGGING PROTOCOL)
> **STATUS DA POLÍTICA:** MANDATÓRIA (ENFORCED)  
> **APLICAÇÃO:** Qualquer alteração em arquivos de código (`.py`, `.ts`, `.tsx`, `.json`, `.yaml`, `.sql`, `.sh`, `.rs`, `Dockerfile`) DEVE ser registrada imediatamente nesta seção antes da conclusão de qualquer tarefa ou resposta ao usuário.

---

### 📋 Diretrizes de Governança e Auditoria Contínua:
1. **Registro Atômico Obrigatório:** Toda modificação de código gera uma entrada na tabela de *Histórico de Mutações*.
2. **Classificação Semântica Padronizada:**
   - `[FEAT]`: Nova funcionalidade, novo pipeline ou novos componentes de UI.
   - `[FIX]`: Correção de bug, falha de inferência, vazamento de memória ou erro de renderização.
   - `[FORENSIC]`: Ajustes em algoritmos periciais, filtros de super-resolução, ALPR, restauração facial ou laudos.
   - `[PERF]`: Redução de latência, aceleração por GPU/WebGL, otimização de banda ou double-buffering.
   - `[SEC]`: Hardening, criptografia (Ghost Protocol, AES-256, PAdES-LTA, SHA-256) ou conformidade jurídica (CNJ 484 / CPP 158).
   - `[INFRA]`: Alterações em containers Docker, portas de rede, go2rtc, Redis, PostgreSQL ou Vite/Tauri.
3. **Mapeamento de Dependências:** Caso novas portas, pacotes (`poetry`/`npm`) ou rotas de API sejam adicionados, as seções correspondentes deste documento devem ser atualizadas no mesmo commit.

---

### 📊 Histórico Contínuo de Mutações Recentes
| Timestamp (ISO 8601) | Tipo | Módulo / Arquivos Afetados | Resumo Técnico da Alteração | Agente / Autor |
| :--- | :--- | :--- | :--- | :--- |
| `2026-08-20T20:25:00-03:00` | `[CONSULT]` | `catalog/src-tauri/Cargo.toml`, `PROJECT_MAP.md`, `README.md` | Incorporação da Consultoria Arquitetural C4ISR: IPC de alta performance (Custom URIs, Channels), otimizações de compilação Cargo (LTO, strip, codegen-units=1), despacho heterogêneo de Edge AI (TensorRT, OpenVINO, NCNN), Tiering Híbrido de BDs (Milvus/Qdrant/Memgraph/ArcadeDB) e postura Zero Trust FIPS 140-3. | Antigravity AI |
| `2026-08-20T19:35:00-03:00` | `[ARCH]` | `intelligence/spatial_engine.py`, `olho_de_deus/forensic_core.py`, `PROJECT_MAP.md` | Integração da arquitetura de Visão Computacional (Sub-center ArcFace, YOLOv8 + EasyOCR), DGGS Uber H3 com h3-pg v4.x (Generated Columns GiST), Ledger Imutável via Árvores de Merkle e assinaturas digitais PAdES-LTA com pyHanko. | Antigravity AI |
| `2026-08-20T19:17:00-03:00` | `[AUDIT]` | `RELATORIO_AUDITORIA_GERAL.md`, `Layout.tsx`, `i18n/*.json`, `api_server.py` | Auditoria técnica simultânea com 10 subagentes especializados, validação de todos os subsistemas (WebRTC, Shaders WebGL, IA Forense 4x, UX Pan/Zoom, Dual-DB H3, Áudio Procedural) e emissão de laudo executivo consolidado. | Antigravity AI |
| `2026-08-20T19:12:00-03:00` | `[FORENSIC]` | `catalog/src/components/player/hooks/useWebGLVideoFilters.ts`, `config/go2rtc.yaml` | Aplicação da pesquisa técnica de CFTV Forense: implementação dos Shaders GLSL de convolução Unsharp Mask 3x3 (matriz [-1 -1 -1; -1 +9 -1; -1 -1 -1]), ajuste fotométrico vetorial de brilho/contraste, arquitetura híbrida de snapshot PNG 1:1 e remuxing puro go2rtc (#video=copy#audio=opus). | Antigravity AI |
| `2026-08-20T18:30:00-03:00` | `[FIX]` | `olho_de_deus/camera_grid_server.py`, `TacticalVideoPlayer.tsx` | Correção definitiva do erro 500 na rota de snapshot com suporte a ID flexível e fallback rápido de CDN, além de ativação imediata de filtros visuais em tempo real ao clicar nos botões de melhoria. | Antigravity AI |
| `2026-08-20T18:24:00-03:00` | `[FEAT]` | `catalog/src/components/player/InteractiveCanvasViewer.tsx`, `TacticalVideoPlayer.tsx` | Implementação de recorte inteligente de ROI sob zoom (1x a 16x), botões flutuantes de reconstrução neural 4x em tempo real e filtro de nitidez adaptativo anti-blur. | Antigravity AI |
| `2026-08-20T18:20:00-03:00` | `[FORENSIC]` | `catalog/src/components/player/ForensicPlateInspector.tsx`, `olho_de_deus/forensic_sr_engine.py` | Integração completa dos 3 modos periciais com 1-clique: Placas (ALPR Mercosul), Rostos (CNJ 484/2022) e Super-Nitidez 4X com comparador Split-View e dupla custódia SHA-256. | Antigravity AI |
| `2026-08-20T18:15:00-03:00` | `[FIX]` | `catalog/src/components/player/InteractiveCanvasViewer.tsx` | Correção definitiva do bug de tela branca no canvas através de renderização acelerada por GPU com letterbox crop zero-branding. | Antigravity AI |
| `2026-08-20T18:10:00-03:00` | `[FEAT]` | `catalog/src/components/player/` | Criação do ecossistema completo Tactical Military Video Player C4ISR (HUD com ZULU time, Shaders WebGL, Áudio Procedural). | Antigravity AI |
| `2026-08-20T18:00:00-03:00` | `[INFRA]` | `docker-compose.yml`, `config/go2rtc.yaml`, `pyproject.toml` | Auditoria completa de portas (1420, 8000, 8001, 1984, 8554, 5432, 6379) e matriz Ghost Protocol. | Antigravity AI |

<!-- FIM DO PROTOCOLO DE REGISTRO CONTÍNUO DE MUDANÇAS -->

---

# 🗺️ MAPA MESTRE DE ARQUITETURA DO PROJETO — 'OLHO DE DEUS' & DASHBOARD-CAM

```
====================================================================================================
                        SISTEMA C4ISR & PERÍCIA FORENSE DIGITAL (ESCALA 10.000+ CÂMERAS)
====================================================================================================
```

---

## 1. Visão Geral da Topologia e Estrutura de Diretórios

```
dashboard-cam/
├── PROJECT_MAP.md                     # [ESTE DOCUMENTO] Mapa mestre e registro contínuo de mudanças
├── Dockerfile                         # Container base Python 3.11 com OpenCV, CUDA e GL
├── docker-compose.yml                 # Orquestrador (PostgreSQL pgvector, Redis, go2rtc, Intelligence)
├── requirements.txt                   # Dependências Python centralizadas
├── config/
│   └── go2rtc.yaml                    # Configuração de streaming RTSP/WebRTC de ultra-baixa latência
├── database/
│   ├── live_cameras.json              # Catálogo de 10.000+ câmeras públicas/municipais
│   └── omni_cams.json                 # Base de fallback geoespacial
├── catalog/                           # [FRONTEND] Aplicação Tática React 18 + TypeScript + Tauri v2
│   ├── package.json                   # Dependências React, Lucide, Tailwind, Framer-Motion, HLS.js
│   ├── vite.config.ts                 # Servidor de desenvolvimento na porta 1420 (strictPort)
│   ├── tailwind.config.js             # Design System Militar / C4ISR (Ultra-dark #0a0a0b)
│   ├── src-tauri/                     # Camada Desktop Rust (SQLite nativo, proxy de CORS, comandos de I/O)
│   └── src/
│       ├── main.tsx                   # Entrada SPA + React Router v6
│       ├── Layout.tsx                 # Barra de navegação e Central de Alertas persistente
│       ├── App.tsx                    # Catálogo de Inteligência, Dossiês e Ações Táticas
│       ├── pages/
│       │   └── CameraGrid.tsx         # Grade C4ISR de câmeras ao vivo com detecção de ameaças
│       ├── components/
│       │   ├── AlertCenter.tsx        # Central de Alertas Biométricos SSE em tempo real
│       │   └── player/                # [ECOSSISTEMA TACTICAL VIDEO PLAYER]
│       │       ├── TacticalVideoPlayer.tsx      # Orquestrador de vídeo e atalhos de teclado
│       │       ├── InteractiveCanvasViewer.tsx  # Viewport com Pan/Zoom (1x-16x), Lupa e ROI inteligente
│       │       ├── TacticalHUD.tsx              # Overlay militar com relógio ZULU e coordenadas MGRS
│       │       ├── ImageEnhancementToolbar.tsx  # Barra de ferramentas e 3 botões periciais 1-clique
│       │       ├── ForensicPlateInspector.tsx   # Gaveta de perícia, Split-View e laudo oficial PDF
│       │       ├── hooks/
│       │       │   └── useWebGLVideoFilters.ts  # Shaders WebGL GPU (Unsharp, CLAHE, Sobel, NVG, FLIR)
│       │       ├── audio/
│       │       │   └── TacticalAudioEngine.ts   # Síntese procedural de áudio militar via Web Audio API
│       │       └── types/
│       │           └── player.types.ts          # Tipagens estritas de vídeo, filtros e telemetria
├── intelligence/                      # [MOTOR DE INTELIGÊNCIA INVESTIGATIVA & BIOMETRIA]
│   ├── intelligence_db.py             # Abstração Dual DB (SQLite WAL / PostgreSQL + pgvector)
│   ├── spatial_engine.py              # Motor Espacial Uber H3 (Res 7, 8, 9), Frustum 3D e Handover
│   ├── super_resolution.py            # Super-Resolução Forense (CodeFormer, Real-ESRGAN, MSRCP)
│   ├── vision_pipeline.py             # Visão Contínua MTMC, Motion Activity Gate e AdaFace/TransReID
│   ├── behavioral_engine.py           # Análise Comportamental (TSM, Pose 17-kpts, FSM de Alertas)
│   ├── c2_agentic_engine.py           # Núcleo Agêntico C2 Tático, Matriz de Risco e Despacho LAPJV
│   ├── graph_engine.py                # Grafo de Inteligência e Co-Ocorrência Espaciotemporal
│   ├── semantic_search.py             # Busca Semântica Multimodal VLM + Quantização Binária 1-bit
│   └── global_ingestion.py            # Ingestor global (Interpol, FBI, BNMP, MJSP)
└── olho_de_deus/                      # [SERVIDORES & PERÍCIA FORENSE EM TEMPO REAL]
    ├── api_server.py                  # Servidor Central C4ISR FastAPI (Porta 8000)
    ├── camera_grid_server.py          # Servidor de Grid e Captura OpenCV (Porta 8001)
    ├── forensic_sr_engine.py          # Motor Pericial de ALPR, Restauração Facial e Desconvolução
    ├── forensic_core.py               # Cadeia de Custódia (CPP 158), SLR Bayesiana, CNJ 484 e PAdES-LTA
    ├── forensic_report.py             # Gerador de Dossiês Forenses em PDF
    ├── live_pipeline.py               # Pipeline em Tempo Real (AtomicFrameRing, YOLO, ArcFace)
    ├── behavior_pipeline.py           # Pipeline Tático de Detecção de Quedas e Armas em Cena
    ├── biometric_processor.py         # Processador Biométrico com REID e ByteTrack
    ├── streaming_cluster.py           # Gerenciador de Cluster Distribuído (Dual-Stream 10k Cams)
    ├── redis_cache.py                 # Cache Redis com Pub/Sub e Rate-Limit Debounce
    ├── tactical_dispatch.py           # Despacho Ótimo LAPJV, Isócronas de Fuga e Cerco Viário
    ├── tactical_codec.py              # Codec Binário Sub-100B para Rádios LoRa/Mesh
    └── ghost_killswitch.py            # Daemon de Defesa Ativa, Lockdown e Zeroização de Memória
```

---

## 2. Topologia de Rede e Mapeamento de Portas

| Porta | Protocolo | Serviço / Módulo | Bind IP | Descrição & Função no Ecossistema |
| :--- | :--- | :--- | :--- | :--- |
| **1420** | HTTP / WS | **Frontend React / Tauri Dev** | `localhost:1420` | Interface SPA de inteligência, mapa e player tático. |
| **8000** | HTTP / SSE | **Central API C4ISR (`api_server.py`)** | `0.0.0.0:8000` | Endpoints REST de inteligência, emissão de laudos, grafo ontológico e SSE. |
| **8001** | HTTP | **Camera Grid Server (`camera_grid_server.py`)** | `0.0.0.0:8001` | Microserviço de thumbnails em tempo real, snapshots nativos e análise de cena. |
| **1984** | HTTP / WS | **go2rtc Web API** | `127.0.0.1:1984` | Console e endpoints de streaming WebRTC e HLS. |
| **8554** | RTSP | **go2rtc RTSP Ingestion** | `0.0.0.0:8554` | Publicação de pipelines de vídeo para consumo interno e externo. |
| **8555** | TCP / UDP | **go2rtc WebRTC Media ICE** | `0.0.0.0:8555` | Canal direto de transmissão de vídeo com latência sub-150ms. |
| **5432** | TCP / PgSQL | **PostgreSQL + pgvector** | `127.0.0.1:5432` | Banco relacional e armazenamento de vetores biométricos ArcFace 512-d. |
| **6379** | TCP / RESP | **Redis Cache & Pub/Sub** | `127.0.0.1:6379` | Barramento de eventos em tempo real e cache de embeddings. |

---

## 3. Arquitetura do Backend & Endpoints de API

### A. Servidor Central C4ISR (`api_server.py` — Porta 8000)
- `GET /health`: Healthcheck operacional.
- `GET /status`: Status de clientes SSE conectados, memória e Redis.
- `GET /events`: Stream Server-Sent Events (SSE) com notificações de biometria facial e alertas.
- `GET /api/catalog/individuals`: Listagem paginada de alvos com filtros e busca rápida.
- `GET /api/catalog/individuals/{id}`: Dossiê completo de alvo com fotos e crimes associados.
- `POST /api/forensics/generate-laudo/{target_id}`: Geração de Laudo Oficial PDF/A-1b assinado com PAdES-LTA (ICP-Brasil).
- `POST /api/tactical/dispatch-containment`: Cálculo de cerco viário LAPJV e pacote Cursor-on-Target (CoT/ATAK).
- `GET /api/tactical/spatial/nearby`: Busca de câmeras no raio via hexágonos Uber H3 com Frustum 3D.
- `POST /api/tactical/spatial/handover`: Predição de câmeras no vetor de fuga com cálculo de ETA.

### B. Servidor de Câmeras & Grid (`camera_grid_server.py` — Porta 8001)
- `GET /api/cameras`: Catálogo de 10.000+ câmeras com metadados e coordenadas.
- `GET /api/cameras/{id}/thumbnail.jpg`: Thumbnail instantânea da câmera com cache de 5s.
- `GET /api/cameras/{id}/snapshot`: Captura de quadro em resolução nativa com headers forenses.
- `GET /api/cameras/{id}/live_url`: Resolução de stream direto HLS/m3u8/mp4 via yt-dlp.
- `GET /api/cameras/{id}/comprovante`: Emissão de Certificado de Geolocalização com hash SHA-256.

### C. Motor de Perícia e Super-Resolução (`forensic_sr_engine.py` — Portas 8000/8001)
- `POST /api/forensic/enhance-roi`: Pipeline pericial unificado com suporte a:
  - `roi_type: "plate"`: Homografia Mercosul ($400\times130$), Wiener deblur, Sauvola $\mathcal{O}(1)$ e OCR.
  - `roi_type: "face"`: Restauração sem alucinação (CNJ 484/2022, fidelidade $w=0.80$, CIELAB-CLAHE).
  - `roi_type: "general"`: Super-resolução neural 4x universal e deconvolução.
- `POST /api/forensic/license-plate`: Upload direto de arquivo de placa para análise ALPR.

---

## 4. Ecossistema do Tactical Video Player (`catalog/src/components/player/`)

```
                               ┌────────────────────────────────────────────────┐
                               │           TacticalVideoPlayer.tsx              │
                               │  - Atalhos: 1:Placa, 2:Rosto, 3:SR, Espaço, F  │
                               └───────┬──────────────┬──────────────┬──────────┘
                                       │              │              │
                     ┌─────────────────┴─┐     ┌──────┴───────┐     ┌┴──────────────────┐
                     ▼                   ▼     ▼              ▼     ▼                   ▼
          [InteractiveCanvasViewer]  [TacticalHUD]  [ImageToolbar]  [ForensicInspector] [AudioEngine]
          - Pan & Zoom (1x a 16x)    - Relógio ZULU - Sliders CLAHE - Split-View 0-100% - Clique MFD
          - Lupa Tática Digital      - MGRS Coord   - Botão Placa   - Duplo SHA-256     - Shutter Som
          - Recorte ROI Inteligente  - Telemetria   - Botão Rosto   - Laudo PDF Oficial - Lock-on Tone
          - Shaders WebGL / NVG/FLIR - Mil-dot HUD  - Botão 4x SR   - Exportação PNG    - Rádio Squelch
```

---

## 5. Arquitetura de Super-Resolução Extrema 8x (480p para 4K)

Para transformar transmissões severamente degradadas de **480p ($854\times480$) em 4K UHD ($3840\times2160$)** ($64\times$ mais pixels), o sistema emprega uma pirâmide de 4 motores especializados:

```
                                  [ Frame Bruto 480p Degradado ]
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 ▼                              ▼                              ▼
     [Super-Resolução Multi-Frame]    [Restauração Facial Sem Alucinação] [ALPR Forense Mercosul]
     (BasicVSR++ / RealBasicVSR)      (CodeFormer w=0.80 / CNJ 484)       (Homografia 400x130)
     - Acumula 5 a 15 quadros         - Codebook VQ-GAN 1024-d            - Deconvolução de Wiener
     - Alinhamento DCNv2 Guiado       - ArcFace Cosseno >= 0.65           - Binarização de Sauvola
     - Informação Sub-Pixel Real      - Sem alucinação biométrica         - OCR com Regex Mercosul
                 │                              │                              │
                 └──────────────────────────────┼──────────────────────────────┘
                                                │
                                                ▼
                                   [Motor de Upscaling Neural 8x]
                                   (RRDBNet8x / Real-ESRGAN / HAT)
                                   - Tiling com Janela de Hann 2D
                                   - PixelShuffle Sub-Pixel Conv
                                   - Execução TensorRT FP16 / OpenVINO
                                                │
                                                ▼
                                    [ Imagem Final 4K UHD ]
                                (3840x2160 com Hashes SHA-256)
```

---

## 6. Conformidade Pericial, Jurídica e Criptográfica

1. **Visão Computacional & Biometria em Larga Escala (InsightFace / Sub-center ArcFace):**
   - Extração de embeddings topológicos de 512 dimensões com o algoritmo **Sub-center ArcFace (ECCV 2020)**.
   - Isolamento de imagens ruidosas de treino em subcentros secundários para maximização de acurácia de inferência em vias públicas e câmeras CFTV.
2. **Sistema ALPR em Duas Fases (YOLOv8 + EasyOCR):**
   - **Fase 1 (Deteção):** YOLOv8 treinado em datasets dedicados (ex: *Rodosol-ALPR*) isolando a placa e o chassi em passo único com aceleração CUDA.
   - **Fase 2 (OCR):** EasyOCR (PyTorch CNN + RNN) para leitura sequencial de caracteres Mercosul e legados, com limiares de confiança e validação por Regex estrito.
3. **Indexação Espacial DGGS & PostgreSQL/PostGIS (`h3-pg v4.x`):**
   - Resoluções Uber H3 (Res 7 Batalhão ~1.4km, Res 8 Bairro ~500m, Res 9 Cruzamento ~200m).
   - Migração para taxonomia `h3-pg v4.x`: `h3_lat_lng_to_cell()`, `h3_grid_disk()`, `h3_cell_to_children()` e `h3_cell_to_boundary_geometry()` (retornando `MULTIPOLYGON`).
   - Otimização via Colunas Geradas armazenadas:
     ```sql
     ALTER TABLE pontos_acesso ADD h3_ix H3INDEX GENERATED ALWAYS AS (
         h3_lat_lng_to_cell(ST_Transform(geom, 4326), 8)
     ) STORED;
     CREATE INDEX idx_pontos_acesso_h3_gist ON pontos_acesso USING GIST (h3_ix);
     ```
4. **Ledger Imutável & Prova Criptográfica com Árvores de Merkle (`pymerkle`):**
   - Cada evento físico (placa/face + timestamp UTC + célula H3) gera um hash SHA-256 agregado recursivamente na Árvore de Merkle.
   - O *Root Hash* temporal inviabiliza adulterações retroativas em bancos de dados por usuários privilegiados.
5. **Assinaturas Digitais PAdES-LTA e Preservação a Longo Prazo (`pyHanko`):**
   - Conformidade com **ISO 32000-2**, **RFC 5652 (CMS)** e **ETSI PAdES B-LTA**.
   - Injeção de **Document Security Store (DSS)** com CRLs e respostas OCSP para validação de longo prazo (LTV), independente da expiração futura do certificado X.509.
   - Carimbo de tempo atômico oficial via Autoridade de Carimbo do Tempo (TSA / RFC 3161) com `PdfTimeStamper`.
   - Suporte a chaves em hardware HSM via **PKCS#11** (Zero Trust) e auditoria de integridade com `SignatureCoverageLevel` (`ENTIRE_FILE`, `ENTIRE_REVISION`, `CONTIGUOUS_BLOCK_FROM_START`).

---

## 7. Diretrizes da Consultoria Arquitetural C4ISR (Tauri v2, Edge AI & Zero Trust)

### A. IPC de Ultra Performance no Tauri v2 & Streaming Binário
- **Gargalo Superado**: A serialização JSON/Base64 convencional introduz até 200ms de latência em payloads de 3MB e bloqueios na UI do React.
- **Custom URI Protocols**: Uso de `register_asynchronous_uri_scheme_protocol` (ex: `olhodeus://stream/sensor-alfa`) para entrega de bytes brutos direto para `<canvas>` e WebGL, obtendo **ganho de velocidade de 175x**.
- **Tauri Channels (`tauri::ipc::Channel`)**: Barramento de push em tempo real para telemetria, detecções YOLOv8 e bounding boxes, eliminando *polling* do frontend.
- **Tuning de WebSockets (`tauri-plugin-websocket`)**: `maxMessageSize = 64 MiB` (evitando OOM), `writeBufferSize = 128 KiB` para envio sem fragmentação TCP.

### B. Otimização de Binários & Compilação Cargo (Hardware Restrito / Edge)
- **Perfil de Release em `Cargo.toml`**:
  ```toml
  [profile.release]
  codegen-units = 1
  lto = "fat"
  opt-level = 3
  strip = true
  panic = "abort"
  ```
- **Expurgação de Código Morto**: Diretiva `removeUnusedCommands` no `tauri.conf.json` combinada com as ACLs de Capabilities.

### C. Despacho Heterogêneo de Edge AI (Hardware-Aware)
- **NVIDIA GPU (Centros C2 / Viaturas)**: Compilação via **TensorRT** com fusão de camadas e quantização FP16/INT8.
- **Intel x86 (Laptops / Thin Clients)**: Inferência vetorizada via **OpenVINO** explorando instruções AVX-512 e iGPU Xe.
- **ARM SBCs / Drones / Dispositivos Móveis**: Execução leve via **NCNN** com aceleração ARM NEON e NPUs (inferência sub-30ms).
- **Orquestrador Unificado**: **ONNX Runtime** como fallback agnóstico de arquitetura.

### D. Tiering Híbrido de Bases de Dados (OSINT & Grafos)
- **Bases Vetoriais**:
  - **Milvus**: Centro de Comando Principal (bilhões de vetores, HNSW, multi-tenancy, aceleração GPU).
  - **Qdrant**: Nós Regionais (Rust nativo, filtragem payload + vetores).
  - **pgvector**: Borda Tática Local / Dispositivos Individuais (ACID relacional).
- **Bases de Grafos (Redes Complexas de Ameaças)**:
  - **Memgraph**: Interceptação em Tempo Real (In-Memory C++, consultas sub-milissegundo OpenCypher, 120x mais rápido).
  - **Neo4j Enterprise / ArcadeDB**: Data Lake de Inteligência Fria e macro-análise forense em disco (licença Apache 2.0 sem restrições BSL).

### E. Doutrina Militar Zero Trust (ZTA) & FIPS 140-3
- **Capabilities Baseadas em Menor Privilégio**: Manifestos JSON estritos em `src-tauri/capabilities/`.
- **Isolation Pattern**: Iframe em sandbox criptografada via **AES-GCM** com rotação estocástica de chaves em cada inicialização do aplicativo contra ataques de Supply Chain e RCE.
- **NIST SP 800-76 & FIPS 140-3**: Assinaturas digitais de templates biométricos e compilação com `rustls-tls` sobre bibliotecas criptográficas homologadas (BoringSSL FIPS / PKCS#11).

---

## 8. Instruções para Desenvolvimento e Execução

### Executando o Ambiente Completo:
```bash
# 1. Iniciar Banco de Dados e Cache (PostgreSQL + Redis + go2rtc)
docker-compose up -d

# 2. Iniciar API Central C4ISR (Porta 8000)
poetry run python olho_de_deus/api_server.py

# 3. Iniciar Servidor de Câmeras (Porta 8001)
poetry run python olho_de_deus/camera_grid_server.py

# 4. Iniciar Frontend Web / Desktop (Porta 1420)
cd catalog && npm run dev
```

---
*Este documento é a referência única de verdade técnica do projeto. Qualquer atualização de código deve ser imediatamente refletida no topo deste arquivo.*
