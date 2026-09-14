import React from 'react';

interface BreakerSwitchProps {
    isOn: boolean;
    pending: boolean;
    onToggle: () => void;
    label: string;
}

// Disjuntor industrial, não um toggle de app de consumo — a metáfora certa
// pra "ligar uma IA de reconhecimento facial numa câmera de rua ao vivo":
// tem peso, exige intenção, e mostra faixa de risco (padrão real de
// sinalização industrial: preto+amarelo = "energizado") só do lado ON.
export const BreakerSwitch: React.FC<BreakerSwitchProps> = ({ isOn, pending, onToggle, label }) => {
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault();
            if (!pending) onToggle();
        }
    };

    return (
        <button
            type="button"
            role="switch"
            aria-checked={isOn}
            aria-label={label}
            aria-busy={pending}
            disabled={pending}
            onClick={onToggle}
            onKeyDown={handleKeyDown}
            className="group relative w-24 h-12 rounded-md p-1 shrink-0 transition-all duration-300 outline-none focus-visible:ring-2 focus-visible:ring-accent-emerald/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-wait cursor-pointer"
            style={{
                background: isOn
                    ? 'linear-gradient(180deg, #1a2b22 0%, #0d1712 100%)'
                    : 'linear-gradient(180deg, #232326 0%, #141416 100%)',
                boxShadow: isOn
                    ? 'inset 0 1px 2px rgba(0,0,0,0.6), 0 0 18px rgba(16,185,129,0.35), 0 0 2px rgba(16,185,129,0.6)'
                    : 'inset 0 1px 2px rgba(0,0,0,0.6)',
                border: `1px solid ${isOn ? 'rgba(16,185,129,0.4)' : 'rgba(255,255,255,0.08)'}`,
            }}
        >
            {/* Faixa de risco (preto+amarelo) — só aparece do lado ENERGIZADO */}
            <div
                className="absolute inset-y-1 right-1 w-1/2 rounded-sm overflow-hidden transition-opacity duration-300"
                style={{
                    opacity: isOn ? 0.35 : 0,
                    backgroundImage:
                        'repeating-linear-gradient(135deg, #f59e0b 0px, #f59e0b 5px, #0a0a0b 5px, #0a0a0b 10px)',
                }}
            />

            {/* Trilho central (entalhe do disjuntor) */}
            <div className="absolute inset-x-3 top-1/2 -translate-y-1/2 h-0.5 bg-black/50 rounded-full" />

            {/* Alavanca */}
            <div
                className="absolute top-1 bottom-1 w-1/2 rounded transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] flex items-center justify-center"
                style={{
                    transform: isOn ? 'translateX(100%)' : 'translateX(0%)',
                    background: pending
                        ? 'linear-gradient(180deg, #f59e0b 0%, #b45309 100%)'
                        : isOn
                            ? 'linear-gradient(180deg, #34d399 0%, #059669 100%)'
                            : 'linear-gradient(180deg, #52525b 0%, #27272a 100%)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.5), inset 0 1px 1px rgba(255,255,255,0.25)',
                }}
            >
                <div className={`w-4 h-0.5 rounded-full bg-black/30 ${pending ? 'animate-pulse' : ''}`} />
            </div>
        </button>
    );
};
