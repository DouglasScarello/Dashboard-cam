import { useEffect, useState } from 'react';
import { Activity, Fingerprint, Car, ShieldAlert, Radio, Server } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

interface Status {
    status: string;
    timestamp: string;
    redis: { connected?: boolean } | Record<string, unknown>;
    subscribers: number;
    version: string;
}

interface CatalogStats {
    total: number;
    wanted: number;
    missing: number;
    with_biometrics: number;
}

interface MatchRecent {
    individual_id?: string;
    name?: string;
    category?: string;
    camera_id?: string;
    captured_at?: string;
    evidence_url?: string | null;
    ref_photo_url?: string | null;
}

interface PlateRecent {
    plate_text: string;
    camera_id: string;
    vehicle_color?: string | null;
    vehicle_type?: string | null;
    confidence?: number | null;
    created_at: string;
    evidence_url?: string | null;
}

function fmtTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    try {
        return new Date(iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('pt-BR');
    } catch {
        return iso;
    }
}

function StatCard({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: string | number; accent: string }) {
    return (
        <div className="intelligence-card p-5 flex items-center gap-4">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${accent}`}>
                {icon}
            </div>
            <div>
                <p className="text-2xl font-black font-mono text-white leading-none">{value}</p>
                <p className="text-[10px] text-muted tracking-widest uppercase mt-1">{label}</p>
            </div>
        </div>
    );
}

export default function Painel() {
    const [status, setStatus] = useState<Status | null>(null);
    const [catalogStats, setCatalogStats] = useState<CatalogStats | null>(null);
    const [personCount, setPersonCount] = useState<number | null>(null);
    const [vehicleCount, setVehicleCount] = useState<number | null>(null);
    const [matches, setMatches] = useState<MatchRecent[]>([]);
    const [plates, setPlates] = useState<PlateRecent[]>([]);

    useEffect(() => {
        const load = () => {
            fetch(`${API_BASE}/status`).then(r => r.json()).then(setStatus).catch(() => {});
            fetch(`${API_BASE}/api/catalog/stats`).then(r => r.json()).then(setCatalogStats).catch(() => {});
            fetch(`${API_BASE}/api/persons?limit=1000`).then(r => r.json()).then(d => setPersonCount(Array.isArray(d) ? d.length : 0)).catch(() => {});
            fetch(`${API_BASE}/api/vehicles?limit=1000`).then(r => r.json()).then(d => setVehicleCount(Array.isArray(d) ? d.length : 0)).catch(() => {});
            fetch(`${API_BASE}/matches/recent?limit=8`).then(r => r.json()).then(d => setMatches(Array.isArray(d) ? d : [])).catch(() => {});
            fetch(`${API_BASE}/plates/recent?limit=8`).then(r => r.json()).then(d => setPlates(Array.isArray(d) ? d : [])).catch(() => {});
        };
        load();
        const interval = setInterval(load, 10000);
        return () => clearInterval(interval);
    }, []);

    const redisConnected = status && typeof status.redis === 'object' && (status.redis as any).connected;

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="mb-6 pb-4 border-b border-white/5">
                <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                    <Activity className="w-4 h-4 text-accent-emerald" /> PAINEL GERAL
                </h2>
                <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                    STATUS DO SISTEMA E ATIVIDADE RECENTE
                </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
                <StatCard
                    icon={<Server className="w-5 h-5 text-black" />}
                    label={status?.status === 'ONLINE' ? 'Sistema Online' : 'Verificando…'}
                    value={status?.version?.split('-')[0] ?? '—'}
                    accent="bg-accent-emerald"
                />
                <StatCard
                    icon={<Radio className="w-5 h-5 text-black" />}
                    label="Assinantes SSE (/events)"
                    value={status?.subscribers ?? '—'}
                    accent="bg-accent-blue"
                />
                <StatCard
                    icon={<ShieldAlert className="w-5 h-5 text-black" />}
                    label="Procurados/Desaparecidos (FBI)"
                    value={catalogStats?.total ?? '—'}
                    accent="bg-red-500"
                />
                <StatCard
                    icon={<Fingerprint className="w-5 h-5 text-black" />}
                    label="Pessoas Anônimas Catalogadas"
                    value={personCount ?? '—'}
                    accent="bg-accent-amber"
                />
                <StatCard
                    icon={<Car className="w-5 h-5 text-black" />}
                    label="Veículos Catalogados"
                    value={vehicleCount ?? '—'}
                    accent="bg-white/20"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <section>
                    <h4 className="text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                        MATCHES FACIAIS RECENTES
                    </h4>
                    <div className="space-y-2">
                        {matches.length === 0 ? (
                            <p className="text-muted italic text-sm">Nenhum match ainda — bom sinal se ninguém do banco passou nas câmeras.</p>
                        ) : matches.map((m, i) => (
                            <div key={i} className="intelligence-card p-3 flex items-center gap-3">
                                {m.evidence_url && <img src={`${API_BASE}${m.evidence_url}`} className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                {m.ref_photo_url && <img src={`${API_BASE}${m.ref_photo_url}`} className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                <div className="text-xs">
                                    <p className="font-black text-red-400 uppercase">{m.name || m.individual_id}</p>
                                    <p className="text-muted font-mono">{m.category || ''} · câmera {m.camera_id || '?'} · {fmtTime(m.captured_at)}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                <section>
                    <h4 className="text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                        LEITURAS DE PLACA RECENTES
                    </h4>
                    <div className="space-y-2">
                        {plates.length === 0 ? (
                            <p className="text-muted italic text-sm">Nenhuma leitura ainda.</p>
                        ) : plates.map((p, i) => (
                            <div key={i} className="intelligence-card p-3 flex items-center gap-3">
                                {p.evidence_url && <img src={`${API_BASE}${p.evidence_url}`} className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                <div className="text-xs">
                                    <p className="font-black text-accent-amber font-mono">{p.plate_text}</p>
                                    <p className="text-muted font-mono">{p.vehicle_color || '?'} {p.vehicle_type || ''} · câmera {p.camera_id} · {fmtTime(p.created_at)}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </main>
    );
}
