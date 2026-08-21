import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Часовой пояс западнее Гринвича: только в нём наивный new Date(iso)
    // сдвигает дату на сутки, и тесты возраста ловят возврат этого бага.
    env: { TZ: 'America/New_York' },
  },
})
