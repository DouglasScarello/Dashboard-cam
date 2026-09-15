import { useEffect, useState } from 'react';
import { Network, Radar, Gauge, Navigation } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

interface StreamingMetrics {
    total_cameras: number;
    substream_active_cameras?: number;
    mainstream_active_cameras?: number;
    current_bandwidth_gbps?: number;
    naive_bandwidth_gbps?: number;
    bandwidth_savings_percent?: number;
    packet_rate_mpps?: number;
}

interface NearbyCamera {
    id: string;
    name: string;
    lat: number;
    lon: number;
    distance_m: number;
}

interface HandoverTarget {
    camera_id: string;
    camera_name: string;
    distance_m: number;
    predicted_eta_seconds: number;
    handover_confidence: number;
}

interface GraphNode {
    node_id: string;
    type: string;
    label: string;
    category?: string;
}

interface GraphEdge {
    source: string;
    target: string;
    weight?: number;
}

function StatCard({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="intelligence-card p-4">
            <p className="text-xl font-black font-mono text-white leading-none">{value}</p>
            <p className="text-[9px] text-muted tracking-widest uppercase mt-1.5">{label}</p>
        </div>
    );
}

export default function Tatico() {
    const [metrics, setMetrics] = useState<StreamingMetrics | null>(null);

    useEffect(() => {
        const load = () => fetch(`${API_BASE}/api/tactical/streaming/metrics`).then(r => r.json()).then(setMetrics).catch(() => {});
        load();
        const interval = setInterval(load, 15000);
        return () => clearInterval(interval);
    }, []);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="mb-6 pb-4 border-b border-white/5">
                <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                    <Network className="w-4 h-4 text-accent-emerald" /> INTELIGÊNCIA TÁTICA
                </h2>
                <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                    GRAFO DE REDE · ÍNDICE ESPACIAL H3 · HANDOVER ENTRE CÂMERAS · CLUSTER DE STREAMING
                </p>
            </div>

            <section className="mb-8">
                <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                    <Gauge className="w-3.5 h-3.5" /> MÉTRICAS DO CLUSTER DE STREAMING (10K CÂMERAS)
                </h4>
                {metrics ? (
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                        <StatCard label="Câmeras Registradas" value={metrics.total_cameras} />
                        <StatCard label="Substream Ativo" value={metrics.substream_active_cameras ?? '—'} />
                        <StatCard label="Mainstream Ativo" value={metrics.mainstream_active_cameras ?? '—'} />
                        <StatCard label="Banda Atual (Gbps)" value={metrics.current_bandwidth_gbps ?? '—'} />
                        <StatCard label="Economia vs. Ingênuo" value={metrics.bandwidth_savings_percent != null ? `${metrics.bandwidth_savings_percent}%` : '—'} />
                    </div>
                ) : (
                    <p className="text-muted italic text-sm">Carregando métricas…</p>
                )}
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <SpatialSearch />
                <HandoverSearch />
            </div>

            <div className="mt-8">
                <TargetGraph />
            </div>
        </main>
    );
}

function SpatialSearch() {
    const [lat, setLat] = useState('-23.5505');
    const [lon, setLon] = useState('-46.6333');
    const [radius, setRadius] = useState('2000');
    const [results, setResults] = useState<NearbyCamera[] | null>(null);
    const [loading, setLoading] = useState(false);

    const search = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ lat, lon, radius_meters: radius });
            const res = await fetch(`${API_BASE}/api/tactical/spatial/nearby?${params.toString()}`);
            const data = await res.json();
            setResults(data.cameras || []);
        } catch {
            setResults([]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section>
            <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                <Radar className="w-3.5 h-3.5" /> CÂMERAS PRÓXIMAS (ÍNDICE H3)
            </h4>
            <div className="flex flex-wrap gap-2 mb-4">
                <input value={lat} onChange={e => setLat(e.target.value)} placeholder="Latitude" className="w-28 h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <input value={lon} onChange={e => setLon(e.target.value)} placeholder="Longitude" className="w-28 h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <input value={radius} onChange={e => setRadius(e.target.value)} placeholder="Raio (m)" className="w-28 h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <button onClick={search} disabled={loading} className="h-9 px-4 bg-accent-emerald/20 hover:bg-accent-emerald/30 text-accent-emerald border border-accent-emerald/40 rounded-lg text-xs font-black tracking-wider uppercase transition-all disabled:opacity-50">
                    {loading ? 'Buscando…' : 'Buscar'}
                </button>
            </div>
            <div className="space-y-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
                {results === null ? (
                    <p className="text-muted italic text-sm">Informe coordenadas e busque câmeras próximas via índice geoespacial H3.</p>
                ) : results.length === 0 ? (
                    <p className="text-muted italic text-sm">Nenhuma câmera encontrada nesse raio.</p>
                ) : results.map(c => (
                    <div key={c.id} className="intelligence-card p-3 flex items-center justify-between">
                        <div className="text-xs">
                            <p className="font-black text-white">{c.name || c.id}</p>
                            <p className="text-muted font-mono">{c.lat?.toFixed(4)}, {c.lon?.toFixed(4)}</p>
                        </div>
                        <span className="text-[10px] font-mono text-accent-amber">{Math.round(c.distance_m)}m</span>
                    </div>
                ))}
            </div>
        </section>
    );
}

function HandoverSearch() {
    const [camId, setCamId] = useState('');
    const [speed, setSpeed] = useState('60');
    const [targets, setTargets] = useState<HandoverTarget[] | null>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const search = async () => {
        setLoading(true);
        setErrorMsg(null);
        try {
            const params = new URLSearchParams({ last_camera_id: camId, speed_kmh: speed });
            const res = await fetch(`${API_BASE}/api/tactical/spatial/handover?${params.toString()}`, { method: 'POST' });
            const data = await res.json();
            if (data.error) {
                setErrorMsg(data.error);
                setTargets([]);
            } else {
                setTargets(data.handover_priority_targets || []);
            }
        } catch (e) {
            setErrorMsg(String(e));
            setTargets([]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section>
            <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                <Navigation className="w-3.5 h-3.5" /> PREVISÃO DE HANDOVER (ROTA DE FUGA)
            </h4>
            <div className="flex flex-wrap gap-2 mb-4">
                <input value={camId} onChange={e => setCamId(e.target.value)} placeholder="ID da câmera de origem" className="flex-1 min-w-[160px] h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <input value={speed} onChange={e => setSpeed(e.target.value)} placeholder="Velocidade (km/h)" className="w-32 h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <button onClick={search} disabled={loading || !camId} className="h-9 px-4 bg-accent-amber/20 hover:bg-accent-amber/30 text-accent-amber border border-accent-amber/40 rounded-lg text-xs font-black tracking-wider uppercase transition-all disabled:opacity-50">
                    {loading ? 'Calculando…' : 'Prever'}
                </button>
            </div>
            {errorMsg && <p className="text-red-500 text-xs font-mono mb-2">{errorMsg}</p>}
            <div className="space-y-2 max-h-72 overflow-y-auto custom-scrollbar pr-1">
                {targets === null ? (
                    <p className="text-muted italic text-sm">Informe a câmera onde o alvo foi visto por último e a velocidade estimada, pra prever pra onde ele vai.</p>
                ) : targets.length === 0 && !errorMsg ? (
                    <p className="text-muted italic text-sm">Nenhuma câmera candidata encontrada nesse raio de interceptação.</p>
                ) : targets.map((t, i) => (
                    <div key={i} className="intelligence-card p-3 flex items-center justify-between">
                        <div className="text-xs">
                            <p className="font-black text-white">{t.camera_name || t.camera_id}</p>
                            <p className="text-muted font-mono">ETA {t.predicted_eta_seconds}s · {Math.round(t.distance_m)}m</p>
                        </div>
                        <span className="text-[10px] font-mono text-accent-emerald">{Math.round(t.handover_confidence * 100)}% confiança</span>
                    </div>
                ))}
            </div>
        </section>
    );
}

function TargetGraph() {
    const [targetId, setTargetId] = useState('');
    const [nodes, setNodes] = useState<GraphNode[] | null>(null);
    const [edges, setEdges] = useState<GraphEdge[]>([]);
    const [loading, setLoading] = useState(false);

    const search = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/tactical/graph/${encodeURIComponent(targetId)}`);
            const data = await res.json();
            setNodes(data.nodes || []);
            setEdges(data.edges || []);
        } catch {
            setNodes([]);
            setEdges([]);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section>
            <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                <Network className="w-3.5 h-3.5" /> GRAFO DE COMPARSAS E CO-OCORRÊNCIAS
            </h4>
            <p className="text-[10px] text-muted font-mono mb-3">
                Grafo em memória, populado em tempo real quando um alvo do catálogo dá match numa câmera com coordenadas — some se a API reiniciar.
            </p>
            <div className="flex flex-wrap gap-2 mb-4">
                <input value={targetId} onChange={e => setTargetId(e.target.value)} placeholder="ID do alvo (ex: id do catálogo FBI)" className="flex-1 min-w-[220px] h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50" />
                <button onClick={search} disabled={loading || !targetId} className="h-9 px-4 bg-accent-emerald/20 hover:bg-accent-emerald/30 text-accent-emerald border border-accent-emerald/40 rounded-lg text-xs font-black tracking-wider uppercase transition-all disabled:opacity-50">
                    {loading ? 'Buscando…' : 'Buscar Rede'}
                </button>
            </div>
            {nodes === null ? (
                <p className="text-muted italic text-sm">Informe um ID de alvo pra ver a rede de vínculos conhecida.</p>
            ) : nodes.length === 0 ? (
                <p className="text-muted italic text-sm">Nenhum nó encontrado pra esse alvo (grafo vazio ou alvo nunca deu match com coordenadas).</p>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {nodes.map(n => (
                        <div key={n.node_id} className="intelligence-card p-3">
                            <p className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-accent-amber uppercase inline-block mb-1.5">{n.type}</p>
                            <p className="text-xs font-black text-white">{n.label}</p>
                            <p className="text-[10px] text-muted font-mono mt-1">{edges.filter(e => e.source === n.node_id || e.target === n.node_id).length} vínculo(s)</p>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}
