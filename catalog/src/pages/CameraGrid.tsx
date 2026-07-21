import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Video, X, Volume2, VolumeX } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import Hls from 'hls.js';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const API_BASE = 'http://localhost:8001';

interface Camera {
    id: string | number;
    nome: string;
    local?: string | null;
    thumbnail_url: string;
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

    useEffect(() => {
        let mounted = true;
        setLoading(true);
        fetch(`${API_BASE}/api/cameras`)
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

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-sm font-black tracking-widest uppercase text-muted flex items-center gap-2">
                    <Video className="w-4 h-4 text-accent-blue" /> {t('cameras.title')}
                </h2>
                <span className="text-[10px] font-mono text-muted">
                    {cameras.length} {t('cameras.online_suffix')}
                </span>
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
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
                    {[...cameras]
                        .sort((a, b) => {
                            const aAlert = alerts.some((al) => al.camera_id === String(a.id)) ? 1 : 0;
                            const bAlert = alerts.some((al) => al.camera_id === String(b.id)) ? 1 : 0;
                            return bAlert - aAlert;
                        })
                        .map((cam) => (
                            <CameraTile
                                key={cam.id}
                                camera={cam}
                                tick={tick}
                                alert={alerts.find((al) => al.camera_id === String(cam.id)) ?? null}
                                onClick={() => setSelected(cam)}
                            />
                        ))}
                </div>
            )}

            {!loading && !error && cameras.length === 0 && (
                <div className="text-muted italic text-sm">{t('cameras.no_cameras')}</div>
            )}

            <AnimatePresence>
                {selected && <LiveModal camera={selected} onClose={handleClose} />}
            </AnimatePresence>
        </main>
    );
}

function CameraTile({
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
    const src = `${API_BASE}${camera.thumbnail_url}?t=${tick}`;
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
                'intelligence-card group cursor-pointer',
                alert && 'ring-2 ring-red-500 animate-pulse shadow-[0_0_20px_rgba(239,68,68,0.5)]'
            )}
            onClick={onClick}
        >
            <div className="aspect-video relative bg-neutral-900 overflow-hidden">
                <img
                    src={src}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    alt={camera.nome}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent opacity-80" />

                <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/40 backdrop-blur-sm px-2 py-1 rounded-full border border-white/10">
                    <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[9px] font-black tracking-widest text-red-400 uppercase">LIVE</span>
                </div>

                {alertLabel && (
                    <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-red-600/80 backdrop-blur-sm px-2 py-1 rounded-full border border-red-400/50 animate-pulse">
                        <span className="text-[9px] font-black tracking-widest text-white uppercase">{alertLabel}</span>
                    </div>
                )}

                <div className="absolute bottom-3 left-3 right-3 glass-panel rounded-lg border border-white/10 px-3 py-2">
                    <h3 className="text-xs font-black uppercase tracking-tight line-clamp-1 leading-tight">{camera.nome}</h3>
                    {camera.local && (
                        <p className="text-[10px] text-muted font-mono mt-0.5 truncate">{camera.local}</p>
                    )}
                </div>
            </div>
        </motion.div>
    );
}

function LiveModal({ camera, onClose }: { camera: Camera; onClose: () => void }) {
    const { t } = useTranslation();
    const [liveUrl, setLiveUrl] = useState<string | null>(null);
    const [fetchError, setFetchError] = useState<string | null>(null);
    const [muted, setMuted] = useState(true);
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const hlsRef = useRef<Hls | null>(null);

    useEffect(() => {
        let mounted = true;
        setLiveUrl(null);
        setFetchError(null);
        fetch(`${API_BASE}/api/cameras/${camera.id}/live_url`)
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: { url?: string }) => {
                if (!mounted) return;
                if (data?.url) setLiveUrl(data.url);
                else setFetchError(t('cameras.no_stream'));
            })
            .catch((err) => {
                if (mounted) setFetchError(String(err));
            });
        return () => {
            mounted = false;
        };
    }, [camera.id, t]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video || !liveUrl) return;

        if (Hls.isSupported()) {
            const hls = new Hls();
            hlsRef.current = hls;
            hls.loadSource(liveUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.ERROR, (_evt, data) => {
                if (data.fatal) setFetchError(`HLS: ${data.type}`);
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = liveUrl;
        } else {
            setFetchError(t('cameras.hls_unsupported'));
        }

        return () => {
            if (hlsRef.current) {
                hlsRef.current.destroy();
                hlsRef.current = null;
            }
        };
    }, [liveUrl, t]);

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/80 backdrop-blur-sm">
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="bg-surface border border-white/5 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
            >
                <div className="h-16 px-6 border-b border-white/5 flex items-center justify-between bg-white/[0.02]">
                    <div className="flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        <span className="text-[10px] font-black tracking-widest text-muted uppercase">{camera.nome}</span>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-lg transition-colors">
                        <X className="w-5 h-5 text-muted" />
                    </button>
                </div>

                <div className="flex-1 bg-black relative flex items-center justify-center min-h-[40vh]">
                    {liveUrl ? (
                        <video
                            ref={videoRef}
                            autoPlay
                            muted={muted}
                            controls={false}
                            playsInline
                            className="w-full h-full max-h-[70vh] object-contain"
                        />
                    ) : (
                        <div className={cn('text-sm font-mono py-20', fetchError ? 'text-red-500' : 'text-muted')}>
                            {fetchError || t('common.loading')}
                        </div>
                    )}

                    {liveUrl && (
                        <button
                            onClick={() => setMuted((m) => !m)}
                            className="absolute bottom-4 right-4 w-10 h-10 rounded-full bg-black/60 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors"
                        >
                            {muted ? <VolumeX className="w-4 h-4 text-white" /> : <Volume2 className="w-4 h-4 text-accent-emerald" />}
                        </button>
                    )}
                </div>
            </motion.div>
        </div>
    );
}
