# 🔒 Olho de Deus OSS — Sistema de Monitoramento Biométrico

> Sistema de inteligência artificial para identificação de indivíduos procurados e desaparecidos em feeds de vídeo ao vivo. **Ghost Protocol** — 100% local, nenhum dado enviado externamente.

---

## 📦 Arquitetura Modular

```
Dashboard/
├── 🌐 catalog/            → Módulo 1: Intelligence Catalog (Tauri + Premium Dark UI)
├── 👁️ olho_de_deus/        → Módulo 2: Motor de análise facial em tempo real (YOLOv8 + ArcFace)
└── 📊 intelligence/       → Módulo 3: Banco de dados global + Ingestão (16.000+ registros)
```

---

## 🌐 Módulo 1 — Intelligence Catalog (`catalog/`)

Interface de alta performance para busca e análise de perfis criminais globais. Redesenhada para um visual **Premium Dark**.

- **Stack:** Tauri V2 + React + Vite + Tailwind CSS
- **Destaques:**
    - **Premium Dark UI:** Estética inspirada em interfaces forenses militares.
    - **Suporte Multi-idioma (i18n):** Interface e dados dinâmicos traduzíveis para **Português, Inglês e Russo**.
    - **Tradução Neural Local:** Integração com **LibreTranslate (Docker)** para traduzir 100% dos dados dinâmicos (crimes, locais, descrições) mantendo o Ghost Protocol.
    - **Galeria Forense:** Suporte a múltiplos indivíduos/faces em um único registro.
    - **Filtros Avançados:** Busca por nome, crime, país e status biométrico.
    - **Rotas por Hash:** Navegação direta para perfis específicos (`#/id/UID`).
- **Inicia com:** `npm run tauri dev` dentro de `catalog/`

---

## 👁️ Módulo 2 — Olho de Deus (`olho_de_deus/`)

Motor de visão computacional com player forense interativo e rastreamento biométrico.

| Componente | Descrição |
|---|---|
| YOLOv8n | Detecção de faces em tempo real (CPU-optimized) |
| ArcFace 512-d | Extração de características biométricas únicas |
| REID / IoU | Rastreamento persistente entre frames (economia de CPU) |
| Player Forense | Seek bar interativo, navegação frame-a-frame, modo passo |

```bash
cd olho_de_deus
# Stream YouTube em modo forense
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic --step 10
```

---

## 📊 Módulo 3 — Intelligence (`intelligence/`)

Central de dados com **16.129 registros** unificados de diversas agências internacionais.

### Fontes Integradas

| Fonte | Registros | Categoria |
|---|---|---|
| Interpol Red Notices | 6.437 | 🔴 Procurados |
| Interpol Yellow Notices | 8.543 | 🟡 Desaparecidos |
| FBI Wanted | 1.129 | 🔴 Procurados (com fotos e galeria) |
| UK NCA | 20 | 🔴 Procurados |
| Europol | ~200 | 🔴 Procurados |

### Como usar o Banco

```bash
cd intelligence
# Sincronizar banco e fotos
poetry run python populate_db.py --sync-photos

# Busca interativa via terminal
poetry run python intelligence_db.py search
```

---

## ⚡ Stack Técnica

| Camada | Tecnologia |
|---|---|
| Frontend | Tauri V2 (Rust) + React / Vite / Tailwind |
| Core i18n | react-i18next (PT, EN, RU) |
| Tradução Neural | LibreTranslate (Auto-hospedado via Docker) |
| Detecção | YOLOv8n (Ultralytics) |
| Biometria | ArcFace (DeepFace Framework) |
| Vetor DB | FAISS (Vetorização de 16k+ faces) |
| Storage | SQLite 3 (WAL Mode) |
| Hardware-alvo | AMD Ryzen 4600H (Otimizado p/ CPU) |

---

## 🚀 Quickstart

```bash
# 1. Inicie o motor de tradução (Ghost Protocol - 100% Local)
docker run -d -p 5000:5000 -e LT_LOAD_ONLY=pt,en,ru libretranslate/libretranslate

# 2. Prepare o banco de inteligência
cd intelligence
poetry install
poetry run python populate_db.py --sync-photos

# 3. Inicie o Catálogo Visual
cd ../catalog
npm install
npm run tauri dev
```

> [!NOTE]
> Fotos e banco de dados local não estão incluídos no GitHub por conta do tamanho. Rode os scripts de ingestão para gerar seus dados locais.
