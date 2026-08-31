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

## Próximos itens da fila (ordem que pretendo seguir)

- [ ] Verificar thumbnail real numa amostra maior de câmeras (não só 1)
- [ ] Scraping de Ontario/Quebec 511 (sem cadastro, mas precisa seguir um
  hop a mais pra achar a URL HLS real por trás da página de embed)
- [ ] Pesquisar mais fontes sem necessidade de cadastro
- [ ] Rodar liveness+conteúdo periodicamente durante a noite
- [ ] Revisar/testar features que a outra sessão está construindo em
  paralelo (CameraMap.tsx, HlsVideoPlayer.tsx) sem pisar no trabalho dela
- [ ] Qualquer bug que aparecer nos logs do servidor
