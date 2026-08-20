import { useCallback, useEffect, useRef, useState } from 'react';

export interface MatchAlert {
    type: string;
    uid: string;
    name: string;
    camera_id: string;
    confidence: string;
    threat_score?: number;
    evidence_url?: string;
    timestamp: string;
    /** Carimbo local (não vem do backend) usado como chave estável de UI. */
    receivedAt: number;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

const EVENTS_URL = 'http://localhost:8000/events';
const MAX_HISTORY = 50;
const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 15000;

/**
 * Assina o stream SSE de matches biométricos (olho_de_deus/api_server.py:/events,
 * alimentado pelo Redis pub/sub que live_pipeline.py publica no canal
 * "tactical_alerts"). Mantém histórico local e reconecta com backoff exponencial
 * se a conexão cair — o EventSource nativo já reconecta sozinho, mas isso dá
 * controle explícito sobre o backoff e um status observável pela UI.
 */
export function useMatchAlerts() {
    const [alerts, setAlerts] = useState<MatchAlert[]>([]);
    const [status, setStatus] = useState<ConnectionStatus>('connecting');
    const sourceRef = useRef<EventSource | null>(null);
    const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const mountedRef = useRef(true);

    const connect = useCallback(() => {
        if (!mountedRef.current) return;
        setStatus('connecting');

        const source = new EventSource(EVENTS_URL);
        sourceRef.current = source;

        source.onopen = () => {
            if (!mountedRef.current) return;
            setStatus('connected');
            reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;
        };

        source.addEventListener('match', (evt) => {
            if (!mountedRef.current) return;
            try {
                const data = JSON.parse((evt as MessageEvent).data);
                const alert: MatchAlert = { ...data, receivedAt: Date.now() };
                setAlerts((prev) => [alert, ...prev].slice(0, MAX_HISTORY));
            } catch (err) {
                console.error('[useMatchAlerts] Payload de match inválido:', err);
            }
        });

        source.onerror = () => {
            source.close();
            if (!mountedRef.current) return;
            setStatus('disconnected');
            const delay = reconnectDelayRef.current;
            reconnectTimerRef.current = setTimeout(connect, delay);
            reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS);
        };
    }, []);

    useEffect(() => {
        mountedRef.current = true;
        connect();
        return () => {
            mountedRef.current = false;
            sourceRef.current?.close();
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        };
    }, [connect]);

    return { alerts, status };
}
