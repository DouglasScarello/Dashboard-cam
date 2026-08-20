# Módulo 05: Interface Tática, Desktop Tauri v2 e Renderização de Vídeo Multi-Grid

## 1. Desktop de Alto Desempenho com Tauri v2 + Rust

### 1.1. Comparativo de Footprint 24/7 (Tauri v2 vs Electron)
| Métrica Operacional | Tauri v2 + Rust | Electron v31+ | Vantagem do Olho de Deus |
| :--- | :--- | :--- | :--- |
| **Consumo de RAM em Repouso** | **30 MB – 50 MB** | 250 MB – 500 MB | **88% de economia de RAM** |
| **16 Câmeras 1080p + Inferência** | **290 MB – 420 MB** | 2.2 GB – 3.8 GB | **87% menor footprint** |
| **Estabilidade Contínua (30+ dias)** | Platô estável (RAII Rust) | Vazamento por GC no V8 | **Zero degradação de memória** |
| **Throughput de IPC** | **1.200+ FPS (Zero-Copy)** | ~90 FPS (JSON-RPC) | **13x mais veloz** |
| **Tamanho do Binário** | **15 MB – 28 MB** | 120 MB – 180 MB | **80% mais leve** |

### 1.2. Arquitetura Multi-Janela & IPC Streaming
- **Janelas Segregadas**:
  - *Matriz Principal*: Mosaico 4x4 a 8x8 de câmeras de vigilância.
  - *HUD Flutuante de Alertas*: Janela *always-on-top* que salta na tela em caso de Threat Score $\ge 8.5$.
  - *Mesa Tática GIS*: Mapa geoespacial 2D/3D com cones de visão de câmeras e viaturas.
- **Custom Protocol Streaming (`cctv://`)**:
  - Transmissão de blocos de vídeo binários diretamente do Rust para o WebView via `tauri::ipc::Response`, sem conversão para strings base64 ou JSON.

---

## 2. Renderização de Vídeo Multi-Grid em Alta Performance (32 a 64 Câmeras)

### 2.1. Superando o Limite de Decodificadores do Browser
- Navegadores comuns bloqueiam após 12 a 16 elementos `<video>` simultâneos por limitações de instâncias de hardware da GPU.
- **Solução de Vanguarda**: **WebCodecs API + WebGPU em Canvas Único Multi-Viewport**.
  - Decodificação assíncrona de NAL units H.264/H.265 em Web Workers dedicados (`VideoDecoder`).
  - Importação de `VideoFrame` direto na GPU com **Zero-Copy** via `importExternalTexture`.
  - Renderização de até **64 câmeras simultâneas a 30 FPS em um único elemento `<canvas>` WebGPU** com shader de instâncias de quads.
  - Descarte imediato da VRAM via `videoFrame.close()`, eliminando vazamentos de memória.

### 2.2. Estratégia de Dual-Stream & Viewport Culling
- **Grid Mode**: Câmeras em mosaico recebem apenas o **Sub-stream** (640x360 @ 15-30 FPS, ~350 kbps), consumindo apenas **~25 Mbps de rede para 64 câmeras** (em vez de 256 Mbps em 1080p).
- **Focus Mode**: Ao dar duplo clique em uma câmera ou no disparo de um alarme de arma/foragido, a janela comuta instantaneamente para o **Main-stream** em 4K/1080p.
- **Viewport Culling**: Câmeras fora do campo visível da tela são pausadas ou recebem apenas 1 snapshot JPEG a cada 5 segundos.

---

## 3. Mapas Táticos Geoespaciais (GIS) & Rastreamento em Tempo Real

### 3.1. Motores Gráficos Geoespaciais
- **MapLibre GL + Deck.gl (`TripsLayer` + `H3HexagonLayer`)**: Renderização de 50.000+ entidades em tempo real a 60 FPS com aceleração por GPU.
- **CesiumJS (3D Globe)**: Operações aéreas com drones, helicópteros e análise volumétrica de linha de visada (Line of Sight - LOS) com suporte a nuvens de pontos LiDAR (PNTS) e 3D Tiles.

### 3.2. Servidores de Tiles OpenStreetMap 100% Offline (Air-Gap)
- **Planetiler**: Geração ultra-rápida de vector tiles `MBTiles` a partir do `.osm.pbf` em menos de 15 minutos.
- **Martin (Rust)**: Servidor de tiles vetoriais de altíssima performance (>50.000 req/s, latência < 2 ms).
- **Nominatim Local**: Geocodificação reversa offline sem dependência de APIs externas de mapas.

### 3.3. Cones de Visão Táticos (FOV DORI)
- Cálculo geométrico do campo de visão da câmera baseado no padrão **DORI** (EN 62676-4):
  - *Detection* (25 px/m), *Observation* (62.5 px/m), *Recognition* (125 px/m), *Identification* (250 px/m).
- Plotagem dinâmica de azimute, tilt e zoom de câmeras PTZ no mapa vetorial.
