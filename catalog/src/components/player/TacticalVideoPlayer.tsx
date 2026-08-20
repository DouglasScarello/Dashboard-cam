import React, { useRef, useState, useEffect, useCallback } from 'react';
import { 
    CameraData, 
    ImageFilters, 
    DEFAULT_IMAGE_FILTERS, 
    InteractiveTool, 
    StreamTelemetry,
    EnhanceTargetType 
} from './types/player.types';
import { InteractiveCanvasViewer } from './InteractiveCanvasViewer';
import { TacticalHUD } from './TacticalHUD';
import { ImageEnhancementToolbar } from './ImageEnhancementToolbar';
import { ForensicPlateInspector } from './ForensicPlateInspector';
import { tacticalAudio } from './audio/TacticalAudioEngine';
import { X, Volume2, VolumeX, Pause, Play, AlertTriangle, Sparkles } from 'lucide-react';

interface TacticalVideoPlayerProps {
    camera: CameraData;
    onClose: () => void;
}

export const TacticalVideoPlayer: React.FC<TacticalVideoPlayerProps> = ({ camera, onClose }) => {
    const containerRef = useRef<HTMLDivElement | null>(null);

    // Identificador de Vídeo
    const initialVideoId = camera.video_id || (camera.url && camera.url.includes('v=') ? camera.url.split('v=')[1].split('&')[0] : null);
    const [videoId, setVideoId] = useState<string | null>(initialVideoId);

    // Estados de Streaming & Controle
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [streamError, setStreamError] = useState<string | null>(null);
    const [isMuted, setIsMuted] = useState<boolean>(true);
    const [isFrozen, setIsFrozen] = useState<boolean>(false);
    const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
    const [showHUD, setShowHUD] = useState<boolean>(true);
    const [isProcessingEnhance, setIsProcessingEnhance] = useState<boolean>(false);

    // Estados de Ferramentas & Filtros
    const [filters, setFilters] = useState<ImageFilters>(DEFAULT_IMAGE_FILTERS);
    const [activeTool, setActiveTool] = useState<InteractiveTool>('PAN');
    const [zoomLevel, setZoomLevel] = useState<number>(1.0);

    // Estados Forenses
    const [forensicDrawerOpen, setForensicDrawerOpen] = useState<boolean>(false);
    const [activeForensicImage, setActiveForensicImage] = useState<string | null>(null);
    const [forensicTargetType, setForensicTargetType] = useState<EnhanceTargetType>('plate');

    // Telemetria
    const [telemetry, setTelemetry] = useState<StreamTelemetry>({
        fps: 30,
        bitrateMbps: 4.5,
        resolution: '1080p FHD',
        bufferSeconds: 1.2,
        latencyMs: 120,
        isLive: true,
        qualityLevels: ['1080p', '720p', '480p'],
        currentLevel: 0,
        protocol: 'HLS',
    });

    // =========================================================================
    // 1. CARREGAMENTO E RESOLUÇÃO DA CÂMERA
    // =========================================================================
    useEffect(() => {
        let isMounted = true;
        tacticalAudio.playRadioSquelch();

        fetch(`http://localhost:8001/api/cameras/${camera.id}/live_url`)
            .then(res => res.json())
            .then(data => {
                if (!isMounted) return;
                if (data.video_id) setVideoId(data.video_id);
            })
            .catch(() => {
                // Fallback silencioso usando camera.id ou videoId inicial
            });

        return () => {
            isMounted = false;
        };
    }, [camera.id]);

    // =========================================================================
    // 2. CAPTURA DE SNAPSHOT FORENSE MASTER & DISPARO DE IA EM TEMPO REAL
    // =========================================================================
    const handleOpenForensicEnhance = useCallback(async (type: EnhanceTargetType = 'plate', customImageBase64?: string) => {
        setForensicTargetType(type);
        setIsProcessingEnhance(true);
        tacticalAudio.playAlert();

        // 1. Aplica filtro em tempo real no feed visível imediatamente para resposta visual instantânea
        if (type === 'plate') {
            setFilters(prev => ({
                ...prev,
                sharpenEnabled: true,
                claheEnabled: true,
                contrast: 1.8,
                brightness: 0.05,
            }));
        } else if (type === 'face') {
            setFilters(prev => ({
                ...prev,
                claheEnabled: true,
                contrast: 1.35,
                brightness: 0.05,
            }));
        } else {
            setFilters(prev => ({
                ...prev,
                sharpenEnabled: true,
                contrast: 1.5,
                brightness: 0.0,
            }));
        }

        // 2. Se já veio um recorte sob zoom customizado
        if (customImageBase64) {
            setActiveForensicImage(customImageBase64);
            setForensicDrawerOpen(true);
            setIsProcessingEnhance(false);
            tacticalAudio.playLockOn();
            return;
        }

        // 3. Captura o frame em alta resolução
        try {
            const res = await fetch(`http://localhost:8001/api/cameras/${camera.id}/snapshot`);
            if (res.ok) {
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onloadend = () => {
                    setActiveForensicImage(reader.result as string);
                    setForensicDrawerOpen(true);
                    setIsProcessingEnhance(false);
                    tacticalAudio.playLockOn();
                };
                reader.readAsDataURL(blob);
            } else {
                setIsProcessingEnhance(false);
            }
        } catch (e) {
            console.error('Falha ao capturar snapshot para perícia:', e);
            setIsProcessingEnhance(false);
        }
    }, [camera.id]);

    const handleTakeSnapshot = useCallback(async () => {
        tacticalAudio.playShutter();

        try {
            const res = await fetch(`http://localhost:8001/api/cameras/${camera.id}/snapshot`);
            if (res.ok) {
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onloadend = () => {
                    setActiveForensicImage(reader.result as string);
                    setForensicTargetType('general');
                    setForensicDrawerOpen(true);
                };
                reader.readAsDataURL(blob);
            }
        } catch (e) {
            console.error('Falha ao capturar snapshot:', e);
        }
    }, [camera.id]);

    // =========================================================================
    // 3. ATALHOS DE TECLADO TÁTICOS
    // =========================================================================
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

            switch (e.key.toLowerCase()) {
                case '1':
                    e.preventDefault();
                    handleOpenForensicEnhance('plate');
                    break;
                case '2':
                    e.preventDefault();
                    handleOpenForensicEnhance('face');
                    break;
                case '3':
                    e.preventDefault();
                    handleOpenForensicEnhance('general');
                    break;
                case ' ':
                    e.preventDefault();
                    setIsFrozen(prev => !prev);
                    tacticalAudio.playClick();
                    break;
                case 'f':
                    e.preventDefault();
                    toggleFullscreen();
                    break;
                case 'm':
                    e.preventDefault();
                    setIsMuted(prev => !prev);
                    tacticalAudio.playClick();
                    break;
                case 's':
                    e.preventDefault();
                    handleTakeSnapshot();
                    break;
                case 'h':
                    e.preventDefault();
                    setShowHUD(prev => !prev);
                    tacticalAudio.playClick();
                    break;
                case 'z':
                    e.preventDefault();
                    setZoomLevel(1.0);
                    tacticalAudio.playClick();
                    break;
                case 'escape':
                    if (forensicDrawerOpen) {
                        setForensicDrawerOpen(false);
                    } else if (document.fullscreenElement) {
                        document.exitFullscreen().catch(() => {});
                    } else {
                        onClose();
                    }
                    break;
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [isFrozen, forensicDrawerOpen, handleTakeSnapshot, handleOpenForensicEnhance, onClose]);

    const toggleFullscreen = () => {
        if (!containerRef.current) return;
        if (!document.fullscreenElement) {
            containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
        } else {
            document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
        }
    };

    return (
        <div
            ref={containerRef}
            className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-md flex flex-col overflow-hidden font-mono select-none"
        >
            {/* Cabeçalho do Player */}
            <div className="h-12 px-5 bg-surface/90 border-b border-white/10 flex items-center justify-between z-30">
                <div className="flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-accent-emerald animate-pulse" />
                    <h2 className="text-sm font-black text-white tracking-widest uppercase truncate max-w-md">
                        {camera.nome}
                    </h2>
                    <span className="text-[10px] text-accent-amber font-bold bg-black/50 px-2 py-0.5 rounded border border-white/10">
                        #{camera.id}
                    </span>
                </div>

                <div className="flex items-center gap-2">
                    <span className="hidden lg:inline text-[9px] text-white/40 tracking-wider">
                        [1: PLACAS] [2: ROSTOS] [3: NITIDEZ 4X] [ESPAÇO: PAUSA] [F: FULLSCREEN] [S: SNAPSHOT] [Z: RESET]
                    </span>

                    <button
                        onClick={() => {
                            tacticalAudio.playClick();
                            onClose();
                        }}
                        className="p-1.5 hover:bg-white/10 rounded-lg text-muted hover:text-white transition-colors"
                        title="Fechar Visualizador Tático (ESC)"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </div>

            {/* Viewport Interativo Central */}
            <div className="relative flex-1 bg-black flex items-center justify-center overflow-hidden">
                {/* Viewport com Pan, Zoom (1x a 16x) e Lupa */}
                <InteractiveCanvasViewer
                    camera={camera}
                    videoId={videoId}
                    filters={filters}
                    activeTool={activeTool}
                    onToolChange={setActiveTool}
                    zoomLevel={zoomLevel}
                    onZoomChange={setZoomLevel}
                    onROISelected={(roiDataUrl) => {
                        handleOpenForensicEnhance('plate', roiDataUrl);
                    }}
                    onQuickEnhanceZoomedArea={(type, croppedBase64) => {
                        handleOpenForensicEnhance(type, croppedBase64);
                    }}
                />

                {/* HUD Tático Sobreposto */}
                <TacticalHUD
                    telemetry={telemetry}
                    camera={camera}
                    filterLabel={filters.nightVisionEnabled ? 'NVG' : filters.thermalPalette !== 'none' ? 'FLIR' : filters.sharpenEnabled ? 'ALPR' : 'RGB'}
                    isFrozen={isFrozen}
                    zoomLevel={zoomLevel}
                    showHUD={showHUD}
                />

                {/* Indicador de Processamento Pericial */}
                {isProcessingEnhance && (
                    <div className="absolute top-16 left-1/2 -translate-x-1/2 bg-black/90 border border-accent-emerald text-accent-emerald px-4 py-2 rounded-xl text-xs font-black tracking-widest flex items-center gap-2 shadow-[0_0_25px_rgba(16,185,129,0.5)] z-50 animate-pulse">
                        <Sparkles className="w-4 h-4 animate-spin" />
                        <span>PROCESSANDO PERÍCIA NEURAL 4X...</span>
                    </div>
                )}
            </div>

            {/* Barra Inferior de Ferramentas Táticas com os 3 Botões de Melhoria */}
            <ImageEnhancementToolbar
                filters={filters}
                onFiltersChange={setFilters}
                activeTool={activeTool}
                onToolChange={setActiveTool}
                zoomLevel={zoomLevel}
                onZoomReset={() => setZoomLevel(1.0)}
                onTakeSnapshot={handleTakeSnapshot}
                onOpenForensicDrawer={(type) => handleOpenForensicEnhance(type || 'plate')}
                isFullscreen={isFullscreen}
                onToggleFullscreen={toggleFullscreen}
            />

            {/* Gaveta Lateral Forense para Placas, Rostos e Super-Nitidez */}
            <ForensicPlateInspector
                isOpen={forensicDrawerOpen}
                onClose={() => setForensicDrawerOpen(false)}
                camera={camera}
                initialImageBase64={activeForensicImage}
                initialTargetType={forensicTargetType}
            />
        </div>
    );
};
