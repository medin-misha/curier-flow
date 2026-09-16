import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxy = {
    '/api': {
      target: env.BACKEND_API_URL || 'https://backend.localhost',
      changeOrigin: true,
      secure: env.BACKEND_TLS_VERIFY !== 'false',
      rewrite: (path: string) => path.replace(/^\/api/, ''),
    },
  }
  return { plugins: [vue()], server: { proxy }, preview: { proxy } }
})
