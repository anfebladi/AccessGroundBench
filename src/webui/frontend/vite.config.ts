import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';

const apiPort = Number(process.env.AGB_API_PORT || '8081');

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  base: '/',
  server: {
    host: '127.0.0.1',
    proxy: { '/api': `http://127.0.0.1:${apiPort}` },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
