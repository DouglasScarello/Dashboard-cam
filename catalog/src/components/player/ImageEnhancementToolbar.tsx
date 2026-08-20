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
                {/* 1. Lado Esquerdo: Modos de Ferramenta Interativa */}
                <div className="flex items-center gap-1.5 bg-black/50 p-1 rounded-xl border border-white/5 shrink-0">
                    <button
                        onClick={() => handleToolSelect('PAN')}
                        title="Modo Navegação e Arrastar (Pan)"
                        className={`p-2 rounded-lg flex items-center gap-1.5 text-xs font-bold transition-all ${
                            activeTool === 'PAN'
                                ? 'bg-accent-emerald text-black shadow-[0_0_12px_rgba(16,185,129,0.4)]'
                                : 'text-muted hover:text-white hover:bg-white/5'
                        }`}
                    >
                        <Move className="w-4 h-4" />
                        <span className="hidden lg:inline">PAN</span>
                    </button>

                    <button
                        onClick={() => handleToolSelect('LOUPE')}
                        title="Lupa Tática Digital de Alta Resolução"
                        className={`p-2 rounded-lg flex items-center gap-1.5 text-xs font-bold transition-all ${
                            activeTool === 'LOUPE'
                                ? 'bg-accent-amber text-black shadow-[0_0_12px_rgba(245,158,11,0.4)]'
                                : 'text-muted hover:text-white hover:bg-white/5'
                        }`}
                    >
                        <Search className="w-4 h-4" />
                        <span className="hidden lg:inline">LUPA</span>
                    </button>

                    <button
                        onClick={() => handleToolSelect('ROI_SELECT')}
                        title="Selecionar Região de Interesse para Perícia"
                        className={`p-2 rounded-lg flex items-center gap-1.5 text-xs font-bold transition-all ${
                            activeTool === 'ROI_SELECT'
                                ? 'bg-cyan-400 text-black shadow-[0_0_12px_rgba(34,211,238,0.4)]'
                                : 'text-muted hover:text-white hover:bg-white/5'
                        }`}
                    >
                        <Crop className="w-4 h-4" />
                        <span className="hidden lg:inline">CROP ROI</span>
                    </button>

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

                {/* 2. Centro: BOTÕES PERICIAIS DE 1-CLIQUE (Destaque Primário) */}
                <div className="flex items-center gap-2 bg-black/60 p-1.5 rounded-xl border border-white/10 shrink-0">
                    {/* Botão MELHORAR PLACA */}
                    <button
                        onClick={() => handleQuickEnhance('plate')}
                        title="Aprimoramento Forense de Placas Veiculares (Homografia + ALPR + 4x SR)"
                        className="px-3.5 py-2 bg-emerald-950/60 hover:bg-emerald-900/80 border-2 border-emerald-500/60 hover:border-emerald-400 text-emerald-300 rounded-lg text-xs font-black flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(16,185,129,0.3)] hover:scale-105 active:scale-95"
                    >
                        <Car className="w-4 h-4 text-emerald-400 animate-pulse" />
                        <span className="tracking-wider">MELHORAR PLACAS</span>
                        <span className="text-[9px] px-1 py-0.5 bg-emerald-500/30 text-emerald-200 rounded font-bold">ALPR</span>
                    </button>

                    {/* Botão MELHORAR ROSTO */}
                    <button
                        onClick={() => handleQuickEnhance('face')}
                        title="Restauração Facial Forense sem Alucinação (CNJ 484 + CLAHE + 4x SR)"
                        className="px-3.5 py-2 bg-cyan-950/60 hover:bg-cyan-900/80 border-2 border-cyan-500/60 hover:border-cyan-400 text-cyan-300 rounded-lg text-xs font-black flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:scale-105 active:scale-95"
                    >
                        <UserCheck className="w-4 h-4 text-cyan-400 animate-pulse" />
                        <span className="tracking-wider">MELHORAR ROSTO</span>
                        <span className="text-[9px] px-1 py-0.5 bg-cyan-500/30 text-cyan-200 rounded font-bold">CNJ 484</span>
                    </button>

                    {/* Botão SUPER-NITIDEZ 4X */}
                    <button
                        onClick={() => handleQuickEnhance('general')}
                        title="Super-Resolução 4x Geral com Desconvolução de Movimento"
                        className="px-3 py-2 bg-amber-950/60 hover:bg-amber-900/80 border border-amber-500/60 hover:border-amber-400 text-amber-300 rounded-lg text-xs font-black flex items-center gap-1.5 transition-all shadow-[0_0_12px_rgba(245,158,11,0.25)] hover:scale-105 active:scale-95"
                    >
                        <Zap className="w-4 h-4 text-amber-400" />
                        <span className="tracking-wider">SUPER-NITIDEZ 4X</span>
                    </button>
                </div>

                {/* 3. Lado Direito: Presets de Visão, Sliders, Snapshot e Fullscreen */}
                <div className="flex items-center gap-1.5 shrink-0">
                    <button
                        onClick={() => applyPreset('NIGHT_VISION')}
                        className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black flex items-center gap-1 transition-all ${
                            activePreset === 'NIGHT_VISION'
                                ? 'bg-green-500 text-black font-black shadow-[0_0_10px_rgba(34,197,94,0.3)]'
                                : 'text-green-400 hover:bg-green-500/10'
                        }`}
                        title="Visão Noturna NVG P43"
                    >
                        <Moon className="w-3.5 h-3.5" />
                        <span className="hidden xl:inline">NVG</span>
                    </button>

                    <button
                        onClick={() => applyPreset('THERMAL_IRONBOW')}
                        className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black flex items-center gap-1 transition-all ${
                            activePreset === 'THERMAL_IRONBOW'
                                ? 'bg-orange-500 text-black font-black shadow-[0_0_10px_rgba(249,115,22,0.3)]'
                                : 'text-orange-400 hover:bg-orange-500/10'
                        }`}
                        title="Térmica FLIR Ironbow"
                    >
                        <Flame className="w-3.5 h-3.5" />
                        <span className="hidden xl:inline">FLIR</span>
                    </button>

                    <button
                        onClick={() => {
                            tacticalAudio.playClick();
                            setShowSlidersPanel(!showSlidersPanel);
                        }}
                        className={`p-2 rounded-lg border transition-all ${
                            showSlidersPanel
                                ? 'bg-white/20 text-white border-white/30'
                                : 'bg-white/5 hover:bg-white/10 text-muted hover:text-white border-white/10'
                        }`}
                        title="Ajuste Granular de Filtros"
                    >
                        <Sliders className="w-4 h-4" />
                    </button>

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
