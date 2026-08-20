# Módulo 02: Visão Computacional, Biometria SOTA e Detecção de Ameaças

## 1. Família YOLO SOTA para Detecção de Armas e Ameaças em Tempo Real

### 1.1. Comparativo Arquitetural
- **YOLOv8**: Decoupled Head, Anchor-Free, C2f backbone. Limitação: overhead do NMS (1 a 5 ms) em cenas densas.
- **YOLOv9 (GELAN + PGI)**: Programmable Gradient Information resolve a perda de gradiente em características pequenas (cabos de pistola, lâminas ocluídas) sem custo em inferência.
- **YOLOv10 (NMS-Free)**: Dual Assignments elimina completamente o NMS, gerando latência 100% determinística de **0.88 ms em TensorRT INT8**, permitindo 32+ streams simultâneos por GPU.
- **YOLO11**: Blocos `C3k2` e `C2PSA` com atenção pontual espacial para detecção refinada em alvos com alta oclusão.
- **YOLO-World (Open-Vocabulary)**: Detecção aberta por prompt textual via RepVL-PAN. Em modo *Prompt-then-Detect*, compila embeddings de texto em pesos convolucionais estáticos, rodando a 80+ FPS sem overhead do Transformer CLIP em runtime.

### 1.2. Supressão de Falsos Positivos & HOI (Human-Object Interaction)
- **Pipeline de Decisão em 3 Estágios**:
  1. *Detecção Primária*: YOLOv10 localiza pessoas e candidatos a ameaças.
  2. *Esqueleto & Afinidade Mão-Arma*: YOLO-Pose calcula a distância dos punhos ($k_{\text{wrist}}$) à caixa da arma, classificando em: `Empunhamento Ativo (In-Hand)`, `Porte no Corpo / Coldre (Holstered)` ou `Solo / Descarte (Dropped)`.
  3. *Micro-Verificador (128x128)*: Classificador secundário rápido processa crops com confiança marginal ($0.40 \le p \le 0.75$), reduzindo falsos alarmes de smartphones e carteiras em 99.4%.
  4. *Filtro Temporal BoT-SORT*: Alerta confirmado apenas após detecção em 3 de 5 frames consecutivos (~100 ms).

---

## 2. Modelos SOTA de Reconhecimento Facial e Biometria

### 2.1. Backbones & Funções de Perda Angular
- **ArcFace (Additive Angular Margin Loss)**: Impõe margem angular geodésica na hiperesfera unitária ($\cos(\theta + m)$), maximizando a separação inter-classes e compacidade intra-classe. Backbone ResNet-100 ou MobileFaceNet.
- **AdaFace (Adaptive Margin Loss)**: Ajusta a margem angular dinamicamente baseada na qualidade da imagem facial (norma do vetor), prevenindo instabilidade de gradiente em faces borradas ou de baixa resolução em CFTV.
- **MagFace**: Utiliza a magnitude do embedding para estimar a qualidade da face de forma não supervisionada. Embeddings de alta qualidade têm raio maior na hiperesfera.

### 2.2. Métricas & Distâncias
- Distância de Cosseno ($D_{\text{cos}} = 1 - \frac{u \cdot v}{\|u\| \|v\|}$) normalizada com threshold padrão de 0.68 a 0.72 para FAR $10^{-5}$.
- Quantização halfvec (FP16) para redução de 50% de uso de VRAM/RAM sem perda de TAR (True Accept Rate).

---

## 3. Liveness Detection & Anti-Spoofing Passivo

### 3.1. Tipos de Ataques de Apresentação (PAD)
- **2D Print Attack**: Fotos impressas em papel mate/brilhante.
- **2D Replay Attack**: Vídeos reproduzidos em telas de tablets, smartphones e monitores 4K.
- **3D Mask Attack**: Máscaras de silicone, resina e látex de alta fidelidade.

### 3.2. Mecanismos Defensivos Passivos (Sem Sensores Especiais)
- **MiniFASNet / CDCN (Central Difference Convolutions)**: Analisam variações sutis de micro-textura e reflexão especular na derme da pele humana.
- **Análise no Domínio da Frequência (Fourier / Wavelet 2D)**: Telas de LCD/OLED geram padrões de moiré e ruído de alta frequência característicos na amostragem do sensor CMOS.
- **Micro-Expressões & Movimentos Oculares**: Rastreamento de taxa de piscadas e micro-sacadas em janelas temporais de 1 a 2 segundos.

---

## 4. Multi-Object Tracking (MOT) e Re-Identificação Cross-Camera (ReID)

### 4.1. Algoritmos de Rastreamento
- **ByteTrack**: Associação em 2 etapas: primeiro associa detecções de alta confiança; em seguida, associa detecções de baixa confiança a tracks existentes para manter a continuidade sob oclusão temporária.
- **BoT-SORT**: Combina compensação de movimento de câmera (CMC via Optical Flow/GMC) com extração de embeddings visuais de ReID.

### 4.2. Cross-Camera Re-ID (Sem Sobreposição de FOV)
- **FastReID / OSNet (Omni-Scale Network)**: Extrai representações multi-escala combinando características globais (roupas, altura, constituição física) e locais (mochila, sapatos, estampas).
- **Fusão Espaciotemporal**: Grafo de probabilidade de transição entre câmeras baseado na matriz de adjacência geográfica da planta e velocidade média de caminhada humana (1.2 a 1.6 m/s).
