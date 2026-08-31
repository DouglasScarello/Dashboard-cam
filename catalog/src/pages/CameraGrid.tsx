import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
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
    // Liveness real vinda do backend (camera_liveness.py) — muitas destas
    // câmeras são lives de terceiros no YouTube que saem do ar ou trocam de
    // video_id sem aviso. Sem isso, o app abria um player pra um stream que
    // já não existe mais (tela "Vídeo indisponível").
    live_confirmed?: boolean;
    confirmed_dead?: boolean;
    live_status?: string;
    live_checked_at?: string | null;
    // "SNAPSHOT_JPEG" (Ontario 511, NZTA, ...) = imagem única por
    // request, não stream HLS contínuo — ver SnapshotImagePlayer.tsx.
    stream_format?: string | null;
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
    const [searchParams] = useSearchParams();
    const [cameras, setCameras] = useState<Camera[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [tick, setTick] = useState(() => Math.floor(Date.now() / 5000));
    const [selected, setSelected] = useState<Camera | null>(null);
    const [alerts, setAlerts] = useState<CameraAlert[]>([]);
    
    // Controles de Busca e Filtro
    const [searchQuery, setSearchQuery] = useState('');
    const [countryFilter, setCountryFilter] = useState('');
    const [geoFilter, setGeoFilter] = useState<'ALL' | 'NO_GEO' | 'WITH_GEO'>('ALL');
    const [areaFilter, setAreaFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState<'ALL' | 'ONLINE' | 'OFFLINE'>('ALL');
    const [displayLimit, setDisplayLimit] = useState(10);
    const [totalCameras, setTotalCameras] = useState(0);

    const [uniqueCountries, setUniqueCountries] = useState<string[]>([]);
    const [uniqueAreas, setUniqueAreas] = useState<string[]>([]);

    useEffect(() => {
        fetch(`${(import.meta as any).env.VITE_API_URL || 'http://localhost:8001'}/api/metadata/countries`)
            .then(res => res.json())
            .then(data => setUniqueCountries(data))
            .catch(err => console.error("Erro countries:", err));

        fetch(`${(import.meta as any).env.VITE_API_URL || 'http://localhost:8001'}/api/metadata/areas`)
            .then(res => res.json())
            .then(data => setUniqueAreas(data))
            .catch(err => console.error("Erro areas:", err));
    }, []);

    useEffect(() => {
        let mounted = true;
        setLoading(true);

        const params = new URLSearchParams();
        params.append('limit', displayLimit.toString());
        params.append('offset', '0');
        
        if (countryFilter) params.append('country', countryFilter);
        if (areaFilter) params.append('area', areaFilter);
        if (statusFilter !== 'ALL') params.append('status', statusFilter);
        if (geoFilter === 'NO_GEO' || geoFilter === 'WITH_GEO') params.append('geo', geoFilter);
        if (searchQuery) params.append('search', searchQuery);

        fetch(`${(import.meta as any).env.VITE_API_URL || 'http://localhost:8001'}/api/cameras?${params.toString()}`)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then(data => {
                if (mounted) {
                    setCameras(data.cameras || data);
                    setTotalCameras(data.total || data.length || 0);
                    setLoading(false);
                }
            })
            .catch(err => {
                console.error("Erro ao carregar câmeras", err);
                if (mounted) {
                    setError(String(err));
                    setLoading(false);
                }
            });

        return () => { mounted = false; };
    }, [countryFilter, areaFilter, statusFilter, geoFilter, searchQuery, displayLimit]);

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

    const [offlineNotice, setOfflineNotice] = useState<string | null>(null);

    // Deep-link vindo do AlertCenter (?camera=<id>): abre a câmera do alerta
    // — mas só se ela estiver confirmadamente ao vivo agora. Muitas câmeras
    // são de fontes de terceiros que saem do ar; abrir mesmo assim só
    // mostra "Vídeo indisponível" pro usuário sem explicação nenhuma.
    //
    // Achado real (2026-08-31): desde que a listagem principal passou a
    // paginar do lado do servidor (`displayLimit`), o array local
    // `cameras` quase nunca contém a câmera do alerta (ela pode estar em
    // qualquer página, entre milhares). Buscar direto por id no backend
    // em vez de procurar só no lote já carregado.
    useEffect(() => {
        const camId = searchParams.get('camera');
        if (!camId) return;
        let cancelled = false;
        fetch(`${(import.meta as any).env.VITE_API_URL || 'http://localhost:8001'}/api/cameras/${camId}`)
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((match: Camera) => {
                if (cancelled) return;
                if (match.confirmed_dead) {
                    setOfflineNotice(`${match.nome}: esta câmera não está confirmadamente ao vivo no momento.`);
                } else {
                    setSelected(match);
                }
            })
            .catch(() => {
                if (!cancelled) setOfflineNotice(`Câmera #${camId}: não encontrada.`);
            });
        return () => { cancelled = true; };
    }, [searchParams]);

    const handleClose = useCallback(() => setSelected(null), []);

    const handleTileClick = useCallback((cam: Camera) => {
        if (cam.confirmed_dead) {
            setOfflineNotice(`${cam.nome}: esta transmissão encerrou e não está mais disponível no YouTube.`);
        } else {
            setSelected(cam);
        }
    }, []);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') handleClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [handleClose]);

    // A filtragem agora é 100% Server-Side via banco de dados!
    const displayedCameras = cameras;

    const activeAlertMap = useMemo(() => {
        const map = new Map<string, CameraAlert>();
        for (const a of alerts) {
            map.set(String(a.camera_id), a);
        }
        return map;
    }, [alerts]);

    const handleNext = useCallback(() => {
        if (!selected) return;
        const idx = cameras.findIndex(c => c.id === selected.id);
        if (idx !== -1) {
            const nextIdx = (idx + 1) % cameras.length;
            setSelected(cameras[nextIdx]);
        }
    }, [selected, cameras]);

    const handlePrev = useCallback(() => {
        if (!selected) return;
        const idx = cameras.findIndex(c => c.id === selected.id);
        if (idx !== -1) {
            const prevIdx = (idx - 1 + cameras.length) % cameras.length;
            setSelected(cameras[prevIdx]);
        }
    }, [selected, cameras]);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            {/* Header & Status C4ISR */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 pb-4 border-b border-white/5">
                <div>
                    <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                        <Video className="w-4 h-4 text-accent-emerald" /> {t('cameras.title')}
                    </h2>
                    <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                        REDE AO VIVO: {totalCameras} TRANSMISSÕES REAIS ATIVAS
                    </p>
                </div>

                {/* Filtros Geográficos */}
                <div className="flex flex-col sm:flex-row flex-wrap items-end sm:items-center gap-4">
                    {/* Filtro de Sem Local */}
                    <div className="flex items-center gap-1.5 bg-black/40 border border-white/10 rounded-lg p-1">
                        <button
                            onClick={() => { setGeoFilter('ALL'); setDisplayLimit(10); }}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-[10px] font-black tracking-wider uppercase transition-all",
                                geoFilter === 'ALL' ? "bg-white/10 text-white" : "text-muted hover:text-white"
                            )}
                        >
                            TODAS
                        </button>
                        <button
                            onClick={() => { setGeoFilter('WITH_GEO'); setDisplayLimit(10); }}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-[10px] font-black tracking-wider uppercase transition-all",
                                geoFilter === 'WITH_GEO' ? "bg-accent-emerald/20 text-accent-emerald" : "text-muted hover:text-white"
                            )}
                        >
                            📍 COM LOCAL
                        </button>
                        <button
                            onClick={() => { setGeoFilter('NO_GEO'); setDisplayLimit(10); }}
                            className={cn(
                                "px-3 py-1.5 rounded-md text-[10px] font-black tracking-wider uppercase transition-all",
                                geoFilter === 'NO_GEO' ? "bg-accent-amber/20 text-accent-amber" : "text-muted hover:text-white"
                            )}
                        >
                            ❓ SEM LOCAL
                        </button>
                    </div>

                    {/* Select de Países */}
                    <div className="relative">
                        <select
                            value={countryFilter}
                            onChange={(e) => { setCountryFilter(e.target.value); setDisplayLimit(10); }}
                            className="h-[34px] appearance-none bg-black/40 border border-white/10 rounded-lg pl-3 pr-8 text-[10px] font-black tracking-wider uppercase text-white focus:outline-none focus:border-accent-emerald/50"
                        >
                            <option value="">🌐 TODOS OS PAÍSES</option>
                            {uniqueCountries.map(c => (
                                <option key={c} value={c}>{c}</option>
                            ))}
                        </select>
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-white/50">
                            <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>

                    {/* Select de Área */}
                    <div className="relative">
                        <select
                            value={areaFilter}
                            onChange={(e) => { setAreaFilter(e.target.value); setDisplayLimit(10); }}
                            className="h-[34px] appearance-none bg-black/40 border border-white/10 rounded-lg pl-3 pr-8 text-[10px] font-black tracking-wider uppercase text-white focus:outline-none focus:border-accent-emerald/50"
                        >
                            <option value="">🏷️ TODAS AS ÁREAS</option>
                            {uniqueAreas.map(a => (
                                <option key={a} value={a}>{a}</option>
                            ))}
                        </select>
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-white/50">
                            <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>

                    {/* Select de Status */}
                    <div className="relative">
                        <select
                            value={statusFilter}
                            onChange={(e) => { setStatusFilter(e.target.value as any); setDisplayLimit(10); }}
                            className="h-[34px] appearance-none bg-black/40 border border-white/10 rounded-lg pl-3 pr-8 text-[10px] font-black tracking-wider uppercase text-white focus:outline-none focus:border-accent-emerald/50"
                        >
                            <option value="ALL">🔴 TODOS STATUS</option>
                            <option value="ONLINE">✅ APENAS ONLINE</option>
                            <option value="OFFLINE">❌ APENAS OFFLINE</option>
                        </select>
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-white/50">
                            <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
                        </div>
                    </div>
                </div>
            </div>

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

            {offlineNotice && (
                <div className="bg-amber-500/10 text-accent-amber px-4 py-3 rounded-lg border border-accent-amber/30 text-xs font-mono mb-6 flex items-center justify-between gap-4">
                    <span>{offlineNotice}</span>
                    <button onClick={() => setOfflineNotice(null)} className="text-accent-amber/70 hover:text-accent-amber shrink-0">✕</button>
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
                                onClick={() => handleTileClick(cam)}
                            />
                        ))}
                    </div>

                    {totalCameras > displayLimit && (
                        <div className="mt-12 flex justify-center pb-12">
                            <button
                                onClick={() => setDisplayLimit((prev) => prev + 10)}
                                className="px-6 py-3 bg-white/[0.03] hover:bg-white/[0.08] border border-accent-amber/30 text-accent-amber hover:text-white font-black text-xs tracking-widest uppercase rounded-xl transition-all shadow-lg flex items-center gap-2"
                            >
                                Carregar Mais Câmeras (+10) — Exibindo {displayedCameras.length} de {totalCameras}
                            </button>
                        </div>
                    )}
                </>
            )}

            {!loading && !error && cameras.length === 0 && (
                <div className="text-muted italic text-sm">{t('cameras.no_cameras')}</div>
            )}

            <AnimatePresence>
                {selected && (
                    <TacticalVideoPlayer 
                        camera={selected} 
                        onClose={handleClose} 
                        onNext={handleNext}
                        onPrev={handlePrev}
                    />
                )}
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
    // Achado real (2026-08-31): `tick` muda a cada 5s (mesmo ritmo do
    // polling de alertas), mas o backend só gera uma thumbnail nova a
    // cada 30s (THUMBNAIL_TTL em camera_grid_server.py) — trocar a `src`
    // da imagem 6x mais rápido do que ela pode mudar de verdade
    // interrompe o carregamento antes de terminar (mesma classe de bug
    // do player HLS que reiniciava a cada 5s e nunca terminava de
    // bufferizar). `thumbTick` arredonda pra um "balde" de 30s — a URL só
    // muda quando a imagem por trás dela genuinamente pode ter mudado.
    const thumbTick = Math.floor(tick / 6);
    const defaultThumb = camera.thumbnail_url
        ? `${API_BASE}${camera.thumbnail_url}?t=${thumbTick}`
        : camera.video_id
            ? `https://img.youtube.com/vi/${camera.video_id}/hqdefault.jpg`
            : '';

    const [imgSrc, setImgSrc] = useState<string>(defaultThumb);

    useEffect(() => {
        if (camera.thumbnail_url) {
            setImgSrc(`${API_BASE}${camera.thumbnail_url}?t=${thumbTick}`);
        } else if (camera.video_id) {
            setImgSrc(`https://img.youtube.com/vi/${camera.video_id}/hqdefault.jpg`);
        }
    }, [camera.thumbnail_url, camera.video_id, thumbTick]);

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
                'intelligence-card group border border-white/5 hover:border-accent-emerald/40 transition-all shadow-lg',
                camera.confirmed_dead ? 'cursor-not-allowed opacity-50 grayscale' : 'cursor-pointer',
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
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                {camera.confirmed_dead ? (
                    <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-2 py-1 rounded-full border border-white/10">
                        <div className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
                        <span className="text-[9px] font-black tracking-widest text-neutral-400 uppercase">OFFLINE — TRANSMISSÃO ENCERRADA</span>
                    </div>
                ) : camera.live_confirmed ? (
                    <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-2 py-1 rounded-full border border-white/10">
                        <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                        <span className="text-[9px] font-black tracking-widest text-red-400 uppercase">C4ISR LIVE</span>
                    </div>
                ) : (
                    <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm px-2 py-1 rounded-full border border-white/10">
                        <div className="w-1.5 h-1.5 rounded-full bg-accent-amber" />
                        <span className="text-[9px] font-black tracking-widest text-accent-amber uppercase">NÃO VERIFICADA</span>
                    </div>
                )}

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
