import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In development the API runs on Django's port; same-origin requests avoid CORS entirely.
    proxy: { '/api': process.env.VITE_DEV_API_PROXY ?? 'http://127.0.0.1:8000' },
  },
  build: {
    // MapLibre (~300 kB gzip) is inherently large; it is lazy-loaded in its own chunk.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Keep the large map engine in its own long-cacheable chunk.
        manualChunks: (id) => (id.includes('maplibre-gl') ? 'maplibre' : undefined),
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
