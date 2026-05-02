import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 51327,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:47821',
        changeOrigin: true,
      },
    },
  },
})
