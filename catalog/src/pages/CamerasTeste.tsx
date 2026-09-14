import { useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { FlaskConical, Plus, Trash2, X } from 'lucide-react';
import { CameraData } from '../components/player/types/player.types';
import { TacticalVideoPlayer } from '../components/player/TacticalVideoPlayer';

const API_BASE = 'http://localhost:8001';

interface CandidateCamera {
    id: string;
    nome: string;
    local: string | null;
    pais: string | null;
    video_id: string | null;
    url: string | null;
    thumbnail_url: string | null;
    test_notes: string | null;
    created_at: string;
}

function fmtTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    try {
        return new Date(iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('pt-BR');
    } catch {
        return iso;
    }
}

export default function CamerasTeste() {
    const [candidates, setCandidates] = useState<CandidateCamera[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selected, setSelected] = useState<CandidateCamera | null>(null);
    const [showForm, setShowForm] = useState(false);

    const [formNome, setFormNome] = useState('');
    const [formYoutube, setFormYoutube] = useState('');
    const [formLocal, setFormLocal] = useState('');
    const [formPais, setFormPais] = useState('');
    const [formNotas, setFormNotas] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    const fetchCandidates = useCallback(() => {
        fetch(`${API_BASE}/api/camera-candidates`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: CandidateCamera[]) => {
                setCandidates(Array.isArray(data) ? data : []);
                setError(null);
                setLoading(false);
            })
            .catch(err => {
                setError(String(err));
                setLoading(false);
            });
    }, []);

    useEffect(() => {
        fetchCandidates();
    }, [fetchCandidates]);

    const handleAdd = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        if (!formNome.trim() || !formYoutube.trim()) return;
        setSubmitting(true);
        setFormError(null);
        const params = new URLSearchParams({ nome: formNome.trim(), youtube: formYoutube.trim() });
        if (formLocal.trim()) params.set('local', formLocal.trim());
        if (formPais.trim()) params.set('pais', formPais.trim().toUpperCase());
        if (formNotas.trim()) params.set('test_notes', formNotas.trim());

        fetch(`${API_BASE}/api/camera-candidates?${params.toString()}`, { method: 'POST' })
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(() => {
                setFormNome(''); setFormYoutube(''); setFormLocal(''); setFormPais(''); setFormNotas('');
                setShowForm(false);
                fetchCandidates();
            })
            .catch(err => setFormError(String(err)))
            .finally(() => setSubmitting(false));
    }, [formNome, formYoutube, formLocal, formPais, formNotas, fetchCandidates]);

    const handleDelete = useCallback((id: string, nome: string) => {
        if (!window.confirm(`Remover "${nome}" da lista de candidatas? Isso não desliga nada, só tira da lista.`)) return;
        fetch(`${API_BASE}/api/camera-candidates/${id}`, { method: 'DELETE' })
            .then(() => fetchCandidates())
            .catch(() => {});
    }, [fetchCandidates]);

    const toCameraData = (c: CandidateCamera): CameraData => ({
        id: c.id,
        nome: c.nome,
        local: c.local,
        pais: c.pais || undefined,
        thumbnail_url: c.thumbnail_url || undefined,
        url: c.url || undefined,
        video_id: c.video_id || undefined,
    });

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="flex items-start justify-between gap-4 mb-6 pb-4 border-b border-white/5">
                <div>
                    <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                        <FlaskConical className="w-4 h-4 text-accent-emerald" /> CÂMERAS TESTE
                    </h2>
                    <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                        WORKSPACE DE CURADORIA — ASSISTA AO VIVO ANTES DE PROMOVER UMA CANDIDATA
                    </p>
                    <p className="text-xs text-white/50 mt-2 max-w-2xl">
                        Câmeras aqui não entram na grade principal nem em nenhum pipeline automaticamente — é só pra
                        você ver ao vivo (com zoom/pan real) e decidir qual promover.
                    </p>
                </div>
                <button
                    onClick={() => setShowForm(v => !v)}
                    className="shrink-0 h-9 px-4 bg-accent-emerald/20 hover:bg-accent-emerald/30 text-accent-emerald border border-accent-emerald/40 rounded-lg text-xs font-black tracking-wider uppercase transition-all flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> Adicionar candidata
                </button>
            </div>

            {showForm && (
                <form onSubmit={handleAdd} className="intelligence-card p-5 mb-6 flex flex-col gap-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <input
                            value={formNome} onChange={e => setFormNome(e.target.value)} placeholder="Nome (ex: Cruzamento Rua X)"
                            required
                            className="h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50"
                        />
                        <input
                            value={formYoutube} onChange={e => setFormYoutube(e.target.value)} placeholder="Link do YouTube ou ID do vídeo"
                            required
                            className="h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50"
                        />
                        <input
                            value={formLocal} onChange={e => setFormLocal(e.target.value)} placeholder="Local (ex: Tubarão, SC)"
                            className="h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50"
                        />
                        <input
                            value={formPais} onChange={e => setFormPais(e.target.value)} placeholder="País (ex: BR)" maxLength={2}
                            className="h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50"
                        />
                    </div>
                    <input
                        value={formNotas} onChange={e => setFormNotas(e.target.value)} placeholder="Notas (ex: resolução, se tem semáforo, o que observar)"
                        className="h-9 bg-black/40 border border-white/10 rounded-lg px-3 text-xs font-mono text-white focus:outline-none focus:border-accent-emerald/50"
                    />
                    {formError && <p className="text-red-500 text-xs font-mono">{formError}</p>}
                    <div className="flex justify-end">
                        <button
                            type="submit" disabled={submitting}
                            className="h-9 px-5 bg-accent-emerald text-black font-black text-xs tracking-wider uppercase rounded-lg transition-all disabled:opacity-50"
                        >
                            {submitting ? 'Adicionando…' : 'Adicionar'}
                        </button>
                    </div>
                </form>
            )}

            {error && (
                <div className="bg-red-500/20 text-red-500 px-4 py-3 rounded-lg border border-red-500/30 text-sm font-mono mb-6">
                    Erro ao carregar candidatas: {error}
                </div>
            )}

            {loading ? (
                <div className="h-40 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                </div>
            ) : candidates.length === 0 ? (
                <div className="text-muted italic text-sm">Nenhuma candidata ainda. Clique em "Adicionar candidata" pra testar a primeira.</div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {candidates.map(c => (
                        <motion.div
                            key={c.id}
                            layout
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="intelligence-card group border border-white/5 hover:border-accent-emerald/40 transition-all shadow-lg cursor-pointer"
                            onClick={() => setSelected(c)}
                        >
                            <div className="aspect-video relative bg-neutral-900 overflow-hidden">
                                {c.thumbnail_url ? (
                                    <img
                                        src={`${API_BASE}${c.thumbnail_url}`}
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                                        alt={c.nome}
                                    />
                                ) : (
                                    <div className="w-full h-full flex items-center justify-center opacity-10"><FlaskConical className="w-16 h-16" /></div>
                                )}
                                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                                <button
                                    onClick={(e) => { e.stopPropagation(); handleDelete(c.id, c.nome); }}
                                    className="absolute top-3 right-3 p-1.5 bg-black/60 hover:bg-red-500/80 rounded-lg text-white/70 hover:text-white transition-colors z-10"
                                    title="Remover candidata"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>

                                <div className="absolute bottom-3 left-3 right-3 glass-panel rounded-lg border border-white/10 px-3 py-2.5">
                                    <h3 className="text-xs font-black uppercase tracking-tight text-white truncate">{c.nome}</h3>
                                    {c.local && <p className="text-[10px] text-accent-amber font-mono truncate mt-0.5">{c.local} {c.pais ? `(${c.pais})` : ''}</p>}
                                </div>
                            </div>
                            {c.test_notes && (
                                <div className="px-3 py-2.5 border-t border-white/5">
                                    <p className="text-[11px] text-white/60 leading-snug">{c.test_notes}</p>
                                    <p className="text-[9px] text-muted font-mono mt-1.5">adicionada {fmtTime(c.created_at)}</p>
                                </div>
                            )}
                        </motion.div>
                    ))}
                </div>
            )}

            <AnimatePresence>
                {selected && (
                    <TacticalVideoPlayer
                        camera={toCameraData(selected)}
                        onClose={() => setSelected(null)}
                    />
                )}
            </AnimatePresence>
        </main>
    );
}
