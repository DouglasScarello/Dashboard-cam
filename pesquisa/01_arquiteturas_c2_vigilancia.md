# Módulo 01: Arquiteturas de C2 (Command & Control), VMS Corporativos e C4ISR

## 1. Palantir Gotham / Foundry & Ontologias Táticas
- **Modelo OLE (Object-Link-Event)**: Separação rigorosa entre metadados ontológicos, conjuntos de objetos e write-back transacional.
- **Fusão de Sensores (JDL Níveis 0 a 3)**: Associação probabilística de trilhas de radar, dados AIS/ADS-B, sinais de rádio e visão computacional via filtros de Kalman Estendido/IMM e distância de Mahalanobis.
- **Emulação Open-Source para o Olho de Deus**:
  - Banco de Grafos Temporais: **Memgraph / Neo4j** (consultas em Cypher).
  - Processamento de Eventos Complexos (CEP): **Apache Flink / Faust Python** em streaming.
  - Esquemas Semânticos Padronizados: **LinkML** para definição de ontologias criminais e táticas.

---

## 2. VMS Corporativos & Video Synopsis (Milestone, Genetec, BriefCam)

### 2.1. Ingestão e Gravação de Alta Performance
- Gravação direta em disco (*Direct-to-Disk Recording*) em blocos de vídeo sem re-codificação, preservando 100% da CPU para a IA de visão.
- Indexação temporal de bounding boxes e embeddings extraídos em tempo real.

### 2.2. Tecnologia de Video Synopsis (BriefCam)
- **Mecânica**: Extração de tubos 3D espaciotemporais ($V_i = (x, y, t)$) via segmentação por instância e tracking.
- **Otimização Global de Energia**:
  $$E = E_{\text{atividade}} + E_{\text{colisão}} + E_{\text{ordem}}$$
  Resolvido via *Graph Cuts* ou *Simulated Annealing*, renderizando objetos detectados em momentos distintos (ex.: 8 horas de gravação) simultaneamente em um resumo de 3 minutos, com carimbo de tempo individualizado e clique para pular ao vídeo original.

---

## 3. AnyVision / Oosto: Reconhecimento Facial em Multidões

### 3.1. Pipeline de 4 Estágios
1. **Detecção Ultrarrápida**: SCRFD-10GF INT8 via TensorRT (< 2 ms).
2. **Filtragem Mandatória de Qualidade (FIQA)**: MagFace / AdaFace Norm Filter descarta faces borradas, com oclusão severa ou ângulos extremos antes de computar o embedding completo.
3. **Agregação de Embeddings do Tracklet**: Em vez de avaliar um único frame, combina múltiplos embeddings do mesmo indivíduo ponderados pela qualidade do frame ($E_{\text{tracklet}} = \sum w_i e_i$).
4. **Busca Vetorial HNSW**: Consulta em sub-milissegundos no pgvector/Qdrant.

---

## 4. Padrões Militares e Interoperabilidade de C2

### 4.1. Cursor-on-Target (CoT) & ATAK / FreeTAKServer
- Padrão XML/Protobuf leve para intercâmbio de alvos e posições táticas entre o Olho de Deus e smartphones operacionais de policiais/agentes em campo com aplicativo **ATAK** (Android Tactical Assault Kit).
- Mensagem de Alerta CoT:
```xml
<event version="2.0" uid="TARGET_ALERT_88192" type="a-f-G-U-C" time="2026-08-16T19:40:00Z" start="2026-08-16T19:40:00Z" stale="2026-08-16T19:55:00Z" how="m-g">
  <point lat="-23.550520" lon="-46.633308" hae="760.0" ce="5.0" le="2.0"/>
  <detail>
    <contact callsign="ALERTA TÁTICO: JOÃO SILVA (FORAGIDO)"/>
    <remarks>Match biométrico (92.4%) na Câmera Praça da Sé 04. Threat Score: 9.4.</remarks>
  </detail>
</event>
```

### 4.2. Orçamento de Latência de Ponta a Ponta (*Glass-to-Glass*)
- Captura de sensor de câmera: **33 ms** (30 FPS).
- Decodificação por Hardware (NVDEC Zero-Copy): **5 ms**.
- Inferência YOLOv10-Threats INT8: **1 ms**.
- Detecção e Alinhamento Facial SCRFD: **2 ms**.
- Extração de Embedding ArcFace / AdaFace INT8: **3 ms**.
- Busca Vetorial HNSW no pgvector: **2 ms**.
- Avaliação do Threat Scoring Engine: **1.8 ms**.
- Despacho de Evento (SSE / WebSocket / CoT): **4 ms**.
- **Latência Total**: **~52 ms** (Completamente imperceptível para o operador humano, permitindo resposta tática instantânea).
