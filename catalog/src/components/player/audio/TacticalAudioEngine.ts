/**
 * Motor de Síntese Sonora Procedural C4ISR / Militar via Web Audio API
 * Não necessita de arquivos externos de áudio (100% sintetizado em tempo real).
 */

class TacticalAudioEngine {
    private ctx: AudioContext | null = null;
    private isMuted: boolean = false;
    private masterGain: GainNode | null = null;

    constructor() {
        // Inicialização preguiçosa no primeiro clique do usuário
    }

    private getContext(): AudioContext | null {
        if (typeof window === 'undefined') return null;
        if (!this.ctx) {
            const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
            if (AudioCtx) {
                this.ctx = new AudioCtx();
                this.masterGain = this.ctx.createGain();
                this.masterGain.gain.setValueAtTime(0.35, this.ctx.currentTime);
                this.masterGain.connect(this.ctx.destination);
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().catch(() => {});
        }
        return this.ctx;
    }

    public setMuted(muted: boolean) {
        this.isMuted = muted;
        if (this.masterGain && this.ctx) {
            this.masterGain.gain.setValueAtTime(muted ? 0 : 0.35, this.ctx.currentTime);
        }
    }

    public getMuted(): boolean {
        return this.isMuted;
    }

    /**
     * Clique de botão tático / MFD Keypress
     */
    public playClick() {
        if (this.isMuted) return;
        const ctx = this.getContext();
        if (!ctx || !this.masterGain) return;

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1400, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(400, ctx.currentTime + 0.035);

        gain.gain.setValueAtTime(0.2, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.035);

        osc.connect(gain);
        gain.connect(this.masterGain);
        osc.start();
        osc.stop(ctx.currentTime + 0.04);
    }

    /**
     * Efeito de obturador mecânico / Snapshot Forense
     */
    public playShutter() {
        if (this.isMuted) return;
        const ctx = this.getContext();
        if (!ctx || !this.masterGain) return;

        const now = ctx.currentTime;

        // Ruído branco filtrado para simular clique mecânico
        const bufferSize = ctx.sampleRate * 0.06;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = Math.random() * 2 - 1;
        }

        const noise = ctx.createBufferSource();
        noise.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(2200, now);

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0.4, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);

        noise.connect(filter);
        filter.connect(gain);
        gain.connect(this.masterGain);

        noise.start(now);

        // Segundo clique rápido (espelho da câmera)
        const osc = ctx.createOscillator();
        const oscGain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(800, now + 0.05);
        osc.frequency.exponentialRampToValueAtTime(200, now + 0.09);

        oscGain.gain.setValueAtTime(0.3, now + 0.05);
        oscGain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);

        osc.connect(oscGain);
        oscGain.connect(this.masterGain);
        osc.start(now + 0.05);
        osc.stop(now + 0.1);
    }

    /**
     * Tom de mira travada / Lock-on Seeker Tone
     */
    public playLockOn() {
        if (this.isMuted) return;
        const ctx = this.getContext();
        if (!ctx || !this.masterGain) return;

        const now = ctx.currentTime;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(880, now);
        osc.frequency.setValueAtTime(1760, now + 0.08);

        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);

        osc.connect(gain);
        gain.connect(this.masterGain);
        osc.start(now);
        osc.stop(now + 0.2);
    }

    /**
     * Beep duplo de alerta tático militar
     */
    public playAlert() {
        if (this.isMuted) return;
        const ctx = this.getContext();
        if (!ctx || !this.masterGain) return;

        const now = ctx.currentTime;

        const playTone = (timeOffset: number) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'square';
            osc.frequency.setValueAtTime(950, now + timeOffset);

            gain.gain.setValueAtTime(0.18, now + timeOffset);
            gain.gain.exponentialRampToValueAtTime(0.001, now + timeOffset + 0.07);

            osc.connect(gain);
            gain.connect(this.masterGain!);
            osc.start(now + timeOffset);
            osc.stop(now + timeOffset + 0.08);
        };

        playTone(0);
        playTone(0.1);
    }

    /**
     * Squelch de rádio VHF/UHF ao conectar stream
     */
    public playRadioSquelch() {
        if (this.isMuted) return;
        const ctx = this.getContext();
        if (!ctx || !this.masterGain) return;

        const now = ctx.currentTime;
        const bufferSize = ctx.sampleRate * 0.09;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = Math.random() * 2 - 1;
        }

        const noise = ctx.createBufferSource();
        noise.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'highpass';
        filter.frequency.setValueAtTime(3000, now);

        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

        noise.connect(filter);
        filter.connect(gain);
        gain.connect(this.masterGain);

        noise.start(now);
    }
}

export const tacticalAudio = new TacticalAudioEngine();
