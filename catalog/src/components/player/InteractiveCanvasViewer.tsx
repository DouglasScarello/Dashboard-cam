import React, { useRef, useEffect, useState, useCallback } from 'react';
import { 
    ImageFilters, 
    InteractiveTool, 
    TransformMatrix, 
    LoupeState, 
    ROISelection, 
    CameraData,
    EnhanceTargetType 
} from './types/player.types';
import { tacticalAudio } from './audio/TacticalAudioEngine';
import { Search, Lock, Unlock, Crop, Zap, Sparkles } from 'lucide-react';

interface InteractiveCanvasViewerProps {
    camera: CameraData;
    videoId: string | null;
    filters: ImageFilters;
    activeTool: InteractiveTool;
    onToolChange?: (tool: InteractiveTool) => void;
    onROISelected?: (roiDataUrl: string, roiRect: { x: number; y: number; width: number; height: number }) => void;
    zoomLevel: number;
    onZoomChange: (zoom: number) => void;
    onQuickEnhanceZoomedArea?: (type: EnhanceTargetType, croppedBase64: string) => void;
}

export const InteractiveCanvasViewer: React.FC<InteractiveCanvasViewerProps> = ({
    camera,
    videoId,
    filters,
    activeTool,
    onROISelected,
    zoomLevel,
    onZoomChange,
    onQuickEnhanceZoomedArea,
}) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const loupeCanvasRef = useRef<HTMLCanvasElement | null>(null);

    // Matriz de Transformação (Pan & Zoom de 1.0x a 16.0x)
    const [transform, setTransform] = useState<TransformMatrix>({
        scale: 1.0,
        translateX: 0,
        translateY: 0,
    });

    const isDraggingRef = useRef(false);
    const dragStartRef = useRef({ x: 0, y: 0 });
    const lastTransformRef = useRef(transform);
    lastTransformRef.current = transform;

    // Sincronizar zoomLevel externo
    useEffect(() => {
        if (zoomLevel !== transform.scale) {
            setTransform(prev => ({
                ...prev,
                scale: Math.max(1.0, Math.min(16.0, zoomLevel)),
                translateX: zoomLevel === 1.0 ? 0 : prev.translateX,
                translateY: zoomLevel === 1.0 ? 0 : prev.translateY,
            }));
        }
    }, [zoomLevel]);

    // Estado da Lupa Tática
    const [loupe, setLoupe] = useState<LoupeState>({
        enabled: activeTool === 'LOUPE',
        x: 0,
        y: 0,
        zoomFactor: 4.0,
        radius: 100,
        isLocked: false,
    });

    useEffect(() => {
        setLoupe(prev => ({ ...prev, enabled: activeTool === 'LOUPE' }));
    }, [activeTool]);

    // Estado da Seleção de ROI
    const [roi, setRoi] = useState<ROISelection>({
        startX: 0,
        startY: 0,
        endX: 0,
        endY: 0,
        isSelecting: false,
    });

    // Posição do cursor
    const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 });

    // =========================================================================
    // CSS FILTER GENERATOR COM NITIDEZ DINÂMICA ADAPTATIVA SOB ZOOM
    // =========================================================================
    const getCssFilterString = (): string => {
        const parts: string[] = [];

        // Nitidez Adaptativa extra quando o usuário dá Zoom (> 1.0x)
        if (transform.scale > 1.2) {
            const zoomSharpness = Math.min(2.5, 1.0 + (transform.scale - 1.0) * 0.15);
            parts.push(`contrast(${zoomSharpness.toFixed(2)})`);
            parts.push(`brightness(1.02)`);
        } else {
            if (filters.contrast !== 1.0) {
                parts.push(`contrast(${filters.contrast})`);
            }
            if (filters.brightness !== 0.0) {
                parts.push(`brightness(${1.0 + filters.brightness})`);
            }
        }

        if (filters.nightVisionEnabled) {
            parts.push('brightness(1.25) contrast(1.9) saturate(0) sepia(1) hue-rotate(85deg) saturate(600%)');
        } else if (filters.thermalPalette === 'ironbow') {
            parts.push('contrast(2.0) saturate(3.0) hue-rotate(180deg) brightness(1.1)');
        } else if (filters.thermalPalette === 'white_hot') {
            parts.push('grayscale(100%) invert(100%) contrast(2.2) brightness(0.9)');
        } else if (filters.sharpenEnabled || filters.claheEnabled) {
            parts.push('contrast(2.4) brightness(1.15) grayscale(100%)');
        } else if (filters.edgeEnabled) {
            parts.push('grayscale(100%) contrast(3.5) invert(100%)');
        }

        return parts.length > 0 ? parts.join(' ') : 'none';
    };

    // =========================================================================
    // ZOOM COM RODA DO MOUSE (PIVOT INVARIANTE NO CURSOR)
    // =========================================================================
    const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
        e.preventDefault();
        e.stopPropagation();

        const container = containerRef.current;
        if (!container) return;

        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const delta = e.deltaY < 0 ? 1.25 : 0.8;
        const currentScale = lastTransformRef.current.scale;
        let newScale = Math.max(1.0, Math.min(16.0, currentScale * delta));
        newScale = Math.round(newScale * 100) / 100;

        if (newScale === 1.0) {
            setTransform({ scale: 1.0, translateX: 0, translateY: 0 });
            onZoomChange(1.0);
            return;
        }

        const factor = newScale / currentScale;
        const newTranslateX = mouseX - factor * (mouseX - lastTransformRef.current.translateX);
        const newTranslateY = mouseY - factor * (mouseY - lastTransformRef.current.translateY);

        setTransform({
            scale: newScale,
            translateX: newTranslateX,
            translateY: newTranslateY,
        });
        onZoomChange(newScale);
    }, [onZoomChange]);

    // =========================================================================
    // PAN VIA ARRASTO DO MOUSE & CONTROLE DE LUPA / ROI
    // =========================================================================
    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        if (activeTool === 'ROI_SELECT') {
            setRoi({
                startX: mouseX,
                startY: mouseY,
                endX: mouseX,
                endY: mouseY,
                isSelecting: true,
            });
            return;
        }

        if (activeTool === 'LOUPE' && e.shiftKey) {
            setLoupe(prev => {
                const nextLocked = !prev.isLocked;
                if (nextLocked) tacticalAudio.playLockOn();
                return { ...prev, isLocked: nextLocked };
            });
            return;
        }

        if (e.button === 0) {
            isDraggingRef.current = true;
            dragStartRef.current = {
                x: e.clientX - lastTransformRef.current.translateX,
                y: e.clientY - lastTransformRef.current.translateY,
            };
        }
    };

    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
        const container = containerRef.current;
        if (!container) return;
        const rect = container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        setCursorPos({ x: mouseX, y: mouseY });

        if (activeTool === 'LOUPE' && !loupe.isLocked) {
            setLoupe(prev => ({ ...prev, x: mouseX, y: mouseY }));
        }

        if (activeTool === 'ROI_SELECT' && roi.isSelecting) {
            setRoi(prev => ({ ...prev, endX: mouseX, endY: mouseY }));
            return;
        }

        if (isDraggingRef.current && transform.scale > 1.0) {
            const nextX = e.clientX - dragStartRef.current.x;
            const nextY = e.clientY - dragStartRef.current.y;
            setTransform(prev => ({ ...prev, translateX: nextX, translateY: nextY }));
        }
    };

    const handleMouseUp = () => {
        isDraggingRef.current = false;

        if (activeTool === 'ROI_SELECT' && roi.isSelecting) {
            setRoi(prev => ({ ...prev, isSelecting: false }));
            handleROIExtraction();
        }
    };

    // =========================================================================
    // RECONSTRUÇÃO DA ÁREA COM ZOOM ATUAL VIA IA 4X
    // =========================================================================
    const handleEnhanceZoomedArea = async (type: EnhanceTargetType = 'face') => {
        tacticalAudio.playAlert();
        try {
            const res = await fetch(`http://localhost:8001/api/cameras/${camera.id}/snapshot`);
            if (res.ok) {
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onloadend = () => {
                    const fullBase64 = reader.result as string;
                    
                    const img = new Image();
                    img.src = fullBase64;
                    img.onload = () => {
                        const container = containerRef.current;
                        if (!container) return;
                        const rect = container.getBoundingClientRect();

                        // Normalização da janela visível sob zoom
                        const normX = Math.max(0, -transform.translateX / (rect.width * transform.scale));
                        const normY = Math.max(0, -transform.translateY / (rect.height * transform.scale));
                        const normW = Math.min(1.0, 1.0 / transform.scale);
                        const normH = Math.min(1.0, 1.0 / transform.scale);

                        const cropX = Math.max(0, Math.floor(normX * img.width));
                        const cropY = Math.max(0, Math.floor(normY * img.height));
                        const cropW = Math.min(img.width - cropX, Math.floor(normW * img.width));
                        const cropH = Math.min(img.height - cropY, Math.floor(normH * img.height));

                        const cropCanvas = document.createElement('canvas');
                        cropCanvas.width = Math.max(cropW, 30);
                        cropCanvas.height = Math.max(cropH, 30);
                        const ctx = cropCanvas.getContext('2d');
                        if (!ctx) return;

                        ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropCanvas.width, cropCanvas.height);
                        const croppedBase64 = cropCanvas.toDataURL('image/png');

                        tacticalAudio.playLockOn();
                        if (onQuickEnhanceZoomedArea) {
                            onQuickEnhanceZoomedArea(type, croppedBase64);
                        } else if (onROISelected) {
                            onROISelected(croppedBase64, { x: cropX, y: cropY, width: cropW, height: cropH });
                        }
                    };
                };
                reader.readAsDataURL(blob);
            }
        } catch (e) {
            console.error('Falha ao capturar crop com zoom:', e);
        }
    };

    const handleROIExtraction = async () => {
        const w = Math.abs(roi.endX - roi.startX);
        const h = Math.abs(roi.endY - roi.startY);
        if (w < 15 || h < 15) return;

        try {
            const res = await fetch(`http://localhost:8001/api/cameras/${camera.id}/snapshot`);
            if (res.ok) {
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onloadend = () => {
                    const fullBase64 = reader.result as string;
                    const img = new Image();
                    img.src = fullBase64;
                    img.onload = () => {
                        const container = containerRef.current;
                        if (!container) return;
                        const rect = container.getBoundingClientRect();
                        const left = Math.min(roi.startX, roi.endX);
                        const top = Math.min(roi.startY, roi.endY);

                        const normX = (left - transform.translateX) / (rect.width * transform.scale);
                        const normY = (top - transform.translateY) / (rect.height * transform.scale);
                        const normW = w / (rect.width * transform.scale);
                        const normH = h / (rect.height * transform.scale);

                        const cropX = Math.max(0, Math.floor(normX * img.width));
                        const cropY = Math.max(0, Math.floor(normY * img.height));
                        const cropW = Math.min(img.width - cropX, Math.floor(normW * img.width));
                        const cropH = Math.min(img.height - cropY, Math.floor(normH * img.height));

                        const cropCanvas = document.createElement('canvas');
                        cropCanvas.width = Math.max(cropW, 20);
                        cropCanvas.height = Math.max(cropH, 20);
                        const ctx = cropCanvas.getContext('2d');
                        if (!ctx) return;

                        ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropCanvas.width, cropCanvas.height);
                        const croppedDataUrl = cropCanvas.toDataURL('image/png');

                        tacticalAudio.playLockOn();
                        if (onROISelected) {
                            onROISelected(croppedDataUrl, { x: cropX, y: cropY, width: cropW, height: cropH });
                        }
                    };
                };
                reader.readAsDataURL(blob);
            }
        } catch (e) {
            console.error('Falha ao extrair ROI:', e);
        }
    };

    let cursorStyle = 'default';
    if (activeTool === 'ROI_SELECT') cursorStyle = 'crosshair';
    else if (activeTool === 'LOUPE') cursorStyle = 'none';
    else if (transform.scale > 1.0) cursorStyle = isDraggingRef.current ? 'grabbing' : 'grab';

    const effectiveVideoId = videoId || String(camera.id);

    return (
        <div
            ref={containerRef}
            onWheel={handleWheel}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            className="relative w-full h-full bg-black overflow-hidden select-none flex items-center justify-center"
            style={{ cursor: cursorStyle }}
        >
            {/* Camada de Vídeo Tático Isolado com Pan & Zoom Matrix */}
            <div
                style={{
                    transform: `translate(${transform.translateX}px, ${transform.translateY}px) scale(${transform.scale})`,
                    transformOrigin: '0 0',
                    filter: getCssFilterString(),
                    width: '100%',
                    height: '100%',
                    transition: isDraggingRef.current ? 'none' : 'transform 0.05s ease-out',
                }}
                className="w-full h-full relative overflow-hidden bg-black flex items-center justify-center pointer-events-none select-none"
            >
                {/* Embed Tático de Stream com Letterbox Crop */}
                <iframe
                    src={`https://www.youtube-nocookie.com/embed/${effectiveVideoId}?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1&rel=0&iv_load_policy=3&showinfo=0&disablekb=1&fs=0`}
                    title={camera.nome}
                    className="w-[115%] h-[115%] min-h-[115%] max-w-none border-0 pointer-events-none select-none object-cover"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                />
            </div>

            {/* BOTÃO FLUTUANTE DE RECONSTRUÇÃO IA 4X QUANDO SOB ZOOM */}
            {transform.scale >= 2.0 && (
                <div className="absolute top-16 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 bg-black/90 backdrop-blur-md p-1.5 rounded-xl border border-accent-amber/50 shadow-[0_0_20px_rgba(245,158,11,0.4)] animate-bounce">
                    <button
                        onClick={() => handleEnhanceZoomedArea('face')}
                        className="px-3 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-black font-black text-xs rounded-lg flex items-center gap-1.5 transition-all shadow-lg"
                        title="Reconstruir Rostos na Área com Zoom Atual"
                    >
                        <Zap className="w-3.5 h-3.5" />
                        <span>RECONSTRUIR ROSTO (IA 4X)</span>
                    </button>

                    <button
                        onClick={() => handleEnhanceZoomedArea('plate')}
                        className="px-3 py-1.5 bg-accent-emerald hover:bg-emerald-400 text-black font-black text-xs rounded-lg flex items-center gap-1.5 transition-all shadow-lg"
                        title="Reconstruir Placa na Área com Zoom Atual"
                    >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>RECONSTRUIR PLACA (IA 4X)</span>
                    </button>
                </div>
            )}

            {/* Retículo de Seleção de ROI */}
            {activeTool === 'ROI_SELECT' && (roi.isSelecting || Math.abs(roi.endX - roi.startX) > 10) && (
                <div
                    className="absolute border-2 border-accent-emerald bg-accent-emerald/15 pointer-events-none z-30 shadow-[0_0_15px_rgba(16,185,129,0.5)]"
                    style={{
                        left: Math.min(roi.startX, roi.endX),
                        top: Math.min(roi.startY, roi.endY),
                        width: Math.abs(roi.endX - roi.startX),
                        height: Math.abs(roi.endY - roi.startY),
                    }}
                >
                    <div className="absolute -top-5 left-0 bg-accent-emerald text-black text-[9px] font-mono font-black px-1.5 py-0.5 rounded-t">
                        ROI FORENSE: {Math.abs(roi.endX - roi.startX)}x{Math.abs(roi.endY - roi.startY)}px
                    </div>
                </div>
            )}

            {/* Lupa Tática Digital Flutuante */}
            {activeTool === 'LOUPE' && (
                <div
                    className="absolute pointer-events-none z-40"
                    style={{
                        left: loupe.x - loupe.radius,
                        top: loupe.y - loupe.radius,
                        width: loupe.radius * 2,
                        height: loupe.radius * 2,
                    }}
                >
                    <div className="w-full h-full rounded-full border-4 border-accent-emerald bg-black/90 shadow-[0_0_40px_rgba(0,0,0,0.9)] overflow-hidden relative flex items-center justify-center">
                        <div
                            className="w-[200%] h-[200%] absolute overflow-hidden pointer-events-none"
                            style={{
                                transform: `scale(${loupe.zoomFactor})`,
                                filter: getCssFilterString(),
                            }}
                        >
                            <iframe
                                src={`https://www.youtube-nocookie.com/embed/${effectiveVideoId}?autoplay=1&mute=1&playsinline=1&controls=0&modestbranding=1&rel=0&iv_load_policy=3&showinfo=0&disablekb=1&fs=0`}
                                title="Loupe Sub-Stream"
                                className="w-full h-full border-0 pointer-events-none object-cover"
                            />
                        </div>

                        {/* Retículo Mil-dot */}
                        <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                            <svg width="100" height="100" viewBox="0 0 100 100" className="stroke-accent-emerald fill-none">
                                <circle cx="50" cy="50" r="30" strokeWidth="1" strokeDasharray="3 3" />
                                <circle cx="50" cy="50" r="4" strokeWidth="1.5" className="stroke-accent-amber" />
                                <line x1="50" y1="20" x2="50" y2="40" strokeWidth="1.5" />
                                <line x1="50" y1="60" x2="50" y2="80" strokeWidth="1.5" />
                                <line x1="20" y1="50" x2="40" y2="50" strokeWidth="1.5" />
                                <line x1="60" y1="50" x2="80" y2="50" strokeWidth="1.5" />
                            </svg>
                        </div>
                    </div>

                    <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 bg-black/90 backdrop-blur-md px-2 py-0.5 rounded border border-white/10 text-[9px] font-mono font-bold text-accent-emerald whitespace-nowrap flex items-center gap-1">
                        {loupe.isLocked ? <Lock className="w-2.5 h-2.5 text-accent-amber" /> : <Unlock className="w-2.5 h-2.5 text-accent-emerald" />}
                        <span>LUPA {loupe.zoomFactor}x {loupe.isLocked ? '[TRAVADA]' : '[SHIFT+CLICK TRAVAR]'}</span>
                    </div>
                </div>
            )}

            {/* Mini-map Radar */}
            {transform.scale > 1.0 && (
                <div className="absolute bottom-4 right-4 z-30 bg-black/85 backdrop-blur-md p-2 rounded-lg border border-accent-emerald/40 shadow-2xl flex flex-col items-center">
                    <div className="w-32 h-20 bg-neutral-900 rounded border border-white/10 relative overflow-hidden flex items-center justify-center">
                        <div
                            className="border-2 border-accent-amber bg-accent-amber/20 absolute"
                            style={{
                                width: `${Math.max(10, 100 / transform.scale)}%`,
                                height: `${Math.max(10, 100 / transform.scale)}%`,
                                left: `${Math.max(0, Math.min(90, (-transform.translateX / (containerRef.current?.clientWidth || 1000) / transform.scale) * 100))}%`,
                                top: `${Math.max(0, Math.min(90, (-transform.translateY / (containerRef.current?.clientHeight || 600) / transform.scale) * 100))}%`,
                            }}
                        />
                    </div>
                    <div className="text-[8px] font-mono text-accent-emerald/90 mt-1 uppercase tracking-wider font-bold">
                        RADAR VIEWPORT ({transform.scale.toFixed(1)}x)
                    </div>
                </div>
            )}
        </div>
    );
};
