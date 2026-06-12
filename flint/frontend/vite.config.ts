import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    allowedHosts: ['frontend', 'localhost'],
    watch: {
      usePolling: true,
      interval: 500,
    },
    proxy: {
      '/ValueSet': 'http://backend:8000',
      '/CodeSystem': 'http://backend:8000',
      '/ConceptMap': 'http://backend:8000',
      '/analytics': 'http://backend:8000',
      '/sdo': 'http://backend:8000',
      '/ai': 'http://backend:8000',
      '/health': 'http://backend:8000',
      '/metadata': 'http://backend:8000',
      '/admin': 'http://backend:8000',
      '/mcp-chat': 'http://backend:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/tests/setup.ts'],
  },
})
