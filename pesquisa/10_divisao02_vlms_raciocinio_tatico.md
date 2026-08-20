# DIVISÃO 02: MODELOS FOUNDATION DE VISÃO & LINGUAGEM (VLMs) & RACIOCÍNIO TÁTICO ON-DEVICE

## 1. Moondream2, Florence-2 e MobileVLM-v2 em INT4 para Edge (Latência < 200ms)
* **Moondream2 (1.86B)**: Combina SigLIP com Phi-1.5/Phi-2. Otimizado em INT4 AWQ / GGUF Q4_K_M ocupa ~1.15 GB de VRAM. Atinge latência de prefill de 32ms e tempo total por frame de **49ms** em RTX 4060 e **190ms** em CPU/NPU RK3588.
* **Florence-2 (Microsoft - Base 230M / Large 770M)**: Modelo seq2seq unificado (DaViT + BART/BERT). Opera com tokens de comando táticos (`<OD>`, `<DETAILED_CAPTION>`, `<DENSE_REGION_CAPTION>`). Atinge **62ms** no Jetson AGX Orin e **78ms** no Jetson Orin Nano (8GB).
* **MobileVLM-v2 (1.7B / 3B)**: Utiliza projetor LDPv2 para reduzir tokens visuais de 576 para 144, viabilizando execução em NPUs móveis com latência de **125ms**.

---

## 2. Qwen2-VL e MiniCPM-V 2.6 para Busca Semântica em Vídeo ("homem de jaqueta azul entrando no beco")
* **Qwen2-VL (2B / 7B / 72B)**: Incorpora Naive Dynamic Resolution ViT e Multimodal 3D RoPE, preservando aspect ratio nativo e resolução temporal.
* **Pipeline de Indexação Forense**: Amostragem de keyframes (2-3s) $\rightarrow$ Dense Captioning via Qwen2-VL $\rightarrow$ Vetorização com BGE-M3 (1024-D) $\rightarrow$ Ingestão no Qdrant/Milvus com payload de metadados temporais e de câmera.
* **Desempenho**: Busca em linguagem natural com retorno de timestamp e evidência em **< 50ms**.

---

## 3. Geração Automática de Dossiês Narrativos e Resumos via SLMs Locais (Mistral NeMo 12B, Llama-3.2 3B)
* **Conformidade Jurídico-Policial**: Modelos calibrados com terminologia do Código Penal Brasileiro (CPB), Lei de Drogas (11.343/06) e Estatuto do Desarmamento (10.826/03).
* **Estruturação Estrita**: Uso de Pydantic e vLLM Guided Decoding / Outlines para garantir saída 100% válida em JSON (qualificação de vítimas/autores, cadeia de custódia de materiais apreendidos, histórico formal e tipificação penal preliminar).

---

## 4. Extração de Entidades Nomeadas (NER) e Relações Criminais em PDFs Policiais
* **Pipeline**: Surya OCR / PaddleOCR $\rightarrow$ Limpeza $\rightarrow$ **GliNER (Generalist and Lightweight NER)** para extração zero-shot de entidades (`individuo`, `vulgo`, `faccao_criminosa`, `veiculo_placa`, `arma_fogo`, `calibre`, `endereco_biqueira`).
* **Grafo de Conhecimento Criminal**: Geração automatizada de queries Cypher para ingestão no **Neo4j/Memgraph**, estabelecendo arestas `COMPARSA_DE`, `INTEGRANTE_DE`, `UTILIZOU_VEICULO` para link analysis tático.

---

## 5. Análise Semântica de Modus Operandi (MO) e Detecção de Reincidência
* **Vetorização de MO**: Uso do BGE-M3 para transformar relatos táticos em vetores densos estruturados em 5 eixos (espaço-temporal, método de entrada, armamento, violência com reféns, logística de fuga).
* **Clustering & Match**: Similaridade de cosseno e HDBSCAN para cruzar novos crimes com histórico criminal de quadrilhas ativas, apontando autoria provável e risco de reincidência.

---

## 6. Análise Multimodal de Áudio + Vídeo para Cenas de Violência
* **Fusão Multissensorial**:
  * **Acústico**: YAMNet / BEATs (disparos de arma de fogo, vidros quebrando, explosões) + Whisper Large-v3-Turbo (ASR em tempo real para ameaças verbais).
  * **Visual**: Florence-2 / YOLOv11-Pose (agressão física, empunhadura de armas).
* **Late Fusion com Sinergia Cruzada**: Fórmula de risco ponderada com termo multiplicativo de co-ocorrência visual-acústica, disparando Alerta Vermelho de despacho imediato em latência de **< 250ms**.

---

## 7. Video Question Answering (Video-QA) Forense em CFTV
* **Arquitetura Video-LLM**: LLaVA-Video-7B/72B e Qwen2-VL processando sequências temporais de 24 a 64 frames.
* **Aplicações Periciais**: Respostas a perguntas abertas de peritos forenses sobre horas de gravação, localizando ações suspeitas, itinerários e alterações de indumentária com carimbo de tempo.

---

## 8. Embeddings Multimodais Conjuntos (CLIP, SigLIP, ImageBind)
* **Meta ImageBind (Huge 1024-D)**: **6 modalidades conjuntas** (Imagem, Texto, Áudio, Térmico/FLIR, Profundidade, IMU).
* **Capacidade Tática**: Busca cruzada direta (consultar gravações térmicas por som de motor, ou buscar vídeo por áudio de disparo).

---

## 9. Raciocínio em Cadeia de Pensamento (CoT) para Tomada de Decisão em C2
* **Automação do Ciclo OODA**: Observe $\rightarrow$ Orient $\rightarrow$ Decide $\rightarrow$ Act estruturado em prompts táticos para modelos de raciocínio profundo (DeepSeek-R1, QwQ-32B, Llama-3.1-70B).
* **Validação de ROE**: Avaliação explícita de risco colateral a civis (CRA), probabilidade de emboscada e simulação de Cursos de Ação (COA) antes do envio de ordens operacionais.

---

## 10. Otimização e Quantização Extrema (TensorRT-LLM, vLLM, MLC-LLM, ONNX GenAI)
* **TensorRT-LLM**: Servidores GPU e Jetson AGX Orin (Kernel Fusion, FP8/INT4-AWQ, In-flight Batching e Paged KV-Cache, TTFT < 25ms).
* **vLLM**: Throughput multi-stream concorrente na central C4ISR.
* **MLC-LLM & ONNX Runtime GenAI**: Dispositivos heterogêneos de borda (NPUs Qualcomm Snapdragon X Elite, Apple Silicon Metal, Android e Vulkan).
