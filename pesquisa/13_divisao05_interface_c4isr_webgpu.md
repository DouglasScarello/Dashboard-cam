# DIVISÃO 05: INTERFACE TÁTICA C4ISR, WEBGPU & ENGENHARIA DESKTOP

## 1. Renderização Monolítica de 64 a 128 Câmeras em 1 Canvas WebGPU
- **1 Único Draw Call (`draw(6, camera_count, 0, 0)`)**: Eliminação de elementos `<video>` múltiplos com Storage Buffers para matrizes, UV coords e modos térmicos (FLIR Ironbow, White-Hot, Fósforo Verde).
- **Zero-Copy Import**: `device.importExternalTexture({ source: videoFrame })` direto da GPU sem trânsito pela CPU.

---

## 2. Pipeline de Decodificação Hardware-Accelerated (WebCodecs)
- **Worker Thread Pool**: Distribuição de 64 a 128 streams em Web Workers mantendo 120 FPS estáveis na UI principal.
- **Configuração de Baixa Latência**: H.264, H.265/HEVC e AV1 com `postMessage` transferível zero-copy.

---

## 3. Mapas Táticos Vetoriais 3D (CesiumJS & MapLibre GL)
- **Cones de Visão Volumétricos (Frustums)**: Cálculo ECEF/WGS84 com gradientes translúcidos e pulsação em caso de alerta.
- **Simbologia Militar MIL-STD-2525D**: Identificação gráfica padronizada de câmeras fixas, domos PTZ, sensores térmicos e drones UAV.

---

## 4. Design System Tático Militar & Modo Noturno Vermelho
- **MIL-STD-1472H & NATO UI/UX**: Superfícies escuras de alto contraste, tipografia monoespaçada tabular e hierarquia de alertas (Nominal, Caution, Warning).
- **Scotopic Red Mode (620-700nm)**: Proteção à rodopsina do operador e compatibilidade com equipamentos NVG.

---

## 5. Linha do Tempo Forense & Video Synopsis (BriefCam Open-Source)
- **Compressão Temporal**: Condensação de horas em minutos via tubos espaço-temporais ($YOLO + SAM/ByteTrack$) sobrepostos em fundo estático com recozimento simulado.

---

## 6. Controle PTZ de Baixa Latência (< 30ms) & Feedback Háptico
- **Loop Assíncrono Rust (250 Hz)**: Leitura USB via `gilrs` com curvas cúbicas e comandos Pelco-D/VISCA diretos por UDP (< 20ms).
- **Force Feedback**: Vibração tátil no joystick ao atingir limites de rotação ou geofences.

---

## 7. Virtualização de Grid & Gerenciamento de VRAM
- **LOD Inteligente**: 360p @ 15fps no mosaico (~1.3MB VRAM/canal), 1080p @ 30fps em foco e 4K @ 60fps em fullscreen com Texture Pool reciclado.

---

## 8. Gravador Local Contínuo com Indexação de Metadados
- **Edge Recorder Rust**: Pré-alocação de blocos fMP4 com `fallocate` e `io_uring` acoplado a SQLite WAL e miniaturas WebP instantâneas.

---

## 9. Exportação de Clipes Forenses com Hash SHA-256 e Esteganografia
- **ISO/IEC 27037**: Manifesto assinado com Ed25519 e marca d'água esteganográfica no canal de luminância Y contendo UUID, timestamp atômico e GPS.

---

## 10. Arquitetura Tauri v2 Rust Hardened (< 35MB RAM)
- **Capabilities & Sandboxing**: Alocador `mimalloc` estático e memória compartilhada `memfd_create`, mantendo footprint de RAM inferior a 35 MB.
