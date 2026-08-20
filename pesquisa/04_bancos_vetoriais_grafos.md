# Módulo 04: Bancos de Dados Vetoriais, Grafos de Conexão e Infraestrutura de Dados

## 1. PostgreSQL com pgvector em Escala de Milhões de Vetores

### 1.1. HNSW vs IVFFlat no pgvector
- **HNSW (Hierarchical Navigable Small World)**:
  - *Latência*: **1.4 ms a 2.8 ms** para 1M vetores 512d com Recall > 98%.
  - *Comportamento*: Grafo multicamada ideal para streams contínuos de câmeras CFTV; sem degradação ou necessidade de rebuilds periódicos.
  - *Parâmetros de Produção*: `m = 16`, `ef_construction = 64`, `ef_search = 80`, `iterative_scan = 'relaxed_order'`.
- **IVFFlat**:
  - Baseado em centróides $K$-Means. Sofre de *drift* de distribuição em inserções contínuas, exigindo `REINDEX` frequente.

### 1.2. Otimizações de Memória & Quantização
- **`halfvec` (FP16)**: Reduz o consumo de RAM em **50%** (1.032 bytes/linha para 512d) sem perda mensurável de TAR (True Accept Rate).
- **Binary Quantization (BQ 1-bit)**: Converte vetores normalizados em `bit(512)` (72 bytes/linha, economia de 96.5%).
- **Busca em 2 Estágios (Two-Stage Re-Ranking)**:
  1. Filtragem rápida dos Top-200 candidatos via HNSW em `bit(512)` com distância de Hamming (`<~>`) em $< 0.5 \text{ ms}$.
  2. Re-ranking exato dos 200 candidatos calculando o Cosseno no vetor `halfvec(512)` em $< 1.0 \text{ ms}$.
  3. Latência total: **~1.5 ms** com **Recall > 98%**.

### 1.3. Particionamento Físico & Tiering de Armazenamento
- **Particionamento Híbrido**: Range Temporal (Semanal/Diário) + Subparticionamento por Setor Geográfico (`sector_id`).
- Cada partição folha contém ~500k a 1M vetores, garantindo que o índice HNSW de cada setor permaneça **100% residente no `shared_buffers` e L3 Cache** ($< 400\text{ MB}$ por partição).

---

## 2. Bancos de Grafos e Análise de Redes Criminosas (Link Analysis)

### 2.1. Comparativo de Motores de Grafos
| Motor | Arquitetura | Linguagem de Consulta | Uso Tático Recomendado |
| :--- | :--- | :--- | :--- |
| **Memgraph** | In-Memory C++ | OpenCypher | Análise em tempo real de coocorrência em câmeras |
| **Neo4j** | Grafo Nativo Java | Cypher + GDS Library | Investigações aprofundadas e clusterização de facções |
| **Apache AGE** | Extensão PostgreSQL | OpenCypher em SQL | Solução unificada relacional + vetores + grafos |

### 2.2. Modelagem da Ontologia Criminal
- **Nós ($\mathcal{V}$)**: `Suspeito`, `Veículo`, `Câmera`, `Crime`, `Localização`, `Organização Criminosa`.
- **Arestas ($\mathcal{E}$)**:
  - `(Suspeito)-[:VISTO_COM {camera_id, timestamp, delta_t}]->(Suspeito)`
  - `(Suspeito)-[:CONDUZ {placa, confianca}]->(Veículo)`
  - `(Suspeito)-[:MEMBRO_DE {hierarquia, desde}]->(Organização)`
  - `(Suspeito)-[:INCIDENTE_REGISTRADO {artigo_penal, bo_id}]->(Crime)`

### 2.3. Algoritmos de Grafos para Inteligência Policial
- **PageRank Ponderado**: Identificação de líderes e pontos focais em redes criminosas.
- **Detecção de Comunidades (Louvain / Leiden)**: Mapeamento de células e quadrilhas atuantes em diferentes bairros.
- **Caminho Mais Curto (Shortest Path)**: Descoberta de elos intermediários ocultos entre dois alvos de alto valor.

---

## 3. Armazenamento Imutável de Evidências (WORM) & Cadeia de Custódia

### 3.1. Arquitetura de Armazenamento
- **MinIO / SeaweedFS**: Armazenamento de objetos compatível com S3 em rede local isolada (Air-gap).
- **Object Locking (WORM - Write Once Read Many)**: Impede deleção ou modificação de fotos e clipes de vídeo por período legal estipulado (ex.: 5 anos).

### 3.2. Carimbo e Integridade Criptográfica
- No exato milissegundo da detecção:
  1. Hash SHA-256 do arquivo original gravado em tabela imutável com carimbo de tempo RFC 3161.
  2. Assinatura digital da evidência com par de chaves ED25519 do nó de captura.
  3. Criptografia em repouso com envelope AES-256-GCM antes do envio ao storage.
