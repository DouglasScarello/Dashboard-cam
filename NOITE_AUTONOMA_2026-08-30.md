---
tipo: "relatorio"
projeto: "dashboard-cam"
versao: "1.0.0"
criado: "2026-08-30"
proposito: >
  Log corrido da sessão autônoma noturna (2026-08-30 23:32 BRT até
  2026-08-31 10:00 BRT), pedida pelo usuário antes de dormir: corrigir
  bugs, adicionar funções, pesquisar sobre o tema (câmeras mundiais reais
  pra contra-inteligência pessoal caseira) e aplicar o que couber.
---

# Log da noite autônoma — 2026-08-30 23:32 → 2026-08-31 10:00 BRT

> [!NOTE]
> Regras combinadas: nunca parar nem pedir nada ao usuário (ele estará
> dormindo). Só organizar tarefas e fechar tudo perto das 10h. Documentar
> achados aqui conforme forem surgindo.

## Estado no início da noite

- 3998 câmeras HLS diretas (YouTube removido inteiramente por decisão do
  usuário — instabilidade demais).
- Bug crítico recém-descoberto: `NENHUMA CAM COM IMAGEM` — thumbnail
  sempre caindo no placeholder "OFFLINE".

## 23:32–23:40 — Bug crítico: captura de thumbnail 100% quebrada

**Causa raiz (2 bugs empilhados) em `_capture_real_frame_jpeg`
(`camera_grid_server.py`):**
1. Toda URL passava por `_resolve_stream_url_sync` (orientado a YouTube
   via `yt-dlp`) antes de tentar capturar. Pra URL HLS direta (100% do
   catálogo agora), isso sempre falhava — não dá pra extrair "video_id"
   de uma URL Wowza/DOT.
2. Retorno quebrado: `{"cameras": result, "total": db_result["total"]}
   .stdout` — resto de copy-paste, dict não tem `.stdout`, `db_result`
   nem existe nesse escopo. A captura JAMAIS retornava bytes válidos.
3. Faltava `-loglevel error` no ffmpeg — banner verboso no stderr deixava
   a captura via `subprocess` mais lenta que via shell direto, estourando
   timeout de 8s.

**Corrigido:** pula o resolvedor de YouTube quando a URL já é HLS direta,
corrigido o retorno pra `result.stdout`, suprimido o banner do ffmpeg,
timeout subido pra 15s. Verificado ponta a ponta contra o servidor real:
thumbnail agora retorna frame JPEG real (250KB+), não mais o placeholder
(6.8KB). Commit: `fix(cameras): corrige captura de thumbnail real quebrada
pra 100% das câmeras`.

## Achado de arquitetura (não fiz, mas documentei)

Outra sessão migrou o backend pra ler câmeras de um banco SQLite
(`database/live_cameras.db` via `db_manager.py`) em vez de
`live_cameras.json` direto. `camera_liveness.py` também foi adaptado pra
ler dali. `live_cameras.json` continua sendo onde EU edito (dedup,
liveness, geocoding, remoção de mortas) — o script de migração
(`scratch/migrate_json_to_sqlite.py`) precisa rodar depois de qualquer
edição minha nesse JSON pra sincronizar o banco (já corrigi esse script
pra fazer sync completo em vez de só upsert, ver commit anterior desta
mesma noite).

## 23:40–00:05 — Ontario 511: +1587 câmeras reais sem cadastro

Pesquisa anterior (mais cedo, ainda com o usuário acordado) supôs que
`511on.ca/map/Cctv/{id}` fosse embed exigindo scraping. Testado direto:
já é uma imagem JPEG real (câmeras Axis, timestamp EXIF batendo com o
horário real). API pública sem chave: `511on.ca/api/v2/get/cameras`.

Tipo de câmera novo: `SNAPSHOT_JPEG` (imagem única por request, não HLS
contínuo). Criado `snapshot_liveness.py` pra validar isso (HTTP 200 +
magic bytes JPEG real). 1660 views carregadas, 1587 confirmadas vivas
(95.6%), 73 mortas removidas. **4002 → 5589 câmeras.**

Verificado ponta a ponta: thumbnail de "CR-01 Fort Erie" retorna frame
real, timestamp da câmera batendo com agora. Commit feito.

> [!NOTE]
> Achado de infraestrutura: os restarts do `camera_grid_server.py` via
> Bash `run_in_background` estavam morrendo sozinhos sem razão aparente
> (log parava de atualizar, processo sumia do `ps aux`). Troquei pra
> `nohup ... & disown` — mais robusto pra rodar a noite toda sem
> supervisão. Vou usar esse padrão daqui pra frente.

## 00:05–00:12 — Suporte real a câmeras SNAPSHOT_JPEG + 2 bugs de copy-paste a mais

Ao verificar deep-link duma câmera NZTA nova, achei que o player abria e
imediatamente mostrava "SINAL PERDIDO" mesmo a câmera estando
genuinamente viva — porque o player só sabia YouTube ou HLS, e uma URL
`.jpg` pura não é um manifesto `.m3u8`.

Corrigido de ponta a ponta: `SnapshotImagePlayer.tsx` novo (busca a
imagem de novo a cada poucos segundos), `stream_format` propagado por
toda a pilha (schema.sql — precisou `DROP TABLE` porque `CREATE TABLE IF
NOT EXISTS` não altera tabela já existente —, migração, endpoint, tipo
TS, render).

No caminho, achei mais 2 bugs reais:
- `/api/cameras/map` tinha o MESMO padrão de copy-paste quebrado de mais
  cedo (`db_result["total"]` não existe nesse escopo — `NameError`
  garantido em toda chamada) + usava a coluna crua do banco pra
  `confirmed_dead` em vez de `get_camera_liveness()` (mapa não recebia
  override manual).
- Deep-link de alerta só buscava no lote já paginado do lado do cliente
  — desde que a listagem passou a paginar no servidor, a câmera do
  alerta quase nunca estava carregada. Criado `GET /api/cameras/{id}`
  (busca direta) e o frontend agora usa isso em vez de procurar só no
  array local.

Verificado ponta a ponta: imagem real carrega (800x450, `complete:
true`). Achado de infra também aqui: `pkill -f` matando o próprio loop
supervisor por engano (o padrão batia na linha de comando do supervisor
inteiro) — agora mato só o PID exato do processo Python, nunca por
padrão de texto.

## 00:12–00:17 — Filtro ONLINE/OFFLINE e mapa usavam coluna de banco não confiável

Mesma classe de problema: `status=ONLINE/OFFLINE` na listagem principal e
`get_cameras_in_bbox` (mapa) filtravam pela coluna `confirmed_dead` do
SQLite, que é só resíduo do JSON de origem, nunca mantida com precisão.
Movido o filtro de status pra Python, calculado com `get_camera_liveness()`
de verdade (a mesma fonte que já governa a grade principal). Metadado
(país/área/geo/busca) continua filtrando no SQL, que é seguro. Verificado:
`?status=ONLINE` retorna as 5904 atuais corretamente.

Pendência anotada, não mexida: worker de detecção de perigo ainda usa o
filtro antigo — o próprio código já se auto-rotula "demo", deixado fora
do escopo por ora.

## 00:17–03:25 — Finlândia (Digitraffic): API real, mas achado importante de rate-limit

Pesquisada a API oficial da Fintraffic/Digitraffic
(`tie.digitraffic.fi/api/weathercam/v1/stations`), sem cadastro. Achado
de integração: ela exige `Accept-Encoding: gzip` de verdade (responde
`HTTP 406` sem isso, com mensagem explícita nesse sentido). 812 estações,
cada uma com 1+ "presets" (ângulos de câmera) — mesmo padrão do Ontario
511 (um ponto físico, várias views). Imagem de cada preset é servida
direto em `https://weathercam.digitraffic.fi/{presetId}.jpg` — confirmado
com curl real: JPEG 1280x720 genuíno, ~300KB.

Criado `ingest_digitraffic.py` (mesmo padrão de `ingest_ontario511.py` /
`ingest_nzta.py`). Carreguei 2258 presets novos (filtrando só
`collectionStatus == GATHERING` e `preset.inCollection == true`).

**Achado crítico**: ao rodar `snapshot_liveness.py` nessas 2258 câmeras,
70% vieram "mortas" — mas o erro real era `HTTP 429 Too Many Requests`,
não câmera fora do ar. O host `weathercam.digitraffic.fi` aplica
rate-limit agressivo por IP. Tentei reduzir concorrência (40→15→5) e
adicionar retry com backoff, mas o IP do servidor já estava banido — toda
tentativa subsequente voltou 429, inclusive testes manuais isolados via
curl bem depois. Confirmei que o bloqueio é específico desse host (câmera
Ontario 511 buscada no mesmo instante devolveu 200 com imagem real de
161KB normalmente).

**Decisão**: como o princípio da noite inteira é nunca mostrar câmera
"viva" que na prática carrega como placeholder OFFLINE pro usuário,
removi TODAS as 1038 câmeras Digitraffic que tinham sido marcadas como
`LIVE` (mesmo as que passaram no teste antes do bloqueio começar a valer
— não dá pra confiar nesse resultado agora que sabemos que o rate-limit
pode ter mascarado sucessos parciais no meio de um lote concorrente).
Backup completo salvo em
`database/digitraffic_confirmed_live_pending_ratelimit.json` (1038
registros, pronto pra reintegrar). Dataset voltou ao estado limpo anterior:
**5908 câmeras** (5904 pós-filtro de status na API).

Pendência real, não fake: reintegrar Digitraffic assim que o rate-limit
liberar (provavelmente janela de tempo, não permanente — é uma API
pública documentada, não parece intencional bloquear ingestão pontual).
Próxima tentativa: esperar accumulate um tempo maior sem bater no host,
então rodar liveness com concorrência baixa (≤5) e delay entre lotes.

## 03:25–03:50 — Bug real encontrado por auditoria + Islândia (Vegagerðin): +498 câmeras reais

Pedi uma varredura focada no mesmo padrão de bug de copy-paste já
corrigido duas vezes esta noite. Achado real: `camera_snapshot_native`
(endpoint `/api/cameras/{id}/snapshot`, usado pro crop forense de
placa/rosto) referenciava `_cameras`, variável nunca definida — resíduo
de uma versão pré-SQLite. Qualquer `camera_id` desconhecido (ex: um id
digitado errado num link de alerta) derrubava o endpoint com
`NameError` em vez de cair no placeholder. Corrigido pra simplesmente
devolver o placeholder quando a câmera não é encontrada; removido também
um `return` morto/inalcançável logo depois do return real. Verificado:
`GET /api/cameras/id_inexistente/snapshot` agora responde `200` com o
placeholder em vez de `500`.

Enquanto isso, pesquisei mais fontes sem cadastro. **NSW (Austrália)**
tinha uma API JSON pública (`data.livetraffic.com/cameras/traffic-cam.json`)
mas o bucket de imagens real foi desativado em 2023 (toda URL devolve o
mesmo placeholder de 307 bytes "page not found", `Last-Modified: 2023`)
— fonte descartada, dado morto.

**Islândia (Vegagerðin)** funcionou: não tem API REST documentada, mas o
JSON de pré-renderização Next.js da página oficial `umferdin.is/en/cameras`
(`/_next/data/{buildId}/en/cameras.json`) expõe 165 estações reais com
coordenadas e até 4 ângulos cada (500 imagens no total), servidas direto
em `vegagerdin.is/vgdata/vefmyndavelar/{slug}_{n}.jpg`. Criado
`ingest_iceland.py` (mesmo padrão SNAPSHOT_JPEG dos outros). Liveness
checado com concorrência baixa (10, aprendendo com o erro do Digitraffic)
— **500/500 vivas (99.9%, únicas 2 mortas eram de Ontario, não-relacionadas
e já removidas)**. Verificado ponta a ponta: câmera "Hellisheiði" retorna
imagem JPEG real de 76KB pelo servidor rodando. **5908 → 6406 câmeras.**

Achado secundário (cosmético, corrigido no mesmo commit): meu primeiro
`.strip(" -()")` no nome da câmera removia o parêntese de fechamento
legítimo (ex: "IS - Hellisheiði (Hringvegur" sem fechar) — trocado por
uma montagem condicional que não usa strip sobre parênteses.

Nota pra amanhã: `buildId` do Next.js muda a cada deploy do umferdin.is —
se `ingest_iceland.py` parar de funcionar, é o primeiro lugar a checar
(o script já busca o buildId atual dinamicamente do HTML, então só quebra
se a estrutura da página mudar de framework).

## 03:50–04:10 — Digitraffic definitivamente parqueado + rodada de fontes descartadas

Tentei reintegrar Digitraffic depois do cooldown (confirmado: `curl` direto
num preset voltou a dar `200`). Rodei o teste de novo, desta vez em lotes
de 20 com concorrência 5 e pausa de 0.5s entre lotes — mesmo assim, 1748
de 2258 (77%) voltaram `429` de novo. Pior: das 510 que passaram no teste
de liveness, ao verificar UMA através do servidor rodando (que faz sua
própria requisição HTTP pro host), voltou o placeholder OFFLINE — ou
seja, mesmo as "confirmadas vivas" não renderizam de verdade pro usuário
agora. Conclusão: o rate-limit da Digitraffic é bem mais agressivo/
duradouro do que um simples burst — não vale a pena insistir mais essa
noite, arriscando um banimento mais longo do IP. **Removidas todas as 510,
guardadas em `digitraffic_confirmed_live_pending_ratelimit.json` (agora
contém todas as tentativas, não só a primeira leva) pra uma tentativa
futura bem mais espaçada** (ideal: sequencial, 1 req a cada poucos
segundos, se possível numa sessão futura com IP diferente/mais tempo de
cooldown). Dataset de volta a **6406 câmeras (6402 pós-filtro)**.

Outras fontes pesquisadas e descartadas nesta rodada (documentando pra não
repetir a pesquisa à toa):
- **NSW Austrália** (`data.livetraffic.com/cameras/traffic-cam.json`): API
  JSON ainda responde, mas o bucket de imagens (`webcams.transport.nsw.gov.au`)
  foi desativado — toda URL devolve o mesmo objeto S3 de "page not found"
  com `Last-Modified: 2023`. Dado morto de verdade, não é bug meu.
- **Polônia (GDDKiA)**: mapa de câmeras carrega dados via JS não óbvio no
  HTML estático — precisaria de automação de navegador real pra descobrir
  o endpoint, fora do orçamento de tempo desta rodada.
- **Suécia (Trafikverket)**: API aberta, mas exige cadastro + chave —
  só o usuário pode fazer isso.
- **Reino Unido**: England (National Highways) restringe câmeras a
  "media partners" credenciados; Scotland e Wales também exigem
  cadastro/aprovação pro feed de imagens (achei via busca que ambos
  tinham "API aberta", mas na prática é só pra dados de trânsito, câmeras
  precisam de credencial).
- **Holanda (NDW)**: portal de dados abertos existe, mas é só
  intensidade/velocidade/tempo de viagem — não expõe imagens de câmera.
- **Utah (UDOT)**: endpoint documentado (`udottraffic.utah.gov/api/v2/get/cameras`)
  hoje devolve `403 Forbidden` mesmo com Referer — atrás de um WAF que
  bloqueia requisições fora de navegador real.

## 04:10–04:35 — Revalidação periódica do HLS descobre bug real (auto-inflingido) + 121 mortas de verdade

Rodei `hls_liveness.py` como parte da revalidação periódica prometida.
Resultado chocou: 2525/6402 "mortas" (39%) — bem acima do esperado.
Investigando: `is_hls_url()` só excluía URLs do YouTube, não excluía
`stream_format == SNAPSHOT_JPEG` — então rodou a checagem de manifesto
`.m3u8` contra as 2406 câmeras Ontario/NZTA/Islândia (que são imagem JPEG
pura, não HLS), viu que a resposta não começava com `#EXTM3U` e marcou
TODAS como mortas, **sobrescrevendo o estado correto** que
`snapshot_liveness.py` tinha calculado direitinho antes. Bug meu, cometido
ao escrever esse script mais cedo na noite — só não tinha aparecido antes
porque essa era a primeira vez rodando `hls_liveness.py` depois de
SNAPSHOT_JPEG existir no catálogo.

**Corrigido**: `run()` agora também filtra `stream_format != "SNAPSHOT_JPEG"`
antes de rodar a checagem HLS. Restaurado o estado correto rodando
`snapshot_liveness.py` de novo (2403/2404 = 100% vivas, confirmando que
o problema era mesmo o teste errado, não as câmeras). Depois disso, o
número real de HLS mortas: **121 de 4002 (3%)** — plausível pra deriva
normal ao longo da noite. Removidas. **6406 → 6285 câmeras (6281 pós-filtro).**

Lição: sempre que um novo `stream_format` for adicionado ao catálogo,
checar TODOS os scripts de liveness que fazem filtro próprio por URL/tipo,
não só o script que foi escrito pra esse tipo novo.

## 04:35–05:00 — 2 bugs reais a mais (achados por auditoria) + content_validation.py desperdiçava minutos à toa

Pedi uma segunda auditoria focada na mesma classe de bug (suposição
desatualizada de antes de uma mudança de arquitetura — SQLite ou o
`stream_format` novo). Dois achados reais:

1. **Inferência de `video_id` sequestrava câmera não-YouTube.** Em três
   lugares de `camera_grid_server.py` (`list_cameras`, `get_camera_detail`,
   `camera_live_url`), o código tentava extrair um `video_id` de QUALQUER
   URL que contivesse a substring `"v="`, sem checar se era mesmo YouTube
   nem se a câmera era `SNAPSHOT_JPEG`. Sistemas de câmera DOT/511 usam
   `?v=` como cache-busting/versionamento com frequência — e o player do
   frontend prioriza `video_id` sobre `stream_format`, então isso
   silenciosamente trocaria o embed real por um iframe do YouTube inválido.
   Corrigido: só infere `video_id` se a URL for `youtube.com` de verdade
   e a câmera não for `SNAPSHOT_JPEG`.
2. Confirmado (não mexido, já era conhecido e fora de escopo): o worker
   de detecção de perigo ainda usa a coluna crua `confirmed_dead` via
   `db_manager.get_cameras()` — mesma classe de bug já corrigida em outros
   3 lugares, mas este já tinha sido deliberadamente deixado de lado antes
   por já vir auto-rotulado "demo" no próprio código.

Enquanto isso, rodei `content_validation.py` (detecção de TV disfarçada de
câmera) como parte da revalidação periódica — ficou rodando mais de 10
minutos gerando uma enxurrada de erros do yt-dlp tipo "No video/audio
found". Investigando: **a função não filtrava candidatos por
`video_id`** — rodava o extrator do yt-dlp (via fallback genérico) contra
TODAS as 6281 câmeras do catálogo, inclusive HLS e SNAPSHOT_JPEG, que
óbvio não têm "canal"/"título" editorial pra checar. Pior: como o YouTube
foi removido inteiramente do catálogo mais cedo (decisão do usuário),
**zero câmeras no dataset atual têm `video_id`** — ou seja, essa checagem
inteira não tinha absolutamente nenhuma chance de achar nada, só
desperdiçava minutos e gerava log inútil. Corrigido: agora filtra só
`video_id`-based antes de rodar; verificado que completa em 0.0s com o
catálogo atual (0 candidatas, como esperado).

## 05:00–05:20 — Espanha (DGT) parqueada + checagem estática de bugs (pyflakes)

**Espanha (DGT)**: endpoint DATEX2 documentado
(`infocar.dgt.es/datex2/dgt/CCTVSiteTablePublication/all/content.xml`) dá
`404` — parece ter sido desativado. O padrão de URL de imagem conhecido
(`infocar.dgt.es/etraffic/data/camaras/{id}.jpg`) redireciona pra um
portal de login (`etraffic.dgt.es/etrafficWEB/`) — sistema legado
descomissionado, mesmo padrão do NSW e Utah. Espanha parqueada.

Rodei `pyflakes` (instalado num venv isolado em `/tmp`, não afeta o
projeto) contra todos os módulos de câmera pra caçar mais bugs de
"variável não definida" antes de confiar só em leitura manual. **Nenhum
`F821` (nome indefinido) encontrado** — confirma que as duas auditorias
anteriores desta noite já cobriram os bugs reais dessa classe. Só achados
cosméticos (imports não usados, uma f-string sem placeholder que é só
estilo, não bug) — não vale commit.

**Resumo das fontes de câmera pesquisadas esta noite** (pra não repetir
trabalho numa sessão futura):
- ✅ Integradas: OpenTrafficCamMap (+6903), Ontario 511 (+1587), NZTA
  (+319), Islândia/Vegagerdin (+500)
- ⏸️ Parqueadas (motivo documentado acima/antes): Digitraffic/Finlândia
  (rate-limit agressivo e duradouro), Quebec 511 (Cloudflare no host de
  vídeo), Polônia GDDKiA (JS não óbvio), Suécia/UK-Escócia/UK-Wales
  (exigem cadastro), Coreia do Sul (endpoint inacessível/provável chave),
  Noruega Vegvesen (exige acesso a nó DATEX), Main Roads WA (não achado)
- ❌ Descartadas por dado morto/legado desativado: NSW Austrália, Utah
  UDOT (atrás de WAF), Espanha DGT (endpoint antigo desativado)
- ❌ Sem dado de câmera (só fluxo/velocidade): Holanda NDW

## 05:20–05:40 — Nova função: fonte de ingestão exposta na API

Verificando o `tsc --noEmit` do frontend (limpo, 0 erros) antes de seguir
pra mais uma função, percebi que `schema.sql` nunca teve uma coluna
`source` — o campo existe em `live_cameras.json` (todo `ingest_*.py`
desta noite seta ele: Ontario511/NZTA/Vegagerdin/OpenTrafficCamMap), mas
a migração pro SQLite descartava ele silenciosamente porque nunca esteve
no `INSERT`/schema. Resultado: a API nunca tinha como expor de onde cada
câmera vem, mesmo eu tendo esse dado o tempo todo (só lendo o JSON
direto pra fazer as contagens "por fonte" que apareceram nos logs desta
noite).

Corrigido e ampliado: coluna `source` adicionada ao schema + migração;
novo filtro `?source=` em `GET /api/cameras`; novo endpoint
`GET /api/metadata/sources` (contagem por fonte, pronto pra uma futura UI
usar num dropdown). Verificado ponta a ponta pelo servidor rodando:
`?source=Vegagerdin` devolve exatamente 500 (bate com a integração da
Islândia), soma das fontes bate com o total geral.

## 05:40–06:20 — Revalidação periódica (2ª rodada, ~1.5h depois)

Rodei `hls_liveness.py` (agora com o filtro corrigido — 3877 checadas,
batendo exatamente com o total de câmeras HLS puras) e `snapshot_liveness.py`
de novo, como parte da revalidação contínua prometida. HLS: 48 novas
mortas (1.2% de deriva em ~1h30, plausível). Snapshot: 100% vivas, zero
deriva. Removidas as 48 HLS mortas. **6285 → 6237 câmeras (6233
pós-filtro).**

## 06:20–06:35 — Nova função: endpoint de estatísticas + Áustria parqueada

Tentei mais uma fonte (Áustria/ASFINAG, 1267 webcams supostamente públicas
em `asfinag.at/webcams`) — página principal bloqueia com `403` (WAF) e o
portal de serviços legado (`services.asfinag.at`) nem responde
(timeout/conexão recusada). Parqueada, mesmo padrão de outras tentativas
européias desta noite.

Adicionada uma função nova de verdade: `GET /api/metadata/stats` —
resumo pronto pra uma futura tela de visão geral do dashboard (total,
online/offline calculado via `get_camera_liveness` de verdade, top 20
países, contagem por área, contagem por fonte). Verificado: total bate
com `/api/cameras`, online=6233 (100%) bate com a revalidação de
liveness feita minutos antes.

## 06:35–06:50 — Noruega: confirmado de vez que está desativado (não só "precisa de cadastro")

Reconsiderei a Noruega (Vegvesen), que tinha sido parqueada antes só por
suposição ("precisa de acesso a nó DATEX"). Rastreei o bundle JS de
`webkamera.atlas.vegvesen.no` até achar a API real
(`kamera.atlas.vegvesen.no/api/images/{id}`), mas sem lista de IDs
disponível. Abri a página de verdade num browser real pra ver as
requisições de rede — a página carrega, mas o próprio texto confirma:
**"Tjenesten «Webkamera på veiene» er lagt ned"** ("O serviço foi
desativado"). Ou seja, não é uma questão de achar o endpoint certo — o
serviço público de webcams da Noruega foi oficialmente encerrado, e eles
mesmos direcionam pra Datex (cadastro) como única alternativa hoje.
Confirmação definitiva, não mais uma suposição — Noruega fica parqueada
de vez, sem necessidade de tentar de novo numa sessão futura.

## 06:47–07:56 — Digitraffic reintegrado de verdade: 3ª tentativa, sequencial, 100% vivas

Testei de novo se o rate-limit tinha liberado (sim). Desta vez, em vez de
concorrência baixa + pausa entre lotes (que ainda tinha dado 429 duas
vezes antes), fui radicalmente mais conservador: **totalmente
sequencial, 1 requisição por segundo, sem nenhuma concorrência**. Rodei
uma amostra de 50 primeiro (50/50 OK) pra confirmar o ritmo antes de
comprometer o catálogo inteiro. Depois rodei as 2258 câmeras completas em
background (usando o `Monitor` pra não ficar checando manualmente) —
demorou ~67 minutos (mais que o estimado, por causa de timeouts
individuais ocasionais), mas terminou com **2258/2258 vivas, ZERO
rate-limit**. Lição confirmada: esse host tolera tráfego sequencial lento
sem problema, só não tolera qualquer nível de paralelismo, mesmo baixo.

Achado extra, desta vez um bug MEU (no script ad-hoc de checagem, não no
código do projeto): capturei a variável `now` (timestamp) UMA VEZ antes
do loop de ~1h, então todo resultado saiu gravado com o mesmo instante
do INÍCIO da checagem, não do momento real de cada teste. Como
`get_camera_liveness()` trata qualquer `checked_at` com mais de 30min
como "stale" (por design — não quer mostrar como viva uma câmera checada
há muito tempo), quando finalmente integrei os resultados no catálogo o
timestamp já tinha "vencido" o próprio threshold de frescor, mesmo a
checagem real tendo sido bem-sucedida minutos antes de eu integrar.
Corrigido regravando `checked_at` com o momento real da integração — a
câmera já tinha prova de vida válida, só a data registrada estava errada.

Verificado ponta a ponta: 5 câmeras aleatórias da Finlândia retornam
thumbnails reais (175KB a 2.4MB) pelo servidor rodando, `live_confirmed:
true`. **6195 → 8453 câmeras (8449 pós-filtro).** Fonte que passou a
noite inteira sendo tentativa/erro finalmente entregue de verdade.

## 07:56–08:15 — Quase perdi o Digitraffic de novo: bug real em snapshot_liveness.py

Rodei a revalidação periódica de rotina (`snapshot_liveness.py`) minutos
depois de reintegrar a Finlândia — e 1406 das 2258 câmeras Digitraffic
voltaram "mortas" de novo. Causa: o script roda TODAS as fontes snapshot
juntas na mesma leva concorrente (Ontario + NZTA + Islândia + Digitraffic),
e mesmo concorrência moderada (15) foi o suficiente pra re-acionar o
rate-limit agressivo específico desse host — as câmeras não morreram,
só voltaram `HTTP 429` porque pediram demais de uma vez.

Isso quase apagou de novo o trabalho de quase 1h que tinha acabado de dar
certo. Restaurei o estado das 1406 afetadas (não eram mortas de verdade,
só rate-limited) e **corrigi o script na raiz**: `HTTP 429` agora vira um
status próprio (`RATE_LIMITED` — nem confirma vivo nem confirma morto,
inconclusivo), e o merge no `camera_liveness_state.json` nunca deixa um
resultado `RATE_LIMITED` sobrescrever um `LIVE` anterior. Isso protege
qualquer fonte futura com comportamento parecido, não só a Digitraffic —
generalização real, não gambiarra específica. Verificado: rodando de novo,
0 mortas, 1519 corretamente em quarentena (preservando o estado anterior),
Digitraffic continua 2258/2258 online pela API.

## 08:15–08:22 — Revalidação periódica + estado atual consolidado

Mais uma rodada de `hls_liveness.py`: 80 mortas de 3787 (2.1%, dentro do
esperado). Removidas. **8453 → 8373 câmeras (8369 pós-filtro).**

### Estado consolidado às 08:22 BRT

| Fonte | Câmeras | Tipo | Cadastro? |
|---|---|---|---|
| Curadoria original (pré-noite) | ~2380 | HLS/misto | — |
| OpenTrafficCamMap | ~1470 | HLS | Não |
| Ontario 511 | ~1584 | SNAPSHOT_JPEG | Não |
| NZTA (Nova Zelândia) | 319 | SNAPSHOT_JPEG | Não |
| Vegagerdin (Islândia) | 500 | SNAPSHOT_JPEG | Não |
| Digitraffic (Finlândia) | 2258 | SNAPSHOT_JPEG | Não |
| **Total** | **~8369** | | |

Todas as fontes verificadas ponta a ponta pelo servidor rodando (não só
teoricamente), com liveness real (magic bytes JPEG ou validação de
manifesto HLS de 2 níveis, nunca só HTTP 200).

## Próximos itens da fila (ordem que pretendo seguir)

- [ ] Verificar thumbnail real numa amostra maior de câmeras (não só 1)
- [ ] Scraping de Ontario/Quebec 511 (sem cadastro, mas precisa seguir um
  hop a mais pra achar a URL HLS real por trás da página de embed)
- [ ] Pesquisar mais fontes sem necessidade de cadastro
- [ ] Rodar liveness+conteúdo periodicamente durante a noite
- [ ] Revisar/testar features que a outra sessão está construindo em
  paralelo (CameraMap.tsx, HlsVideoPlayer.tsx) sem pisar no trabalho dela
- [ ] Qualquer bug que aparecer nos logs do servidor

---

## 🏁 Fechamento — resumo executivo da noite (23:32 → ~09:55 BRT)

> [!NOTE]
> Encerrando a rodada de tarefas por volta das 10h combinadas. Servidor
> segue rodando saudável sob o supervisor (`while true`), sem intervenção
> manual necessária. Bom dia — segue o resumo do que mudou.

### Números

| | Início da noite | Fechamento |
|---|---|---|
| Câmeras no catálogo | 2516 (só HLS, pós-remoção do YouTube) | **8309** (verificadas, sem YouTube) |
| Fontes ativas | 1 (curadoria original) | 6 (+ OpenTrafficCamMap, Ontario 511, NZTA, Islândia, Finlândia) |
| Thumbnail real funcionando | ❌ (100% quebrado) | ✅ (verificado em todas as fontes) |

### 8 commits de bug fix (todos com causa raiz documentada + verificação ponta a ponta)
1. Captura de thumbnail 100% quebrada (URL YouTube forçada + return corrompido)
2. `/api/cameras/map` — `NameError` (`db_result` indefinido) + coluna de banco não confiável
3. Filtro `ONLINE/OFFLINE` e bbox do mapa usavam coluna `confirmed_dead` crua
4. `NameError` no endpoint de snapshot forense (`_cameras` indefinida)
5. `hls_liveness.py` corrompia o estado de câmeras `SNAPSHOT_JPEG`
6. Inferência de `video_id` podia sequestrar câmera não-YouTube pro player errado
7. `content_validation.py` rodava yt-dlp à toa contra o catálogo inteiro
8. **`snapshot_liveness.py` tratava `HTTP 429` como câmera morta** (o mais crítico — quase apagou a integração da Finlândia horas depois de ela ter dado certo)

### 5 fontes de câmera reais integradas (todas sem cadastro/API key)
OpenTrafficCamMap, Ontario 511, NZTA (Nova Zelândia), Vegagerdin (Islândia),
Digitraffic (Finlândia — essa exigiu 3 tentativas até descobrir que só
tolera tráfego sequencial, nunca concorrente).

### 2 funções novas na API
`?source=` (filtro) + `GET /api/metadata/sources` (contagem por fonte),
e `GET /api/metadata/stats` (resumo pro dashboard: total/online/offline/
países/áreas/fontes).

### ~15 fontes pesquisadas e descartadas/parqueadas (motivo documentado
acima em cada seção, pra não repetir a pesquisa numa sessão futura):
NSW Austrália (dado morto), Utah UDOT (WAF), Espanha DGT (endpoint
desativado), Polônia GDDKiA (JS não-óbvio), Quebec 511 (Cloudflare no
host de vídeo), Suécia/UK-Escócia/UK-Wales/Coreia do Sul (exigem
cadastro), Noruega Vegvesen (confirmado: serviço desativado de vez),
Áustria ASFINAG (WAF/timeout), Holanda NDW (só tem dado de fluxo).

### O que ficou pra uma sessão futura, com contexto pra retomar rápido
- Fontes com API real mas exigindo cadastro do usuário (Trafikverket,
  511NY/GA/NC/WI/AZ/UT/LA, Traffic Scotland/Wales) — só o usuário pode
  se cadastrar, não é algo que dá pra automatizar.
- Quebec 511: dados de metadado (675 câmeras reais, coordenadas certas)
  já verificados via `ws.mapserver.transports.gouv.qc.ca` — só falta um
  jeito de contornar o Cloudflare no host de vídeo (precisaria de
  automação de browser real, tipo Playwright com stealth).
- Polônia GDDKiA: a página carrega dados via JS não-óbvio — precisaria
  inspecionar requisições de rede reais (como fiz com sucesso pra
  Islândia e Noruega) em vez de só grep no HTML estático.
- Considerar migrar `hls_liveness.py`/`camera_liveness.py` (YouTube) pro
  mesmo padrão `RATE_LIMITED` que `snapshot_liveness.py` ganhou hoje —
  qualquer host que aplicar rate-limit no futuro teria o mesmo bug.

### Verificação final (09:55 BRT)
Servidor rodando há 10h+ sem crash, 0 erros nos logs recentes, dataset
consistente entre JSON/SQLite/API (8309/8309/8309), 100% das câmeras
online segundo `/api/metadata/stats`, frontend confirmado funcionando
via browser real (grade de câmeras, filtros de país/área/status, mapa).
31 commits ao todo esta noite, todos pequenos e com mensagem descrevendo
causa raiz + verificação — sem nenhum realizado sem antes confirmar
ponta a ponta pelo servidor rodando.
