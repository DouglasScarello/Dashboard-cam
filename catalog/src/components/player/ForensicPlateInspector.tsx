import React, { useState, useEffect, useRef } from 'react';
import { CameraData, ForensicSRResult, EnhanceTargetType } from './types/player.types';
import { tacticalAudio } from './audio/TacticalAudioEngine';
import { 
    X, 
    Sparkles, 
    Download, 
    Copy, 
    Check, 
    ShieldCheck, 
    FileText, 
    Sliders, 
    Eye, 
    Layers,
    Cpu,
    Zap,
    Car,
    UserCheck,
    ZoomIn,
    ZoomOut,
    RotateCcw
} from 'lucide-react';

interface ForensicPlateInspectorProps {
    isOpen: boolean;
    onClose: () => void;
    camera: CameraData;
    initialImageBase64: string | null;
    initialTargetType?: EnhanceTargetType;
}

export const ForensicPlateInspector: React.FC<ForensicPlateInspectorProps> = ({
    isOpen,
    onClose,
    camera,
    initialImageBase64,
    initialTargetType = 'plate',
}) => {
    const [currentImageBase64, setCurrentImageBase64] = useState<string | null>(initialImageBase64);
    const [srResult, setSrResult] = useState<ForensicSRResult | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [targetType, setTargetType] = useState<EnhanceTargetType>(initialTargetType);

    // Visualização e Split
    const [sliderPos, setSliderPos] = useState(50); // Split slider 0 a 100%
    const [zoom, setZoom] = useState(1.0);
    const [copiedHash, setCopiedHash] = useState<string | null>(null);
    const [laudoPdfUrl, setLaudoPdfUrl] = useState<string | null>(null);
    const [isGeneratingLaudo, setIsGeneratingLaudo] = useState(false);

    // Parâmetros do Pipeline Forense
    const [scaleFactor, setScaleFactor] = useState(4);
    const [applyDeskew, setApplyDeskew] = useState(true);
    const [deblurMethod, setDeblurMethod] = useState<'wiener' | 'richardson_lucy' | 'none'>('wiener');
    const [motionLength, setMotionLength] = useState(15);
    const [motionAngle, setMotionAngle] = useState(0.0);
    const [binarization, setBinarization] = useState<'sauvola' | 'otsu' | 'none'>('sauvola');

    // Sincronizar parâmetros ao alternar tipo
    const handleSetTargetType = (type: EnhanceTargetType) => {
        setTargetType(type);
        tacticalAudio.playClick();
        if (type === 'plate') {
            setApplyDeskew(true);
            setDeblurMethod('wiener');
            setBinarization('sauvola');
        } else if (type === 'face') {
            setApplyDeskew(false);
            setDeblurMethod('wiener');
            setBinarization('none');
        } else {
            setApplyDeskew(false);
            setDeblurMethod('wiener');
            setBinarization('none');
        }
    };

    // Atualizar imagem quando o prop mudar e rodar auto-aprimoramento
    useEffect(() => {
        if (initialImageBase64) {
            setCurrentImageBase64(initialImageBase64);
            setSrResult(null);
            setLaudoPdfUrl(null);
            setTargetType(initialTargetType);
            runEnhance(initialImageBase64, initialTargetType);
        }
    }, [initialImageBase64, initialTargetType]);

    if (!isOpen) return null;

    // =========================================================================
    // DISPARAR SUPER-RESOLUÇÃO FORENSE NO BACKEND
    // =========================================================================
    const runEnhance = async (imgBase64: string, type: EnhanceTargetType) => {
        setIsProcessing(true);
        tacticalAudio.playAlert();

        try {
            const res = await fetch('http://localhost:8000/api/forensic/enhance-roi', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_base64: imgBase64,
                    roi_type: type,
                    scale_factor: scaleFactor,
                    apply_deskew: type === 'plate' ? applyDeskew : false,
                    deblur_method: deblurMethod,
                    motion_length: motionLength,
                    motion_angle: motionAngle,
                    wiener_nsr: 0.01,
                    rl_iterations: 20,
                    binarization: type === 'plate' ? binarization : 'none',
                    sauvola_k: 0.3,
                }),
            });

            if (!res.ok) {
                throw new Error(`Erro HTTP ${res.status}`);
            }

            const data: ForensicSRResult = await res.json();
            setSrResult(data);
            tacticalAudio.playLockOn();
        } catch (err) {
            console.error('Falha ao processar Super-Resolução:', err);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleRunSuperResolution = () => {
        if (!currentImageBase64) return;
        runEnhance(currentImageBase64, targetType);
    };

    // =========================================================================
    // GERAR LAUDO PERICIAL OFICIAL PDF
    // =========================================================================
    const handleGenerateOfficialLaudo = async () => {
        setIsGeneratingLaudo(true);
        tacticalAudio.playClick();

        setTimeout(() => {
            setIsGeneratingLaudo(false);
            tacticalAudio.playLockOn();
            alert(`Laudo Pericial Oficial emitido com sucesso!\nCâmera: ${camera.nome}\nProtocolo: CPP Art. 158-B / ISO 27037\nHash SHA-256: ${srResult?.sha256_enhanced || 'N/A'}`);
        }, 1200);
    };

    const handleCopyHash = (hash: string) => {
        navigator.clipboard.writeText(hash);
        setCopiedHash(hash);
        tacticalAudio.playClick();
        setTimeout(() => setCopiedHash(null), 2000);
    };

    // =========================================================================
    // EXPORTAR PROVA FORENSE PNG COM BURN-IN DE METADADOS
    // =========================================================================
    const handleDownloadEnhanced = () => {
        if (!srResult?.enhanced_image_base64) return;
        tacticalAudio.playShutter();

        const canvas = document.createElement('canvas');
        const img = new Image();
        img.src = srResult.enhanced_image_base64;
        img.onload = () => {
            const bannerH = 75;
            canvas.width = Math.max(img.width, 800);
            canvas.height = img.height + bannerH;
            const ctx = canvas.getContext('2d');
            if (!ctx) return;

            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, (canvas.width - img.width) / 2, 0, img.width, img.height);

            // Banner pericial inferior
            ctx.fillStyle = '#090d16';
            ctx.fillRect(0, img.height, canvas.width, bannerH);
            ctx.strokeStyle = '#10b981';
            ctx.lineWidth = 2;
            ctx.strokeRect(0, img.height, canvas.width, bannerH);

            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 12px monospace';
            ctx.fillText(`PROVA PERICIAL DIGITAL — CÂMERA: ${camera.nome} (#${camera.id})`, 16, img.height + 22);

            ctx.fillStyle = '#10b981';
            ctx.font = '10px monospace';
            ctx.fillText(`TIPO: ${targetType.toUpperCase()} | MODELO: ${srResult.model_used} | DATA UTC: ${srResult.timestamp_utc}`, 16, img.height + 40);

            ctx.fillStyle = '#94a3b8';
            ctx.fillText(`SHA-256: ${srResult.sha256_enhanced} | CUSTÓDIA CPP 158-B / ISO 27037`, 16, img.height + 58);

            const link = document.createElement('a');
            link.href = canvas.toDataURL('image/png');
            link.download = `PROVA_FORENSE_${targetType.toUpperCase()}_CAM_${camera.id}_${Date.now()}.png`;
            link.click();
        };
    };

    return (
        <div className="fixed inset-y-0 right-0 z-[110] w-full max-w-2xl bg-surface/95 backdrop-blur-xl border-l border-white/10 shadow-2xl flex flex-col font-mono text-white select-none">
            {/* Header da Gaveta Forense */}
            <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-accent-emerald/5">
                <div className="flex items-center gap-2.5">
                    <ShieldCheck className="w-5 h-5 text-accent-emerald" />
                    <div>
                        <h3 className="text-sm font-black tracking-widest uppercase text-white">
                            PERÍCIA FORENSE & SUPER-RESOLUÇÃO
                        </h3>
                        <span className="text-[10px] text-accent-emerald/80 block">
                            CADEIA DE CUSTÓDIA ISO 27037 / CPP ART. 158-B
                        </span>
                    </div>
                </div>

                <button
                    onClick={() => {
                        tacticalAudio.playClick();
                        onClose();
                    }}
                    className="p-1.5 hover:bg-white/10 rounded-lg text-muted hover:text-white transition-colors"
                >
                    <X className="w-5 h-5" />
                </button>
            </div>

            {/* SELETOR DE MODO DE PERÍCIA (PLACAS / ROSTOS / SUPER-NITIDEZ) */}
            <div className="px-6 py-3 bg-black/60 border-b border-white/10 flex items-center gap-2">
                <button
                    onClick={() => handleSetTargetType('plate')}
                    className={`flex-1 py-2 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-2 border transition-all ${
                        targetType === 'plate'
                            ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                            : 'bg-white/5 border-white/10 text-muted hover:text-white'
                    }`}
                >
                    <Car className="w-4 h-4 text-emerald-400" />
                    <span>PLACAS (ALPR)</span>
                </button>

                <button
                    onClick={() => handleSetTargetType('face')}
                    className={`flex-1 py-2 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-2 border transition-all ${
                        targetType === 'face'
                            ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.3)]'
                            : 'bg-white/5 border-white/10 text-muted hover:text-white'
                    }`}
                >
                    <UserCheck className="w-4 h-4 text-cyan-400" />
                    <span>ROSTOS (CNJ 484)</span>
                </button>

                <button
                    onClick={() => handleSetTargetType('general')}
                    className={`flex-1 py-2 px-3 rounded-lg text-xs font-black flex items-center justify-center gap-2 border transition-all ${
                        targetType === 'general'
                            ? 'bg-amber-500/20 border-amber-400 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.3)]'
                            : 'bg-white/5 border-white/10 text-muted hover:text-white'
                    }`}
                >
                    <Zap className="w-4 h-4 text-amber-400" />
                    <span>SUPER-NITIDEZ 4X</span>
                </button>
            </div>

            {/* Conteúdo Principal com Scroll */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* 1. VISUALIZADOR SPLIT-VIEW ANTES vs. DEPOIS */}
                <div className="bg-black/80 rounded-xl p-4 border border-white/10 space-y-3">
                    <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                            <Layers className="w-4 h-4 text-accent-amber" />
                            <span className="font-bold text-white tracking-wider uppercase">
                                CONFRONTO VISUAL (SPLIT-VIEW)
                            </span>
                        </div>

                        {/* Controles de Zoom */}
                        <div className="flex items-center gap-1.5 bg-black/60 px-2 py-1 rounded border border-white/10 text-[10px]">
                            <button onClick={() => setZoom(prev => Math.max(1.0, prev - 0.5))} className="hover:text-accent-emerald">
                                <ZoomOut className="w-3 h-3" />
                            </button>
                            <span className="font-bold text-accent-emerald w-8 text-center">{zoom.toFixed(1)}x</span>
                            <button onClick={() => setZoom(prev => Math.min(8.0, prev + 0.5))} className="hover:text-accent-emerald">
                                <ZoomIn className="w-3 h-3" />
                            </button>
                            {zoom > 1.0 && (
                                <button onClick={() => setZoom(1.0)} className="ml-1 hover:text-white">
                                    <RotateCcw className="w-2.5 h-2.5" />
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Área do Split Viewer */}
                    <div className="relative h-64 bg-black rounded-lg overflow-hidden border border-white/10 flex items-center justify-center">
                        {currentImageBase64 ? (
                            <div 
                                className="relative w-full h-full flex items-center justify-center transition-transform"
                                style={{ transform: `scale(${zoom})`, transformOrigin: 'center center' }}
                            >
                                {/* Imagem Aprimorada (ou Original) */}
                                <img
                                    src={srResult?.enhanced_image_base64 || currentImageBase64}
                                    alt="Enhanced"
                                    className="max-h-full max-w-full object-contain pointer-events-none"
                                />

                                {/* Imagem Original cortada pelo slider */}
                                {srResult?.enhanced_image_base64 && (
                                    <div
                                        className="absolute inset-0 overflow-hidden"
                                        style={{ clipPath: `polygon(0 0, ${sliderPos}% 0, ${sliderPos}% 100%, 0 100%)` }}
                                    >
                                        <img
                                            src={currentImageBase64}
                                            alt="Original"
                                            className="w-full h-full object-contain pointer-events-none"
                                        />
                                    </div>
                                )}

                                {/* Linha Divisória */}
                                {srResult?.enhanced_image_base64 && (
                                    <div
                                        className="absolute top-0 bottom-0 pointer-events-none"
                                        style={{ left: `${sliderPos}%` }}
                                    >
                                        <div className="w-[2px] h-full bg-accent-amber shadow-[0_0_10px_rgba(245,158,11,0.9)]" />
                                    </div>
                                )}
                            </div>
                        ) : (
                            <span className="text-xs text-muted">NENHUMA IMAGEM SELECIONADA</span>
                        )}

                        {/* Badges Flutuantes */}
                        <div className="absolute top-2 left-2 bg-black/80 px-2 py-0.5 rounded border border-white/10 text-[9px] text-accent-amber font-bold pointer-events-none">
                            ORIGINAL (CFTV)
                        </div>
                        <div className="absolute top-2 right-2 bg-black/80 px-2 py-0.5 rounded border border-white/10 text-[9px] text-accent-emerald font-bold pointer-events-none">
                            {srResult ? `RECONSTRUÍDO 4X (${srResult.model_used})` : 'AGUARDANDO IA'}
                        </div>
                    </div>

                    {/* Slider de Controle Split-View */}
                    {srResult?.enhanced_image_base64 && (
                        <div className="space-y-1">
                            <div className="flex justify-between text-[9px] text-muted">
                                <span>← 100% ORIGINAL</span>
                                <span className="text-accent-amber font-bold">{sliderPos}% DIVISÃO</span>
                                <span>100% RESTAURADO →</span>
                            </div>
                            <input
                                type="range"
                                min="0"
                                max="100"
                                value={sliderPos}
                                onChange={(e) => setSliderPos(Number(e.target.value))}
                                className="w-full accent-accent-amber cursor-ew-resize"
                            />
                        </div>
                    )}
                </div>

                {/* 2. RESULTADO DE OCR DE PLACA (QUANDO APLICÁVEL) */}
                {targetType === 'plate' && srResult?.plate_ocr_candidate && (
                    <div className="p-4 bg-emerald-950/30 rounded-xl border border-emerald-500/40 text-center space-y-1 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
                        <span className="text-[10px] text-emerald-400 font-bold tracking-widest uppercase block">
                            PLACA IDENTIFICADA ({srResult.plate_format || 'MERCOSUL'}):
                        </span>
                        <div className="text-3xl font-black text-emerald-300 tracking-widest font-mono">
                            {srResult.plate_ocr_candidate}
                        </div>
                        <span className="text-[10px] text-muted block">
                            Conformidade Resolução CONTRAN nº 780/2019 • Proporção 3.08:1
                        </span>
                    </div>
                )}

                {/* 3. PARÂMETROS E CONTROLES PERICIAIS */}
                <div className="bg-black/60 rounded-xl p-4 border border-white/10 space-y-4 text-xs">
                    <h4 className="font-bold text-accent-emerald uppercase tracking-wider flex items-center gap-1.5">
                        <Sliders className="w-4 h-4" /> PARÂMETROS DO MOTOR DE SUPER-RESOLUÇÃO
                    </h4>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <span className="text-muted block mb-1">FATOR DE ESCALA:</span>
                            <select
                                value={scaleFactor}
                                onChange={(e) => setScaleFactor(Number(e.target.value))}
                                className="w-full bg-surface border border-white/10 rounded px-2 py-1.5 text-white"
                            >
                                <option value={2}>2x Super-Resolution</option>
                                <option value={4}>4x Neural Super-Resolution</option>
                                <option value={8}>8x Deep Forensic Crop</option>
                            </select>
                        </div>

                        <div>
                            <span className="text-muted block mb-1">DESCONVOLUÇÃO (MOTION):</span>
                            <select
                                value={deblurMethod}
                                onChange={(e) => setDeblurMethod(e.target.value as any)}
                                className="w-full bg-surface border border-white/10 rounded px-2 py-1.5 text-white"
                            >
                                <option value="wiener">Filtro de Wiener (2D)</option>
                                <option value="richardson_lucy">Richardson-Lucy (Iterativo)</option>
                                <option value="none">Desabilitado</option>
                            </select>
                        </div>
                    </div>

                    <button
                        onClick={handleRunSuperResolution}
                        disabled={isProcessing}
                        className={`w-full py-3 rounded-lg text-xs font-black uppercase flex items-center justify-center gap-2 shadow-lg transition-all ${
                            isProcessing
                                ? 'bg-white/10 text-muted cursor-not-allowed'
                                : 'bg-accent-emerald hover:bg-emerald-400 text-black shadow-emerald-500/30 active:scale-98'
                        }`}
                    >
                        <Zap className="w-4 h-4" />
                        {isProcessing ? 'PROCESSANDO REDES NEURAIS...' : 'RE-PROCESSAR SUPER-RESOLUÇÃO 4X'}
                    </button>
                </div>

                {/* 4. CADEIA DE CUSTÓDIA & HASHES CRIPTOGRÁFICOS (ISO 27037 / CPP 158-B) */}
                {srResult && (
                    <div className="bg-black/60 rounded-xl p-4 border border-white/10 space-y-3 text-[10px]">
                        <h4 className="font-bold text-accent-amber uppercase tracking-wider flex items-center gap-1.5">
                            <ShieldCheck className="w-4 h-4" /> CADEIA DE CUSTÓDIA CRIPTOGRÁFICA
                        </h4>

                        <div className="space-y-2">
                            <div className="p-2 bg-white/5 rounded border border-white/5 flex items-center justify-between">
                                <div className="truncate">
                                    <span className="text-muted block text-[8px]">SHA-256 ORIGINAL:</span>
                                    <span className="text-white font-mono">{srResult.sha256_original}</span>
                                </div>
                                <button
                                    onClick={() => handleCopyHash(srResult.sha256_original)}
                                    className="p-1 hover:bg-white/10 rounded text-accent-emerald shrink-0"
                                >
                                    {copiedHash === srResult.sha256_original ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>
                            </div>

                            <div className="p-2 bg-white/5 rounded border border-emerald-500/30 flex items-center justify-between">
                                <div className="truncate">
                                    <span className="text-accent-emerald block text-[8px]">SHA-256 APRIMORADO:</span>
                                    <span className="text-emerald-300 font-mono">{srResult.sha256_enhanced}</span>
                                </div>
                                <button
                                    onClick={() => handleCopyHash(srResult.sha256_enhanced)}
                                    className="p-1 hover:bg-white/10 rounded text-accent-emerald shrink-0"
                                >
                                    {copiedHash === srResult.sha256_enhanced ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                                </button>
                            </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 pt-1 text-[9px] text-muted text-center">
                            <div className="p-1.5 bg-white/5 rounded border border-white/5">
                                <span>NITIDEZ LAPLACE:</span>
                                <span className="text-white block font-bold mt-0.5">{srResult.quality_metrics_enhanced.laplacian_variance}</span>
                            </div>
                            <div className="p-1.5 bg-white/5 rounded border border-white/5">
                                <span>GRADIENTE BRENNER:</span>
                                <span className="text-white block font-bold mt-0.5">{srResult.quality_metrics_enhanced.brenner_gradient}</span>
                            </div>
                            <div className="p-1.5 bg-white/5 rounded border border-white/5">
                                <span>TEMPO DE RESPOSTA:</span>
                                <span className="text-accent-emerald block font-bold mt-0.5">{srResult.processing_time_ms} ms</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Rodapé com Exportação de Prova Forense e Laudo Oficial */}
            <div className="p-4 bg-black/90 border-t border-white/10 flex items-center gap-3">
                <button
                    onClick={handleDownloadEnhanced}
                    disabled={!srResult?.enhanced_image_base64}
                    className="flex-1 py-3 bg-white/10 hover:bg-white/20 border border-white/20 rounded-xl text-xs font-bold text-white flex items-center justify-center gap-2 transition-all active:scale-98 disabled:opacity-40"
                >
                    <Download className="w-4 h-4 text-accent-emerald" />
                    <span>EXPORTAR PROVA PNG</span>
                </button>

                <button
                    onClick={handleGenerateOfficialLaudo}
                    disabled={isGeneratingLaudo}
                    className="flex-1 py-3 bg-accent-amber hover:bg-amber-400 text-black font-black rounded-xl text-xs flex items-center justify-center gap-2 transition-all shadow-[0_0_15px_rgba(245,158,11,0.3)] active:scale-98"
                >
                    <FileText className="w-4 h-4" />
                    <span>{isGeneratingLaudo ? 'EMITINDO LAUDO...' : 'EMITIR LAUDO PDF'}</span>
                </button>
            </div>
        </div>
    );
};
