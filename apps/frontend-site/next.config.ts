import type { NextConfig } from 'next'

const backendApiUrl = (process.env.BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: '/api/courier', destination: `${backendApiUrl}/courier` }]
  },
}

export default nextConfig
