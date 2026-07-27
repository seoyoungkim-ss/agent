import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // 로컬 개발 시 백엔드(FastAPI, 기본 8000포트)로 프록시한다.
      // 백엔드도 /api 아래에 라우터를 마운트하므로(app/main.py) 경로를 그대로 전달한다.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
