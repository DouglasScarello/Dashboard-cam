#!/usr/bin/env python3
"""
snap_camera.py — Olho de Deus (ferramenta de curadoria, não parte do produto)

Salva um screenshot real de uma câmera candidata (YouTube ao vivo ou HLS
direto) em disco, pra dar pra olhar de verdade com o Read tool — contorna
o bug do screenshot do navegador MCP nesta sessão (2026-09-10, ver
SESSAO_CAMERAS_2026-09-10.md).

Uso:
    poetry run python3 snap_camera.py --youtube VIDEO_ID --out /tmp/x.png
    poetry run python3 snap_camera.py --hls "https://.../playlist.m3u8" --out /tmp/x.png
"""
import argparse
import signal
import sys
import time

from playwright.sync_api import sync_playwright


class _HardTimeout(Exception):
    pass


def _with_hard_timeout(seconds, fn, *a, **kw):
    """Teto absoluto pro processo inteiro — nenhum timeout do Playwright
    cobre TODA ação possível (achado real: Akihabara travou >90s mesmo com
    set_default_timeout configurado). Isso garante que nunca mais trava."""
    def _raise(signum, frame):
        raise _HardTimeout(f"passou de {seconds}s")
    old = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(int(seconds))
    try:
        return fn(*a, **kw)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

HLS_PLAYER_HTML = """<!DOCTYPE html><html><body style="margin:0;background:#000">
<video id="v" autoplay muted playsinline style="width:100vw;height:100vh;object-fit:contain"></video>
<script>
  // Achado 2026-09-10: carregar hls.js com <script src> direto no HTML de
  // set_content() não disparava (fica parado em networkState=NETWORK_NO_SOURCE,
  // sem erro nenhum) — script criado via JS + onload explícito funciona.
  // Achado 2026-09-11: o Chromium do Playwright dá falso-positivo em
  // canPlayType('application/vnd.apple.mpegurl') (retorna "maybe" sem
  // decoder real) — usar sempre hls.js, nunca confiar nesse check.
  const video = document.getElementById('v');
  const src = {src!r};
  window.__snapError = null;
  const tag = document.createElement('script');
  tag.src = 'https://cdn.jsdelivr.net/npm/hls.js@1';
  tag.onload = () => {{
    if (window.Hls && window.Hls.isSupported()) {{
      const hls = new Hls();
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (_e, data) => {{ window.__snapError = JSON.stringify(data); }});
    }} else {{
      window.__snapError = 'Hls not supported';
    }}
  }};
  tag.onerror = () => {{ window.__snapError = 'failed to load hls.js'; }};
  document.head.appendChild(tag);
</script>
</body></html>"""


YT_EMBED_HTML = """<!DOCTYPE html><html><body style="margin:0;background:#000">
<iframe id="f" src="https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1&controls=0"
  style="width:100vw;height:100vh;border:0" allow="autoplay"></iframe>
</body></html>"""


def _snap_youtube_embed(video_id: str, out_path: str, wait_s: float) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 960, "height": 540})
        page.set_default_timeout(6000)
        page.set_content(YT_EMBED_HTML.format(video_id=video_id))
        time.sleep(wait_s)
        embed_blocked = False
        try:
            frame = page.frame_locator("#f")
            embed_blocked = (
                frame.locator("text=watch this video on YouTube").count() > 0
                or frame.locator("text=Assista a este vídeo no YouTube").count() > 0
                or frame.locator("text=Erro 153").count() > 0
                or frame.locator("text=Error 153").count() > 0
            )
        except Exception:
            pass
        page.screenshot(path=out_path)
        browser.close()
        return {"embed_blocked": embed_blocked}


def snap_youtube(video_id: str, out_path: str, wait_s: float = 5.0, allow_watch_fallback: bool = True) -> dict:
    # Achado 2026-09-10: navegar pra página cheia de "watch" trava de forma
    # imprevisível em vários vídeos (>90s, nenhum timeout configurado
    # explicava — provável peso de JS/anúncios/sidebar da página inteira).
    # Wrapper leve com <iframe> do /embed/ é MUITO mais rápido e confiável;
    # só cai pra "watch" (com teto absoluto de 25s via sinal) se o canal
    # bloquear embed (Erro 153) — ~50-60% dos canais de turismo bloqueiam.
    info = _with_hard_timeout(15, _snap_youtube_embed, video_id, out_path, wait_s)
    if info.get("embed_blocked") and allow_watch_fallback:
        try:
            page_info = _with_hard_timeout(
                25, snap_page, f"https://www.youtube.com/watch?v={video_id}", out_path, wait_s
            )
            info["watch_fallback"] = True
            info["title"] = page_info.get("title")
        except _HardTimeout:
            info["watch_fallback_failed"] = "timeout"
    return info


def snap_hls(src_url: str, out_path: str, wait_s: float = 8.0) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 960, "height": 540})
        page.set_default_timeout(6000)
        page.set_content(HLS_PLAYER_HTML.format(src=src_url), wait_until="domcontentloaded", timeout=15000)
        time.sleep(wait_s)
        state = page.evaluate(
            "({readyState: document.querySelector('video')?.readyState, "
            "err: window.__snapError, "
            "vw: document.querySelector('video')?.videoWidth})"
        )
        page.screenshot(path=out_path)
        browser.close()
        return {"error": state.get("err"), "videoWidth": state.get("vw")}


def snap_page(url: str, out_path: str, wait_s: float = 6.0) -> dict:
    """Navega direto pra uma página (ex: earthcam.com) — pra sites com player
    próprio (não YouTube), evita a restrição de embed."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_default_timeout(8000)
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        title = page.title()
        for label in ["Aceitar tudo", "Accept all", "Allow all", "I agree", "Aceito", "Accept", "OK"]:
            try:
                page.get_by_role("button", name=label, exact=False).first.click(timeout=2000)
                time.sleep(1.0)
                break
            except Exception:
                pass
        time.sleep(wait_s)
        try:
            video_el = page.locator("video, iframe").first
            if video_el.count() > 0:
                video_el.scroll_into_view_if_needed(timeout=3000)
                time.sleep(1.0)
        except Exception:
            pass
        page.screenshot(path=out_path)
        browser.close()
        return {"title": title}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--youtube", help="video_id do YouTube")
    parser.add_argument("--hls", help="URL do .m3u8")
    parser.add_argument("--page", help="URL de página com player próprio (ex: earthcam.com)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--wait", type=float, default=6.0)
    args = parser.parse_args()

    if args.youtube:
        info = snap_youtube(args.youtube, args.out, wait_s=args.wait)
    elif args.hls:
        info = snap_hls(args.hls, args.out, wait_s=args.wait)
    elif args.page:
        info = snap_page(args.page, args.out, wait_s=args.wait)
    else:
        print("passe --youtube, --hls ou --page", file=sys.stderr)
        sys.exit(1)

    print(f"[snap] salvo em {args.out} — {info}")
