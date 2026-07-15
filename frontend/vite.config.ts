import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The FastAPI read API runs on :8000. Proxying /api to it in dev keeps the
// browser same-origin, so no CORS handling is needed while developing.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Honour the port the preview tool assigns via PORT (Vite ignores it by default).
    host: '127.0.0.1',
    port: process.env.PORT ? Number(process.env.PORT) : 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
