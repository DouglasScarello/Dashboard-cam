import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Video, X, Volume2, VolumeX, MapPin, Compass, ExternalLink, ShieldCheck } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { TacticalVideoPlayer } from '../components/player/TacticalVideoPlayer';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const API_BASE = 'http://localhost:8001';

interface Camera {
    id: string | number;
    nome: string;
    local?: string | null;
    endereco?: string | null;
    cidade?: string | null;
    uf?: string | null;
    tipo_area?: string | null;
    setor?: string;
    pais?: string;
    thumbnail_url: string;
    url?: string;
    video_id?: string;
    lat?: number | null;
    long?: number | null;
}

interface CameraAlert {
    camera_id: string;
    type: 'WEAPON' | 'FALL';
    level: number;
    detail: string;
    ts: number;
}

export default function CameraGrid() {
    const { t } = useTranslation();
    const [cameras, setCameras] = useState<Camera[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [tick, setTick] = useState(() => Math.floor(Date.now() / 5000));
    const [selected, setSelected] = useState<Camera | null>(null);
    const [alerts, setAlerts] = useState<CameraAlert[]>([]);
    
    // Controles de Busca e Filtro
    const [searchQuery, setSearchQuery] = useState('');
    const [sectorFilter, setSectorFilter] = useState(''); // Padrão: Todas as câmeras reais
    const [stateFilter, setStateFilter] = useState('');
    const [displayLimit, setDisplayLimit] = useState(10); // 10 em 10 câmeras

    useEffect(() => {
        let mounted = true;
        setLoading(true);
        // Carrega as transmissões reais ao vivo do backend
        fetch(`${API_BASE}/api/cameras?limit=2000`)
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: Camera[]) => {
                if (mounted) setCameras(Array.isArray(data) ? data : []);
            })
            .catch((err) => {
                if (mounted) setError(String(err));
            })
            .finally(() => {
                if (mounted) setLoading(false);
            });
        return () => {
            mounted = false;
        };
    }, []);

    useEffect(() => {
        const fetchAlerts = () => {
            fetch(`${API_BASE}/api/alerts`)
                .then((res) => {
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                    return res.json();
                })
                .then((data: CameraAlert[]) => {
                    setAlerts(Array.isArray(data) ? data : []);
                })
                .catch(() => {
                    // non-fatal: alerts are best-effort, don't disrupt the grid
                });
        };

        fetchAlerts();
        const interval = setInterval(() => {
            setTick(Math.floor(Date.now() / 5000));
            fetchAlerts();
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    const handleClose = useCallback(() => setSelected(null), []);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') handleClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [handleClose]);

    // Filtragem Instantânea em Memória
    const filteredCameras = useMemo(() => {
        let list = cameras;

        if (sectorFilter) {
            list = list.filter((c) => (c.setor || c.pais || '').toUpperCase() === sectorFilter.toUpperCase());
        }

        if (stateFilter && sectorFilter === 'BR') {
            const uf = stateFilter.toUpperCase();
            list = list.filter((c) => (c.local || '').toUpperCase().includes(uf));
        }

        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase().trim();
            list = list.filter(
                (c) =>
                    c.nome.toLowerCase().includes(q) ||
                    (c.endereco && c.endereco.toLowerCase().includes(q)) ||
                    (c.local && c.local.toLowerCase().includes(q)) ||
                    (c.cidade && c.cidade.toLowerCase().includes(q)) ||
                    (c.tipo_area && c.tipo_area.toLowerCase().includes(q)) ||
                    (c.pais && c.pais.toLowerCase().includes(q))
            );
        }

        return list;
    }, [cameras, sectorFilter, stateFilter, searchQuery]);

    const displayedCameras = useMemo(() => {
        return filteredCameras.slice(0, displayLimit);
    }, [filteredCameras, displayLimit]);

    const activeAlertMap = useMemo(() => {
        const map = new Map<string, CameraAlert>();
        for (const a of alerts) {
            map.set(String(a.camera_id), a);
        }
        return map;
    }, [alerts]);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            {/* Header & Status C4ISR */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-white/5">
                <div>
                    <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                        <Video className="w-4 h-4 text-accent-emerald" /> {t('cameras.title')}
                    </h2>
                    <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                        REDE AO VIVO: {cameras.length} TRANSMISSÕES REAIS ATIVAS
                    </p>
                </div>

                {/* Filtros Rápidos de Continente / Setor */}
                <div className="flex flex-wrap items-center gap-2">
                    <button
                        onClick={() => { setSectorFilter(''); setStateFilter(''); setDisplayLimit(10); }}
                        className={cn(
                            "px-3 py-1.5 rounded-full text-[10px] font-black tracking-wider uppercase transition-all border",
                            sectorFilter === '' ? "bg-accent-amber/20 border-accent-amber text-accent-amber" : "bg-white/[0.02] border-white/10 text-muted hover:bg-white/5"
                        )}
                    >
                        🌐 TODAS AS CÂMERAS ({cameras.length})
                    </button>
                    <button
                        onClick={() => { setSectorFilter('BR'); setStateFilter(''); setDisplayLimit(10); }}
                        className={cn(
                            "px-3 py-1.5 rounded-full text-[10px] font-black tracking-wider uppercase transition-all border",
                            sectorFilter === 'BR' ? "bg-accent-emerald/20 border-accent-emerald text-accent-emerald" : "bg-white/[0.02] border-white/10 text-muted hover:bg-white/5"
                        )}
                    >
                        🇧🇷 BRASIL
                    </button>
                    <button
                        onClick={() => { setSectorFilter('US'); setStateFilter(''); setDisplayLimit(10); }}
                        className={cn(
                            "px-3 py-1.5 rounded-full text-[10px] font-black tracking-wider uppercase transition-all border",
                            sectorFilter === 'US' ? "bg-blue-500/20 border-blue-500 text-blue-400" : "bg-white/[0.02] border-white/10 text-muted hover:bg-white/5"
                        )}
                    >
                        🇺🇸 AMÉRICA DO NORTE
                    </button>
                </div>
            </div>

            {/* Sub-Filtros de Estados Brasileiros */}
            {sectorFilter === 'BR' && (
                <div className="flex flex-wrap items-center gap-1.5 mb-4">
                    <span className="text-[9px] font-mono uppercase text-muted mr-1">ESTADOS:</span>
                    {['', 'SP', 'RJ', 'SC', 'PR', 'RS', 'MG', 'BA', 'CE', 'PE', 'DF'].map((uf) => (
                        <button
                            key={uf}
                            onClick={() => { setStateFilter(uf); setDisplayLimit(10); }}
                            className={cn(
                                "px-2.5 py-1 rounded-md text-[9px] font-mono tracking-wider transition-all border",
                                stateFilter === uf 
                                    ? "bg-accent-emerald text-black font-black border-accent-emerald" 
                                    : "bg-white/[0.02] text-muted border-white/5 hover:bg-white/[0.06] hover:text-white"
                            )}
                        >
                            {uf === '' ? 'TODOS UFs' : uf}
                        </button>
                    ))}
                </div>
            )}

            {/* Barra de Busca Rápida */}
            <div className="mb-6">
                <input
                    type="text"
                    placeholder="Filtrar por cidade, rodovia, praia ou aeroporto (ex: São Paulo, Florianópolis, Tóquio, Times Square, Rodovia)..."
                    value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); setDisplayLimit(10); }}
                    className="w-full h-11 bg-white/[0.03] border border-white/10 rounded-xl px-4 text-xs font-medium focus:outline-none focus:border-accent-amber/50 focus:bg-white/[0.05] transition-all text-white placeholder:text-muted"
                />
            </div>

            {error && (
                <div className="bg-red-500/20 text-red-500 px-4 py-3 rounded-lg border border-red-500/30 text-sm font-mono mb-6">
                    {t('cameras.fetch_error')}: {error}
                </div>
            )}

            {loading ? (
                <div className="h-40 flex items-center justify-center">
                    <div className="w-6 h-6 border-2 border-accent-amber border-t-transparent rounded-full animate-spin" />
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
                        {displayedCameras.map((cam) => (
                            <CameraTile
                                key={cam.id}
                                camera={cam}
                                tick={tick}
                                alert={alerts.find((al) => al.camera_id === String(cam.id)) ?? null}
                                onClick={() => setSelected(cam)}
                            />
                        ))}
                    </div>

                    {filteredCameras.length > displayLimit && (
                        <div className="mt-12 flex justify-center pb-12">
                            <button
                                onClick={() => setDisplayLimit((prev) => prev + 10)}
                                className="px-6 py-3 bg-white/[0.03] hover:bg-white/[0.08] border border-accent-amber/30 text-accent-amber hover:text-white font-black text-xs tracking-widest uppercase rounded-xl transition-all shadow-lg flex items-center gap-2"
                            >
                                Carregar Mais Câmeras (+10) — Exibindo {displayedCameras.length} de {filteredCameras.length}
                            </button>
                        </div>
                    )}
                </>
            )}

            {!loading && !error && filteredCameras.length === 0 && (
                <div className="text-muted italic text-sm">{t('cameras.no_cameras')}</div>
            )}

            <AnimatePresence>
                {selected && <TacticalVideoPlayer camera={selected} onClose={handleClose} />}
            </AnimatePresence>
        </main>
    );
}

const CameraTile = React.memo(function CameraTile({
    camera,
    tick,
    alert,
    onClick,
}: {
    camera: Camera;
    tick: number;
    alert: CameraAlert | null;
    onClick: () => void;
}) {
    const { t } = useTranslation();
    const defaultThumb = camera.thumbnail_url 
        ? `${API_BASE}${camera.thumbnail_url}?t=${tick}`
        : camera.video_id 
            ? `https://img.youtube.com/vi/${camera.video_id}/hqdefault.jpg`
            : '';

    const [imgSrc, setImgSrc] = useState<string>(defaultThumb);

    useEffect(() => {
        if (camera.thumbnail_url) {
            setImgSrc(`${API_BASE}${camera.thumbnail_url}?t=${tick}`);
        } else if (camera.video_id) {
            setImgSrc(`https://img.youtube.com/vi/${camera.video_id}/hqdefault.jpg`);
        }
    }, [camera.thumbnail_url, camera.video_id, tick]);

    const alertLabel = alert
        ? alert.type === 'WEAPON'
            ? t('cameras.alert_weapon')
            : t('cameras.alert_fall')
        : null;

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn(
                'intelligence-card group cursor-pointer border border-white/5 hover:border-accent-emerald/40 transition-all shadow-lg',
                alert && 'ring-2 ring-red-500 animate-pulse shadow-[0_0_20px_rgba(239,68,68,0.5)]'
            )}
            onClick={onClick}
        >
            <div className="aspect-video relative bg-neutral-900 overflow-hidden">
                <img
                    src={imgSrc}
                    onError={() => {
                        if (camera.thumbnail_url) {
                            setImgSrc(`${API_BASE}${camera.thumbnail_url}`);
                        }
                    }}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    alt={camera.nome}
                    loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-2 py-1 rounded-full border border-white/10">
                    <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[9px] font-black tracking-widest text-red-400 uppercase">C4ISR LIVE</span>
                </div>

                {alertLabel && (
                    <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-red-600/80 backdrop-blur-sm px-2 py-1 rounded-full border border-red-400/50 animate-pulse">
                        <span className="text-[9px] font-black tracking-widest text-white uppercase">{alertLabel}</span>
                    </div>
                )}

                <div className="absolute bottom-3 left-3 right-3 glass-panel rounded-lg border border-white/10 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-1 mb-1">
                        <h3 className="text-xs font-black uppercase tracking-tight line-clamp-1 leading-tight text-white">{camera.nome}</h3>
                        {camera.tipo_area && (
                            <span className="text-[8px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-accent-amber shrink-0 uppercase">
                                {camera.tipo_area.split('/')[0].trim()}
                            </span>
                        )}
                    </div>
                    {camera.endereco && (
                        <p className="text-[10px] text-accent-amber font-mono truncate flex items-center gap-1">
                            <MapPin className="w-2.5 h-2.5 text-accent-amber shrink-0" />
                            <span className="truncate">{camera.endereco}</span>
                        </p>
                    )}
                    {camera.local && (
                        <p className="text-[9px] text-muted font-mono mt-0.5 truncate flex items-center gap-1">
                            <Compass className="w-2.5 h-2.5 text-muted shrink-0" />
                            <span className="truncate">{camera.local} ({camera.pais || 'BR'})</span>
                        </p>
                    )}
                </div>
            </div>
        </motion.div>
    );
});
