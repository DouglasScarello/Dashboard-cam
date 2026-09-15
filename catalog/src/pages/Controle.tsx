import { useCallback, useEffect, useRef, useState } from 'react';
import { Power, Cpu, MemoryStick, Clock, AlertTriangle } from 'lucide-react';
import { BreakerSwitch } from '../components/BreakerSwitch';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL_MS = 3000;

interface PipelineStatus {
    id: string;
    label: string;
    location: string;
    service: string;
    active_state: 'active' | 'inactive' | 'activating' | 'deactivating' | 'failed' | 'unknown';
    sub_state: string;
    since: string | null;
    since_epoch: number | null;
    cpu_percent: number | null;
    memory_mb: number | null;
    last_log_line: string | null;
}

function fmtUptime(sinceEpoch: number | null): string {
    if (!sinceEpoch) return '—';
    const seconds = Math.max(0, Math.floor(Date.now() / 1000 - sinceEpoch));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

const STATE_META: Record<string, { label: string; dot: string; text: string }> = {
    active: { label: 'LIGADO', dot: 'bg-accent-emerald animate-pulse', text: 'text-accent-emerald' },
    inactive: { label: 'DESLIGADO', dot: 'bg-neutral-600', text: 'text-muted' },
    activating: { label: 'LIGANDO…', dot: 'bg-accent-amber animate-pulse', text: 'text-accent-amber' },
    deactivating: { label: 'DESLIGANDO…', dot: 'bg-accent-amber animate-pulse', text: 'text-accent-amber' },
    failed: { label: 'FALHOU', dot: 'bg-red-500 animate-pulse', text: 'text-red-500' },
    unknown: { label: 'DESCONHECIDO', dot: 'bg-neutral-600', text: 'text-muted' },
};

export default function Controle() {
    const [pipelines, setPipelines] = useState<PipelineStatus[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
    const mounted = useRef(true);

    const fetchStatus = useCallback(() => {
        fetch(`${API_BASE}/api/pipelines`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: PipelineStatus[]) => {
                if (!mounted.current) return;
                setPipelines(data);
                setError(null);
                setLoading(false);
                // Uma vez que o backend confirma o novo estado, some com o
                // spinner de "pendente" — nunca fingimos que já ligou antes
                // do systemd confirmar de verdade.
                setPendingIds(prev => {
                    const next = new Set(prev);
                    for (const p of data) {
                        if (p.active_state === 'active' || p.active_state === 'inactive' || p.active_state === 'failed') {
                            next.delete(p.id);
                        }
                    }
                    return next;
                });
            })
            .catch(err => {
                if (!mounted.current) return;
                setError(String(err));
                setLoading(false);
            });
    }, []);

    useEffect(() => {
        mounted.current = true;
        fetchStatus();
        const interval = setInterval(fetchStatus, POLL_INTERVAL_MS);
        return () => { mounted.current = false; clearInterval(interval); };
    }, [fetchStatus]);

    const handleToggle = useCallback((pipeline: PipelineStatus) => {
        const turningOn = pipeline.active_state !== 'active';
        setPendingIds(prev => new Set(prev).add(pipeline.id));
        fetch(`${API_BASE}/api/pipelines/${pipeline.id}/${turningOn ? 'start' : 'stop'}`, { method: 'POST' })
            .then(res => res.json())
            .then(() => fetchStatus())
            .catch(() => {
                setPendingIds(prev => {
                    const next = new Set(prev);
                    next.delete(pipeline.id);
                    return next;
                });
            });
    }, [fetchStatus]);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="mb-6 pb-4 border-b border-white/5">
                <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                    <Power className="w-4 h-4 text-accent-emerald" /> CONTROLE DE PIPELINES
                </h2>
                <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                    LIGAR/DESLIGAR MANUALMENTE — NÃO RODAM MAIS 24/7 SOZINHOS POR PADRÃO
                </p>
                <p className="text-xs text-white/50 mt-2 max-w-2xl">
                    A calibração de reconhecimento facial e leitura de placa ainda está sendo ajustada, e os dois
                    juntos competem por CPU/RAM com o resto da máquina. Ligue só quando for observar/testar.
                </p>
            </div>

            {error && (
                <div className="bg-red-500/20 text-red-500 px-4 py-3 rounded-lg border border-red-500/30 text-sm font-mono mb-6 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0" /> Erro ao carregar pipelines: {error}
                </div>
            )}

            {loading ? (
                <div className="h-40 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                </div>
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {pipelines.map(p => {
                        const pending = pendingIds.has(p.id);
                        const meta = STATE_META[p.active_state] || STATE_META.unknown;
                        const isOn = p.active_state === 'active';
                        return (
                            <div key={p.id} className="intelligence-card p-5 flex flex-col gap-4">
                                <div className="flex items-start justify-between gap-4">
                                    <div>
                                        <h3 className="text-sm font-black text-white uppercase tracking-wide">{p.label}</h3>
                                        <p className="text-[10px] text-muted font-mono uppercase tracking-wider mt-0.5">{p.location}</p>
                                    </div>
                                    <BreakerSwitch
                                        isOn={isOn}
                                        pending={pending}
                                        onToggle={() => handleToggle(p)}
                                        label={`${isOn ? 'Desligar' : 'Ligar'} ${p.label}`}
                                    />
                                </div>

                                <div className="flex items-center gap-2">
                                    <span className={`w-2 h-2 rounded-full ${pending ? 'bg-accent-amber animate-pulse' : meta.dot}`} />
                                    <span className={`text-[10px] font-black tracking-widest uppercase ${pending ? 'text-accent-amber' : meta.text}`}>
                                        {pending ? (isOn ? 'DESLIGANDO…' : 'LIGANDO…') : meta.label}
                                    </span>
                                </div>

                                {isOn && !pending && (
                                    <div className="flex items-center gap-4 text-[11px] font-mono text-white/70">
                                        <span className="flex items-center gap-1.5">
                                            <Clock className="w-3 h-3 text-accent-blue" /> {fmtUptime(p.since_epoch)}
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <Cpu className="w-3 h-3 text-accent-amber" /> {p.cpu_percent != null ? `${p.cpu_percent.toFixed(0)}%` : 'N/D'}
                                        </span>
                                        <span className="flex items-center gap-1.5">
                                            <MemoryStick className="w-3 h-3 text-accent-emerald" /> {p.memory_mb != null ? `${p.memory_mb.toFixed(0)} MB` : 'N/D'}
                                        </span>
                                    </div>
                                )}

                                <div className="bg-black/40 border border-white/5 rounded-lg px-3 py-2 overflow-hidden">
                                    <p className="text-[10px] font-mono text-white/40 truncate">
                                        {p.last_log_line || 'sem atividade registrada ainda'}
                                    </p>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </main>
    );
}
