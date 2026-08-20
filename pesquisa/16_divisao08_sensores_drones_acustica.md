# DIVISÃO 08: SENSORES TÁTICOS, CÂMERAS ESPECIALIZADAS & DRONES

## 1. Controle Autônomo PTZ com Visual Servoing PID e Master-Slave Handover
- **Câmera Master (Panorâmica)**: Projeção de vetor 3D $\mathbf{r} = \mathbf{K}_m^{-1}[u_m, v_m, 1]^T$ para câmera Slave (Domo PTZ).
- **Controle IBVS**: Image Jacobian $\mathbf{L}_s$ com atenuação $1/\text{Zoom}(t)$ e comandos ONVIF Profile S/T (`ContinuousMove` e `AbsoluteMove`) com predição via Filtro de Kalman.

---

## 2. Câmeras Térmicas LWIR (8-14 µm) & Fusão Multi-Espectral
- **Microbolômetros VOx**: NETD $< 40\text{mK}$ com fusão neural em tempo real (TarDAL, SuperFusion) combinando gradientes de alta resolução RGB com saliência térmica sob fumaça e escuridão total.

---

## 3. Ingestão de Drones Táticos (STANAG 4609 & MISB ST 0601)
- **Padrão OTAN**: Vídeo H.264/H.265 multiplexado com KLV Metadata (Lat/Lon/Alt, Azimute, Pitch/Roll, Slant Range) em MPEG-TS com conversão para Cursor-on-Target (CoT / ATAK).

---

## 4. Bodycams Policiais Conectadas sobre 4G/5G com Jitter Severo
- **Protocolos Resilientes**: **SRT (Secure Reliable Transport)** com ARQ adaptativo ($T_{buffer} \ge 3 \times \text{RTT}$) e cifra AES-256, e **WebRTC WHIP** com codificação H.265 Intra-Refresh e Edge Store-and-Forward.

---

## 5. Detecção Acústica de Tiros via TDoA (ShotSpotter Open-Source)
- **Triangulação TDoA 3D**: Discriminação entre onda de choque supersônica (Cone de Mach) e onda de boca (Muzzle Blast) com estimativa de atrasos $\tau_{ij}$ via **GCC-PHAT** e otimização Levenberg-Marquardt com GPS PPS.

---

## 6. Classificação de Eventos Sonoros Urbanos (SED)
- **Modelos**: YAMNet ($< 5\text{ms}$) na borda e **Audio Spectrogram Transformer (AST)** para reconhecimento de tiros, gritos, quebra de vidros, explosões e sirenes.

---

## 7. Radares de Vigilância Terrestre (GSR) FMCW
- **Assinaturas Micro-Doppler**: Diferenciação entre pedestres, veículos e drones via 2D-FFT e CA-CFAR, com comando **Slew-to-Cue** automatizado para câmeras PTZ óptico-térmicas.

---

## 8. Câmeras LiDAR 3D para Intrusão Perimétrica
- **Sensores 128 feixes (Ouster/Hesai)**: Segmentação de solo Patchwork++ e detecção volumétrica 3D **PointPillars** acoplada a odometria forense **FAST-LIO2 (iEKF)**.

---

## 9. Câmeras Hiperespectrais (SWIR 1000-2500 nm)
- **Identificação Química**: Bandas vibracionais C-H e N-H (cocaína/crack em 1680 e 2180 nm, canabinoides em 1410 e 1930 nm) via **Spectral Angle Mapper (SAM)** e **Adaptive Coherence Estimator (ACE)**.

---

## 10. Câmeras Neuromórficas (Event-based Sensors - DVS)
- **Pixels Assíncronos**: Resolução temporal de microssegundos ($> 10.000\text{ FPS}$ equivalente) e faixa dinâmica $> 120\text{dB}$ para rastrear projéteis e drones sem motion blur via Spiking Neural Networks (SNNs).
