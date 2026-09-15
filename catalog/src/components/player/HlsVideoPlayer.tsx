import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import Hls from 'hls.js';

// Telemetria real, lida direto do hls.js e do elemento <video> — nunca
// estimada ou inventada. Campo `null` = essa fonte de stream não expõe
// esse dado (ex: player nativo do Safari não dá bitrate nem níveis).
export interface HlsStreamTelemetry {
    fps: number | null;
    bitrateMbps: number | null;
    resolution: string | null;
    bufferSeconds: number | null;
    latencyMs: number | null;
    qualityLevels: string[];
    currentLevel: number;
}

interface HlsVideoPlayerProps {
    src: string;
    style?: React.CSSProperties;
    className?: string;
    onReady?: () => void;
    onTelemetry?: (telemetry: HlsStreamTelemetry) => void;
}

export const HlsVideoPlayer: React.FC<HlsVideoPlayerProps> = ({ src, style, className, onReady, onTelemetry }) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [errorMsg, setErrorMsg] = useState<string | null>(null);

    // `onReady` costuma ser um arrow function inline no componente pai
    // (ex: `onReady={() => setVideoReady(true)}`), então a referência muda
    // a cada re-render do pai. Achado real (2026-08-31, câmera relatada
    // como "tela preta" mesmo com stream confirmado ao vivo): o pai
    // (CameraGrid.tsx) re-renderiza a cada 5s por causa do polling de
    // alertas — isso ficava no array de dependências do useEffect abaixo,
    // destruindo e recriando a conexão HLS a cada 5s, e câmeras com
    // segmentos de 10-12s (comum em servidores Wowza) nunca tinham tempo
    // de terminar o buffer inicial antes de serem reiniciadas de novo.
    // Um ref guarda a versão mais recente sem entrar na dependência do
    // efeito — só `src` deve reiniciar a conexão.
    const onReadyRef = useRef(onReady);
    onReadyRef.current = onReady;
    const onTelemetryRef = useRef(onTelemetry);
    onTelemetryRef.current = onTelemetry;

    useEffect(() => {
        const video = videoRef.current;
        if (!video) return;

        let hls: Hls | null = null;
        setErrorMsg(null);

        // FPS real vem da diferença de frames decodificados entre duas
        // amostras (API padrão do browser), não de um valor fixo — precisa
        // de estado entre chamadas do interval, por isso o ref aqui fora.
        let lastFrameSample: { time: number; frames: number } | null = null;

        const sampleTelemetry = () => {
            if (!onTelemetryRef.current) return;

            let fps: number | null = null;
            const quality = video.getVideoPlaybackQuality?.();
            if (quality && typeof quality.totalVideoFrames === 'number') {
                const now = performance.now();
                if (lastFrameSample) {
                    const dtSeconds = (now - lastFrameSample.time) / 1000;
                    const frameDelta = quality.totalVideoFrames - lastFrameSample.frames;
                    if (dtSeconds > 0.2) {
                        fps = Math.round(frameDelta / dtSeconds);
                    }
                }
                lastFrameSample = { time: now, frames: quality.totalVideoFrames };
            }

            let bufferSeconds: number | null = null;
            if (video.buffered.length > 0) {
                bufferSeconds = Math.max(0, video.buffered.end(video.buffered.length - 1) - video.currentTime);
            }

            let resolution: string | null = video.videoWidth && video.videoHeight
                ? `${video.videoWidth}x${video.videoHeight}`
                : null;

            let bitrateMbps: number | null = null;
            let qualityLevels: string[] = [];
            let currentLevel = -1;
            let latencyMs: number | null = null;

            if (hls) {
                if (typeof hls.bandwidthEstimate === 'number' && hls.bandwidthEstimate > 0) {
                    bitrateMbps = Math.round((hls.bandwidthEstimate / 1_000_000) * 10) / 10;
                }
                qualityLevels = hls.levels.map(level => `${level.height}p`);
                currentLevel = hls.currentLevel;
                if (hls.currentLevel >= 0 && hls.levels[hls.currentLevel]) {
                    const level = hls.levels[hls.currentLevel];
                    resolution = `${level.width}x${level.height}`;
                }
                if (Number.isFinite(hls.latency) && hls.latency > 0) {
                    latencyMs = Math.round(hls.latency * 1000);
                }
            }

            onTelemetryRef.current({ fps, bitrateMbps, resolution, bufferSeconds, latencyMs, qualityLevels, currentLevel });
        };

        const telemetryInterval = window.setInterval(sampleTelemetry, 1000);

        if (Hls.isSupported()) {
            hls = new Hls({
                enableWorker: true,
                lowLatencyMode: true,
            });
            
            hls.on(Hls.Events.ERROR, (event, data) => {
                if (data.fatal) {
                    switch (data.type) {
                        case Hls.ErrorTypes.NETWORK_ERROR:
                            console.error("HLS Network Error:", data);
                            setErrorMsg("CÂMERA OFFLINE (Sinal de vídeo indisponível na fonte)");
                            hls?.destroy();
                            break;
                        case Hls.ErrorTypes.MEDIA_ERROR:
                            console.error("HLS Media Error:", data);
                            hls?.recoverMediaError();
                            break;
                        default:
                            setErrorMsg("ERRO NO STREAM HLS");
                            hls?.destroy();
                            break;
                    }
                }
            });

            hls.loadSource(src);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => {
                video.play().catch(e => console.log('Autoplay prevented', e));
                if (onReadyRef.current) onReadyRef.current();
                sampleTelemetry();
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            video.src = src;
            video.addEventListener('loadedmetadata', () => {
                video.play().catch(e => console.log('Autoplay prevented', e));
                if (onReadyRef.current) onReadyRef.current();
                sampleTelemetry();
            });
            video.addEventListener('error', () => {
                setErrorMsg("CÂMERA OFFLINE (Sinal indisponível)");
            });
        }

        return () => {
            window.clearInterval(telemetryInterval);
            if (hls) {
                hls.destroy();
            }
        };
    }, [src]);

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
            <video
                ref={videoRef}
                style={{ ...style, display: errorMsg ? 'none' : 'block' }}
                className={className}
                autoPlay
                muted
                playsInline
                crossOrigin="anonymous"
            />
        </div>
    );
};
