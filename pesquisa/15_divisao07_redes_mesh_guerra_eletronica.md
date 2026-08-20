# DIVISÃO 07: REDES MESH OFF-GRID, COMUNICAÇÕES & GUERRA ELETRÔNICA (C4ISR)

## 1. Protocolo Biométrico-Tático Sub-100 Bytes (Wire-Format 34 Bytes)
- **Compactação Extrema**: Latitude/Longitude em 32-bit fixed-point (precisão < 1cm), Altitude, Azimute, Velocidade, Biometria (FC, SpO2, Temp), Postura, SOS/Jamming Flags, SeqNum e Auth Tag ChaCha20-Poly1305.
- **Performance RF**: Time-on-Air de apenas **184ms** em LoRa SF10/125kHz com 99.8% de silêncio de rádio (LPI/LPD).

---

## 2. Topologia Mesh B.A.T.M.A.N. Advanced para Comboios
- **Layer 2 Kernel Space**: Enlaces Ad-Hoc 802.11ac 5.8 GHz sem latência de roaming e seleção transparente de Gateway WAN móvel (Starlink).

---

## 3. Protocolo Yggdrasil Network P2P Criptografado IPv6
- **Tree Metric Routing**: Endereçamento determinístico IPv6 derivado do hash SHA-512 da chave pública Ed25519 de cada nó sem servidor DHCP/DNS central.

---

## 4. Resiliência Anti-Jamming com CUSUM & FHSS
- **Detecção CUSUM**: Monitoramento contínuo da elevação de ruído térmico ($\Delta RSSI - \Delta SNR$) e salto pseudo-aleatório de frequência ChaCha20 com canal de contingência.

---

## 5. SDR & Interceptação Tática SIGINT
- **Hardware Compatível**: RTL-SDR v4, HackRF One, USRP B205mini integrados via GNU Radio 3.10 com publicação em tempo real via ZeroMQ.

---

## 6. Arquitetura Multi-Bearer Failover Dinâmico
- **Matriz de Prioridade**: Tier 1 (5G Privado) $\to$ Tier 2 (B.A.T.M.A.N. 5.8GHz) $\to$ Tier 3 (LoRa 915MHz) $\to$ Tier 4 (VHF AX.25 Packet Radio de sobrevivência).

---

## 7. Link Budget em Selva Densa e Cânions Urbanos
- **Física de Propagação**: LoRa 915 MHz sustenta **+25.34 dB** de margem de desvanecimento através de 300m de selva densa a 3.5 km.

---

## 8. Sincronização de Relógio Sem GPS (Microsecond PPS)
- **Holdover com Filtro de Kalman**: Osciladores OCXO ($\pm 1.0\text{ ppb}$, deriva $< 86.4\mu\text{s}$ em 24h) com calibração contínua por balizas LoRa/PTP IEEE 1588v2 sob GPS spoofing.

---

## 9. Gateway Portátil de Campo (ESP32 / LoRa SX1262)
- **Firmware C++ FreeRTOS / RadioLib**: Ponte transparente BLE 5.0 para smartphones executando ATAK-CIV (Cursor-on-Target).

---

## 10. Protocolo de Inundação Controlada (Managed Flood)
- **Deduplicação $O(1)$ por Filtro de Bloom**: Decremento de Hop-to-Live (HTL) e backoff inteligente (*Polite Snooping*) contra tempestades de broadcast.
