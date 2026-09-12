import asyncio
import json
import time
from datetime import datetime
from typing import List, Optional


from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
import uvicorn
import os
import sys
from pathlib import Path

# Adicionar o diretório 'intelligence' ao sys.path (Fase 32-Fix)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from intelligence_db import (
    DB, get_recent_matches, get_recent_plate_reads,
    get_recurring_vehicles, get_vehicle_history, get_all_vehicles,
    get_recurring_persons, get_person_history, get_all_persons,
)
from redis_cache import RedisCache
from forensic_core import build_official_forensic_laudo, BayesianSLREngine, CNJLineupEngine
from tactical_dispatch import LAPJVDispatchEngine, TacticalContainmentEngine, TacticalUnit, TacticalIncident
from graph_engine import TacticalGraphEngine
from spatial_engine import global_spatial_index, CrossCameraHandoverEngine
from streaming_cluster import global_cluster_manager
from forensic_sr_engine import forensic_sr_router

# Instância global do motor de grafos
global_graph_engine = TacticalGraphEngine()

app = FastAPI(title="Olho de Deus — Tactical C4ISR API (10k Scale)", version="35.0.0")
app.include_router(forensic_sr_router)

# Habilitar CORS para o dashboard web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2026-09-11: nunca existia serving estático nenhum pra essas pastas — o payload
# de alerta já montava "evidence_url": f"/evidence/{filename}" há tempos, mas
# a rota nunca foi criada (só funcionava dentro do app Tauri via comando Rust
# get_image_base64, não no navegador puro). Monta as duas pastas que o
# live_pipeline.py escreve pra dar pra ver a IA rodando de verdade no browser.
_EVIDENCE_DIR = ROOT / "intelligence" / "evidence"
_EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=str(_EVIDENCE_DIR)), name="evidence")


def evidence_url(path: Optional[str]) -> Optional[str]:
    """Converte um caminho absoluto de evidência pra URL servível — usa o
    caminho RELATIVO a _EVIDENCE_DIR (não só o nome do arquivo), porque
    evidência de pessoa anônima fica numa subpasta (evidence/anonimos/...),
    e os.path.basename sozinho perderia esse prefixo e quebraria a URL."""
    if not path:
        return None
    try:
        rel = os.path.relpath(path, _EVIDENCE_DIR)
        if rel.startswith(".."):
            return f"/evidence/{os.path.basename(path)}"  # fora de _EVIDENCE_DIR, fallback simples
        return f"/evidence/{rel}"
    except Exception:
        return f"/evidence/{os.path.basename(path)}"

_LIVEVIEW_DIR = ROOT / "olho_de_deus" / "live_view"
_LIVEVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/live-frames", StaticFiles(directory=str(_LIVEVIEW_DIR)), name="live-frames")

# individuals.img_path/individual_images.img_path são relativos a intelligence/data/
# (ver populate_db.py) — monta pra dar pra comparar a foto de referência do FBI
# lado a lado com a evidência capturada ao vivo, sem depender do Tauri.
_INTEL_DATA_DIR = ROOT / "intelligence" / "data"
if _INTEL_DATA_DIR.exists():
    app.mount("/ref-data", StaticFiles(directory=str(_INTEL_DATA_DIR)), name="ref-data")

@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {"status": "HEALTHY", "c4isr_version": "34.0.0", "timestamp": datetime.utcnow().isoformat()}

class ConnectionManager:
    """Gerenciador Fan-Out para distribuição de eventos SSE a múltiplos clientes."""
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        async with self._lock:
            self.subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue):
        async with self._lock:
            self.subscribers.discard(q)

    async def broadcast(self, event_data: dict):
        async with self._lock:
            subs = list(self.subscribers)
        for q in subs:
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                pass


manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve o dashboard tático visual."""
    path = os.path.join(os.path.dirname(__file__), "monitoring.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Dashboard não encontrado</h1>"

@app.get("/status")
async def get_status():
    """Retorna o status geral do sistema e do cache."""
    cache = RedisCache()
    return {
        "status": "ONLINE",
        "timestamp": datetime.now().isoformat(),
        "redis": cache.health(),
        "subscribers": len(manager.subscribers),
        "version": "34.0.0-C4ISR-Hardened"
    }

@app.get("/matches/recent")
async def matches_recent(limit: int = 10):
    """Retorna os matches mais recentes do banco de dados."""
    db = DB()
    try:
        matches = get_recent_matches(db, limit=limit)
        for m in matches:
            fp = m.get("file_path")
            m["evidence_url"] = f"/evidence/{os.path.basename(fp)}" if fp else None
            m["ref_photo_url"] = f"/ref-data/{m['img_path']}" if m.get("img_path") else None
        return matches
    except Exception as e:
        return {"error": str(e), "matches": []}
    finally:
        db.close()


@app.get("/live-ai", response_class=HTMLResponse)
async def live_ai_view(camera: str = "globetv_soi11_bangkok"):
    """Página standalone (sem build, sem React) pra ver a IA rodando de verdade
    numa câmera: frame anotado (YOLO + ArcFace) atualizado por polling de imagem,
    mais a lista de matches confirmados com foto da câmera lado a lado com a
    foto de referência do banco — pra julgar visualmente, não só confiar no score.
    Criada em 2026-09-11 a pedido do usuário pra comprovar visualmente o
    reconhecimento funcionando, sem depender do app Tauri nem de WebRTC/go2rtc."""
    return f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Olho de Deus — IA ao vivo</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0a0e14; color:#d7e0ea; font-family:'Consolas','Menlo',monospace; }}
  header {{ padding:10px 16px; border-bottom:1px solid #1c2531; display:flex; align-items:center; gap:12px; }}
  header h1 {{ font-size:14px; letter-spacing:.05em; margin:0; color:#7fd8ff; text-transform:uppercase; }}
  .dot {{ width:10px; height:10px; border-radius:50%; background:#3a4656; }}
  .dot.live {{ background:#2ecc71; box-shadow:0 0 8px #2ecc71; }}
  .dot.stale {{ background:#e74c3c; box-shadow:0 0 8px #e74c3c; }}
  main {{ display:flex; gap:16px; padding:16px; flex-wrap:wrap; }}
  .video-col {{ flex:2; min-width:420px; }}
  .video-col img {{ width:100%; border:1px solid #1c2531; border-radius:6px; background:#000; display:block; }}
  .feed-col {{ flex:1; min-width:320px; max-height:80vh; overflow-y:auto; }}
  .feed-col h2 {{ font-size:12px; text-transform:uppercase; color:#8aa0b8; letter-spacing:.08em; }}
  .card {{ display:flex; gap:8px; background:#111826; border:1px solid #1c2531; border-radius:6px; padding:8px; margin-bottom:8px; align-items:center; }}
  .card img {{ width:56px; height:56px; object-fit:cover; border-radius:4px; background:#000; }}
  .card .meta {{ font-size:11px; line-height:1.4; }}
  .card .name {{ color:#ff6b6b; font-weight:bold; }}
  .empty {{ color:#4a5b70; font-size:12px; padding:8px 0; }}
  .badge {{ font-size:10px; padding:1px 6px; border-radius:3px; background:#1c2531; color:#8aa0b8; }}
</style></head>
<body>
<header>
  <div class="dot" id="dot"></div>
  <h1>Olho de Deus — reconhecimento ao vivo</h1>
  <span class="badge" id="cam">{camera}</span>
</header>
<main>
  <div class="video-col">
    <img id="frame" alt="aguardando frame...">
    <p class="empty" id="frameinfo">conectando...</p>
  </div>
  <div class="feed-col">
    <h2>Matches confirmados (câmera vs. banco)</h2>
    <div id="feed"><p class="empty">nenhum match ainda — bom sinal se ninguém do banco passou na câmera.</p></div>
  </div>
</main>
<script>
const CAM = {camera!r};
const img = document.getElementById('frame');
const dot = document.getElementById('dot');
const frameinfo = document.getElementById('frameinfo');
const feed = document.getElementById('feed');

function refreshFrame() {{
  const probe = new Image();
  const url = `/live-frames/${{CAM}}.jpg?t=${{Date.now()}}`;
  probe.onload = () => {{ img.src = url; dot.className = 'dot live'; frameinfo.textContent = 'ao vivo — ' + new Date().toLocaleTimeString('pt-BR'); }};
  probe.onerror = () => {{ dot.className = 'dot stale'; frameinfo.textContent = 'sem frame ainda (pipeline rodando? veja o terminal)'; }};
  probe.src = url;
}}
setInterval(refreshFrame, 700);
refreshFrame();

let lastIds = new Set();
async function refreshMatches() {{
  try {{
    const res = await fetch('/matches/recent?limit=15');
    const matches = await res.json();
    if (!Array.isArray(matches) || matches.length === 0) return;
    feed.innerHTML = '';
    for (const m of matches) {{
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <img src="${{m.evidence_url || ''}}" title="foto da câmera">
        <img src="${{m.ref_photo_url || ''}}" title="referência do banco">
        <div class="meta">
          <div class="name">${{m.name || m.individual_id}}</div>
          <div>${{m.category || ''}} · câmera ${{m.camera_id || '?'}}</div>
          <div>${{m.captured_at || ''}}</div>
        </div>`;
      feed.appendChild(card);
    }}
  }} catch (e) {{ /* silencioso — só tenta de novo no próximo tick */ }}
}}
setInterval(refreshMatches, 2000);
refreshMatches();
</script>
</body></html>"""


@app.get("/plates/recent")
async def plates_recent(limit: int = 20):
    """Leituras de placa mais recentes (consenso multi-frame, monitor_plates.py)."""
    db = DB()
    try:
        reads = get_recent_plate_reads(db, limit=limit)
        for r in reads:
            r["evidence_url"] = evidence_url(r.get("evidence_path"))
        return reads
    except Exception as e:
        return {"error": str(e), "reads": []}
    finally:
        db.close()


@app.get("/api/vehicles")
async def api_vehicles(limit: int = 200, recurring_only: bool = False):
    """Galeria de cards de veículo — cada um com código próprio (V-000001),
    cor/carroceria (CLIP) e quantas vezes já visto. Base da aba de veículos
    na interface (2026-09-12)."""
    db = DB()
    try:
        rows = get_recurring_vehicles(db, limit=limit) if recurring_only else get_all_vehicles(db, limit=limit)
        return rows
    except Exception as e:
        return {"error": str(e), "vehicles": []}
    finally:
        db.close()


@app.get("/api/vehicles/{vehicle_id}")
async def api_vehicle_detail(vehicle_id: int):
    """Ficha de um veículo: dados + linha do tempo completa de onde/quando
    apareceu (get_vehicle_history), com URL de evidência de cada leitura."""
    db = DB()
    try:
        row = db.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Veículo não encontrado")
        vehicle = dict(row)
        history = get_vehicle_history(db, vehicle_id)
        for h in history:
            h["evidence_url"] = evidence_url(h.get("evidence_path"))
        vehicle["history"] = history
        return vehicle
    finally:
        db.close()


@app.get("/api/persons")
async def api_persons(limit: int = 200, recurring_only: bool = False):
    """Galeria de cards de pessoa anônima — código próprio (P-000001),
    NUNCA nome real. Base da aba de pessoas na interface (2026-09-12)."""
    db = DB()
    try:
        rows = get_recurring_persons(db, limit=limit) if recurring_only else get_all_persons(db, limit=limit)
        for r in rows:
            r.pop("reference_embedding", None)  # binário, não serializa bem em JSON e não serve pro front
        return rows
    except Exception as e:
        return {"error": str(e), "persons": []}
    finally:
        db.close()


@app.get("/api/persons/{person_id}")
async def api_person_detail(person_id: int):
    """Ficha de uma pessoa anônima: código + linha do tempo completa de
    onde/quando apareceu, com foto de evidência de cada passagem — o
    'relatório ao vivo de lugares e câmeras' pedido pelo usuário."""
    db = DB()
    try:
        row = db.execute("SELECT * FROM anonymous_persons WHERE id = ?", (person_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pessoa não encontrada")
        person = dict(row)
        person.pop("reference_embedding", None)
        history = get_person_history(db, person_id)
        for h in history:
            h["evidence_url"] = evidence_url(h.get("evidence_path"))
        person["history"] = history
        return person
    finally:
        db.close()


@app.get("/live-plates", response_class=HTMLResponse)
async def live_plates_view(camera: str = "globetv_davao_leongarcia"):
    """Irmã da /live-ai, mas pro lado de placa (monitor_plates.py) — mostra o
    frame anotado (YOLO + votação de OCR por consenso) e a lista de placas já
    fechadas (consenso atingido), com a foto da câmera como evidência. Criada
    em 2026-09-11 junto com o pipeline de leitura de placa ao vivo."""
    return f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Olho de Deus — Placas ao vivo</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0a0e14; color:#d7e0ea; font-family:'Consolas','Menlo',monospace; }}
  header {{ padding:10px 16px; border-bottom:1px solid #1c2531; display:flex; align-items:center; gap:12px; }}
  header h1 {{ font-size:14px; letter-spacing:.05em; margin:0; color:#7fd8ff; text-transform:uppercase; }}
  .dot {{ width:10px; height:10px; border-radius:50%; background:#3a4656; }}
  .dot.live {{ background:#2ecc71; box-shadow:0 0 8px #2ecc71; }}
  .dot.stale {{ background:#e74c3c; box-shadow:0 0 8px #e74c3c; }}
  main {{ display:flex; gap:16px; padding:16px; flex-wrap:wrap; }}
  .video-col {{ flex:2; min-width:420px; }}
  .video-col img {{ width:100%; border:1px solid #1c2531; border-radius:6px; background:#000; display:block; }}
  .feed-col {{ flex:1; min-width:320px; max-height:80vh; overflow-y:auto; }}
  .feed-col h2 {{ font-size:12px; text-transform:uppercase; color:#8aa0b8; letter-spacing:.08em; }}
  .card {{ display:flex; gap:8px; background:#111826; border:1px solid #1c2531; border-radius:6px; padding:8px; margin-bottom:8px; align-items:center; }}
  .card img {{ width:72px; height:56px; object-fit:cover; border-radius:4px; background:#000; }}
  .card .meta {{ font-size:11px; line-height:1.4; }}
  .card .plate {{ color:#7fffd4; font-weight:bold; font-size:16px; letter-spacing:.05em; }}
  .empty {{ color:#4a5b70; font-size:12px; padding:8px 0; }}
  .badge {{ font-size:10px; padding:1px 6px; border-radius:3px; background:#1c2531; color:#8aa0b8; }}
</style></head>
<body>
<header>
  <div class="dot" id="dot"></div>
  <h1>Olho de Deus — leitura de placa ao vivo</h1>
  <span class="badge" id="cam">{camera}</span>
</header>
<main>
  <div class="video-col">
    <img id="frame" alt="aguardando frame...">
    <p class="empty" id="frameinfo">conectando...</p>
  </div>
  <div class="feed-col">
    <h2>Placas confirmadas (consenso de vários frames)</h2>
    <div id="feed"><p class="empty">nenhuma placa fechada ainda — cada uma exige várias leituras concordando.</p></div>
  </div>
</main>
<script>
const CAM = {camera!r};
const img = document.getElementById('frame');
const dot = document.getElementById('dot');
const frameinfo = document.getElementById('frameinfo');
const feed = document.getElementById('feed');

function refreshFrame() {{
  const probe = new Image();
  const url = `/live-frames/${{CAM}}_plates.jpg?t=${{Date.now()}}`;
  probe.onload = () => {{ img.src = url; dot.className = 'dot live'; frameinfo.textContent = 'ao vivo — ' + new Date().toLocaleTimeString('pt-BR'); }};
  probe.onerror = () => {{ dot.className = 'dot stale'; frameinfo.textContent = 'sem frame ainda (pipeline rodando? veja o terminal)'; }};
  probe.src = url;
}}
setInterval(refreshFrame, 700);
refreshFrame();

async function refreshReads() {{
  try {{
    const res = await fetch('/plates/recent?limit=15');
    const reads = await res.json();
    if (!Array.isArray(reads) || reads.length === 0) return;
    feed.innerHTML = '';
    for (const r of reads) {{
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <img src="${{r.evidence_url || ''}}" title="foto da câmera">
        <div class="meta">
          <div class="plate">${{r.plate_text}}</div>
          <div>${{r.country_code || '?'}} · formato ${{r.plate_format || 'INCERTO'}} · confiança ${{Math.round((r.confidence||0)*100)}}%</div>
          <div>${{r.frames_voted}} frames votados · câmera ${{r.camera_id || '?'}}</div>
          <div>${{r.created_at || ''}}</div>
        </div>`;
      feed.appendChild(card);
    }}
  }} catch (e) {{ /* silencioso — só tenta de novo no próximo tick */ }}
}}
setInterval(refreshReads, 2000);
refreshReads();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS PERICIAIS FORENSES (DIVISÃO 09 & CNJ 484)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/forensics/generate-laudo/{target_id}")
async def generate_forensic_laudo(target_id: str):
    """Gera laudo pericial oficial em PDF/A-1b assinado digitalmente com PAdES-LTA."""
    db = DB()
    try:
        cur = db.execute("SELECT * FROM individuals WHERE id = ?", (target_id,))
        row = cur.fetchone()
        if not row:
            dossier = {"id": target_id, "name": f"SUSPEITO-{target_id}", "match_score": 0.85, "source": "BNMP 3.0"}
        else:
            dossier = dict(row)
            dossier["match_score"] = 0.88
            
        out_dir = os.path.join(str(ROOT), "pesquisa", "laudos")
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"LAUDO_PERICIAL_{target_id}_{int(time.time())}.pdf")
        
        generated_path = build_official_forensic_laudo(dossier, pdf_path)
        manifest_path = generated_path.replace(".pdf", "_manifest_audit.json")

        # Ler de volta o status REAL da assinatura gravado pelo próprio
        # forensic_core.py — nunca reafirmar "certified: True" aqui de forma
        # fixa (esse exato bug já existiu tanto aqui quanto no manifesto).
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        return {
            "status": "SUCCESS",
            "target_id": target_id,
            "laudo_pdf_path": generated_path,
            "manifest_audit_path": manifest_path,
            "pades_lta_signed": manifest.get("pades_lta_signed", False),
            "pades_signing_error": manifest.get("pades_signing_error"),
            "icp_brasil_accredited": manifest.get("icp_brasil_accredited", False),
            "tsa_used": manifest.get("tsa_used"),
            "cnj_484_lineup_generated": manifest.get("cnj_484_lineup_generated", False),
            "created_at_utc": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS DE DESPACHO TÁTICO & CERCO VIÁRIO LAPJV (DIVISÃO 04)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/tactical/dispatch-containment")
async def dispatch_containment(lat: float = -23.55052, lon: float = -46.63330, threat_level: int = 4):
    """Calcula a alocação de viaturas LAPJV, Isócronas de fuga e cerco em pinça."""
    # Frota ativa simulada
    fleet = [
        TacticalUnit("V-101", "ROTA-TATICO-01", lat + 0.008, lon + 0.005, armor_level=4, tactical_specialty="TÁTICO"),
        TacticalUnit("V-102", "PATRULHA-LESTE-04", lat - 0.006, lon - 0.008, armor_level=3, tactical_specialty="PATRULHA"),
        TacticalUnit("V-103", "CHOQUE-BLINDADO-09", lat + 0.012, lon - 0.004, armor_level=5, tactical_specialty="BLINDADO")
    ]
    incident = TacticalIncident(
        incident_id=f"INC-{int(time.time())}",
        target_name="FORAGIDO DETECTADO EM CFTV",
        lat=lat,
        lon=lon,
        threat_level=threat_level,
        is_armed=True
    )
    
    dispatch_plan = LAPJVDispatchEngine.dispatch_optimal(fleet, [incident])
    isochrones = TacticalContainmentEngine.generate_escape_isochrones(lat, lon)
    pincer = TacticalContainmentEngine.compute_chokepoints_and_pincer(lat, lon, fleet)
    cot_xml = TacticalContainmentEngine.export_cursor_on_target_xml(incident)
    
    return {
        "status": "DISPATCH_ENGAGED",
        "incident_id": incident.incident_id,
        "dispatch_assignments": dispatch_plan,
        "isochrones": isochrones,
        "containment_pincer": pincer,
        "cursor_on_target_cot": cot_xml
    }

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS DE GRAFOS DE VÍNCULOS & CO-OCORRÊNCIA H3 (DIVISÃO 03)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/tactical/graph/{target_id}")
async def get_target_graph(target_id: str):
    """Retorna o subgrafo de comparsas e co-ocorrências do alvo."""
    subgraph = global_graph_engine.get_target_network(target_id)
    return subgraph

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS ESPACIAIS UBER H3, FRUSTUM 3D & HANDOVER (ESCALA 10K)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/tactical/spatial/nearby")
async def get_nearby_cameras(lat: float = -23.5505, lon: float = -46.6333, radius_meters: float = 2000.0):
    """Busca câmeras próximas via índice H3 com cones de visão 3D projetados no solo."""
    cams = global_spatial_index.find_cameras_in_radius(lat, lon, radius_meters=radius_meters)
    return {
        "center": {"lat": lat, "lon": lon},
        "radius_meters": radius_meters,
        "total_cameras_found": len(cams),
        "cameras": cams
    }

@app.post("/api/tactical/spatial/handover")
async def compute_camera_handover(last_camera_id: str = "1000", speed_kmh: float = 60.0):
    """Prediz as próximas câmeras de interceptação ao longo da rota provável de fuga."""
    res = CrossCameraHandoverEngine.compute_handover(
        last_sighting_cam_id=last_camera_id,
        target_embedding=None,
        target_speed_kmh=speed_kmh,
        spatial_index=global_spatial_index
    )
    return res

@app.get("/api/tactical/streaming/metrics")
async def get_streaming_cluster_metrics():
    """Retorna métricas de vazão de rede, economia ABR e status do cluster de 10k câmeras."""
    return global_cluster_manager.compute_bandwidth_metrics()

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS REST DO CATÁLOGO DE INTELIGÊNCIA (FBI, BRASIL & INTERPOL)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/catalog/stats")
async def get_catalog_stats():
    """Retorna estatísticas consolidadas do catálogo de inteligência."""
    db = DB()
    try:
        cur_total = db.execute("SELECT COUNT(*) FROM individuals")
        total = cur_total.fetchone()[0] if cur_total else 0
        
        cur_wanted = db.execute("SELECT COUNT(*) FROM individuals WHERE category='wanted'")
        wanted = cur_wanted.fetchone()[0] if cur_wanted else 0
        
        cur_missing = db.execute("SELECT COUNT(*) FROM individuals WHERE category='missing'")
        missing = cur_missing.fetchone()[0] if cur_missing else 0
        
        cur_bio = db.execute("SELECT COUNT(*) FROM individuals WHERE has_embedding=1")
        with_bio = cur_bio.fetchone()[0] if cur_bio else 0
        
        cur_src = db.execute("SELECT source, COUNT(*) as count FROM individuals GROUP BY source ORDER BY count DESC LIMIT 10")
        rows = cur_src.fetchall()
        by_source = []
        for r in rows:
            if isinstance(r, dict):
                by_source.append(r)
            else:
                by_source.append({"source": r[0], "count": r[1]})
        
        return {
            "total": total,
            "wanted": wanted,
            "missing": missing,
            "with_biometrics": with_bio,
            "by_source": by_source
        }
    except Exception as e:
        return {"error": str(e), "total": 0, "wanted": 0, "missing": 0, "with_biometrics": 0, "by_source": []}
    finally:
        db.close()

@app.get("/api/catalog/individuals")
async def get_catalog_individuals(
    name: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    crime: Optional[str] = None,
    has_embedding: Optional[bool] = None,
    source_filter: Optional[str] = None,
    page: int = 0,
    limit: int = 40
):
    """Busca paginada de indivíduos com filtros avançados."""
    db = DB()
    try:
        conds = ["1=1"]
        params = []
        if name and name.strip():
            conds.append("(i.name LIKE ? OR i.description LIKE ? OR i.aliases LIKE ?)")
            p = f"%{name.strip()}%"
            params.extend([p, p, p])
        if category and category.strip():
            conds.append("i.category = ?")
            params.append(category.strip())
        if country and country.strip():
            c = country.strip()
            if c.upper() in ("BR", "BRASIL", "BRAZIL"):
                conds.append("(i.nationalities LIKE '%BR%' OR i.nationalities LIKE '%Brasil%' OR i.nationalities LIKE '%Brazilian%' OR i.nationalities LIKE '%Brazil%')")
            elif c.upper() in ("US", "USA", "EUA"):
                conds.append("(i.nationalities LIKE '%US%' OR i.nationalities LIKE '%United States%' OR i.nationalities LIKE '%American%')")
            elif c.upper() in ("RU", "RUSSIA", "RUS"):
                conds.append("(i.nationalities LIKE '%RU%' OR i.nationalities LIKE '%Russian%' OR i.nationalities LIKE '%Russia%')")
            elif c.upper() in ("IR", "IRAN"):
                conds.append("(i.nationalities LIKE '%IR%' OR i.nationalities LIKE '%Iranian%' OR i.nationalities LIKE '%Iran%')")
            else:
                conds.append("i.nationalities LIKE ?")
                params.append(f"%{c}%")
                
        if source_filter and source_filter.strip():
            sf = source_filter.strip()
            if sf.lower() in ("brasil", "br", "mjsp", "bnmp", "pf"):
                conds.append("(i.source LIKE '%MJSP%' OR i.source LIKE '%BNMP%' OR i.source LIKE '%Federal%' OR i.nationalities LIKE '%Brasil%' OR i.nationalities LIKE '%BR%')")
            else:
                conds.append("i.source LIKE ?")
                params.append(f"%{sf}%")
                
        if has_embedding is not None and has_embedding:
            conds.append("i.has_embedding = 1")

        crime_join = ""
        if crime and crime.strip():
            conds.append("c.crime LIKE ?")
            params.append(f"%{crime.strip()}%")
            crime_join = "LEFT JOIN crimes c ON c.individual_id = i.id"

        offset = page * limit
        sql = f"""
            SELECT DISTINCT i.id, i.name, i.category, i.source, i.birth_date, i.nationalities,
                   i.description, i.reward, i.img_path, i.img_url, i.has_embedding, i.ingested_at,
                   i.image_content_type, t.score AS threat_score
            FROM individuals i {crime_join}
            LEFT JOIN threat_scores t ON t.individual_id = i.id
            WHERE {' AND '.join(conds)}
            ORDER BY
                (CASE WHEN i.reward IS NOT NULL THEN 0 ELSE 1 END),
                i.name ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cur = db.execute(sql, params)
        rows = cur.fetchall()
        results = []
        for r in rows:
            if isinstance(r, dict):
                results.append(r)
            else:
                results.append({
                    "id": r[0], "name": r[1], "category": r[2], "source": r[3],
                    "birth_date": r[4], "nationalities": r[5], "description": r[6],
                    "reward": r[7], "img_path": r[8], "img_url": r[9],
                    "has_embedding": r[10], "ingested_at": r[11],
                    "image_content_type": r[12], "threat_score": r[13]
                })
        return results
    except Exception as e:
        print(f"[API] Erro busca catálogo: {e}")
        return []
    finally:
        db.close()

@app.get("/api/catalog/export-csv")
async def export_catalog_csv():
    """Exporta base de dados em formato CSV para download."""
    import io
    import csv
    from fastapi.responses import StreamingResponse
    
    db = DB()
    try:
        cur = db.execute("SELECT id, name, category, source, birth_date, nationalities, reward, url, ingested_at FROM individuals")
        rows = cur.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Nome", "Categoria", "Fonte", "Data_Nascimento", "Nacionalidades", "Recompensa", "URL", "Data_Ingestao"])
        
        for r in rows:
            if isinstance(r, dict):
                writer.writerow([r.get("id"), r.get("name"), r.get("category"), r.get("source"), r.get("birth_date"), r.get("nationalities"), r.get("reward"), r.get("url"), r.get("ingested_at")])
            else:
                writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]])
                
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=catalogo_inteligencia_procurados.csv"}
        )
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.get("/api/catalog/individuals/{id}")
async def get_catalog_individual_detail(id: str):
    """Retorna dossiê completo de um indivíduo por ID."""
    db = DB()
    try:
        cur = db.execute(
            """SELECT id, name, category, source, birth_date, nationalities, description,
                      reward, img_path, img_url, has_embedding, aliases, sex, url, ingested_at,
                      height_cm, weight_kg, eye_color, hair_color, occupation,
                      image_content_type, ocr_text
               FROM individuals WHERE id = ?""",
            (id,)
        )
        row = cur.fetchone()
        if not row:
            return {"error": "Alvo não encontrado"}

        detail = dict(row) if isinstance(row, dict) else {
            "id": row[0], "name": row[1], "category": row[2], "source": row[3],
            "birth_date": row[4], "nationalities": row[5], "description": row[6],
            "reward": row[7], "img_path": row[8], "img_url": row[9], "has_embedding": row[10],
            "aliases": row[11], "sex": row[12], "url": row[13], "ingested_at": row[14],
            "height_cm": row[15], "weight_kg": row[16], "eye_color": row[17],
            "hair_color": row[18], "occupation": row[19],
            "image_content_type": row[20], "ocr_text": row[21]
        }

        # Score de periculosidade (calculado por score_engine.py) — antes só chegava
        # até o AlertCenter.tsx (alerta ao vivo), nunca até o dossiê estático que
        # é o que a maioria das pessoas realmente navega. armed_and_dangerous vem
        # de dentro do factors_json (ver score_engine.py:ThreatScorer).
        cur_score = db.execute(
            "SELECT score, factors_json FROM threat_scores WHERE individual_id = ?", (id,)
        )
        score_row = cur_score.fetchone()
        if score_row:
            score_val = score_row[0] if not isinstance(score_row, dict) else score_row.get("score")
            factors_raw = score_row[1] if not isinstance(score_row, dict) else score_row.get("factors_json")
            try:
                factors = json.loads(factors_raw) if factors_raw else {}
            except Exception:
                factors = {}
            detail["threat_score"] = score_val
            detail["armed_and_dangerous"] = bool(factors.get("armed_and_dangerous"))
        else:
            detail["threat_score"] = None
            detail["armed_and_dangerous"] = False

        # Crimes
        cur_crimes = db.execute("SELECT crime FROM crimes WHERE individual_id = ?", (id,))
        detail["crimes"] = [r[0] if not isinstance(r, dict) else r["crime"] for r in cur_crimes.fetchall()]

        # Locations
        cur_locs = db.execute("SELECT type, country, state, city, details FROM locations WHERE individual_id = ?", (id,))
        locs = []
        for r in cur_locs.fetchall():
            if isinstance(r, dict):
                locs.append({"loc_type": r.get("type", "unknown"), "country": r.get("country"), "state": r.get("state"), "city": r.get("city"), "details": r.get("details")})
            else:
                locs.append({"loc_type": r[0], "country": r[1], "state": r[2], "city": r[3], "details": r[4]})
        detail["locations"] = locs

        # Images — inclui image_content_type/ocr_text POR FOTO (não só a principal),
        # pedido do usuário pra saber qual foto da galeria é rosto vs tatuagem vs
        # documento sem precisar abrir cada uma manualmente.
        cur_imgs = db.execute(
            "SELECT img_url, img_path, caption, is_primary, image_content_type, ocr_text "
            "FROM individual_images WHERE individual_id = ?",
            (id,)
        )
        imgs = []
        for r in cur_imgs.fetchall():
            if isinstance(r, dict):
                imgs.append(r)
            else:
                imgs.append({
                    "img_url": r[0], "img_path": r[1], "caption": r[2], "is_primary": r[3],
                    "image_content_type": r[4], "ocr_text": r[5]
                })

        if not imgs and (detail.get("img_url") or detail.get("img_path")):
            imgs.append({
                "img_url": detail.get("img_url"), "img_path": detail.get("img_path"),
                "caption": "Foto Principal", "is_primary": 1,
                "image_content_type": detail.get("image_content_type"), "ocr_text": detail.get("ocr_text")
            })

        detail["images"] = imgs
        return detail
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.get("/events")
async def event_stream(request: Request):
    """Stream de eventos em tempo real (SSE) para o dashboard com Fan-Out."""
    queue = await manager.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield {
                        "event": "match",
                        "data": json.dumps(event_data)
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "ping",
                        "data": "keep-alive"
                    }
        finally:
            await manager.unsubscribe(queue)

    return EventSourceResponse(event_generator())

# Hook para o live_pipeline.py publicar eventos diretamente
def publish_match_event(match_data: dict):
    """Publica um match para todos os clientes SSE conectados de forma não-bloqueante."""
    try:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(manager.broadcast(match_data), loop)
    except RuntimeError:
        pass

async def redis_event_listener():
    """Listener em background não-bloqueante que consome do Redis Pub/Sub."""
    cache = RedisCache()
    pubsub = cache.get_pubsub()
    if not pubsub:
        print("[API] ⚠️ Redis Pub/Sub indisponível. SSE operará apenas via chamadas diretas.")
        return

    pubsub.subscribe("tactical_alerts")
    print("[API] 📡 Inscrito no canal 'tactical_alerts' do Redis.")
    loop = asyncio.get_running_loop()

    while True:
        try:
            message = await loop.run_in_executor(
                None, pubsub.get_message, True, 1.0
            )
            if message and message.get('type') == 'message':
                data = json.loads(message['data'])
                # Atualizar grafo em memória com a detecção
                target_id = data.get("id") or data.get("individual_id")
                if target_id:
                    global_graph_engine.add_target_node(target_id, data.get("name", "ALVO"))
                    global_graph_engine.record_sighting(target_id, data.get("lat", -23.55), data.get("lon", -46.63))
                await manager.broadcast(data)
        except Exception:
            await asyncio.sleep(1)
            continue
        await asyncio.sleep(0.01)

@app.on_event("startup")
async def startup_event():
    json_path = ROOT / "database" / "live_cameras.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                cams = json.load(f)
            for c in cams:
                cid = str(c.get("id"))
                lat = float(c.get("lat") or -23.5505)
                lon = float(c.get("long") or c.get("lon") or -46.6333)
                global_spatial_index.index_camera(cid, c.get("nome", ""), lat, lon, metadata=c)
                global_cluster_manager.register_camera(cid, c.get("nome", ""), c.get("url", ""), lat, lon)
            print(f"[API] 📍 Indexadas {len(cams)} câmeras no Spatial H3 Index e Cluster Manager.")
        except Exception as e:
            print(f"[API] ⚠️ Erro ao carregar câmeras no startup: {e}")
            
    asyncio.create_task(redis_event_listener())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

