# OSS - Omniscient Surveillance System 🛡️🛰️

![OSS Banner](https://img.shields.io/badge/Status-Operational-emerald?style=for-the-badge&logo=target)
![Aesthetics](https://img.shields.io/badge/Aesthetics-FBI%20Design-black?style=for-the-badge)
![Tech](https://img.shields.io/badge/Tech-Tauri%20%7C%20Python%20%7C%20Poetry-blue?style=for-the-badge)
![Version](https://img.shields.io/badge/Version-15.0-red?style=for-the-badge)

O **Omniscient Surveillance System (OSS)** é uma plataforma de inteligência e vigilância centralizada. O sistema é composto por um Dashboard tático de alto desempenho e um backend de processamento de imagem autônomo.

---

## 🏗️ Arquitetura do Sistema

O projeto é dividido em dois núcleos principais:

### 1. Dashboard Tauri (Painel de Controle)
Uma interface desktop ultra-rápida que serve como o "Command Center".
- **Thumbnail First**: Otimização de performance que carrega apenas imagens estáticas no grid, ativando o stream real apenas sob demanda (Economia de 80% de CPU/Banda).
- **Navegação Hierárquica**: Fluxo drill-down de geolocalização (**País > Estado > Cidade**) para gestão de milhares de feeds sem latência.
- **Importação Bulk**: Sistema de ingestão em massa de novos feeds via texto formatado.

### 2. Olho de Deus (Backend Python)
O "músculo" do sistema, responsável pelo processamento pesado e automação.
- **Auto-Healing**: Sistema de monitoramento de saúde do stream. Detecta quedas ou "Vídeo Indisponível" e recupera a conexão automaticamente via `yt-dlp`.
- **Farm Cams**: Crawler automatizado para descoberta de novas transmissões ao vivo no YouTube baseadas em termos de busca e localização.
- **Health Check**: Análise de frames via OpenCV para garantir sinal ativo e detecção de telas pretas.

---

## 🚀 Como Rodar

### Dashboard (Frontend)
Requer Node.js e Rust instalado.
```bash
cd "Dashboard Cam FBI"
npm install
npm run tauri dev
```

### Olho de Deus (Backend/Processing)
Requer Python 3.10+ e Poetry.
```bash
cd "olho_de_deus"
poetry install

# Para rodar o monitor com Auto-Healing:
poetry run python main.py --cam "Koxixos" --interval 2.0

# Para farmar novas câmeras:
poetry run python farm_cams.py
```

---

## 🛠️ Stack Tecnológica

- **Frontend**: Tauri, HTML5, JavaScript (ES6+), Tailwind CSS, HLS.js.
- **Backend/IA**: Python, OpenCV, yt-dlp, Poetry.
- **Data**: JSON Hierárquico (País/Estado/Cidade).

---

## 🌐 Rede de Monitoramento (Destaques)

| Unidade | Localização | Tipo |
| :--- | :--- | :--- |
| **Ponte Hercílio Luz** | Florianópolis, SC (BR) | YouTube Live |
| **Beira Mar Norte** | Florianópolis, SC (BR) | YouTube Live |
| **Times Square** | New York, NY (US) | 4K Stream |
| **Shibuya Crossing** | Tokyo, JP | 4K Stream |

---

*“Vigilance is our currency.”* - **OSS Command Center**
