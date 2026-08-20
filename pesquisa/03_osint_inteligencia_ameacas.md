# Módulo 03: OSINT, Inteligência Tática e Ingestão de Ameaças Globais

## 1. Arquitetura de Ingestão de Agências Internacionais

### 1.1. Interpol (Red & Yellow Notices)
- **Endpoints Públicos**:
  - `GET https://ws-public.interpol.int/notices/v1/red` (Filtros: `name`, `forename`, `nationality`, `ageMin`, `ageMax`, `resultPerPage=160`).
  - `GET https://ws-public.interpol.int/notices/v1/red/{entity_id}` (Detalhes completos: marcas corporais, tatuagens, idiomas, mandados de prisão, mandados de extradição).
- **Extração de Imagens**: Endpoint de fotos `_embedded.images` com resolução máxima original.
- **Normalização de Dados**:
  - Nomes em formato `LASTNAME, Firstname Middlename`.
  - Tratamento de caracteres não-ASCII (cirílico, árabe, caracteres diacríticos) via transliteração Unicode NFKD.
  - Geração de UID determinístico: `hashlib.sha256(interpol_entity_id.encode('utf-8')).hexdigest()[:16]`.

### 1.2. FBI Wanted API
- **Endpoint**: `https://api.fbi.gov/wanted/v1/list` (Parâmetros: `page`, `pageSize=50`, `poster_classification=default`).
- **Campos Estruturados**: `title`, `aliases`, `reward_text`, `reward_min`, `reward_max`, `scars_and_marks`, `caution`, `details`, `fingerprint_classification`, `dates_of_birth_used`.
- **Download Resiliente**: Pipeline com backoff exponencial assíncrono (`aiohttp` + `tenacity`) para download de fotos em alta definição.

### 1.3. Europol, US Marshals & Polícia Federal Brasileira (BNMP / CNJ)
- **Europol Most Wanted**: Scraping estruturado com extração de acusações penais e categorias EU-FAST (Fugitive Active Search Teams).
- **Banco Nacional de Mandados de Prisão (BNMP 3.0 / CNJ)**: Consulta automatizada a mandados em aberto, tipificação penal do Código Penal Brasileiro e dados de varas de execução criminal.

---

## 2. Frameworks de OSINT Open-Source

### 2.1. Comparativo de Motores
| Framework | Foco Principal | Arquitetura | Integração Olho de Deus |
| :--- | :--- | :--- | :--- |
| **SpiderFoot** | Footprinting automatizado & OSINT passivo | Python / Flask / Celery | Módulo de enriquecimento de IP, domínio e rede |
| **Maltego** | Visualização de entidades e link analysis | Java / Transform Hub | Exportação de grafos de vínculos criminais |
| **IntelOwl** | Orquestração de Threat Intelligence | Django / Celery / Docker | Analisador de arquivos, hashes e metadados de mídia |
| **Maigret / Sherlock** | Enumeração de perfis sociais em 3.000+ sites | Python assíncrono | Descoberta de pegada digital por apelidos/aliases |

---

## 3. Algoritmos de Threat Scoring e Avaliação de Risco

### 3.1. Fórmula Ponderada de Periculosidade Tática
$$Score = \min\left(10.0, \, W_{\text{crime}} \cdot S_{\text{crime}} + W_{\text{reward}} \cdot S_{\text{reward}} + W_{\text{rec}} \cdot S_{\text{rec}} + W_{\text{weapon}} \cdot S_{\text{weapon}} + W_{\text{fugitive}} \cdot S_{\text{fugitive}}\right)$$

Onde os pesos táticos normalizados ($\sum W_i = 1.0$) são calibrados:
- $W_{\text{crime}} = 0.40$: Gravidade penal (Homicídio, Tráfico Internacional, Terrorismo, Latrocínio $\to$ $S_{\text{crime}} \in [8.0, 10.0]$).
- $W_{\text{weapon}} = 0.25$: Histórico ou indícios de porte de armamento de grosso calibre / confronto armado.
- $W_{\text{reward}} = 0.15$: Recompensa monetária (ex.: FBI \$100k a \$5M $\to$ $S_{\text{reward}} \in [7.0, 10.0]$).
- $W_{\text{fugitive}} = 0.10$: Status de fuga ativa e mandado de prisão de alta prioridade.
- $W_{\text{rec}} = 0.10$: Reincidência e múltiplos mandados em diferentes jurisdições.

### 3.2. Thresholds de Despacho Operacional
- **Score $\ge 8.5$ (Nível Vermelho / Crítico)**: Disparo imediato de alarme sonoro, notificação push prioritária para equipes táticas de pronta resposta, lock down preventivo de acessos monitorados.
- **Score $6.0 - 8.4$ (Nível Âmbar / Elevado)**: Alerta na Sala de Situação com acompanhamento contínuo por câmeras PTZ.
- **Score $< 6.0$ (Nível Azul / Monitoramento)**: Registro silencioso na cadeia de custódia e alimentação do grafo de movimentação espaciotemporal.
