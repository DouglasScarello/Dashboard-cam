# Regras de Desenvolvimento Tático — Olho de Deus (Ghost Protocol)

## 1. Segurança & Ghost Protocol
- **Segredos & Credenciais**: NUNCA commitar tokens de API, senhas ou credenciais de bots Telegram. Sempre utilizar variáveis de ambiente via `.env` ou expansão `${VAR}`.
- **Air-gap & Metadata**: Não utilizar servidores STUN públicos ou serviços externos de telemetria que possam vazar IPs ou stream metadata.
- **Cadeia de Custódia**: Todas as evidências e relatórios periciais PDF devem ter hash SHA-256 e ser cifrados com AES-256-EAX antes de repouso em disco.

## 2. Concorrência e Processamento de Vídeo
- **Isolamento de Inferência**: Jamais desenhar bounding boxes ou HUDs diretamente no array NumPy do frame de inferência; sempre usar `.copy()`.
- **AtomicFrameRing**: Sempre proteger métodos de push/latest com Locks (`threading.Lock` ou `asyncio.Lock`) para prevenir corrupção de memória.
- **Executors Dedicados**: Operações bloqueantes de I/O de câmeras (OpenCV `VideoCapture`, `imencode`) devem rodar em `ThreadPoolExecutor` dedicado para nunca travar o event loop do FastAPI.

## 3. Desktop & Frontend Tauri
- **Segurança de Caminhos**: Toda operação de leitura/escrita de arquivos deve ser sanitizada via `canonicalize()` para mitigar Directory Traversal.
- **Content Security Policy**: Manter CSP estrita no Tauri sem `unsafe-eval`, restringindo conexões estritamente às portas locais autorizadas (8000, 8001, 1984, 5000).
- **Gerenciamento de Memória React**: Sempre limpar instâncias de `Hls.js`, desmontar vídeos com `removeAttribute('src')`, e usar `useMemo` / `React.memo` para evitar re-renderizações desnecessárias do grid de câmeras.
