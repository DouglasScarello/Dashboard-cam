# DIVISÃO 01: VISÃO COMPUTACIONAL DE PRÓXIMA GERAÇÃO & FUNDAÇÕES BIOMÉTRICAS

## 1. Detectores NMS-Free para Vigilância (YOLOv12, RT-DETR v2, Co-DETR)
- **YOLOv12-S INT8**: **0.92 ms (1087 FPS)** em RTX 4090 e **8.40 ms (119 FPS)** em Jetson Orin Nano (8GB) sem overhead de NMS graças ao mecanismo *Area Attention* ($A^2$) e atribuição bipartida *one-to-one*.
- **RT-DETR v2**: Desacoplamento intra-escala (AIFI) e fusão multi-escala (CCFM) com 1.40ms em GPU.

---

## 2. Biometria Facial Não-Cooperativa & Pose Extrema ($\pm 85^\circ$)
- **AdaFace Adaptive Margin**: Ajuste de margem angular via norma $\|z_i\|$ como proxy de qualidade facial, evitando colapso gradiente em poses severas.
- **Probabilistic Face Embeddings (PFE)**: Modelagem gaussiana $\mathcal{N}(\mu, \Sigma)$ para estimativa de incerteza biométrica. Atinge **94.8%** no benchmark CFP-FP contra 88.5% do ArcFace.

---

## 3. Re-Identificação Corporal Cross-Camera & Troca de Roupas (CC-ReID)
- **SOLIDER + CAL (Cloth-Agnostic Learning)**: Decomposição ortogonal do vetor de representação em morfologia anatômica óssea $z_{id}$ e vestimenta $z_{cloth}$ com perda adversarial. Atinge **52.4% Rank-1** no LTCC (dobro do ReID tradicional).

---

## 4. Reconhecimento de Marcha Humana em Longa Distância (>50m)
- **GaitGL / OpenGait / SMPL 3D Mesh**: Combinação de convoluções 3D espaço-temporais com cinemática óssea $(\beta, \theta)$, tornando o reconhecimento invariante a roupas largas, calçados e mochilas (67.1% Rank-1 no Gait3D).

---

## 5. Anti-Spoofing 3D & Liveness Subdérmico (rPPG)
- **MiniFASNetV2 + rPPG (Algoritmo POS)**: Rastreamento microvascular de pulso sanguíneo arterial facial ($0.75\text{ a }3.0\text{ Hz} \iff 45\text{ a }180\text{ BPM}$) com taxa de erro ACER de apenas **1.4%**, rejeitando fotos impressas e telas 4K.

---

## 6. Super-Resolução Forense Não-Alucinatória
- **CodeFormer + Restormer Pericial**: Codebook discreto VQ-VAE com restrição de desvio de embedding biométrico ($\Delta\text{Cos} \le 0.05$) com ArcFace congelado, impedindo a invenção de traços inexistentes.

---

## 7. Reconhecimento Facial Cross-Spectral Visível para Térmico (V2T)
- **Desacoplamento Espaço Latente**: Separação em vetor anatômico espectro-invariante e assinatura espectral de domínio, atingindo **86.4% Rank-1** no benchmark ARL-VTF (térmico para visível).

---

## 8. Interação Humano-Objeto (HOI) & Armas Ocultas
- **QPIC + Spatio-Temporal Pose-GCN**: Rastreamento de movimentos anômalos em direção à cintura (*security check / drawing kinematics*) $0.4\text{s}$ antes do saque da arma de fogo.

---

## 9. ALPR Mercosul & VMMR em Alta Velocidade (>160 km/h)
- **Pipeline**: YOLOv12-Poly 4 cantos $\to$ Retificação homográfica STN $\to$ OCR SVTR com Regex Mercosul direcionado $\to$ Classificação VMMR (marca, modelo, cor, geração) em **1.8 ms**.

---

## 10. Alinhamento Fotoantropométrico 3D para Laudos Forenses
- **3DMM / FLAME**: Alinhamento Procrustes 3D e extração de índices craniométricos ($I_{FM}, I_N$) integrados à Razão de Verossimilhança Bayesiana (SLR) segundo as normas ENFSI/FISWG.
