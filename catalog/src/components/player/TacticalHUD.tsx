import React, { useEffect, useState } from 'react';
import { StreamTelemetry, CameraData } from './types/player.types';
import { Shield, Radio, Activity, Compass, Clock, MapPin, Eye } from 'lucide-react';

interface TacticalHUDProps {
    telemetry: StreamTelemetry;
    camera: CameraData;
    filterLabel: string;
    isFrozen: boolean;
    zoomLevel: number;
    showHUD: boolean;
}

export const TacticalHUD: React.FC<TacticalHUDProps> = ({
    telemetry,
    camera,
    filterLabel,
    isFrozen,
    zoomLevel,
    showHUD,
}) => {
    const [timeZulu, setTimeZulu] = useState('');
    const [timeLocal, setTimeLocal] = useState('');
    const [azimuth, setAzimuth] = useState(142);

    useEffect(() => {
        const updateTime = () => {
            const now = new Date();
            setTimeZulu(now.toISOString().substring(11, 23) + ' ZULU');
            setTimeLocal(now.toLocaleTimeString('pt-BR'));
        };
        updateTime();
        const interval = setInterval(updateTime, 100);
        return () => clearInterval(interval);
    }, []);

    if (!showHUD) return null;

    const coordsFormatted = camera.lat && camera.long 
        ? `${camera.lat.toFixed(5)}, ${camera.long.toFixed(5)}` 
        : 'GEO-N/D';

    // Conversão MGRS simulada para fidelidade tática
    const mgrsCoord = camera.lat && camera.long
        ? `23K PR ${Math.abs(Math.floor(camera.long * 1000) % 100000)} ${Math.abs(Math.floor(camera.lat * 1000) % 100000)}`
        : '23K PR 33410 88204';

    return (
        <div className="absolute inset-0 pointer-events-none z-20 flex flex-col justify-between p-4 overflow-hidden select-none font-mono">
            {/* Scanlines Sutis Militares */}
            <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.35)_50%)] bg-[length:100%_4px] opacity-20 pointer-events-none" />

            {/* Cantos Táticos de Alvo (Target Brackets) */}
            <div className="absolute top-4 left-4 w-7 h-7 border-t-2 border-l-2 border-accent-emerald shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            <div className="absolute top-4 right-4 w-7 h-7 border-t-2 border-r-2 border-accent-emerald shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            <div className="absolute bottom-4 left-4 w-7 h-7 border-b-2 border-l-2 border-accent-emerald shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            <div className="absolute bottom-4 right-4 w-7 h-7 border-b-2 border-r-2 border-accent-emerald shadow-[0_0_10px_rgba(16,185,129,0.5)]" />

            {/* Retículo Central C4ISR com Mil-dots */}
            <div className="absolute inset-0 flex items-center justify-center opacity-30">
                <svg width="180" height="180" viewBox="0 0 180 180" className="stroke-accent-emerald fill-none">
                    <circle cx="90" cy="90" r="60" strokeWidth="1" strokeDasharray="4 4" />
                    <circle cx="90" cy="90" r="6" strokeWidth="1.5" />
                    <circle cx="90" cy="90" r="1.5" className="fill-accent-emerald" />
                    
                    {/* Linhas Cardeais */}
                    <line x1="90" y1="10" x2="90" y2="50" strokeWidth="1.5" />
                    <line x1="90" y1="130" x2="90" y2="170" strokeWidth="1.5" />
                    <line x1="10" y1="90" x2="50" y2="90" strokeWidth="1.5" />
                    <line x1="130" y1="90" x2="170" y2="90" strokeWidth="1.5" />

                    {/* Mil-dots */}
                    <circle cx="90" cy="30" r="1.5" className="fill-accent-emerald" />
                    <circle cx="90" cy="40" r="1.5" className="fill-accent-emerald" />
                    <circle cx="90" cy="140" r="1.5" className="fill-accent-emerald" />
                    <circle cx="90" cy="150" r="1.5" className="fill-accent-emerald" />
                    <circle cx="30" cy="90" r="1.5" className="fill-accent-emerald" />
                    <circle cx="40" cy="90" r="1.5" className="fill-accent-emerald" />
                    <circle cx="140" cy="90" r="1.5" className="fill-accent-emerald" />
                    <circle cx="150" cy="90" r="1.5" className="fill-accent-emerald" />
                </svg>
            </div>

            {/* Cabeçalho Superior do HUD */}
            <div className="flex items-start justify-between text-[11px] text-white/90">
                {/* Status de Conexão, Protocolo & Zoom */}
                <div className="flex flex-col gap-1.5">
                    <div className="flex items-center gap-2 bg-black/75 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 shadow-lg">
                        <span className={`w-2.5 h-2.5 rounded-full ${isFrozen ? 'bg-amber-500 animate-pulse' : 'bg-red-500 animate-ping'}`} />
                        <span className="font-black tracking-widest text-white uppercase text-xs">
                            {isFrozen ? 'FREEZE FRAME // ANÁLISE ESTÁTICA' : 'LIVE C4ISR STREAM'}
                        </span>
                        <span className="text-white/30">|</span>
                        <span className="text-accent-emerald font-bold">{telemetry.protocol || 'HLS-DIRECT'}</span>
                        <span className="text-white/30">|</span>
                        <span className="text-accent-amber font-bold">{zoomLevel.toFixed(1)}x MAG</span>
                    </div>

                    <div className="flex items-center gap-2 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded border border-white/5 text-[9px] w-fit">
                        <Eye className="w-3 h-3 text-accent-emerald" />
                        <span className="text-white/70">FILTRO ATIVO:</span>
                        <span className="text-accent-emerald font-bold tracking-wider">{filterLabel}</span>
                    </div>
                </div>

                {/* Bússola Tática & Azimute Central */}
                <div className="hidden md:flex flex-col items-center bg-black/65 backdrop-blur-md px-4 py-1 rounded-lg border border-white/10">
                    <div className="flex items-center gap-1 text-[10px] text-accent-emerald font-bold">
                        <Compass className="w-3.5 h-3.5" />
                        <span>AZM: {azimuth}° [SSE]</span>
                    </div>
                    <div className="text-[8px] text-white/50 tracking-widest mt-0.5">
                        MGRS: {mgrsCoord}
                    </div>
                </div>

                {/* Relógio Atômico UTC Zulu & Local */}
                <div className="bg-black/75 backdrop-blur-md px-3.5 py-1.5 rounded-lg border border-white/10 text-right flex flex-col shadow-lg">
                    <div className="flex items-center justify-end gap-1.5 text-accent-amber font-black tracking-wider text-xs">
                        <Clock className="w-3.5 h-3.5" />
                        <span>{timeZulu}</span>
                    </div>
                    <span className="text-[9px] text-white/60">LOCAL: {timeLocal} [BRT/UTC-3]</span>
                </div>
            </div>

            {/* Rodapé do HUD com Telemetria e Coordenadas */}
            <div className="flex items-end justify-between text-[11px]">
                {/* Dados da Câmera & Localização */}
                <div className="bg-black/75 backdrop-blur-md px-3.5 py-2 rounded-lg border border-white/10 max-w-[55%] shadow-lg">
                    <div className="text-xs font-black text-white truncate uppercase tracking-wide flex items-center gap-1.5">
                        <Shield className="w-3.5 h-3.5 text-accent-emerald shrink-0" />
                        <span>{camera.nome}</span>
                    </div>
                    <div className="text-[9px] text-accent-amber flex items-center gap-2 mt-1 truncate">
                        <span>ID: #{camera.id}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1 text-white/70">
                            <MapPin className="w-2.5 h-2.5 text-accent-emerald" />
                            {camera.endereco || camera.local || 'SETOR DE VIGILÂNCIA'}
                        </span>
                        <span>•</span>
                        <span className="text-accent-emerald">{coordsFormatted}</span>
                    </div>
                </div>

                {/* Telemetria de Streaming em Tempo Real */}
                <div className="bg-black/75 backdrop-blur-md px-3.5 py-2 rounded-lg border border-white/10 flex items-center gap-4 text-[10px] text-white/80 shadow-lg">
                    <div>
                        <span className="text-white/40 text-[8px] block uppercase font-bold">FPS</span>
                        <span className="text-accent-emerald font-black text-xs">{telemetry.fps || 30}</span>
                    </div>
                    <div className="h-5 w-[1px] bg-white/10" />
                    <div>
                        <span className="text-white/40 text-[8px] block uppercase font-bold">RES</span>
                        <span className="text-white font-bold text-[10px]">{telemetry.resolution || '1080p'}</span>
                    </div>
                    <div className="h-5 w-[1px] bg-white/10" />
                    <div>
                        <span className="text-white/40 text-[8px] block uppercase font-bold">BITRATE</span>
                        <span className="text-accent-emerald font-black text-xs">{telemetry.bitrateMbps || 4.2} Mb/s</span>
                    </div>
                    <div className="h-5 w-[1px] bg-white/10" />
                    <div>
                        <span className="text-white/40 text-[8px] block uppercase font-bold">BUFFER</span>
                        <span className="text-accent-amber font-bold text-xs">{telemetry.bufferSeconds || 0.8}s</span>
                    </div>
                </div>
            </div>
        </div>
    );
};
