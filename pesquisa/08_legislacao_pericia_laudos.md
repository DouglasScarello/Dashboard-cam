# Módulo 08: Legislação Penal, Cadeia de Custódia Legal e Laudos Periciais de IA

## 1. Lei Geral de Proteção de Dados (LGPD - Lei 13.709/18)

### 1.1. Exceção Expressa de Segurança Pública (Art. 4º, III)
- O tratamento de dados pessoais para fins exclusivos de segurança pública, defesa nacional e investigação penal está **isento** do regime ordinário da LGPD (dispensa consentimento prévio do titular).
- **Salvaguarda do § 2º**: É terminantemente vedado o tratamento desses dados por entidades privadas, salvo sob estrita tutela, custódia e controle de órgão público de segurança.

### 1.2. Requisitos de Conformidade no Olho de Deus
- **Segregação Lógica e Física**: Isolamento de bases de dados criminais em relação a dados civis.
- **Audit Trail Compulsório (Accountability)**: Todo acesso, consulta ou alerta biométrico registra matricula do policial/operador, número do procedimento investigativo (Inquérito Policial / Ordem Judicial) e hash de integridade temporal.

---

## 2. Pacote Anticrime (Lei 13.964/19) & Cadeia de Custódia Digital (CPP Arts. 158-A a 158-F)

### 2.1. As 10 Etapas da Cadeia de Custódia Digital
1. **Reconhecimento**: Detecção do evento tático (match facial, placa ou arma).
2. **Isolamento**: Congelamento imediato do buffer de vídeo (*Ring Buffer Freeze*) e gravação do fluxo bruto RAW em partição WORM (*Write Once Read Many*).
3. **Fixação**: Registro de metadados (GPS, Sensor ID, iluminação, frame rate, timestamp UTC em microssegundos).
4. **Coleta**: Extração do fluxo em bit-stream original sem recompressão.
5. **Acondicionamento**: Empacotamento em contêiner forense com cálculo simultâneo de **Duplo Hash: SHA-256 + SHA3-512**.
6. **Transporte**: Túnel seguro TLS 1.3 com autenticação mútua (mTLS) e certificados digitais ICP-Brasil.
7. **Recebimento**: Lavratura automática de termo digital de recebimento pericial com conferência do hash.
8. **Processamento**: Execução da inferência de IA em ambiente determinístico (semente fixa).
9. **Armazenamento**: Guarda segura em Object Storage cifrado com AES-256-GCM sob retenção imutável.
10. **Descarte**: Destruição criptográfica certificada (NIST SP 800-88) apenas após trânsito em julgado judicial.

---

## 3. Jurisprudência Vinculante do STJ e Resolução CNJ 484/2022

### 3.1. STJ - Habeas Corpus 598.886/SC
- O procedimento do art. 226 do CPP é **formalidade essencial e obrigatória**.
- O reconhecimento fotográfico/facial por IA **NÃO** pode servir como prova exclusiva para decretação de prisão ou condenação; atua exclusivamente como **indício preliminar (*notitia criminis*)** que exige diligências probatórias confirmatórias.

### 3.2. Resolução CNJ 484/2022 (Proibição de Show-Up & Lineup Justo)
- **Vedação de Show-Up**: É proibido apresentar uma única foto isolada do suspeito à vítima/testemunha.
- **Lineup Automatizado**: O Olho de Deus gera automaticamente uma grade 1:N com **1 foto do suspeito + 4 distratores com características físicas e morfológicas semelhantes** selecionados por proximidade vetorial secundária no banco de dados.
- **XAI (Inteligência Artificial Explicável)**: Inclusão no laudo pericial de mapas de calor **Grad-CAM**, provando a ausência de viés algorítmico e demonstrando os marcos faciais anatômicos que embasaram a similaridade.
- **Formato Final**: Laudo pericial estruturado em **PDF/A-1b** com assinatura digital PAdES (ICP-Brasil / X.509).
