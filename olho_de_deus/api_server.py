import asyncio
import json
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn
import os
import sys
from pathlib import Path

# Adicionar o diretório 'intelligence' ao sys.path (Fase 32-Fix)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "intelligence"))

from intelligence_db import DB, get_recent_matches
from redis_cache import RedisCache

app = FastAPI(title="Olho de Deus — Tactical API", version="32.0.0")

# Habilitar CORS para o dashboard web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fila global para SSE (Server-Sent Events)
event_queue = asyncio.Queue()

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
        "version": "32.0.0-Adaptive"
    }

@app.get("/matches/recent")
async def matches_recent(limit: int = 10):
    """Retorna os matches mais recentes do banco de dados."""
    db = DB()
    try:
        matches = get_recent_matches(db, limit=limit)
        return matches
    finally:
        db.close()

@app.get("/events")
async def event_stream(request: Request):
    """Stream de eventos em tempo real (SSE) para o dashboard."""
    async def event_generator():
        while True:
            # Se o cliente desconectar, encerra o generator
            if await request.is_disconnected():
                break
            
            try:
                # Aguarda novo evento na fila com timeout
                event_data = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield {
                    "event": "match",
                    "data": json.dumps(event_data)
                }
            except asyncio.TimeoutError:
                # Keep-alive
                yield {
                    "event": "ping",
                    "data": "keep-alive"
                }

    return EventSourceResponse(event_generator())

# Hook para o live_pipeline.py publicar eventos (legado/direto)
def publish_match_event(match_data: dict):
    """Publica um match na fila SSE de forma não-bloqueante."""
    asyncio.run_coroutine_threadsafe(event_queue.put(match_data), asyncio.get_event_loop())

async def redis_event_listener():
    """Listener em background que consome do Redis Pub/Sub e alimenta a fila SSE."""
    cache = RedisCache()
    pubsub = cache.get_pubsub()
    if not pubsub:
        print("[API] ⚠️ Redis Pub/Sub indisponível. SSE operará apenas via chamadas diretas.")
        return

    pubsub.subscribe("tactical_alerts")
    print("[API] 📡 Inscrito no canal 'tactical_alerts' do Redis.")
    
    while True:
        try:
            # message: {'type': 'message', 'pattern': None, 'channel': '...', 'data': '...'}
            message = pubsub.get_message(ignore_subscribe_init=True, timeout=1.0)
            if message and message['type'] == 'message':
                data = json.loads(message['data'])
                await event_queue.put(data)
        except Exception as e:
            await asyncio.sleep(1)
            continue
        await asyncio.sleep(0.01)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_event_listener())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
