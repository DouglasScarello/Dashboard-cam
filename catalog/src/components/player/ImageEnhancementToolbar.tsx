import React, { useState } from 'react';
import { 
    ImageFilters, 
    VisualPreset, 
    InteractiveTool, 
    EnhanceTargetType,
    DEFAULT_IMAGE_FILTERS 
} from './types/player.types';
import { tacticalAudio } from './audio/TacticalAudioEngine';
import { 
    Move, 
    Search, 
    Crop, 
    Sliders, 
    RotateCcw, 
    Camera, 
    FileText, 
    Maximize2, 
    Minimize2,
    Sparkles, 
    Flame, 
    Moon, 
    UserCheck,
    Car,
    Zap
} from 'lucide-react';

interface ImageEnhancementToolbarProps {
    filters: ImageFilters;
    onFiltersChange: (filters: ImageFilters) => void;
    activeTool: InteractiveTool;
    onToolChange: (tool: InteractiveTool) => void;
    zoomLevel: number;
    onZoomReset: () => void;
    onTakeSnapshot: () => void;
    onOpenForensicDrawer: (initialType?: EnhanceTargetType) => void;
    isFullscreen: boolean;
    onToggleFullscreen: () => void;
}

export const ImageEnhancementToolbar: React.FC<ImageEnhancementToolbarProps> = ({
    filters,
    onFiltersChange,
    activeTool,
    onToolChange,
    zoomLevel,
    onZoomReset,
    onTakeSnapshot,
    onOpenForensicDrawer,
    isFullscreen,
    onToggleFullscreen,
}) => {
    const [activePreset, setActivePreset] = useState<VisualPreset>('NORMAL');
    const [showSlidersPanel, setShowSlidersPanel] = useState<boolean>(false);

    // =========================================================================
    // APLICAÇÃO DE PRESETS DE 1-CLIQUE
    // =========================================================================
    const applyPreset = (preset: VisualPreset) => {
        setActivePreset(preset);
        tacticalAudio.playClick();

        switch (preset) {
            case 'NORMAL':
                onFiltersChange(DEFAULT_IMAGE_FILTERS);
                break;
            case 'NIGHT_VISION':
                onFiltersChange({
                    ...DEFAULT_IMAGE_FILTERS,
                    brightness: 0.15,
                    contrast: 1.4,
                    nightVisionEnabled: true,
                    nightVisionNoise: 0.12,
                    sharpenEnabled: true,
                    sharpenStrength: 0.4,
                    thermalPalette: 'none',
                    edgeEnabled: false,
                });
                break;
            case 'THERMAL_IRONBOW':
                onFiltersChange({
                    ...DEFAULT_IMAGE_FILTERS,
                    contrast: 1.6,
                    thermalPalette: 'ironbow',
                    nightVisionEnabled: false,
                    edgeEnabled: false,
                });
                break;
            case 'THERMAL_WHITE_HOT':
                onFiltersChange({
                    ...DEFAULT_IMAGE_FILTERS,
                    contrast: 1.8,
                    thermalPalette: 'white_hot',
                    nightVisionEnabled: false,
                    edgeEnabled: false,
                });
                break;
            case 'PLATE_ALPR_OPTIMIZED':
                onFiltersChange({
                    ...DEFAULT_IMAGE_FILTERS,
                    brightness: 0.05,
                    contrast: 1.7,
                    gamma: 1.2,
                    sharpenEnabled: true,
                    sharpenStrength: 0.85,
                    claheEnabled: true,
                    claheAmount: 1.4,
                    claheClipLimit: 3.5,
                    nightVisionEnabled: false,
                    thermalPalette: 'none',
                    edgeEnabled: false,
                });
                break;
            case 'SOBEL_EDGES':
                onFiltersChange({
                    ...DEFAULT_IMAGE_FILTERS,
                    edgeEnabled: true,
                    edgeThreshold: 0.12,
                    nightVisionEnabled: false,
                    thermalPalette: 'none',
                });
                break;
        }
    };

    const updateFilter = <K extends keyof ImageFilters>(key: K, value: ImageFilters[K]) => {
        onFiltersChange({
            ...filters,
            [key]: value,
        });
    };

    const handleToolSelect = (tool: InteractiveTool) => {
        tacticalAudio.playClick();
        onToolChange(tool);
    };

    const handleQuickEnhance = (target: EnhanceTargetType) => {
        tacticalAudio.playAlert();
        if (target === 'plate') {
            applyPreset('PLATE_ALPR_OPTIMIZED');
        }
        onOpenForensicDrawer(target);
    };

    return (
        <div className="flex flex-col bg-surface border-t border-white/10 select-none font-mono">
            {/* Painel Expansível de Sliders Granulares */}
            {showSlidersPanel && (
                <div className="px-6 py-4 bg-black/60 border-b border-white/5 grid grid-cols-2 sm:grid-cols-4 gap-4 text-[11px] text-white/90">
                    <div>
                        <div className="flex justify-between mb-1">
                            <span className="text-accent-amber font-bold">NITIDEZ (UNSHARP):</span>
                            <span>{filters.sharpenEnabled ? `${(filters.sharpenStrength * 100).toFixed(0)}%` : 'OFF'}</span>
                        </div>
                        <input
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={filters.sharpenStrength}
                            onChange={(e) => {
                                updateFilter('sharpenStrength', parseFloat(e.target.value));
                                if (!filters.sharpenEnabled) updateFilter('sharpenEnabled', true);
                            }}
                            className="w-full accent-accent-amber cursor-pointer"
                        />
                    </div>

                    <div>
                        <div className="flex justify-between mb-1">
                            <span className="text-accent-emerald font-bold">CLAHE / ADAPTATIVO:</span>
                            <span>{filters.claheEnabled ? `${filters.claheClipLimit.toFixed(1)}x` : 'OFF'}</span>
                        </div>
                        <input
                            type="range"
                            min="1.0"
                            max="5.0"
                            step="0.2"
                            value={filters.claheClipLimit}
                            onChange={(e) => {
                                updateFilter('claheClipLimit', parseFloat(e.target.value));
                                if (!filters.claheEnabled) updateFilter('claheEnabled', true);
                            }}
                            className="w-full accent-accent-emerald cursor-pointer"
                        />
                    </div>

                    <div>
                        <div className="flex justify-between mb-1">
                            <span>CONTRASTE:</span>
                            <span>{filters.contrast.toFixed(2)}x</span>
                        </div>
                        <input
                            type="range"
                            min="0.2"
                            max="2.5"
                            step="0.05"
                            value={filters.contrast}
                            onChange={(e) => updateFilter('contrast', parseFloat(e.target.value))}
                            className="w-full accent-white cursor-pointer"
                        />
                    </div>

                    <div>
                        <div className="flex justify-between mb-1">
                            <span>BRILHO:</span>
                            <span>{filters.brightness.toFixed(2)}</span>
                        </div>
                        <input
                            type="range"
                            min="-0.8"
                            max="0.8"
                            step="0.05"
                            value={filters.brightness}
                            onChange={(e) => updateFilter('brightness', parseFloat(e.target.value))}
                            className="w-full accent-white cursor-pointer"
                        />
                    </div>
                </div>
            )}

            {/* Barra Principal de Ferramentas */}
            <div className="h-16 px-4 flex items-center justify-between gap-3 overflow-x-auto">
                {/* 1. Lado Esquerdo: Ferramentas Interativas */}
                <div className="flex items-center gap-1.5 shrink-0">
                    {/* Removido botões de Lupa e Crop ROI a pedido do usuário, mantendo interface limpa */}
                    {zoomLevel > 1.0 && (
                        <button
                            onClick={() => {
                                tacticalAudio.playClick();
                                onZoomReset();
                            }}
                            title="Resetar Zoom (1.0x)"
                            className="px-2 py-1 bg-white/10 hover:bg-white/20 text-white rounded text-[10px] font-black tracking-wider transition-all"
                        >
                            RESET 1X
                        </button>
                    )}
                </div>

                {/* 2. Centro: STATUS REAL DA IA (FUSÃO MULTI-FRAME) e BOTÃO PERICIAL */}
                <div className="flex items-center gap-2 bg-black/60 p-1.5 rounded-xl border border-white/10 shrink-0">
                    <div className="px-3.5 py-2 bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 rounded-lg text-xs font-black flex items-center gap-2 shadow-[0_0_10px_rgba(16,185,129,0.1)]">
                        <Car className="w-4 h-4 text-emerald-400" />
                        <span className="tracking-wider">ALPR ATIVO</span>
                        <span className="text-[9px] px-1 py-0.5 bg-emerald-500/20 text-emerald-200 rounded font-bold border border-emerald-500/30 animate-pulse">FUSÃO MULTI-FRAME</span>
                    </div>

                    <button
                        onClick={() => {
                            tacticalAudio.playAlert();
                            onOpenForensicDrawer('plate');
                        }}
                        title="Abrir laboratório forense com Inteligência Artificial Generativa"
                        className="px-3.5 py-2 ml-2 bg-indigo-950/60 hover:bg-indigo-900/80 border-2 border-indigo-500/60 hover:border-indigo-400 text-indigo-300 rounded-lg text-xs font-black flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(99,102,241,0.3)] hover:scale-105 active:scale-95"
                    >
                        <Zap className="w-4 h-4 text-indigo-400" />
                        <span className="tracking-wider">LABORATÓRIO FORENSE</span>
                        <span className="text-[9px] px-1 py-0.5 bg-indigo-500/30 text-indigo-200 rounded font-bold">HAT / CODEFORMER</span>
                    </button>
                </div>

                {/* 3. Lado Direito: Snapshot e Fullscreen */}
                <div className="flex items-center gap-1.5 shrink-0">
                    <button
                        onClick={() => {
                            tacticalAudio.playShutter();
                            onTakeSnapshot();
                        }}
                        className="p-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white rounded-lg text-xs font-black flex items-center gap-1.5 transition-all"
                        title="Capturar Snapshot da Câmera"
                    >
                        <Camera className="w-4 h-4 text-emerald-400" />
                    </button>

                    <button
                        onClick={() => {
                            tacticalAudio.playClick();
                            onToggleFullscreen();
                        }}
                        className="p-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-white transition-colors"
                        title="Tela Cheia Tática"
                    >
                        {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    </button>
                </div>
            </div>
        </div>
    );
};
