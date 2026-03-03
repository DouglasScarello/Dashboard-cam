import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],

    // Tauri espera que o frontend esteja servindo em localhost:1420 por padrão
    server: {
        port: 1420,
        strictPort: true,
    },

    // Opções de build para Tauri
    build: {
        target: [
            'es2021',
            'chrome100',
            'safari13'
        ],
        minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
        sourcemap: !!process.env.TAURI_DEBUG,
    },
});
