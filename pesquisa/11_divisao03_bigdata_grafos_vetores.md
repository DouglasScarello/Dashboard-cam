# DIVISÃO 03: BANCOS DE DADOS VETORIAIS, GRAFOS DE INTELIGÊNCIA & BIG DATA C4ISR

## 1. pgvector em Escala de Bilhões: BQ + PQ + HNSW + pgvectorscale (PostgreSQL 16/17)
- **Desafio de RAM:** 1 bilhão de vetores float32 de 512d exigem ~6 TB de RAM em HNSW padrão ($M=32$).
- **Solução BQ (Binary Quantization):** Vetores de 512d são comprimidos para colunas `bit(512)` (64 bytes/vetor, redução de **32×** em RAM e storage).
- **Distância de Hamming:** Comparação bitwise via hardware (`XOR` + `POPCNT` AVX-512/Neon).
- **Busca em 2 Fases (Retrieve-and-Rerank):** 
  1. *Fase 1:* Filtra Top-80 candidatos via índice HNSW sobre bits com Hamming Distance (`<~>`).
  2. *Fase 2:* Reranking exato com Cosine Distance (`<=>`) nos 80 vetores float originais.
- **pgvectorscale (StreamingDiskANN + SBQ):** Extensão Rust da Timescale que armazena grafos no SSD NVMe e aplica *Statistical Binary Quantization*, escalando para centenas de milhões de vetores com latência p99 < 5ms.

---

## 2. Qdrant vs. Milvus vs. LanceDB para Clusters Forenses Distribuídos
- **Qdrant (Rust):** Destaque para **Busca Tática em Tempo Real (<3ms)** com *Single-Stage Iterative Graph Filtering* (avaliação de filtros durante a navegação HNSW).
- **Milvus 2.4/2.5 (Go + C++ Knowhere):** Ideal para **Mega-Clusters Centrais (>500M vetores)** em arquitetura desacoplada Kubernetes.
- **LanceDB (Rust + Apache Arrow):** Engine disk-based otimizada para Direct NVMe I/O e analytics forense com consumo mínimo de RAM.

---

## 3. Grafos de Vínculo Criminal em Tempo Real com Memgraph (C++) e Neo4j Cypher
- **Memgraph (C++ In-Memory):** Elimina pausas de GC da JVM, fornecendo traversals de grafos com latências determinísticas de sub-milissegundo.
- **Queries Forenses:** Detecção de co-ocorrência espaço-temporal em mesmo hexágono H3 ($\Delta t \le 5\text{ min}$) e caminho mais curto (*Shortest Path*) com filtragem de risco entre líderes e operadores.

---

## 4. Algoritmos de Centralidade, Detecção de Comunidades (Louvain/Leiden) e Facções
- **Betweenness Centrality (Intermediação):** Identifica pontes financeiras e operadores logísticos entre facções distintas.
- **PageRank / Eigenvector:** Identifica chefes e mandantes estratégicos com alta autoridade recursiva.
- **Louvain / Leiden:** Agrupamento não-supervisionado de facções criminosas em células especializadas.

---

## 5. Resolução Probabilística de Entidades (Splink 4 / Fellegi-Sunter)
- **Modelo Fellegi-Sunter:** Match Weight $\log_2(m/u)$ com estimação EM não-supervisionada.
- **Deduplicação de Fraudes:** Unificação de cadastros com CPFs divergentes, nomes com variações fonéticas e sobreposição de vulgos criminais.

---

## 6. Motores Espaciotemporais: Uber H3, PostGIS e Tile38
- **Uber H3:** Resolução 9 (~174m) para co-presença veicular e Resolução 10 (~65m) para encontros a pé.
- **Tile38:** Geofencing in-memory em $< 1\text{ms}$ para disparo imediato de alarmes.
- **PostGIS:** Detecção de comboios suspeitos (veículos trafegando juntos em múltiplos pontos LPR com $\Delta t \le 60\text{s}$).

---

## 7. Armazenamento Imutável de Evidências com MinIO WORM e Object Lock
- **Conformidade CPP Art. 158:** Modo Compliance onde nem o `root` consegue alterar ou deletar arquivos antes do período legal (5 anos).
- **Legal Hold:** Bloqueio perpétuo de evidências digitais durante o processo criminal com SHA-256 Hash Chaining.

---

## 8. DuckDB e Apache Arrow para Analytics Forense em Memória
- **Zero-Copy Architecture:** Execução colunar vetorizada sobre Parquet com agregação e cruzamento sobre **100 milhões de registros LPR em menos de 800ms**.

---

## 9. Barramentos de Streaming: Redpanda vs. NATS JetStream
- **Redpanda (C++20 Seastar):** Core Central C4ISR (> 2.8M msgs/s por nó, p99 < 4ms).
- **NATS JetStream (Go):** Edge Broker ultraleve (~30MB) embarcado em viaturas e drones.

---

## 10. Sincronização Bidirecional Multi-Região (Edge-to-Central Store-and-Forward)
- **Operação Offline-First:** Viatura opera desconectada com SQLite WAL local e sincroniza por prioridade de QoS (P0 Alertas Imediatos por Rádio $\to$ P1 Metadados LPR $\to$ P2 Imagens $\to$ P3 Vídeo Full HD via Wi-Fi na base).
