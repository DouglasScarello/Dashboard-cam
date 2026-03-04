# 🔒 Olho de Deus — Sistema de Inteligência Biométrica Global

> Sistema de inteligência artificial para identificação de indivíduos procurados e desaparecidos em feeds de vídeo ao vivo. **Ghost Protocol** — 100% local, nenhum dado enviado externamente.

---

## 📦 Arquitetura Modular

```
Dashboard/
├── 🌐 catalog/            → Módulo 1: Intelligence Catalog (Tauri V2 + React + i18n Neural)
├── 👁️  olho_de_deus/       → Módulo 2: Motor de análise facial e comportamento (YOLOv8 + OpenVINO)
├── 🛰️  Dashboard Cam FBI/  → Módulo 3: Central de Comando Tático (Mapa, Heatmap, Telemetria)
├── 📊 intelligence/       → Módulo 4: Banco de dados unificado (PostgreSQL + pgvector)
└── 📹 [Vigilancia/]       → Sistema tático de CFTV (anti-sabotagem, Telegram, biometria local)
```

---

## 🌐 Módulo 1 — Intelligence Catalog (`catalog/`)

Interface forense de alta performance para busca e análise de perfis criminais globais.

- **Stack:** Tauri V2 (Rust) + React + Vite + Tailwind CSS
- **Destaques:**
  - **Premium Dark UI:** Estética inspirada em interfaces forenses militares.
  - **i18n Neural (Fase 9):** Tradução 100% local via **LibreTranslate (Docker)** com proxy Rust `async/await`.
    - Rust backend: `translate_text` usa `reqwest::Client` gerenciado via `tauri::State` (sem re-criação por chamada).
    - React: traduções disparam em **paralelo** com `Promise.allSettled()` — sem race conditions, sem memory leaks.
  - **Idiomas:** Português 🇧🇷, Inglês 🇺🇸, Russo 🇷🇺
  - **Dossiê Forense:** Galeria multi-face, traços físicos completos, aliases, crimes, locais.
  - **Filtros Avançados:** Busca por nome, crime, país, status biométrico, fonte.
  - **Rotas por Hash:** Navegação direta via `#/id/UID`.

```bash
# Iniciar sistema de tradução (Ghost Protocol)
docker run -d -p 5000:5000 -e LT_LOAD_ONLY=pt,en,ru libretranslate/libretranslate

# Iniciar o catálogo
cd catalog && npm run tauri dev
```

---

## 👁️ Módulo 2 — Olho de Deus (`olho_de_deus/`)

Motor de visão computacional com player forense interativo e rastreamento biométrico em tempo real.

| Componente | Descrição |
|---|---|
| YOLOv8n-pose | Detecção de anomalias (quedas/comportamento) |
| YOLOv8n-weapon| Detecção de armas com lógica HOI (Human-Object Interaction) |
| ArcFace 512-d | Extração de características biométricas únicas |
| OpenVINO | Aceleração por hardware para Ryzen 7 (Static Shapes) |
| FAISS | Busca vetorial de alta velocidade (16k+ embeddings) |
| REID / IoU | Rastreamento persistente entre frames |
| Player Forense | Seek bar interativo, modo passo-a-passo |

### 🛡️ Prevenção Tática Ativa (Fase 30.1)
- **Detecção de Armas:** Lógica profissional que confere a distância entre o pulso da pessoa e a arma detectada.
- **Níveis de Alerta:** Escala tática de 1 a 10 para triagem de ameaças.
- **Dossiê Criptografado (Fase 22):** Geração de relatórios periciais protegidos por **AES-256** em modo EAX.

### 🌍 Camada de Ingestão Global (Fase 9)

| Script | Fonte | Registros |
|---|---|---|
| `fbi_ingestion.py` | FBI Wanted API | ~1.129 |
| `interpol_ingestion.py` | Interpol Red + Yellow Notices | ~15.000 |
| `opensanctions_ingestion.py` | Europol, NCA UK (OpenSanctions CSV) | ~220 |
| `bnmp_ingestion.py` | BNMP — Banco Nacional de Mandados (Brasil) | variável |
| `asia_ingestion.py` | Fontes regionais Ásia-Pacífico | variável |
| `us_local_ingestion.py` | Delegacias estaduais dos EUA | variável |
| `extract_embeddings.py` | Extrator ArcFace em lote + indexador FAISS | — |
| `verify_intel.py` | Verificador pós-ingestão (integridade do banco) | — |
| `run_global_intelligence.py` | **Orquestrador unificado** (executa todos em sequência) | — |

```bash
cd olho_de_deus

# Executar todos os ingestores em sequência
poetry run python run_global_intelligence.py

# Extrair embeddings ArcFace e indexar no FAISS
poetry run python extract_embeddings.py

# Verificar integridade do banco
poetry run python verify_intel.py

# Stream YouTube em modo forense com IA ativa
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic
```

---

## 🛰️ Módulo 3 — Central de Comando Tático (`Dashboard Cam FBI/`)

Visualização em tempo real de múltiplas fontes com inteligência geográfica integrada.

- **Mapa Tático (Fase 13):** Integração Leaflet.js com marcadores pulsantes e heatmap de risco.
- **Auto-Focus:** O mapa centraliza automaticamente em ameaças com Score > 8.0.
- **Tactical Log:** Registro cronológico lateral de todos os avistamentos detectados.
- **Filtros de Busca (Fase 15):** Filtragem instantânea por Score, Categoria e Localização sobre 60k+ registros.
- **System Health (Fase 20):** Telemetria via Rust (CPU/RAM/Temp) integrada ao dashboard para monitoramento de hardware.

---

## 📊 Módulo 3 — Intelligence Backend (`intelligence/`)

Central de dados com **16.000+ registros** unificados de diversas agências internacionais.

- **Suporte Dual:** SQLite (local/dev) com fallback automático de PostgreSQL.
- **Busca Vetorial:** PostgreSQL + `pgvector` para similaridade biométrica em alta velocidade.
- **Path Resolution:** `DB_FILE` usa caminho absoluto derivado de `__file__` — sem banco fantasma.

```bash
cd intelligence

# Inicializar banco
poetry run python intelligence_db.py

# Popular tudo (FBI + OpenSanctions + FAISS embeddings)
poetry run python populate_db.py

# Busca interativa via terminal
poetry run python intelligence_db.py search
```

---

## ⚡ Stack Técnica

| Camada | Tecnologia |
|---|---|
| Frontend | Tauri V2 (Rust) + React / Vite / Tailwind |
| Tradução Neural | LibreTranslate (Docker, auto-hospedado) |
| Proxy Rust | `reqwest async` + `tauri::State` |
| i18n React | `react-i18next` + `Promise.allSettled()` |
| Detecção | YOLOv8n (Ultralytics, CPU-optimized) |
| Biometria | ArcFace 512-d via DeepFace |
| Vetor DB | FAISS (local) + pgvector (produção) |
| Storage | SQLite 3 (WAL) / PostgreSQL 15 |
| Hardware-alvo | AMD Ryzen 4600H (otimizado p/ CPU) |

---

## 🚀 Quickstart

```bash
# 1. Tradução local (Ghost Protocol)
docker run -d -p 5000:5000 -e LT_LOAD_ONLY=pt,en,ru libretranslate/libretranslate

# 2. (Opcional) PostgreSQL via Docker
docker compose up -d postgres

# 3. Popular banco de inteligência
cd olho_de_deus
poetry install
poetry run python run_global_intelligence.py  # todos os ingestores
poetry run python extract_embeddings.py        # gerar vetores ArcFace

# 4. Iniciar o Catálogo Visual
cd ../catalog
npm install
npm run tauri dev
```

> [!NOTE]
> Fotos, banco de dados e embeddings FAISS não estão incluídos no repositório por tamanho e privacidade. Execute os scripts de ingestão para gerar os dados localmente.

> [!IMPORTANT]
> **Ghost Protocol ativo:** nenhum dado biométrico ou de inteligência é transmitido para servidores externos. Todo o processamento e armazenamento é 100% local.

---

## 📋 Changelog

| Fase | Descrição |
|---|---|
| **Fase 30-31** | **Prevenção Ativa:** Detecção HOI de armas, Aceleração OpenVINO, Cache Redis, WebRTC Low-Latency |
| **Fase 22** | **Hardening:** Criptografia AES-256 de dossiês periciais (.locked files) |
| **Fase 20** | **System Health:** Telemetria de hardware via Rust (sysinfo) integrada ao HUD |
| **Fase 15** | **Busca Avançada:** Filtros multicritério instantâneos no dashboard |
| **Fase 13** | **Geo-Intelligence:** Mapa tático, Heatmap de risco, Pulse Markers e Tactical Log |
| **Fase 12** | **Threat Scoring:** Motor de pontuação de risco automatizado |
| **Fase 9** | Camada de ingestão global (+7 ingestores), proxy Rust async, `Promise.allSettled` no i18n |
| **Fase 8** | Cobertura i18n global (PT/EN/RU), tradução neural local via Rust Proxy |
| **Fase 5-7** | Overhaul arquitetural, Intelligence Catalog, Dossiê forense completo |
| **Fase 1-4** | Video Wall, Motion Trail, Modularização e FBI API |
