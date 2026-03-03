import { useState, useEffect, useRef } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Search, Info, Download, X, User, ChevronDown, Fingerprint, MapPin, Briefcase } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Helper de classes
function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

// ─── Interfaces ──────────────────────────────────────────────────────────────
interface Individual {
    id: string;
    name: string;
    category: string;
    source: string;
    img_path?: string;
    has_embedding: number;
    reward?: string;
    ingested_at?: string;
}

interface Stats {
    total: number;
    wanted: number;
    missing: number;
    with_biometrics: number;
}

interface IndividualDetail extends Individual {
    aliases?: string;
    sex?: string;
    birth_date?: string;
    nationalities?: string;
    description?: string;
    height_cm?: number;
    weight_kg?: number;
    eye_color?: string;
    hair_color?: string;
    occupation?: string;
    images: Array<{ img_path: string; is_primary: number }>;
    crimes: string[];
}

// ─── Componentes ─────────────────────────────────────────────────────────────

export default function App() {
    const [individuals, setIndividuals] = useState<Individual[]>([]);
    const [stats, setStats] = useState<Stats | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [category, setCategory] = useState<string>('');
    const [bioOnly, setBioOnly] = useState(false);
    const [source, setSource] = useState('');
    const [country, setCountry] = useState('');
    const [page, setPage] = useState(0);
    const [loading, setLoading] = useState(false);
    const [hasMore, setHasMore] = useState(true);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [detail, setDetail] = useState<IndividualDetail | null>(null);

    const observer = useRef<IntersectionObserver | null>(null);
    const lastElementRef = useRef<HTMLDivElement | null>(null);

    // Carregar Stats
    useEffect(() => {
        invoke<Stats>('get_stats').then(setStats).catch(console.error);
    }, []);

    // Atalhos de Teclado
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                document.querySelector<HTMLInputElement>('input[type="text"]')?.focus();
            }
            if (e.key === 'Escape') setSelectedId(null);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    // Busca e Scroll
    useEffect(() => {
        const timeout = setTimeout(() => {
            loadPage(0, true);
        }, 300);
        return () => clearTimeout(timeout);
    }, [searchQuery, category, bioOnly, source, country]);

    async function loadPage(p: number, reset = false) {
        if (loading && !reset) return;
        setLoading(true);
        try {
            const results = await invoke<Individual[]>('search_individuals', {
                name: searchQuery || null,
                category: category || null,
                has_embedding: bioOnly ? 1 : null,
                source_filter: source || null,
                country: country || null,
                page: p,
                limit: 40
            });
            if (reset) {
                setIndividuals(results);
                setPage(0);
            } else {
                setIndividuals(prev => [...prev, ...results]);
                setPage(p);
            }
            setHasMore(results.length === 40);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }

    // Infinite Scroll Observer
    useEffect(() => {
        if (loading) return;
        if (observer.current) observer.current.disconnect();
        observer.current = new IntersectionObserver(entries => {
            if (entries[0].isIntersecting && hasMore) {
                loadPage(page + 1);
            }
        });
        if (lastElementRef.current) observer.current.observe(lastElementRef.current);
    }, [loading, hasMore]);

    // Carregar Detalhe
    useEffect(() => {
        if (selectedId) {
            invoke<IndividualDetail>('get_individual', { id: selectedId })
                .then(setDetail)
                .catch(console.error);
        } else {
            setDetail(null);
        }
    }, [selectedId]);

    return (
        <div className="min-h-screen bg-background flex flex-col font-sans selection:bg-accent-amber/30 selection:text-white">
            {/* HEADER */}
            <header className="sticky top-0 z-50 glass-panel h-20 px-8 flex items-center justify-between">
                <div className="flex items-center gap-12">
                    {/* LOGO */}
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-accent-amber rounded-lg flex items-center justify-center text-black font-black text-xl shadow-[0_0_20px_rgba(245,158,11,0.3)]">O</div>
                        <div>
                            <h1 className="text-lg font-bold tracking-tight leading-none">OLHO DE DEUS</h1>
                            <p className="text-[10px] font-mono text-accent-amber tracking-[0.2em] opacity-80 uppercase">Intelligence Catalog</p>
                        </div>
                    </div>

                    {/* STATS */}
                    <div className="hidden lg:flex items-center gap-8 border-l border-white/10 pl-12 h-10">
                        <StatItem label="Wanted" value={stats?.wanted} color="text-red-500" />
                        <StatItem label="Missing" value={stats?.missing} color="text-accent-amber" />
                        <StatItem label="Biometria" value={stats?.with_biometrics} color="text-accent-emerald" />
                    </div>
                </div>

                {/* SEARCH */}
                <div className="relative w-96 group">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-accent-amber transition-colors" />
                    <input
                        type="text"
                        placeholder="PESQUISAR ALVO / ID / CRIMES..."
                        className="w-full h-11 bg-white/[0.03] border border-white/10 rounded-full pl-11 pr-4 text-sm font-medium focus:outline-none focus:border-accent-amber/50 focus:bg-white/[0.05] transition-all"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 flex gap-1 opacity-30 group-focus-within:opacity-0 transition-opacity">
                        <span className="text-[10px] font-mono border border-white/20 px-1 rounded">⌘</span>
                        <span className="text-[10px] font-mono border border-white/20 px-1 rounded">K</span>
                    </div>
                </div>
            </header>

            {/* FILTER BAR */}
            <div className="px-8 py-6 flex items-center justify-between border-b border-white/5 bg-white/[0.01]">
                <div className="flex items-center gap-3">
                    <FilterButton active={!category} onClick={() => setCategory('')}>TODOS</FilterButton>
                    <FilterButton active={category === 'wanted'} onClick={() => setCategory('wanted')}>PROCURADOS</FilterButton>
                    <FilterButton active={category === 'missing'} onClick={() => setCategory('missing')}>DESAPARECIDOS</FilterButton>

                    <div className="w-[1px] h-4 bg-white/10 mx-4" />

                    <button
                        onClick={() => setBioOnly(!bioOnly)}
                        className={cn(
                            "h-9 px-4 rounded-full border text-[10px] font-black tracking-widest transition-all flex items-center gap-2",
                            bioOnly ? "bg-accent-emerald/20 border-accent-emerald text-accent-emerald" : "border-white/10 text-muted hover:bg-white/5"
                        )}
                    >
                        <Fingerprint className="w-3.5 h-3.5" /> BIOMETRIA
                    </button>

                    <div className="relative group">
                        <select
                            value={source}
                            onChange={(e) => setSource(e.target.value)}
                            className="appearance-none h-9 pl-4 pr-10 rounded-full border border-white/10 bg-transparent text-[10px] font-black tracking-widest hover:bg-white/5 transition-all outline-none cursor-pointer"
                        >
                            <option value="" className="bg-surface">FONTE: TODAS</option>
                            <option value="FBI" className="bg-surface">FBI</option>
                            <option value="Interpol" className="bg-surface">INTERPOL</option>
                            <option value="Europol" className="bg-surface">EUROPOL</option>
                        </select>
                        <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-3 h-3 text-muted pointer-events-none" />
                    </div>

                    <div className="relative group">
                        <select
                            value={country}
                            onChange={(e) => setCountry(e.target.value)}
                            className="appearance-none h-9 pl-4 pr-10 rounded-full border border-white/10 bg-transparent text-[10px] font-black tracking-widest hover:bg-white/5 transition-all outline-none cursor-pointer"
                        >
                            <option value="" className="bg-surface">PAÍS: TODOS</option>
                            <option value="BR" className="bg-surface">BRASIL</option>
                            <option value="US" className="bg-surface">EUA</option>
                            <option value="RU" className="bg-surface">RÚSSIA</option>
                            <option value="IR" className="bg-surface">IRÃ</option>
                        </select>
                        <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-3 h-3 text-muted pointer-events-none" />
                    </div>
                </div>

                <button
                    onClick={() => invoke('export_csv').catch(alert)}
                    className="h-9 px-5 rounded-full border border-accent-amber/20 text-accent-amber text-[10px] font-black tracking-widest hover:bg-accent-amber/10 transition-all flex items-center gap-2 shadow-[0_0_15px_rgba(245,158,11,0.05)]"
                >
                    <Download className="w-3.5 h-3.5" /> EXPORTAR CSV
                </button>
            </div>

            {/* GRID */}
            <main className="flex-1 px-8 pb-12">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
                    {individuals.map((person) => (
                        <IndividualCard key={person.id} person={person} onClick={() => setSelectedId(person.id)} />
                    ))}
                </div>

                <div ref={lastElementRef} className="h-20 flex items-center justify-center mt-8">
                    {loading && (
                        <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                    )}
                </div>
            </main>

            {/* MODAL / DOSSIER */}
            <AnimatePresence>
                {selectedId && detail && (
                    <DossierModal
                        detail={detail}
                        onClose={() => setSelectedId(null)}
                    />
                )}
            </AnimatePresence>
        </div>
    );
}

// ─── Sub-componentes ─────────────────────────────────────────────────────────

function StatItem({ label, value, color }: { label: string, value?: number, color: string }) {
    return (
        <div className="flex flex-col">
            <span className="text-[9px] font-black uppercase text-muted tracking-widest">{label}</span>
            <span className={cn("text-lg font-black leading-tight", color)}>{value?.toLocaleString() || '---'}</span>
        </div>
    );
}

function FilterButton({ children, active, onClick }: { children: React.ReactNode, active: boolean, onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className={cn(
                "h-9 px-5 rounded-full text-[11px] font-black tracking-widest transition-all",
                active ? "bg-accent-amber text-black" : "border border-white/10 hover:bg-white/5"
            )}
        >
            {children}
        </button>
    );
}

function IndividualCard({ person, onClick }: { person: Individual, onClick: () => void }) {
    const [imgUrl, setImgUrl] = useState<string | null>(null);

    useEffect(() => {
        if (person.img_path) {
            invoke<string>('get_image_base64', { imgPath: person.img_path })
                .then(setImgUrl)
                .catch(() => setImgUrl(null));
        }
    }, [person.img_path]);

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="intelligence-card group cursor-pointer"
            onClick={onClick}
        >
            <div className="aspect-[3/4] relative bg-neutral-900 overflow-hidden">
                {imgUrl ? (
                    <img src={imgUrl} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" alt={person.name} />
                ) : (
                    <div className="w-full h-full flex items-center justify-center opacity-30 bg-neutral-950">
                        <User className="w-20 h-20" />
                    </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                {/* Badges */}
                <div className="absolute top-3 left-3 flex gap-2">
                    {person.has_embedding === 1 && (
                        <div className="w-8 h-8 rounded-full bg-accent-emerald text-black flex items-center justify-center shadow-lg shadow-accent-emerald/20 border border-black" title="Biometria Disponível">
                            <Fingerprint className="w-4 h-4" />
                        </div>
                    )}
                </div>

                <div className="absolute top-3 right-3">
                    <span className={cn(
                        "text-[9px] font-black px-2 py-1 rounded border",
                        person.category === 'wanted' ? "border-red-500/50 bg-red-500/20 text-red-500" : "border-accent-amber/50 bg-accent-amber/20 text-accent-amber"
                    )}>
                        {person.category.toUpperCase()}
                    </span>
                </div>

                {/* Info */}
                <div className="absolute bottom-4 left-4 right-4">
                    <h3 className="text-sm font-black uppercase tracking-tight line-clamp-2 leading-tight drop-shadow-lg">{person.name}</h3>
                    <p className="text-[10px] text-muted font-mono mt-2 flex items-center gap-1">
                        <Info className="w-3 h-3" /> {person.source}
                    </p>
                </div>
            </div>
        </motion.div>
    );
}

function DossierModal({ detail, onClose }: { detail: IndividualDetail, onClose: () => void }) {
    const [activeImg, setActiveImg] = useState<string | null>(null);

    useEffect(() => {
        if (detail.img_path) {
            invoke<string>('get_image_base64', { imgPath: detail.img_path }).then(setActiveImg);
        }
    }, [detail.img_path]);

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/80 backdrop-blur-sm overflow-hidden">
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="bg-surface border border-white/5 rounded-2xl w-full max-w-6xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
            >
                {/* Modal Header */}
                <div className="h-16 px-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
                    <div className="flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        <span className="text-[10px] font-black tracking-widest text-muted uppercase">Conexão Segura Ativa — Terminal de Inteligência</span>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg transition-colors">
                        <X className="w-5 h-5 text-muted" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col md:flex-row">
                    {/* SIDEBAR */}
                    <aside className="w-full md:w-80 border-r border-white/5 p-6 flex flex-col gap-6">
                        <div className="aspect-[3/4] bg-black rounded-lg overflow-hidden border border-white/10 relative">
                            <div className="absolute inset-0 scanline pointer-events-none" />
                            {activeImg ? (
                                <img src={activeImg} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center opacity-10"><User className="w-32 h-32" /></div>
                            )}
                        </div>

                        {/* Gallery */}
                        <div>
                            <h4 className="text-[10px] font-black text-muted tracking-widest uppercase mb-4">Galeria Forense</h4>
                            <div className="grid grid-cols-4 gap-2">
                                {detail.images.map((img, i) => (
                                    <GalleryThumb key={i} path={img.img_path} active={img.img_path === activeImg} onClick={() => {
                                        invoke<string>('get_image_base64', { imgPath: img.img_path }).then(setActiveImg);
                                    }} />
                                ))}
                            </div>
                        </div>
                    </aside>

                    {/* CONTENT */}
                    <main className="flex-1 p-8 lg:p-12">
                        <div className={cn(
                            "text-[10px] font-black px-2 py-1 rounded inline-block mb-4",
                            detail.category === 'wanted' ? "bg-red-500/10 text-red-500 border border-red-500/20" : "bg-accent-amber/10 text-accent-amber border border-accent-amber/20"
                        )}>
                            {detail.category === 'wanted' ? 'INVESTIGAÇÃO ATIVA' : 'ALERTA DE DESAPARECIMENTO'}
                        </div>

                        <h2 className="text-4xl font-extrabold tracking-tight mb-2 leading-tight uppercase">{detail.name}</h2>
                        {detail.aliases && detail.aliases !== '[]' && (
                            <p className="text-accent-blue font-mono text-sm font-semibold mb-6 opacity-80">AKA: {Array.isArray(JSON.parse(detail.aliases)) ? JSON.parse(detail.aliases).join(", ") : detail.aliases}</p>
                        )}

                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-y-8 gap-x-12 mt-12 mb-16">
                            <DetailItem label="Gênero" value={detail.sex} />
                            <DetailItem label="Nascimento" value={detail.birth_date} />
                            <DetailItem label="Nacionalidade" value={detail.nationalities ? JSON.parse(detail.nationalities).join(", ") : 'N/A'} />
                            <DetailItem label="Ocupação" value={detail.occupation} />
                            <DetailItem label="Altura" value={detail.height_cm ? `${detail.height_cm} cm` : null} />
                            <DetailItem label="Peso" value={detail.weight_kg ? `${detail.weight_kg} kg` : null} />
                            <DetailItem label="Olhos" value={detail.eye_color} />
                            <DetailItem label="Cabelo" value={detail.hair_color} />
                        </div>

                        {detail.reward && (
                            <div className="bg-accent-amber/5 border border-dashed border-accent-amber/30 p-6 rounded-xl mb-12">
                                <span className="text-[10px] font-black text-accent-amber tracking-widest uppercase block mb-1">RECOMPENSA OFERECIDA</span>
                                <p className="text-2xl font-mono font-bold text-white">{detail.reward}</p>
                            </div>
                        )}

                        <div className="space-y-12">
                            <section>
                                <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50"><MapPin className="w-3 h-3" /> Acusações e Infrações</h4>
                                <div className="flex flex-wrap gap-2">
                                    {detail.crimes.length > 0 ? detail.crimes.map((c, i) => (
                                        <span key={i} className="px-3 py-1.5 bg-white/[0.03] border border-white/10 rounded-lg text-xs font-medium text-white/80">{c}</span>
                                    )) : <span className="text-muted italic text-sm">Nenhuma acusação detalhada.</span>}
                                </div>
                            </section>

                            <section>
                                <h4 className="flex items-center gap-2 text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50"><Briefcase className="w-3 h-3" /> Relatório de Inteligência</h4>
                                <div className="text-sm text-white/70 leading-relaxed font-medium whitespace-pre-wrap">{detail.description || 'Nenhuma descrição adicional disponível.'}</div>
                            </section>
                        </div>

                        <div className="mt-20 pt-8 border-t border-white/5 flex items-center justify-between opacity-30 text-[10px] font-mono tracking-wider">
                            <span>FONTE: {detail.source} / ID: {detail.id}</span>
                            <span>COLETADO EM: {detail.ingested_at || 'N/A'}</span>
                        </div>
                    </main>
                </div>
            </motion.div>
        </div>
    );
}

function DetailItem({ label, value }: { label: string, value: any }) {
    return (
        <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-black text-muted tracking-widest uppercase">{label}</span>
            <span className="text-sm font-semibold tracking-tight">{value || '---'}</span>
        </div>
    )
}

function GalleryThumb({ path, active, onClick }: { path: string, active: boolean, onClick: () => void }) {
    const [url, setUrl] = useState<string | null>(null);
    useEffect(() => {
        invoke<string>('get_image_base64', { imgPath: path }).then(setUrl);
    }, [path]);

    return (
        <div
            onClick={onClick}
            className={cn(
                "aspect-square rounded border cursor-pointer overflow-hidden transition-all",
                active ? "border-accent-amber scale-95" : "border-white/10 hover:border-white/30"
            )}
        >
            {url && <img src={url} className="w-full h-full object-cover" />}
        </div>
    )
}
