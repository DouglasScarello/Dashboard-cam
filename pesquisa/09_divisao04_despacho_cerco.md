# DIVISÃO 04: MOTORES DE DESPACHO TÁTICO, PERSEGUIÇÃO & CERCO VIÁRIO (C4ISR)

## 1. Algoritmos de Despacho Ótimo DEVRP-TW-TM e Jonker-Volgenant (LAPJV)
- **Formulação DEVRP-TW-TM:** Modela frotas heterogêneas sob janelas de tempo $[e_i, l_i]$, severidade de ocorrência $\omega_i$, demandas de unidades especializadas $\mathbf{d}_i$, matriz de custo dependente do tempo $T_{ij}(t)$ com penalidades por quebra de SLA e risco balístico $\mathcal{R}_{ij}$.
- **LAPJV (Linear Assignment Problem Jonker-Volgenant):** Para despacho em tempo real ($< 2\text{ ms}$ para matrizes $500 \times 50$), superando o método Húngaro via fases de aumento dual e caminhos aumentantes mais curtos (Dijkstra esparso).
- **Janela Deslizante (Rolling Horizon):** Re-otimização orientada a eventos (ex.: novos alertas LPR de veículos roubados ou chamada 10-33) combinada com meta-heurística ALNS (*Adaptive Large Neighborhood Search*).

---

## 2. Isócronas de Fuga Dinâmicas com Ingestão de Tráfego em Tempo Real (Valhalla CCH / OpenLR)
- **Valhalla Customizable Contraction Hierarchies (CCH):** Separação estrita entre a contração métrico-independente do grafo viário e a customização dinâmica de pesos ($< 100\text{ ms}$ para a malha metropolitana inteira).
- **Ingestão OpenLR:** Decodificação de referências de localização linear para aplicar reduções ou aumentos de velocidade em arestas específicas com base em feeds de tráfego (TomTom/Waze/radares).
- **Fator de Fuga Agressiva:** Arestas sofrem multiplicação pelo fator de transgressão $\alpha_{\text{fuga}} = 1.35$ e tolerância de acostamento $\lambda = 1.20$, gerando polígonos GeoJSON (*Alpha-Shape Concave Hull*) para os horizontes $T \in \{2, 5, 10, 15\}\text{ min}$.

---

## 3. Identificação de Pontos de Estrangulamento (Min-Cut / Vertex Cut) e Cerco Urbano
- **Teoria de Grafos e Corte Mínimo:** Formulação do problema como um *Minimum Vertex Cut* entre a origem do fugitivo $S$ e o conjunto de sumidouros de fronteira externa $T_{\text{target}}$ no subgrafo induzido pela isócrona.
- **Otimização de Capacidade e Gargalos:** Gargalos naturais (pontes, saídas de túneis, viadutos e pistas únicas) recebem menor custo de bloqueio $c(v)$ por demandarem menos viaturas.
- **Resolução em Milissegundos:** Algoritmo de Dinic / Boykov-Kolmogorov com restrição de tempo de chegada da viatura com margem de segurança $\tau_{\text{segurança}} \ge 45\text{ s}$ antes do fugitivo.

---

## 4. Simulação de Dinâmica de Perseguição e Evasão (Pursuit-Evasion Game Theory)
- **Jogos Diferenciais:** Modela a cinemática de viaturas e evasor como veículos de Dubins multi-agente, solucionando a equação PDE de Hamilton-Jacobi-Isaacs (HJI) para delimitar as bacias de captura.
- **Particionamento Dinâmico de Voronoi em Grafo:** Em vez de perseguição linear traseira (*tail-chase*), as viaturas policiais convergem para os vértices de fronteira e centroide da célula de Voronoi do fugitivo $\mathcal{V}_E(t)$, forçando seu encolhimento monotônico $|\mathcal{V}_E(t)| \to 0$ com fechamento de rotas de escape.

---

## 5. Planejamento de Rotas Seguras de Abordagem Tática (Polícia e Resgate Médico)
- **Superfície de Custo Multi-Critério:** $C(e) = w_1 T(e) + w_2 \mathcal{R}_{\text{balístico}}(e) + w_3 \mathcal{A}_{\text{acústico}}(e) + w_4 \mathcal{M}_{\text{manobra}}(e) + w_5 \mathcal{E}_{\text{elevação}}(e)$.
- **Modo Furtivo (*Silent Approach*):** Desativação automática de sirene e giroflex a $600\text{ m}$ do alvo, elegendo trajetórias com obstrução de visada (*line-of-sight*) contra posições hostis dominantes.
- **Corredor Médico SAMU:** Roteamento com minimização de aceleração transversal e vibração ($G$-forces) para pacientes com trauma e triagem automatizada com capacidade cirúrgica hospitalar em tempo real.

---

## 6. Alocação de Recursos Especializados em Crise (K9, Blindados, Drones, GATE/BOPE)
- **Matriz de Capacidade & Restrições Físicas:** Modelagem de tempo de prontidão ($t_{\text{prep}}$), blindagem balística (NIJ IIIA a IV / STANAG 4569), decaimento de rastro olfativo K9 ($\Delta t \le 4\text{ h}$), autonomia de bateria de drones ($35 - 45\text{ min}$) e protocolos de não-divisibilidade de equipes de intervenção especial.
- **Formulação GAP / MMKP:** Resolução de alocação minimizando tempo de resposta e maximizando adequação ao nível de ameaça $\text{ThreatLevel}(i)$.

---

## 7. Geofencing Dinâmico e Alertas em Cruzamentos Semafóricos
- **Indexação Hierárquica Uber H3:** Células H3 de resolução 8 (macro-despacho regional) a resolução 10 ($\sim 65\text{ m}$, controle de cruzamento) operando a $1000\text{ Hz}$.
- **Protocolo NTCIP 1202 & SPaT:** Comandos automatizados de **Onda Verde (Green Wave EVP)** para viaturas a menos de $350\text{ m}$ e **Bloqueio Vermelho (Red Lock All-Red Hold)** nos eixos de fuga prováveis do suspeito.

---

## 8. Integração de Despacho com Terminal Móvel Tático (MDT)
- **Arquitetura Resiliente:** App local em tablets/smartphones com cache offline (SQLite/SpatiaLite), MapLibre GL Native e transporte híbrido:
  1. Canal Primário: 4G/5G Privado via gRPC / TLS 1.3.
  2. Canal Secundário: MQTT com QoS 1/2.
  3. Canal Terciário (Guerra Eletrônica / Sem Sinal): LoRa Tactical Mesh / SDR.
- **Máquina de Estados:** Estados 10-8, 10-6, 10-97 (geofence automático), 10-98 e 10-33 (*Oficial Sob Fogo* com gatilho de preempção total do DEVRP).

---

## 9. Predição de Destino de Fugitivos via HMM e Grafos de Atratividade
- **HMM Map Matching:** Estados ocultos como segmentos de via $e_k$, emissões Gaussianas de leituras LPR e transições ponderadas por topologia e plausibilidade cinemática.
- **Modelo Gravitacional de Atratividade:** $\mathcal{P}(D_k) \propto W_k \cdot \text{Afinidade}(k, \text{Fugitivo}) \cdot \exp(-\lambda \cdot T_{\text{mín}})$, ponderando residências de comparsas, desmanches, acessos a rodovias e pontos de apoio logístico da facção.

---

## 10. Protocolo Cursor-on-Target (CoT) e Integração ATAK / WinTAK
- **Esquema CoT MIL-STD-2525D:** Tipificação formal (`a-f-G-U-C-I` para viaturas policiais, `a-u-G-U-C-F` para fugitivos, `b-m-p-s-p-loc` para pontos de bloqueio).
- **FreeTAKServer / TAK Server Gateway:** Conector bidirecional TCP/TLS (portas 8087/8089) que injeta telemetria, feeds de radar e rotas prescritas diretamente na tela situacional das equipes operacionais.
