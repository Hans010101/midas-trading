import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  transpilePackages: ['@midas/shared'],
  typedRoutes: true,
}

export default nextConfig
