import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `npm run dev` serves the UI on :5173 and forwards /api to the Python backend on :8050.
// `npm run build` writes dist/, which `python -m dashboard.server` serves directly.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8050' } },
  build: { outDir: 'dist', emptyOutDir: true },
});
