import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, ScanFace, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { useMatchAlerts, type MatchAlert } from '../hooks/useMatchAlerts';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

const TOAST_LIFETIME_MS = 8000;

/**
 * Sino de alertas (com histórico em dropdown) + pilha de toasts para matches
 * biométricos recebidos via SSE. Monta uma única conexão useMatchAlerts —
 * fica em Layout.tsx para persistir entre as rotas /  e /cameras.
 */
export default function AlertCenter() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { alerts, status } = useMatchAlerts();
    const [open, setOpen] = useState(false);
    const [unread, setUnread] = useState(0);
    const [toasts, setToasts] = useState<MatchAlert[]>([]);
    const lastSeenKeyRef = useRef<string | null>(null);
    const panelRef = useRef<HTMLDivElement | null>(null);

    // Dispara um toast + incrementa o contador quando um alerta genuinamente novo chega no topo da lista
    useEffect(() => {
        if (alerts.length === 0) return;
        const latest = alerts[0];
        const key = `${latest.uid}-${latest.receivedAt}`;
        if (lastSeenKeyRef.current === key) return;
        lastSeenKeyRef.current = key;

        setToasts((prev) => [latest, ...prev]);
        setUnread((prev) => prev + 1);
        const timer = setTimeout(() => {
            setToasts((prev) => prev.filter((toast) => toast.receivedAt !== latest.receivedAt));
        }, TOAST_LIFETIME_MS);
        return () => clearTimeout(timer);
    }, [alerts]);

    useEffect(() => {
        if (!open) return;
        const handleClick = (e: MouseEvent) => {
            if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        };
        window.addEventListener('mousedown', handleClick);
        return () => window.removeEventListener('mousedown', handleClick);
    }, [open]);

    function goToCamera(cameraId: string) {
        setOpen(false);
        navigate(`/cameras?camera=${encodeURIComponent(cameraId)}`);
    }

    function dismissToast(receivedAt: number) {
        setToasts((prev) => prev.filter((toast) => toast.receivedAt !== receivedAt));
    }

    return (
        <>
            <div className="relative" ref={panelRef}>
                <button
                    onClick={() => {
                        setOpen((v) => !v);
                        if (!open) setUnread(0);
                    }}
                    className="relative h-7 px-3 rounded-full text-[10px] font-black tracking-widest uppercase flex items-center gap-2 text-muted hover:bg-white/5 hover:text-white transition-all"
                    title={t(`alerts.status.${status}`)}
                >
                    <span className="relative flex items-center">
                        <Bell className="w-3.5 h-3.5" />
                        <span
                            className={cn(
                                'absolute -top-1 -right-1 w-1.5 h-1.5 rounded-full',
                                status === 'connected' && 'bg-accent-emerald animate-pulse',
                                status === 'connecting' && 'bg-accent-amber animate-pulse',
                                status === 'disconnected' && 'bg-red-500'
                            )}
                        />
                    </span>
                    {unread > 0 && (
                        <span className="min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[9px] font-black flex items-center justify-center">
                            {unread > 99 ? '99+' : unread}
                        </span>
                    )}
                </button>

                <AnimatePresence>
                    {open && (
                        <motion.div
                            initial={{ opacity: 0, y: -8, scale: 0.98 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: -8, scale: 0.98 }}
                            className="absolute right-0 top-10 w-96 max-h-[70vh] overflow-y-auto custom-scrollbar bg-surface border border-white/10 rounded-xl shadow-2xl z-[80]"
                        >
                            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between sticky top-0 bg-surface">
                                <span className="text-[10px] font-black tracking-widest uppercase text-white">{t('alerts.title')}</span>
                                <span className="text-[9px] font-mono text-muted">{t(`alerts.status.${status}`)}</span>
                            </div>
                            {alerts.length === 0 ? (
                                <div className="px-4 py-8 text-center text-muted italic text-xs">{t('alerts.empty')}</div>
                            ) : (
                                <div className="divide-y divide-white/5">
                                    {alerts.map((alert) => (
                                        <button
                                            key={`${alert.uid}-${alert.receivedAt}`}
                                            onClick={() => goToCamera(alert.camera_id)}
                                            className="w-full text-left px-4 py-3 hover:bg-white/[0.04] transition-colors flex items-start gap-3"
                                        >
                                            <ScanFace className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="text-xs font-bold text-white truncate">{alert.name || t('alerts.unknown_target')}</span>
                                                    <span className="text-[9px] font-mono text-accent-amber shrink-0">{alert.confidence}</span>
                                                </div>
                                                <p className="text-[10px] text-muted font-mono mt-0.5">
                                                    {t('alerts.camera_label')} {alert.camera_id} · {formatRelativeTime(alert.timestamp)}
                                                </p>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            <div className="fixed top-16 right-6 z-[90] flex flex-col gap-3 w-80 pointer-events-none">
                <AnimatePresence>
                    {toasts.map((toast) => (
                        <motion.div
                            key={toast.receivedAt}
                            initial={{ opacity: 0, x: 40 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 40, transition: { duration: 0.2 } }}
                            className="pointer-events-auto bg-surface border border-red-500/40 rounded-xl shadow-2xl shadow-red-500/10 overflow-hidden"
                        >
                            <div className="px-4 py-3 flex items-start gap-3">
                                <div className="w-8 h-8 rounded-full bg-red-500/20 border border-red-500/40 flex items-center justify-center shrink-0">
                                    <ScanFace className="w-4 h-4 text-red-500" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[9px] font-black tracking-widest text-red-500 uppercase">{t('alerts.new_match')}</span>
                                        <button onClick={() => dismissToast(toast.receivedAt)} className="text-muted hover:text-white transition-colors">
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                    <p className="text-sm font-bold text-white truncate mt-0.5">{toast.name || t('alerts.unknown_target')}</p>
                                    <p className="text-[10px] text-muted font-mono mt-1">
                                        {t('alerts.camera_label')} {toast.camera_id} · {toast.confidence}
                                    </p>
                                    <button
                                        onClick={() => goToCamera(toast.camera_id)}
                                        className="mt-2 text-[10px] font-black tracking-wider uppercase text-accent-amber hover:underline"
                                    >
                                        {t('alerts.view_camera')} →
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </>
    );
}

function formatRelativeTime(iso: string): string {
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return iso;
    const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (diffSec < 60) return `${diffSec}s`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
    return `${Math.floor(diffSec / 3600)}h`;
}
