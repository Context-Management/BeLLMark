import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

const version = fs.readFileSync(path.resolve(__dirname, '../VERSION'), 'utf-8').trim()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    allowedHosts: true,
    port: Number(process.env.FRONTEND_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT ?? 8000}`,
        changeOrigin: true,
      },
      '/ws': {
        target: `http://127.0.0.1:${process.env.BACKEND_PORT ?? 8000}`,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
