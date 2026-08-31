import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

interface SnapshotImagePlayerProps {
    src: string;
    style?: React.CSSProperties;
    className?: string;
    onReady?: () => void;
    /** Intervalo de atualização em ms — câmeras tipo Ontario 511/NZTA são
     * uma imagem única por request, não um stream contínuo, então "ao
     * vivo" aqui significa buscar de novo periodicamente. */
    refreshMs?: number;
}

/**
 * Player pra câmeras "SNAPSHOT_JPEG" (Ontario 511, NZTA, ...) — imagem
 * única que atualiza a cada request, não manifesto HLS. Achado real
 * (2026-08-31): sem isso, essas câmeras caíam no HlsVideoPlayer, que
 * tentava interpretar um .jpg puro como playlist .m3u8 e sempre falhava
 * com "SINAL PERDIDO" mesmo a câmera estando genuinamente ao vivo.
 */
export const SnapshotImagePlayer: React.FC<SnapshotImagePlayerProps> = ({
    src, style, className, onReady, refreshMs = 4000,
}) => {
    const [displaySrc, setDisplaySrc] = useState<string>(`${src}${src.includes('?') ? '&' : '?'}t=${Date.now()}`);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);
    const readyFiredRef = useRef(false);

    useEffect(() => {
        readyFiredRef.current = false;
        setErrorMsg(null);
        const tick = () => setDisplaySrc(`${src}${src.includes('?') ? '&' : '?'}t=${Date.now()}`);
        tick();
        const interval = setInterval(tick, refreshMs);
        return () => clearInterval(interval);
    }, [src, refreshMs]);

    return (
        <div style={{ position: 'relative', width: '100%', height: '100%' }}>
            {errorMsg && (
                <div style={{
                    position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center', backgroundColor: '#000',
                    color: '#ef4444', zIndex: 50, fontFamily: 'monospace', textAlign: 'center', padding: '20px'
                }}>
                    <AlertTriangle style={{ width: 48, height: 48, marginBottom: 16 }} />
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>SINAL PERDIDO</h2>
                    <p style={{ marginTop: 8, opacity: 0.8 }}>{errorMsg}</p>
                </div>
            )}
            <img
                src={displaySrc}
                style={{ ...style, display: errorMsg ? 'none' : 'block' }}
                className={className}
                alt="Câmera ao vivo (snapshot)"
                onLoad={() => {
                    setErrorMsg(null);
                    if (!readyFiredRef.current) {
                        readyFiredRef.current = true;
                        onReady?.();
                    }
                }}
                onError={() => setErrorMsg("CÂMERA OFFLINE (Snapshot indisponível na fonte)")}
            />
        </div>
    );
};
