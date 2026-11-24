import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `npm run dev` serves the UI on :5174 and forwards /api to the advisor backend on :8070.
// `npm run build` writes dist/, which `python -m advisor.server` serves directly.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, proxy: { '/api': 'http://127.0.0.1:8070' } },
  build: { outDir: 'dist', emptyOutDir: true },
});
