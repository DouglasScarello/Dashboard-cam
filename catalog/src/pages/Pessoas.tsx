import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Fingerprint, X, MapPin, Clock } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const API_BASE = 'http://localhost:8000';

interface PersonRow {
    id: number;
    code: string;
    first_seen_at: string;
    last_seen_at: string;
    times_seen: number;
    cameras_seen: string | null;
}

interface Sighting {
    id: number;
    camera_id: string;
    distance: number;
    evidence_path: string | null;
    evidence_url: string | null;
    created_at: string;
}

interface PersonDetail extends PersonRow {
    history: Sighting[];
}

function fmtTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    try {
        return new Date(iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('pt-BR');
    } catch {
        return iso;
    }
}

export default function Pessoas() {
    const [rows, setRows] = useState<PersonRow[]>([]);
    const [photos, setPhotos] = useState<Record<number, string>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedId, setSelectedId] = useState<number | null>(null);

    useEffect(() => {
        let mounted = true;
        fetch(`${API_BASE}/api/persons?limit=200`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: PersonRow[]) => {
                if (!mounted) return;
                setRows(Array.isArray(data) ? data : []);
                setLoading(false);
            })
            .catch(err => {
                if (!mounted) return;
                setError(String(err));
                setLoading(false);
            });
        return () => { mounted = false; };
    }, []);

    // A listagem não traz foto — só a ficha individual traz a última
    // evidência (ver /api/persons/{id}). Resolve por card, uma vez.
    useEffect(() => {
        rows.forEach(p => {
            if (photos[p.id]) return;
            fetch(`${API_BASE}/api/persons/${p.id}`)
                .then(res => res.json())
                .then((detail: PersonDetail) => {
                    const last = detail.history?.[detail.history.length - 1];
                    if (last?.evidence_url) {
                        setPhotos(prev => ({ ...prev, [p.id]: `${API_BASE}${last.evidence_url}` }));
                    }
                })
                .catch(() => {});
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [rows]);

    const handleClose = useCallback(() => setSelectedId(null), []);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between gap-4 mb-6 pb-4 border-b border-white/5">
                <div>
                    <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                        <Fingerprint className="w-4 h-4 text-accent-emerald" /> PESSOAS ANÔNIMAS
                    </h2>
                    <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                        {rows.length} IDENTIDADES CATALOGADAS — NUNCA NOME REAL, SÓ BIOMETRIA + CÓDIGO
                    </p>
                </div>
            </div>

            {error && (
                <div className="bg-red-500/20 text-red-500 px-4 py-3 rounded-lg border border-red-500/30 text-sm font-mono mb-6">
                    Erro ao carregar pessoas: {error}
                </div>
            )}

            {loading ? (
                <div className="h-40 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                </div>
            ) : rows.length === 0 ? (
                <div className="text-muted italic text-sm">
                    Ninguém catalogado ainda. Assim que um rosto de qualidade boa passar numa câmera monitorada, aparece aqui sozinho.
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
                    {rows.map(p => (
                        <motion.div
                            key={p.id}
                            layout
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            onClick={() => setSelectedId(p.id)}
                            className="intelligence-card group border border-white/5 hover:border-accent-emerald/40 transition-all shadow-lg cursor-pointer"
                        >
                            <div className="aspect-[3/4] relative bg-neutral-900 overflow-hidden">
                                {photos[p.id] ? (
                                    <img src={photos[p.id]} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt={p.code} />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center opacity-10"><Fingerprint className="w-16 h-16" /></div>
                                )}
                                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                                {p.times_seen > 1 && (
                                    <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-accent-emerald/80 backdrop-blur-sm px-2 py-1 rounded-full">
                                        <span className="text-[9px] font-black tracking-widest text-black uppercase">{p.times_seen}× VISTO</span>
                                    </div>
                                )}

                                <div className="absolute bottom-3 left-3 right-3 glass-panel rounded-lg border border-white/10 px-3 py-2.5">
                                    <h3 className="text-xs font-black uppercase tracking-tight text-white font-mono">{p.code}</h3>
                                    <p className="text-[9px] text-muted font-mono mt-0.5">última: {fmtTime(p.last_seen_at)}</p>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}

            <AnimatePresence>
                {selectedId != null && (
                    <PersonDossier id={selectedId} onClose={handleClose} />
                )}
            </AnimatePresence>
        </main>
    );
}

function PersonDossier({ id, onClose }: { id: number; onClose: () => void }) {
    const [detail, setDetail] = useState<PersonDetail | null>(null);

    useEffect(() => {
        let mounted = true;
        fetch(`${API_BASE}/api/persons/${id}`)
            .then(res => res.json())
            .then(data => { if (mounted) setDetail(data); })
            .catch(() => {});
        return () => { mounted = false; };
    }, [id]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [onClose]);

    const history = detail?.history ?? [];
    const lastPhoto = history[history.length - 1]?.evidence_url;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/80 backdrop-blur-sm overflow-hidden">
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="bg-surface border border-white/5 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
            >
                <div className="h-16 px-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
                    <div className="flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-accent-emerald animate-pulse" />
                        <span className="text-[10px] font-black tracking-widest text-muted uppercase font-mono">{!detail ? 'CARREGANDO…' : (detail.code || 'P-?????????-?')}</span>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg transition-colors">
                        <X className="w-5 h-5 text-muted" />
                    </button>
                </div>

                {!detail ? (
                    <div className="h-40 flex items-center justify-center">
                        <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : (
                    <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col md:flex-row">
                        <aside className="w-full md:w-64 border-r border-white/5 p-6 flex flex-col gap-4 shrink-0">
                            <div className="aspect-[3/4] bg-black rounded-lg overflow-hidden border border-white/10">
                                {lastPhoto ? (
                                    <img src={`${API_BASE}${lastPhoto}`} className="w-full h-full object-cover" />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center opacity-10"><Fingerprint className="w-16 h-16" /></div>
                                )}
                            </div>
                            <div className="text-xs text-white/70 space-y-1.5 font-mono">
                                <p>Visto <b className="text-accent-emerald">{detail.times_seen}×</b></p>
                                <p>Câmeras: {detail.cameras_seen || '—'}</p>
                                <p>1ª vez: {fmtTime(detail.first_seen_at)}</p>
                                <p>Última: {fmtTime(detail.last_seen_at)}</p>
                            </div>
                        </aside>

                        <main className="flex-1 p-6">
                            <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                                <Clock className="w-3 h-3" /> LINHA DO TEMPO DE PASSAGENS
                            </h4>
                            {history.length === 0 ? (
                                <p className="text-muted italic text-sm">Sem histórico.</p>
                            ) : (
                                <div className="space-y-3">
                                    {history.slice().reverse().map(h => (
                                        <div key={h.id} className="p-3 bg-white/[0.03] border border-white/5 rounded-xl flex items-center gap-3">
                                            {h.evidence_url ? (
                                                <img src={`${API_BASE}${h.evidence_url}`} className="w-14 h-14 object-cover rounded-lg border border-white/10 shrink-0" />
                                            ) : (
                                                <div className="w-14 h-14 rounded-lg bg-black/40 shrink-0" />
                                            )}
                                            <div className="text-xs">
                                                <p className="flex items-center gap-1.5 text-accent-blue font-mono font-bold">
                                                    <MapPin className="w-3 h-3" /> {h.camera_id}
                                                </p>
                                                <p className="text-muted font-mono mt-0.5">{fmtTime(h.created_at)} · distância {Number(h.distance).toFixed(3)}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </main>
                    </div>
                )}
            </motion.div>
        </div>
    );
}
