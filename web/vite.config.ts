import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only: forward API calls to the local FastAPI server (make dev-api).
    // 127.0.0.1 (not localhost) so we never IPv6-resolve onto someone else's port.
    proxy: {
      '/api': 'http://127.0.0.1:8100',
    },
  },
})
