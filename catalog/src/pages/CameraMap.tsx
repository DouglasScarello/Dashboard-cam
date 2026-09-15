import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { MapContainer, TileLayer, Marker, Popup, useMapEvents } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, Crosshair, Play } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';
import { TacticalVideoPlayer } from '../components/player/TacticalVideoPlayer';
import L from 'leaflet';

// Fix for default Leaflet icon not showing up in React
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

// Ícones Customizados C4ISR
const greenIcon = new L.Icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

const redIcon = new L.Icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

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
    live_confirmed?: boolean;
    confirmed_dead?: boolean;
}

// Componente para sincronizar os Bounds do mapa com o backend
const BoundingBoxFetcher = ({ setCameras }: { setCameras: any }) => {
    const map = useMapEvents({
        moveend: () => {
            fetchCamerasInBounds();
        },
        zoomend: () => {
            fetchCamerasInBounds();
        }
    });

    const fetchCamerasInBounds = () => {
        const bounds = map.getBounds();
        const north = bounds.getNorth();
        const south = bounds.getSouth();
        const east = bounds.getEast();
        const west = bounds.getWest();

        fetch(`${API_BASE}/api/cameras/map?north=${north}&south=${south}&east=${east}&west=${west}&limit=2000`)
            .then(res => res.json())
            .then(data => setCameras(data))
            .catch(err => console.error("Erro bbox:", err));
    };

    // Fetch initial
    useEffect(() => {
        fetchCamerasInBounds();
    }, []);

    return null;
};

export default function CameraMap() {
    const { t } = useTranslation();
    const [cameras, setCameras] = useState<Camera[]>([]);

    const filteredCameras = cameras;
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selected, setSelected] = useState<Camera | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true);
        fetch(`${API_BASE}/api/cameras?limit=5000`)
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
        return () => { mounted = false; };
    }, []);

    const validCameras = useMemo(() => {
        return cameras.filter(c => c.lat !== null && c.long !== null && c.lat !== undefined && c.long !== undefined);
    }, [cameras]);

    const handleNext = useCallback(() => {
        if (!selected) return;
        const idx = validCameras.findIndex(c => c.id === selected.id);
        if (idx !== -1) {
            setSelected(validCameras[(idx + 1) % validCameras.length]);
        }
    }, [selected, validCameras]);

    const handlePrev = useCallback(() => {
        if (!selected) return;
        const idx = validCameras.findIndex(c => c.id === selected.id);
        if (idx !== -1) {
            setSelected(validCameras[(idx - 1 + validCameras.length) % validCameras.length]);
        }
    }, [selected, validCameras]);

    const handleClose = useCallback(() => setSelected(null), []);

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center bg-black">
                <div className="w-8 h-8 border-2 border-accent-emerald border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex-1 flex items-center justify-center bg-black text-red-500 font-mono">
                ERRO AO CARREGAR MAPA: {error}
            </div>
        );
    }

    const centerLat = validCameras.length > 0 ? validCameras[0].lat! : -14.2350;
    const centerLong = validCameras.length > 0 ? validCameras[0].long! : -51.9253;

    return (
        <main className="flex-1 relative bg-black font-mono flex flex-col">
            <style>{`
                .leaflet-popup-content-wrapper {
                    background-color: #111827 !important;
                    color: white !important;
                    border: 1px solid rgba(16, 185, 129, 0.4);
                    border-radius: 0.5rem;
                }
                .leaflet-popup-tip {
                    background-color: #111827 !important;
                }
                .leaflet-container {
                    background-color: #000 !important;
                }
            `}</style>

            <div className="absolute top-4 left-4 z-[400] bg-black/80 backdrop-blur-md px-4 py-2 border border-accent-emerald/40 rounded-lg pointer-events-none">
                <h1 className="text-accent-emerald font-black tracking-widest text-sm flex items-center gap-2">
                    <Crosshair className="w-4 h-4" />
                    C4ISR GEO-TRACKING
                </h1>
                <p className="text-white/60 text-[10px] mt-1">
                    EXIBINDO {validCameras.length} ALVOS GEO-REFERENCIADOS
                </p>
            </div>

            <div className="absolute inset-0 z-0">
                <MapContainer 
                    center={[centerLat, centerLong]} 
                    zoom={4} 
                    style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
                    zoomControl={true}
                >
                    <TileLayer
                        attribution='&copy; <a href="https://www.google.com/maps">Google Maps</a>'
                        url="http://mt0.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}"
                        maxZoom={20}
                    />

                    {validCameras.map(cam => (
                        <Marker 
                            key={cam.id} 
                            position={[cam.lat!, cam.long!]}
                            icon={cam.confirmed_dead ? redIcon : greenIcon}
                        >
                            <Popup>
                                <div className="p-1 min-w-[220px]">
                                    <h3 className="text-xs font-black text-accent-emerald tracking-tight truncate mb-2">
                                        {cam.nome}
                                    </h3>
                                    
                                    <div className="relative aspect-video bg-black rounded overflow-hidden mb-2 border border-white/10">
                                        <img 
                                            src={cam.thumbnail_url ? `${API_BASE}${cam.thumbnail_url}` : `https://img.youtube.com/vi/${cam.video_id}/hqdefault.jpg`}
                                            alt={cam.nome}
                                            className="w-full h-full object-cover"
                                            onError={(e) => { e.currentTarget.src = 'https://via.placeholder.com/320x180/000000/10B981?text=SEM+IMAGEM'; }}
                                        />
                                        {cam.confirmed_dead ? (
                                            <div className="absolute top-1 left-1 bg-red-600/80 px-1 rounded text-[8px] font-bold">OFFLINE</div>
                                        ) : (
                                            <div className="absolute top-1 left-1 bg-accent-emerald/80 text-black px-1 rounded text-[8px] font-bold flex items-center gap-1">
                                                <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse" />
                                                LIVE
                                            </div>
                                        )}
                                    </div>

                                    <div className="text-[9px] text-gray-400 font-mono mb-2 leading-tight">
                                        <p className="truncate"><MapPin className="w-3 h-3 inline mr-1 text-accent-amber" />{cam.endereco || cam.local}</p>
                                        <p className="mt-1">LAT: {cam.lat!.toFixed(4)} | LNG: {cam.long!.toFixed(4)}</p>
                                    </div>

                                    {!cam.confirmed_dead && (
                                        <button 
                                            onClick={() => setSelected(cam)}
                                            className="w-full bg-accent-emerald/20 hover:bg-accent-emerald/40 border border-accent-emerald text-accent-emerald text-[10px] font-black py-1.5 rounded transition-colors flex items-center justify-center gap-1 cursor-pointer"
                                        >
                                            <Play className="w-3 h-3" />
                                            ABRIR FEED TÁTICO
                                        </button>
                                    )}
                                </div>
                            </Popup>
                        </Marker>
                    ))}
                </MapContainer>
            </div>

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
