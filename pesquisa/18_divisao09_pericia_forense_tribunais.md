# DIVISÃO 09: PERÍCIA FORENSE, CADEIA DE CUSTÓDIA, LGPD & TRIBUNAIS

## 1. Cadeia de Custódia Digital Estrita (CPP Arts. 158-A a 158-F)
- **10 Etapas Taxativas**: Reconhecimento, Isolamento, Fixação, Coleta, Acondicionamento, Transporte, Recebimento, Processamento, Armazenamento e Descarte.
- **Multihash Redundante**: Cálculo simultâneo de SHA-256, SHA-512, SHA-3-256 e BLAKE2b com Merkle Tree para lotes de frames e manifesto JSON append-only com HMAC.

---

## 2. Lineup Duplo-Cego com 4 Distratores Morfológicos (Resolução CNJ nº 484/2022 & STJ HC 598.886/SC)
- **Protocolo Cego**: Apresentação sequencial/simultânea de 4 distratores com características morfológicas análogas (idade, tom de pele, corte de cabelo, barba) selecionados automaticamente por similaridade vetorial, eliminando vícios e indução de testemunhas.
- **Registro Gravado Obrigatório**: Auto de descrição prévia e gravação audiovisual integral sob pena de nulidade absoluta da prova.

---

## 3. Razão de Verossimilhança Bayesiana (SLR) segundo FISWG e ENFSI
- **Superação do "Percentual de Certeza"**: Cálculo da Razão de Verossimilhança $LR = \frac{f(s \mid H_p)}{f(s \mid H_d)}$ sob hipóteses concorrentes ($H_p$: mesma origem, $H_d$: origens distintas).
- **Calibração de Escore & Incerteza**: Calibração por Regressão Logística (Platt Scaling) e PAV com métrica $C_{llr} < 0.01$ e Intervalo Crível Bootstrap 95% adotando o limite inferior conservador (*in dubio pro reo*).

---

## 4. Assinatura Digital Forense PAdES-LTA ICP-Brasil (RFC 3161)
- **Padrão PAdES Long-Term Archival**: Assinatura em PDF/A-1b com chave RSA-4096 / Ed25519 e carimbo de tempo ICP-Brasil emitido por Autoridade Certificadora do Tempo credenciada no ITI.

---

## 5. Inteligência Artificial Explicável (XAI) Forense & Landmarks Saliency
- **Mapas de Calor Grad-CAM**: Visualização das regiões de maior ativação da rede neural convolucional/ViT (região ocular, dorso nasal, comissuras labiais) comprovando que o modelo não tomou decisão baseado em ruídos de fundo.

---

## 6. LGPD Penal (Art. 4º, III da Lei 13.709/18) & Relatório de Impacto (RIPD)
- **Exceção Legal de Segurança Pública**: Tratamento legítimo ancorado na persecução penal, com princípios de estrita necessidade, proporcionalidade, minimização de dados e expurgo automatizado vinculado à prescrição da pretensão punitiva penal.

---

## 7. Padrões Internacionais ISO/IEC 27037 & ISO/IEC 19794-5
- **Garantia de Qualidade de Amostra**: Validação de resolução mínima interocular (> 60px), ângulos de pose ($|\text{yaw}| < 30^\circ$, $|\text{pitch}| < 20^\circ$) e iluminação controlada para aceitabilidade pericial.

---

## 8. Estrutura Canônica de Laudos dos Institutos de Criminalística
- Preâmbulo oficial, histórico e requisição, exame antropométrico minucioso, confronto bayesiano, resposta categórica aos quesitos da autoridade e encerramento assinado digitalmente.
