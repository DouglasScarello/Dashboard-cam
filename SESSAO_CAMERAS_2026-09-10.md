---
tipo: "relatorio"
projeto: "dashboard-cam"
criado: "2026-09-10"
proposito: >
  Log da sessão de trabalho autônomo pedida pelo usuário às ~13:20 de
  2026-09-10: catalogar câmeras PÚBLICAS de acesso livre, de RUA (não
  rodovia/trânsito), em áreas movimentadas de centros de cidade —
  pra uso no reconhecimento facial. Usuário saiu de casa (trabalho no
  Bob's) e volta às 23h de hoje; pediu trabalho contínuo até lá.
  Regra explícita: pesquisar e entender o contexto ANTES de agir.
---

# 📋 RESUMO (atualizado ~14:30) — leia isso primeiro

**Status até agora: 2 câmeras aprovadas e catalogadas, de ~35 verificadas.**
Baixo, mas cada aprovação passou por 3 critérios rígidos de verdade
(pública, de rua — não rodovia, e movimentada) — prefiro poucas
confiáveis a muitas duvidosas. Trabalho contínuo, sem parar, até 23h.

## O que já funciona
- **Ferramenta de verificação visual própria** (`snap_camera.py`,
  Playwright) — contorna um bug do screenshot nativo do navegador MCP
  que travava nesta sessão. Salva screenshot real em disco, eu confiro
  com meus "olhos" via Read tool antes de aprovar qualquer câmera.
- **`add_street_camera.py`** — cadastra câmera verificada no catálogo
  (`database/live_cameras.db`), separada das 8.198 de rodovia por
  `source="GlobeTV-Rua-Verificada"` e `tipo_area="RUA_PEDESTRE"`.

## As 2 aprovadas
Krupówki (rua de pedestres mais famosa de Zakopane, Polônia) — 2
ângulos diferentes, dezenas de pessoas bem identificáveis, altura de
câmera baixa o suficiente pro rosto não virar ponto. IDs:
`globetv_krupowki_zakopane_1` e `_2`.

## Três achados que estão guiando a busca agora
1. **Altura da câmera importa mais que "tem gente"**: praças
   principais de cidade grande (Kraków, Varsóvia, Wrocław) quase
   sempre são filmadas do topo de uma torre — lindo, genuinamente
   movimentado, mas rosto vira pontinho. Só rua estreita com câmera
   baixa (tipo Krupówki) realmente serve.
2. **Fuso horário decide se vai ter gente na tela**: testei vários da
   Polônia sem perceber que já era fim de tarde/noite lá — praça vazia
   não é culpa da câmera, é a hora errada. Agora priorizo região que
   está em horário de pico AGORA (ver seção de achados completa).
3. **Nem toda câmera boa pros meus olhos serve pro sistema**: a
   EarthCam de Times Square é visualmente perfeita, mas usa uma URL
   `blob:` (só existe dentro da aba do navegador) — o pipeline de
   reconhecimento (`cv2.VideoCapture`) não consegue ler isso. Só cadastro
   câmera com URL de stream de verdade (`.m3u8` na maioria dos casos).

## Fontes
- **`globetvapp/webcams`** (GitHub, 2.905 câmeras mundiais) — fonte
  principal, filtrada pra 199 candidatas de cena urbana.
- **`webcamera.pl`** — rede comercial polonesa, confirmada legítima,
  expõe URL `.m3u8` de verdade (as 2 aprovadas vêm daqui).
- **`opencctv.org`** — **descartada**, sem documentação de origem das
  câmeras, risco de ser agregador de câmera não-autorizada.
- **EarthCam** — legítima, mas tecnicamente inutilizável (URL blob).

*(O log detalhado câmera-a-câmera, com cada verificação, continua
abaixo.)*

---

# 📋 Contexto e decisões (leia antes do log câmera-a-câmera)

## O pedido exato do usuário
> "precisamos de câmeras que sejam públicas de acesso livre mais que
> sejam de rua tipo centros da cidades coisas movimentadas pra usar pro
> reconhecimento tudo de livre acesso nada de câmeras privadas, talvez
> precise ir cam a cam pra ver o que tem na imagem ao vivo pra vc ir
> catalogando isso é infinito"

Três critérios obrigatórios, nessa ordem de importância:
1. **Pública e de acesso livre** — sem login, sem autenticação, sem
   burlar nada. Nunca câmera privada/não-autorizada.
2. **De rua, não de rodovia/trânsito** — o catálogo atual (8.198
   câmeras: Digitraffic, Ontario511, OpenTrafficCamMap, Vegagerdin,
   NZTA) é **100% câmera de rodovia/trânsito de DOT** — nenhuma delas
   serve pra reconhecimento facial (mostram carro, não rosto). Esse é
   exatamente o motivo desse pedido novo.
3. **Movimentada** — precisa ter gente de verdade passando, visível,
   pra reconhecimento facial fazer sentido. Câmera de praça vazia de
   madrugada não serve.

## Por que não dá pra confiar só em metadado/tag automática
Testei isso primeiro: peguei uma lista pública de webcams do mundo
(`globetvapp/webcams`, no GitHub, 2.905 câmeras, `scene` categorizado
automaticamente) e filtrei por `scene in (city, street, landmark,
urban_panorama)` — 199 candidatas. Mas ao olhar os nomes, vários são
claramente mal-categorizados: "Col de la Tourmente Scenic View"
(paisagem, não rua), "Sangay Volcano 24/7" (vulcão!), "Ehukai Beach Surf
Highlights" (praia) — todos vieram com tag "city"/"landmark" mas não são
rua movimentada nenhuma. **Confirma exatamente o que o usuário previu:
não dá pra confiar em metadado, precisa checar câmera por câmera de
verdade.**

## Fontes pesquisadas e decisão de uso

| Fonte | O que é | Uso |
|---|---|---|
| `globetvapp/webcams` (GitHub) | Lista agregada de 2.905 webcams mundiais, `last_ok` atualizado nas últimas horas (mantida ativamente), 408 são stream do YouTube (`type: youtube`) e 2.497 são HLS direto (`type: hls`) | **Fonte primária** — mas só os 199 filtrados por scene urbano, verificados 1 a 1 |
| YouTube ao vivo (canais de turismo/prefeitura oficiais) | Streams 24/7 de câmera de praça/rua que cidades/prefeituras/pontos turísticos mantêm publicamente de propósito | **Prioridade #1 pra verificar** — legitimidade inequívoca (o dono do canal escolheu transmitir publicamente), fácil de checar (só abrir o vídeo) |
| `opencctv.org` | Agregador que promete "câmeras públicas de rua mundo afora" | **NÃO USAR** — bloqueou fetch automatizado (403), sem documentação clara de onde vêm as câmeras. Nomes desse estilo historicamente incluem sites tipo "insecam" que mostram câmera de segurança privada com senha padrão/sem senha, sem autorização do dono — exatamente o que o usuário pediu pra NUNCA usar. Sem conseguir confirmar a origem, não arrisco. |
| Stream HLS "cru" (não-YouTube) do `globetvapp/webcams` | URLs tipo `wowza.telpin.com.ar/...m3u8` | Uso com mais cautela — só se o domínio for claramente de uma prefeitura/site turístico oficial reconhecível, verificado individualmente |

## Critério de aprovação por câmera (o que eu realmente checo)
Pra cada candidata, abro o stream/vídeo de verdade no navegador e confirmo:
1. Abre sem login/paywall, de verdade ao vivo (não é gravação em loop óbvia)
2. É nível de RUA — pessoas caminhando visíveis, não vista aérea/panorâmica
   só de prédio/paisagem
3. Tem gente de verdade na cena (não praça vazia)

Só entra no banco se passar nos 3. Registro cada verificação abaixo
(aprovadas E reprovadas, pra não checar de novo por engano).

## Onde vai no banco
Tabela `cameras` (mesma do catálogo de 8.198 já existente,
`database/live_cameras.db`), mas com `source = "GlobeTV-Rua-Verificada"`
e `setor`/`tipo_area` marcando "RUA_PEDESTRE" — assim
`monitor_camera.py`/futuras buscas conseguem filtrar só essas quando o
objetivo for reconhecimento facial, sem misturar com as 8.198 de
rodovia.

---

## ⚠️ Limitação técnica encontrada (importante, leia antes de confiar nas aprovações abaixo)

Por volta das 13:25, a ferramenta de **screenshot do navegador parou de
funcionar** nesta sessão — testei em várias abas novas, em site
simples (example.com) e no YouTube, com espera de mais de 15s e menos
de 1.0 de carga de CPU (ou seja, não é sobrecarga da máquina). Sempre
dá timeout de 30s. Navegação, execução de JavaScript, leitura de
console e de rede continuam funcionando normalmente — é especificamente
a captura de pixel/imagem que está quebrada nesta sessão.

**Isso significa que não consigo literalmente "ver" o que está na
câmera ao vivo agora**, exatamente o método que você pediu
("ir cam a cam pra ver o que tem na imagem"). Decisão: em vez de parar
o trabalho esperando a ferramenta voltar, vou adaptar o critério —
uso os sinais mais fortes disponíveis sem visão (JS confirma que o
vídeo está de verdade tocando ao vivo — `readyState`, `paused`,
badge "AO VIVO"/"LIVE" — mais o título/descrição do canal, mais
reputação de câmeras/praças mundialmente conhecidas) e **sou mais
conservador**: só aprovo quando tenho confiança razoável mesmo sem ver
o frame, e pulo (não aprovo) qualquer candidata ambígua em vez de
arriscar. Tento a screenshot de novo periodicamente — se voltar a
funcionar, retomo a verificação visual de verdade e re-confirmo o que
foi aprovado só por texto.

**Toda entrada abaixo marcada "(sem verificação visual — só
metadado+liveness)" precisa de uma conferida seus com seus próprios
olhos quando você puder, antes de confiar 100% nela pro
reconhecimento.**

---

# Log câmera-a-câmera (aprovadas ✅ e reprovadas ❌)

### ❌ "Dublin City Centre" (globetv id, video_id AdUw5RdyZxI)
Na verdade não abre "Dublin City Centre" — o video_id aponta pro canal
oficial @earthcam, mas o vídeo específico está com "Vídeo indisponível"
(confirmado via `read_page`, não só timeout). Lista fonte tinha
`last_ok` recente mas esse ID mudou/morreu. Reprovada (link morto).

### ⏭️ "Basílica Histórica | Santuário Nacional AO VIVO" (X52LJG2z_UQ, era candidata "Aparecida Basilica")
Confirmado genuinamente ao vivo (JS: readyState=4, tocando). Mas nome
sugere foco arquitetônico (fachada/prédio da basílica), sem descrição
confirmando vista de rua/pedestre nível-chão. **Pulada por enquanto**
(ambígua sem checagem visual) — candidata a reconferir quando a
screenshot voltar a funcionar.

## Achado metodológico: altura/ângulo da câmera importa, não só "tem gente"

Primeira verificação visual real (via `snap_camera.py` + Playwright,
contornando o bug do screenshot — ver seção anterior): "Muikku LIVE -
Kuopion Tori" (praça de mercado de Kuopio, Finlândia). Câmera genuína,
ao vivo, com pessoas de verdade andando — mas é uma vista AÉREA/elevada
(prédio alto olhando pra baixo), rosto vira um pontinho, inútil pra
reconhecimento facial de verdade. **Refinando o critério: só aprovar
câmera em altura de rua/olho humano ou no máximo 1º/2º andar, nunca
vista de topo de prédio.**

### ❌ Kuopion Tori (Kuopio Market Square, Finlândia) — T7RdJdFMz-U
Ao vivo, gente de verdade, mas vista aérea alta demais — rosto não dá
pra reconhecer. Reprovada pro propósito de reconhecimento facial
(poderia servir pra outra coisa, tipo densidade de multidão, mas não é
o pedido).

## Resolvido: ferramenta de verificação visual própria (contorna o bug)

Depois de confirmar que o screenshot nativo do navegador MCP está
quebrado nesta sessão (não é sobrecarga de CPU — testei em várias
condições), construí `olho_de_deus/snap_camera.py` — usa Playwright
(já instalado no projeto) pra abrir a câmera de verdade e salvar um
screenshot em disco, que eu leio com a ferramenta `Read` (que exibe
imagem de verdade). **Verificação visual real está de volta**, as
próximas entradas do log já são conferidas com os "olhos".

Dois achados de robustez no processo:
- Navegar pra página cheia do YouTube (`/watch?v=`) trava de forma
  imprevisível em alguns vídeos (>90s sem erro nenhum). Resolvido
  usando `<iframe>` do `/embed/` (muito mais leve/rápido) — só cai em
  "Erro 153" quando o canal desabilita embed (aí pulo essa e sigo).
- URLs de HLS "cru" da lista fonte às vezes retornam 404 mesmo com
  `verified: true`/`last_ok` recente — CDNs de streaming trocam o
  chunklist específico com frequência, o snapshot da lista não
  acompanha. Confirmo cada uma de verdade antes de aprovar.

### ❌ Akihabara - Tokyo (68DhvzKCVOc)
Erro 153 (canal desabilitou embed) — não dá pra verificar sem abrir a
página cheia (que trava). Pulada.

### ❌ Kraków — Rynek Główny (webcamera.pl, chunklist_w1)
URL da lista fonte retorna 404 de verdade (confirmado via rede, não é
bug meu) — chunklist expirado. Reprovada (link morto nessa URL
específica).

### ❌ Fukuoka Tenjin City Center, St. Peter's Square, Reykjavik City
Todas com embed bloqueado pelo canal (não dá pra verificar sem abrir a
página cheia, que tem risco de travar) — puladas por enquanto.

### ❌ Mississauga Celebration Square (webvideo.mississauga.ca — domínio oficial da prefeitura)
Confirmada ao vivo de verdade (relógio na imagem bate com a hora real,
2026-09-10 12:42PM) e fonte com legitimidade máxima (câmera da própria
prefeitura). Mas: vista elevada de cima de prédio E praça
completamente VAZIA no momento (nenhuma pessoa visível). Reprovada
(sem gente agora — pode reconferir em outro horário/dia de evento).

### ✅ Krupówki — Zakopane, Polônia (webcamera.pl)
**PRIMEIRA APROVADA.** Rua de pedestres mais famosa de Zakopane
("najpopularniejszy deptak" = "o passeio mais popular"). Verifiquei ao
vivo de verdade: dezenas de pessoas visíveis andando, sentadas,
comprando, restaurantes/lojas abertos e iluminados (fim de tarde na
Polônia). Altura de câmera moderada (2º/3º andar aprox), pessoas bem
distinguíveis como indivíduos. Fonte: webcamera.pl (rede comercial
polonesa de webcams, hospeda várias cidades — parece legítima, não
achei sinal de ser câmera não-autorizada). **Adicionada ao catálogo**
(`globetv_krupowki_zakopane_1`, source=GlobeTV-Rua-Verificada).

### ✅ Krupówki vista 2 — Zakopane (ângulo mais próximo)
Mesma rua, ângulo mais próximo/baixo, gente ainda mais identificável
(base da imagem). **Adicionada** (`globetv_krupowki_zakopane_2`).

### ❌ Krupówki vista 3 (na verdade é área de tubing/lazer, não a rua)
Apesar do nome, mostra uma área de tobogã/tubing na encosta, quase
vazia, não é a rua de pedestres. Reprovada.

### ❌ Kraków Rynek Główny (Wentzl), Castle Square Varsóvia
Mesmo padrão do Rynek Główny anterior: praça histórica genuinamente
movimentada, mas câmera no topo de torre/prédio alto — rosto
irreconhecível. Reprovadas pro propósito de reconhecimento facial
(achado: a rede webcamera.pl parece favorecer ângulo panorâmico de
torre pras praças principais — bonito pra turismo, inútil pra
reconhecimento).

### ⏭️ Torgallmenningen (Noruega) — erro técnico, não reprovada por conteúdo
`page.set_content` deu timeout carregando o hls.js pra essa URL
específica — não cheguei a ver o conteúdo. Fica pra reconferir.

### ❌ George Street (Canadá), Kamakura Komachi Street (Japão)
Embed bloqueado, pulei.

### ❌ Aspen Square, Colorado, EUA (coloradowebcam.net — hotel, fonte legítima)
Ao vivo confirmado (relógio bate), fonte comercial legítima (hotel
patrocina webcam pública). Mas pouco movimento agora (poucos
pedestres/ciclistas) e altura moderada. Reprovada por enquanto —
poderia reconferir em horário de mais movimento.

### ❌ Wrocław Rynek (elevado, mas com gente — mesmo problema de altura)
### ❌ Wejherowo, praça pequena (sem gente nenhuma visível agora)
### ❌ OSM Webcam "downtown-silver" (cidade pequena nos EUA, rua vazia agora)

## Balanço parcial (~14:00): 2 aprovadas de ~20 verificadas
Padrão claro se formando: a rede `webcamera.pl` favorece ângulo de
torre/telhado alto pras praças principais das cidades grandes (bonito
pra turismo, mas rosto vira ponto). As duas aprovadas (Krupówki) só
funcionaram porque são uma RUA estreita com prédios baixos ao redor,
não uma praça grande — a câmera fica relativamente mais perto de quem
passa. **Próxima estratégia: procurar mais câmeras de RUA ESTREITA
específica (não praça/rynek grande), e pesquisar outras fontes além do
globetvapp/webcams.**

## Achado técnico importante: nem toda câmera "boa visualmente" dá pra catalogar

### ⚠️ EarthCam Times Square (tsrobo1) — ótima pros olhos, inutilizável pro pipeline
Pesquisei e achei a câmera de rua de verdade da EarthCam em Times
Square (não a versão "torre" que vi antes) — visualmente é exatamente
o que o usuário quer: **dezenas de pessoas bem próximas e
identificáveis**, praça mais movimentada do mundo, fonte
inquestionavelmente legítima e pública (EarthCam, empresa conhecida).

Mas ao inspecionar o player, o vídeo usa uma URL `blob:` — construída
por JavaScript no navegador via Media Source Extensions, não existe
como link de rede de verdade. **Isso significa que não dá pra usar no
pipeline de reconhecimento** (`live_pipeline.py`/`monitor_camera.py`
usam `cv2.VideoCapture`, que precisa de uma URL HTTP/HLS de verdade,
não um blob só existente dentro da aba do navegador). Provavelmente
proposital da EarthCam (proteção de conteúdo).

**Não adicionada ao catálogo** — mas fica registrada como referência
"ótima fonte visual, ruim pra automação". Se algum dia quiser assistir
manualmente, é essa: `earthcam.com/usa/newyork/timessquare/?cam=tsrobo1`.

**Ajuste de estratégia:** daqui pra frente, só considero fontes que já
provaram ter URL de stream de verdade e pegável (como a rede
`webcamera.pl`, que expõe `.m3u8` direto) — evita perder tempo em
câmeras visualmente ótimas mas tecnicamente inúteis.

## Achado metodológico: fuso horário importa demais pra "movimentada"

Depois de reprovar Opole, Starachowice, Sucha Beskidzka e Wadowice por
"pouca gente" — percebi o padrão: são todas da Polônia, e agora são
~19h lá (entardecer, já esvaziando). Não é que essas praças sejam
ruins, é que caí verificando todas no horário errado. **Daqui pra
frente: priorizar região que está em horário de pico (meio-dia/tarde)
agora, e guardar as candidatas de fuso "fora de hora" pra reconferir
quando virar dia de lá** (a sessão continua até as 23h de hoje, dá
tempo de voltar).

Agora (14h Brasil): meio-dia nos EUA (bom horário), tarde no Brasil/
América Latina (bom horário), amanhecer/madrugada na Ásia (ruim,
evitar por enquanto), entardecer na Europa (ruim agora, reconferir
mais tarde ainda hoje/à noite European não ajuda tão cedo — melhor
tentar de manhã horário de Brasília, que aí já é meio-dia na Europa).

## Melhorias na ferramenta: fallback pra página cheia com teto absoluto

Adicionei `_with_hard_timeout()` (via `signal.alarm`) — trava real
achada no Akihabara (>90s) não era coberta por nenhum timeout do
Playwright configurado. Agora `snap_youtube()` tenta embed leve
primeiro e, se vier bloqueado, cai pra página cheia com teto de 25s —
nunca mais trava, na pior das hipóteses retorna erro rápido.

### ❌ Plaza Garibaldi, Plaza Fundadores (Querétaro) — vídeos mortos
Canal "Webcams MX" tem vários vídeos antigos indisponíveis na lista
fonte. Rede (webcamsdemexico.com) parece legítima, mas os IDs
específicos dessa lista morreram — vale visitar o site direto depois.

### ❌ "City Center of Dover" — na verdade é demo de fabricante de câmera
Stream de teste da empresa "use-IP Ltd" mostrando uma via/rotatória em
Dover (Reino Unido) — sem pedestres, é demonstração de produto, não
câmera de monitoramento urbano de propósito.

### ❌ "Downtown, Amalie Arena" — na verdade é webcam da University of Tampa
Vista de rio/campus, sem gente, painorâmica. Reprovada.

Balanço: ~35 candidatas verificadas, 2 aprovadas. Continuando.
