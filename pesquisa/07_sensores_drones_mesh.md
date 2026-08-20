# Módulo 07: Sensores Especiais, Drones Táticos, Câmeras PTZ e Redes Mesh

## 1. Controle Autônomo e Rastreamento PTZ (Pan-Tilt-Zoom)

### 1.1. Protocolos de Controle
- **ONVIF Profile S/T (`ContinuousMove`, `AbsoluteMove`, `Stop`)**: Controle assíncrono via SOAP XML sobre HTTP.
- **VISCA over IP & Pelco-D**: Comunicação binária ultra-rápida (UDP/TCP, latência < 5 ms).

### 1.2. Algoritmo de Auto-Tracking com Handover Tático
- **Controle Proporcional-Derivativo (PD)**:
  - Centralização contínua do centróide da bounding box $(x_c, y_c)$ da pessoa/veículo no centro da tela.
  - Zoom dinâmico adaptativo: ajuste da distância focal ótica para manter a altura do pedestre em ~250 pixels (critério **DORI Identification**).
- **Handover Multi-Câmera**:
  - Quando o alvo se aproxima da borda do campo de visão da câmera fixa A, o sistema calcula o vetor de movimento $(\Delta x, \Delta y)$, seleciona a câmera PTZ B mais próxima no grafo topológico e comuta a mira ótica antes do alvo sair de cena.

---

## 2. Fusão Sensorial Multi-Espectral (Visão Térmica, IR e Ótica Visível)

### 2.1. Câmeras Térmicas (LWIR 8–14 µm)
- Detecção infalível de alvos vivos e veículos em total escuridão, neblina, chuva torrencial ou camuflagem militar.
- **Deep Fusion Networks**: Fusão pixel-a-pixel de textura RGB (alta resolução) com gradiente térmico infravermelho (assimetria de calor corporal).
- Detecção de armas e objetos metálicos ocultos sob roupas através da quebra no gradiente de irradiação térmica superficial.

---

## 3. Ingestão de Drones Táticos, Câmeras Móveis e Bodycams

### 3.1. Protocolos de Transmissão Aérea & Móvel
- **SRT (Secure Reliable Transport) & WebRTC WHIP**: Ingestão de feeds de drones (DJI, Autel, MAVLink) e bodycams policiais em redes 4G/5G instáveis com buffer adaptativo ARQ.
- **Metadados KLV / MISB (STANAG 4609)**: Injeção síncrona de telemetria de voo quadro a quadro (Latitude, Longitude, Altitude HAE, Azimute de Câmera, Pitch, Roll e FOV do solo).

---

## 4. Redes Mesh Táticas & Comunicação Descentralizada (Off-Grid C2)

### 4.1. Comunicação Resiliente Sem Internet (LoRa / Meshtastic / Reticulum)
- Operação em caso de colapso de infraestrutura civil, desastres naturais ou interferência eletrônica de jammers.
- **Compactação de Alertas Biométricos via Protobuf / CBOR**:
  - Alerta completo de match (ID do alvo, Threat Score, Coordenadas GPS, Câmera, Hash SHA-256 e Timestamp) comprimido em pacote de **apenas 78 bytes**.
  - Transmissão por rádio de longo alcance **LoRa (915 MHz / 433 MHz)** em distâncias de até **25 km** ponto-a-ponto sem repetidoras.
