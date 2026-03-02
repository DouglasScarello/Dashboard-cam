# 🔒 Olho de Deus OSS — Sistema de Monitoramento Biométrico

> Sistema de inteligência artificial para identificação de indivíduos procurados e desaparecidos em feeds de vídeo ao vivo. **Ghost Protocol** — 100% local, nenhum dado enviado externamente.

---

## 📦 Arquitetura Modular

```
Dashboard/
├── 📊 Dashboard Cam FBI/   → Módulo 1: Interface web (Tauri + HTML/CSS/JS)
├── 👁️ olho_de_deus/        → Módulo 2: Motor de análise facial em tempo real
└── 🌐 intelligence/        → Módulo 3: Banco de dados global + ingestão
```

---

## Módulo 1 — Dashboard (`Dashboard Cam FBI/`)

Interface web para visualização de feeds de câmeras e alertas biométricos.

- **Stack:** Tauri + HTML / CSS / JS
- **Acesso:** `http://localhost:1420`
- **Inicia com:** `npm run dev` dentro de `Dashboard Cam FBI/`

---

## Módulo 2 — Olho de Deus (`olho_de_deus/`)

Motor de visão computacional com player forense interativo.

| Componente | Descrição |
|---|---|
| YOLOv8n | Detecção de faces (CPU, otimizado p/ Ryzen 4600H) |
| ArcFace 512-d | Extração de embeddings biométricos |
| REID / IoU | Re-identificação entre frames (sem re-processar) |
| Player Forense | Seek bar estilo Netflix, play/pause, navegação por mouse |

```bash
cd olho_de_deus

# Stream YouTube em modo forense
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic --step 10

# Arquivo de vídeo local
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --source /caminho/video.mp4 --forensic
```

**Controles do player forense:**

| Tecla | Ação |
|---|---|
| `SPACE` | Play / Pause |
| `→` / `D` | Próximo frame |
| `←` / `A` | Frame anterior |
| `S` | Salvar frame como JPEG |
| `Q` / `ESC` | Sair |
| Click na barra | Seek direto |

---

## Módulo 3 — Intelligence (`intelligence/`)

Banco SQLite local com **15.000+ indivíduos** procurados e desaparecidos do mundo inteiro.

### Fontes de dados

| Fonte | Registros | Categoria |
|---|---|---|
| Interpol Red (OpenSanctions) | 6.437 | 🔴 Procurados |
| Interpol Yellow (OpenSanctions) | 8.543 | 🟡 Desaparecidos |
| FBI Wanted API | ~1.100 | 🔴 Procurados (com foto) |
| Europol EU Most Wanted | ~200 | 🔴 Procurados |
| NCA UK Most Wanted | ~20 | 🔴 Procurados |

### Banco de dados (`data/intelligence.db`)

Tabelas: `individuals` · `crimes` · `locations` · `face_embeddings`

```bash
cd intelligence

# Popular banco completo (todas as fontes)
TF_CPP_MIN_LOG_LEVEL=3 poetry run python populate_db.py

# Ingestão global (baixa imagens + gera embeddings)
TF_CPP_MIN_LOG_LEVEL=3 poetry run python global_ingestion.py

# Busca interativa no banco
poetry run python intelligence_db.py search
```

**Comandos do terminal de busca:**
- `b` → Buscar por nome / crime / país / categoria
- `d <id>` → Perfil completo de um indivíduo
- `e` → Exportar CSV completo
- `q` → Sair

---

## 🔗 Fluxo de Integração

```
intelligence/data/global_vector_db.faiss  ←── FAISS (embeddings ArcFace)
         │
         └──► olho_de_deus/biometric_processor.py  ←── comparação em tempo real
                     │
                     └──► Dashboard Cam FBI/  ←── alertas visuais (WebSocket)
```

---

## ⚡ Stack Técnica

| Camada | Tecnologia |
|---|---|
| Detecção | YOLOv8n |
| Biometria | ArcFace via DeepFace |
| Vetor DB | FAISS (IndexFlatL2) |
| Banco de dados | SQLite 3 |
| Bypass CDN | Playwright (Chromium headless) |
| Streams | yt-dlp + OpenCV |
| Hardware-alvo | AMD Ryzen 4600H · 8 GB RAM |
| OS | Linux (Wayland/X11) |

---

## 🚀 Quickstart Completo

```bash
# 1. Popular o banco de inteligência
cd intelligence
TF_CPP_MIN_LOG_LEVEL=3 poetry run python populate_db.py

# 2. Monitorar um feed com identificação
cd ../olho_de_deus
TF_CPP_MIN_LOG_LEVEL=3 poetry run python main.py --id YOUTUBE_ID --forensic --step 10

# 3. Abrir o dashboard (outro terminal)
cd ../Dashboard\ Cam\ FBI
npm run dev
```
