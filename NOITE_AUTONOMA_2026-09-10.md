---
tipo: "relatorio"
projeto: "dashboard-cam"
versao: "1.0.0"
criado: "2026-09-10"
proposito: >
  Log corrido da sessão autônoma (2026-09-10 02:20 até 2026-09-10 13:00,
  pedida pelo usuário antes de dormir): continuar o trabalho de
  reconhecimento facial + inteligência multimodal (FBI Wanted), melhorar
  o que der, deixar tudo funcional e verificável por humanos ao final.
---

# Log da sessão autônoma — 2026-09-10 02:20 → 13:00 (previsto)

> [!NOTE]
> Regra combinada: o usuário vai dormir e autorizou trabalho autônomo até
> as 13h de amanhã, com liberdade total pra melhorar/adicionar coisas que
> sirvam ao objetivo, desde que tudo fique **funcional e verificável por
> humanos** ao final. Pediu explicitamente que eu documente o processo por
> medo de "faltar contexto pra IA" — este arquivo é a resposta a isso,
> seguindo o mesmo padrão que já funcionou na sessão autônoma anterior
> (`NOITE_AUTONOMA_2026-08-30.md`): log corrido, atualizado conforme as
> coisas acontecem, para que qualquer sessão futura (inclusive eu mesmo,
> se o contexto desta conversa for resumido/perdido) consiga retomar sem
> perder o fio.

## Estado no início da sessão

Nesta mesma conversa (contexto ainda disponível), o trabalho até aqui:

**Sistema de reconhecimento facial (watchlist) — já funcional e testado:**
- 5 bugs corrigidos: `register_match_log` faltando, FAISS↔metadata fora de
  sincronia, Haar Cascade→RetinaFace (falso positivo), **embeddings nunca
  normalizados antes do FAISS (bug crítico — sem isso nenhum match jamais
  dispararia)**, `--force-rebuild` não salvava em disco quando `processed=0`.
- `enroll_person.py` pronto (cadastro manual, watchlist pessoal).
- `live_pipeline.py` religado ao catálogo real de câmeras (`db_manager.py`),
  suporta HLS direto e SNAPSHOT_JPEG (polling), modo headless automático
  (ambiente sem GUI — `opencv-python-headless`).
- `monitor_camera.py` (novo) — inicia a pipeline numa câmera real por ID.
- Testado ponta a ponta contra câmera real do Caltrans (California), 40s,
  sem crash.

**Expansão de dados (decisão do usuário: watchlist = FBI Wanted, não
contatos pessoais):**
- Lista completa do FBI ingerida: 1242 indivíduos (era 770).
- Achado: API tem campos ricos descartados (`caution`, `warning_message`
  — ex. "SHOULD BE CONSIDERED ARMED AND DANGEROUS", `remarks`,
  `additional_information`) — `populate_db.py:load_fbi()` corrigido pra
  capturar tudo isso no campo `description`.
- `score_engine.py` (ThreatScorer, já existia) melhorado: detecta a frase
  oficial "ARMED AND DANGEROUS"/"CONSIDERED DANGEROUS" e força piso de
  score 9.0 (mais forte que qualquer keyword genérica de crime).
- Fotos baixadas: ~1176 de 1242 (66 falham por link quebrado/exigem login
  — não é bug, é limitação de acesso do lado do FBI, não tentar contornar).
- Bug achado e corrigido: `download_fbi_photos.py` pedia `Accept:
  image/webp` sem querer, causando download de WebP disfarçado de `.jpg`
  (~150 arquivos corrompidos silenciosamente) — corrigido header +
  validação de magic bytes antes de salvar.

**Triagem de conteúdo com CLIP (pedido do usuário: "entender o que cada
imagem realmente é antes de processar"):**
- `open_clip_torch` instalado (MIT, roda bem em CPU).
- `classify_images.py` (novo): classifica cada foto em 8 categorias
  (rosto único, mugshot, cartaz múltiplas pessoas, esboço, tatuagem,
  documento, borrada, veículo/local sem pessoa).
- Resultado em 1157 imagens: 1032 utilizáveis (869 mugshot + 163 rosto
  claro), 125 não-utilizáveis (38 documento, 28 veículo, 26 esboço, 17
  borrada, 11 tatuagem, 5 cartaz múltiplas pessoas).
- `delta_embedder.py` agora pula direto (sem gastar RetinaFace) qualquer
  imagem que o CLIP já marcou como não-utilizável pra rosto.

**Ferramentas extras pedidas pelo usuário ("mais ferramentas pra ser
funcional e real", ordem aprovada: OCR → CLIP similaridade → Person
ReID):**
1. `ocr_documents.py` (EasyOCR, já usado no projeto) — rodou nos 38
   "documentos". Achado importante: 26 desses NÃO são documentos reais,
   são cópias idênticas (mesmo hash MD5) do selo genérico do FBI ("sem
   foto disponível") — confirmado visualmente. Só ~4-5 têm conteúdo real
   (não são documento de identidade, são foto de cena/local).
2. `clip_similarity_index.py` (novo) — busca por similaridade visual
   (CLIP + FAISS `IndexFlatIP`) pras 39 fotos de tatuagem/veículo. Testado:
   score 1.000 pra imagem idêntica, resultados coerentes por categoria.
3. `person_reid.py` (novo) — Re-ID de pessoa por roupa/corpo via Torchreid
   OSNet. Inicialmente carregou só backbone ImageNet (genérico); usuário
   pediu pesos de ReID de verdade — baixados de
   https://kaiyangzhou.github.io/deep-person-reid/MODEL_ZOO.html
   (`osnet_x1_0_market1501.pth`, rank-1 94.2%/mAP 82.6% oficial). Salvo em
   `olho_de_deus/models/`. Testado: 1.000 mesma imagem, 0.587 imagens
   diferentes (mudou de 0.384→0.587 ao trocar pro checkpoint certo, como
   esperado — o modelo agora entende "pessoa" de verdade).

## Rodando no momento em que a sessão autônoma começou

`extract_embeddings.py --force-rebuild` rodando desde ~01:38 (processo
232379), reprocessando 1176 registros (quase todos os 1242 indivíduos,
porque re-ingerir a lista do FBI atualizou `last_seen` de todo mundo,
disparando a condição de "precisa re-embedar" mesmo em quem já tinha
embedding — desperdício de CPU mas não incorreto, só redundante). Ficou
lento porque rodou concorrente com toda a instalação/teste de
CLIP+Torchreid. Sem `--limit`, deve terminar sozinho.

## Plano pra sessão autônoma (2026-09-10, até 13h)

Ordem de prioridade, ajustável conforme achados:

1. **Deixar terminar** `extract_embeddings.py` em andamento → rodar
   `ThreatScorer.batch_process()` (score_engine.py) → **nunca rodado
   ainda**, vai gerar score de periculosidade pra todos os 1242.
2. **Verificação de ponta a ponta**: confirmar contagens finais batem
   (individuals × img_path × has_embedding real × threat_scores), rodar
   pelo menos 1 teste de match novo pós-rebuild completo.
3. **Integrar as ferramentas novas no sistema, não deixar soltas**:
   - Ligar `person_reid.py` no `biometric_processor.py`/`live_pipeline.py`
     como fallback quando o rosto não é detectado mas uma pessoa é (YOLO
     já detecta classe "person" — hoje esse crop só alimenta o ArcFace
     via `detector_backend=skip`, o que é impreciso pra corpo inteiro,
     ver nota abaixo). Decisão a tomar: separar detecção de ROSTO (pro
     ArcFace) de detecção de PESSOA (pro ReID) — são coisas diferentes e
     hoje o código mistura os dois.
   - Ligar `clip_similarity_index.py` e `ocr_documents.py` num fluxo que
     rode automaticamente após `download_fbi_photos.py`+
     `classify_images.py` (hoje são scripts manuais separados) —
     considerar um `pipeline_ingestao.py` que chama os 5 passos em ordem.
4. **Achado a investigar** (anotado mas não resolvido ainda): em
   `biometric_processor.py`, o YOLO usado pra achar "rosto" na verdade
   detecta `classes=[0]` (pessoa inteira, padrão COCO), e manda esse crop
   inteiro pro ArcFace com `detector_backend=skip` (que não faz
   detecção/alinhamento nenhum). Isso é uma imprecisão de reconhecimento
   facial ao vivo que existe HOJE, independente de tudo que fizemos —
   precisa decidir: (a) trocar por um detector de ROSTO de verdade antes
   do ArcFace (ex: usar o mesmo RetinaFace do delta_embedder.py, ou um
   YOLO-face), ou (b) manter crop de pessoa só pro Person ReID (que é pra
   isso mesmo) e adicionar uma etapa separada de detecção de rosto pro
   ArcFace. Prioridade alta pra investigar — é sobre PRECISÃO do
   reconhecimento ao vivo, não só sobre os dados do FBI.
5. **Deixar tudo verificável por humano** (pedido explícito do usuário):
   - Script único de "health check" que roda e imprime um relatório
     simples: quantos indivíduos, quantos com foto real, quantos com
     embedding real, quantos com threat score, teste de match
     automático com resultado esperado conhecido (self-test).
   - Atualizar este arquivo continuamente conforme o trabalho avança.
   - Não deixar nada "parece que funciona" sem ter rodado de verdade —
     mesma regra que already document em `PLANO_CONTINUACAO.md` do
     projeto: sempre verificar rodando, nunca assumir.

## Achado crítico de precisão — pipeline ao vivo vs. cadastro (2026-09-10, ~02:20-02:45)

Investigando o item 4 do plano anterior (YOLO detectava PESSOA inteira, não
rosto, e mandava direto pro ArcFace sem alinhamento):

1. **Corrigido**: `biometric_processor.py` agora usa **YuNet** (detector de
   rosto real, ONNX ~230KB, leve o suficiente pra rodar por frame em CPU)
   como segundo estágio depois do YOLO achar a pessoa — testado, 29/30
   (96.7%) de detecção correta em mugshots reais.
2. **Corrigido também**: o YuNet devolve 5 pontos faciais (olhos, nariz,
   boca) que eu não estava usando — adicionei alinhamento de verdade
   (transformação de similaridade contra o template padrão ArcFace 112x112,
   mesma convenção do insightface) em vez de só recortar o retângulo cru.
   Verificado visualmente — rosto sai centralizado, olhos nivelados.
3. **Achado importante (limitação real, não totalmente resolvida)**: testei
   auto-match (a própria foto cadastrada, redetectada via YuNet+alinhamento,
   contra o embedding já indexado da mesma pessoa) em 138 indivíduos reais.
   Resultado: **distância varia de 0.008 a 0.666**, com mediana 0.36 e p95
   em 0.54 — uma faixa larga, mesmo alinhando certo. Em 150 tentativas, 3
   deram "match errado" (pessoa A reconhecida como pessoa B):
   - 2 dos 3 são **duplicata de dados do próprio FBI**, não erro do
     algoritmo — confirmei visualmente/pela URL que a "entidade" (ex: "GRU
     29155 CYBER ACTORS", um grupo) e o "indivíduo" (ex: "Vladislav
     Borovkov", membro nomeado do mesmo caso) usam a MESMA foto de origem.
     O sistema reconheceu certo; é a base de dados do FBI que tem duas
     fichas (grupo + pessoa) pra a mesma imagem.
   - 1 dos 3 (Eulalia "Lolly" Chavez ↔ caso de vandalismo) é um falso
     positivo genuíno — duas pessoas fisicamente diferentes, fotos de baixa
     qualidade (escura/borrada), distância 0.033-0.049 (bem abaixo de
     qualquer threshold razoável). Tentei achar um filtro de nitidez pra
     pegar esses casos automaticamente — não funcionou (medi nitidez do
     recorte de rosto nos dois casos e no caso correto, não teve separação
     clara). **Conclusão honesta: isso é uma limitação conhecida de
     reconhecimento facial em imagem degradada — não existe fix perfeito
     com as ferramentas disponíveis.**
4. **Recalibrei o threshold com base nesses números reais**: estava em
   0.48 (chute antigo), o que rejeitaria boa parte dos matches
   genuinamente corretos (mediana real é 0.36, p90 é 0.52). Subi pra
   **0.6** em `live_pipeline.py` e `monitor_camera.py` (comentário no
   código explica a conta). Isso reduz falso-negativo (deixar de reconhecer
   quem devia) às custas de manter o risco pequeno mas real de falso-
   positivo em fotos degradadas — **decisão consciente, documentada, não
   escondida**.

**Recomendação pro usuário, importante**: dado o achado do item 3, o
sistema NÃO deve ser usado pra ação automática/irreversível sem revisão
humana — mesmo com tudo calibrado direito, ~1-2% de chance de confundir
duas pessoas existe quando a imagem é de baixa qualidade. Isso é normal
pra qualquer sistema de reconhecimento facial real (nenhum é 100%), mas
precisa estar claro pra quem for usar.

## Decisão sobre "pesquisar como proceder" (contexto pra IA)

O usuário pediu pra eu pesquisar como evitar perder contexto numa sessão
autônoma longa. Decisão: em vez de pesquisa genérica na web sobre "boas
práticas de agente autônomo" (que tende a ser abstrato/pouco acionável),
apliquei o padrão que **já existe e já funcionou neste mesmo projeto**:
este arquivo de log corrido, no mesmo formato do
`NOITE_AUTONOMA_2026-08-30.md` anterior — que na prática permitiu a uma
sessão futura (esta mesma conversa, semanas depois) retomar o trabalho
sem perder nada. Complemento com: (1) task list (`TaskCreate`/`TaskUpdate`)
sempre atualizada, (2) commits git incrementais com mensagens claras
(histórico = memória externa), (3) qualquer decisão não-óbvia registrada
aqui com o "porquê", não só o "o quê".
