import { useEffect, useRef, useState } from 'react';
import { Radio, ScanFace, Car as CarIcon } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

// Câmeras fixas dos dois pipelines 24/7 já rodando como systemd service
// (ver olho-de-deus-rosto.service e olho-de-deus-placas.service). Quando o
// usuário decidir quais câmeras usar em produção, isso vira configurável —
// por enquanto reflete exatamente o que já está ao vivo de verdade.
const CAM_FACE = 'globetv_soi11_bangkok';
const CAM_PLATE = 'globetv_davao_leongarcia';

// live_pipeline.py grava o frame anotado com o ID do vídeo do YouTube
// (UemFRPrl1hk), não o ID de câmera do catálogo — mesma gambiarra já usada
// em /mesa/app.js pra achar o arquivo certo em live_view/.
const CAM_FACE_FRAME_ID = CAM_FACE.includes('bangkok') ? 'UemFRPrl1hk' : CAM_FACE;

interface MatchRecent {
    individual_id?: string;
    name?: string;
    category?: string;
    camera_id?: string;
    captured_at?: string;
    evidence_url?: string | null;
    ref_photo_url?: string | null;
}

interface PlateRecent {
    plate_text: string;
    camera_id: string;
    vehicle_color?: string | null;
    vehicle_type?: string | null;
    confidence?: number | null;
    frames_voted?: number | null;
    created_at: string;
    evidence_url?: string | null;
}

function fmtTime(iso: string | null | undefined): string {
    if (!iso) return '—';
    try {
        return new Date(iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('pt-BR');
    } catch {
        return iso;
    }
}

function LiveFrame({ label, camId, suffix, icon }: { label: string; camId: string; suffix: string; icon: React.ReactNode }) {
    const [src, setSrc] = useState<string | null>(null);
    const [live, setLive] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const refresh = () => {
            const url = `${API_BASE}/live-frames/${camId}${suffix}.jpg?t=${Date.now()}`;
            const probe = new Image();
            probe.onload = () => { if (!cancelled) { setSrc(url); setLive(true); } };
            probe.onerror = () => { if (!cancelled) setLive(false); };
            probe.src = url;
        };
        refresh();
        const interval = setInterval(refresh, 700);
        return () => { cancelled = true; clearInterval(interval); };
    }, [camId, suffix]);

    return (
        <div className="intelligence-card overflow-hidden">
            <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
                <span className="flex items-center gap-2 text-[10px] font-black tracking-widest uppercase text-white">
                    {icon} {label}
                </span>
                <span className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${live ? 'bg-red-500 animate-pulse' : 'bg-neutral-600'}`} />
                    <span className="text-[9px] font-mono text-muted uppercase">{live ? 'ao vivo' : 'sem frame'}</span>
                </span>
            </div>
            <div className="aspect-video bg-black flex items-center justify-center">
                {src ? (
                    <img src={src} className="w-full h-full object-contain" alt={label} />
                ) : (
                    <p className="text-[10px] text-muted font-mono">aguardando pipeline… ({camId})</p>
                )}
            </div>
        </div>
    );
}

export default function AoVivo() {
    const [matches, setMatches] = useState<MatchRecent[]>([]);
    const [plates, setPlates] = useState<PlateRecent[]>([]);
    const mounted = useRef(true);

    useEffect(() => {
        mounted.current = true;
        const load = () => {
            fetch(`${API_BASE}/matches/recent?limit=15`).then(r => r.json()).then(d => { if (mounted.current) setMatches(Array.isArray(d) ? d : []); }).catch(() => {});
            fetch(`${API_BASE}/plates/recent?limit=15`).then(r => r.json()).then(d => { if (mounted.current) setPlates(Array.isArray(d) ? d : []); }).catch(() => {});
        };
        load();
        const interval = setInterval(load, 2000);
        return () => { mounted.current = false; clearInterval(interval); };
    }, []);

    return (
        <main className="flex-1 px-8 py-6 overflow-y-auto custom-scrollbar">
            <div className="mb-6 pb-4 border-b border-white/5">
                <h2 className="text-sm font-black tracking-widest uppercase text-white flex items-center gap-2">
                    <Radio className="w-4 h-4 text-red-500 animate-pulse" /> IA AO VIVO
                </h2>
                <p className="text-[10px] font-mono text-accent-emerald tracking-wider uppercase mt-1">
                    FRAME ANOTADO (YOLO + ARCFACE / ALPR) DAS DUAS CÂMERAS MONITORADAS 24/7
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                <LiveFrame label="Reconhecimento Facial — Bangkok" camId={CAM_FACE_FRAME_ID} suffix="" icon={<ScanFace className="w-3.5 h-3.5 text-accent-emerald" />} />
                <LiveFrame label="Leitura de Placa — Davao" camId={CAM_PLATE} suffix="_plates" icon={<CarIcon className="w-3.5 h-3.5 text-accent-amber" />} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <section>
                    <h4 className="text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                        MATCHES CONFIRMADOS (CÂMERA VS. BANCO)
                    </h4>
                    <div className="space-y-2 max-h-[50vh] overflow-y-auto custom-scrollbar pr-1">
                        {matches.length === 0 ? (
                            <p className="text-muted italic text-sm">Nenhum match ainda — bom sinal se ninguém do banco passou na câmera.</p>
                        ) : matches.map((m, i) => (
                            <div key={i} className="intelligence-card p-3 flex items-center gap-3">
                                {m.evidence_url && <img src={`${API_BASE}${m.evidence_url}`} title="foto da câmera" className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                {m.ref_photo_url && <img src={`${API_BASE}${m.ref_photo_url}`} title="referência do banco" className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                <div className="text-xs">
                                    <p className="font-black text-red-400 uppercase">{m.name || m.individual_id}</p>
                                    <p className="text-muted font-mono">{m.category || ''} · câmera {m.camera_id || '?'} · {fmtTime(m.captured_at)}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>

                <section>
                    <h4 className="text-[11px] font-black text-white tracking-widest uppercase mb-4 opacity-50">
                        LEITURAS DE PLACA (CONSENSO MULTI-FRAME)
                    </h4>
                    <div className="space-y-2 max-h-[50vh] overflow-y-auto custom-scrollbar pr-1">
                        {plates.length === 0 ? (
                            <p className="text-muted italic text-sm">Nenhuma leitura ainda.</p>
                        ) : plates.map((p, i) => (
                            <div key={i} className="intelligence-card p-3 flex items-center gap-3">
                                {p.evidence_url && <img src={`${API_BASE}${p.evidence_url}`} className="w-12 h-12 object-cover rounded-lg border border-white/10" />}
                                <div className="text-xs">
                                    <p className="font-black text-accent-amber font-mono">{p.plate_text}</p>
                                    <p className="text-muted font-mono">
                                        {p.vehicle_color || '?'} {p.vehicle_type || ''} · confiança {Math.round((p.confidence || 0) * 100)}% · {fmtTime(p.created_at)}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </main>
    );
}
