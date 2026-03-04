# 🔒 Olho de Deus — Sistema de Inteligência Biométrica Global

> Sistema de inteligência artificial para identificação de indivíduos procurados e desaparecidos em feeds de vídeo ao vivo. **Ghost Protocol** — 100% local, nenhum dado enviado externamente.

---

## 📦 Arquitetura Modular

```
Dashboard/
├── 🌐 catalog/            → Módulo 1: Intelligence Catalog (Tauri V2 + React + i18n Neural)
├── 👁️  olho_de_deus/       → Módulo 2: Motor de análise facial (YOLOv8 + ArcFace + FAISS)
├── 📊 intelligence/       → Módulo 3: Banco de dados unificado (SQLite / PostgreSQL + pgvector)
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
| YOLOv8n | Detecção de faces em tempo real (CPU-optimized) |
| ArcFace 512-d | Extração de características biométricas únicas |
| FAISS | Busca vetorial de alta velocidade (16k+ embeddings) |
| REID / IoU | Rastreamento persistente entre frames |
| Player Forense | Seek bar interativo, modo passo-a-passo |

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

# Stream YouTube em modo forense
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic --step 10
```

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
| **Fase 9** | Camada de ingestão global (+7 ingestores), proxy Rust async, `Promise.allSettled` no i18n, fix de DB path absoluto |
| **Fase 8** | Cobertura i18n global (PT/EN/RU), tradução neural local via Rust Proxy, refinamentos de UI |
| **Fase 7** | Overhaul arquitetural: Docker, PostgreSQL, migração React/Vite |
| **Fase 6** | Dossiê forense completo (galeria multi-face, traços físicos, aliases) |
| **Fase 5** | Intelligence Catalog — Premium Dark UI, suporte multi-face |
| **Fase 4** | Modularização em 3 módulos independentes |
| **Fase 3** | Integração FBI API + Motor de Trânsito SC |
| **Fase 1-2** | Video Wall Militar, Motion Trail Engine |
