/** @type {import('next').NextConfig} */
const internalApi = process.env.INTERNAL_API_URL || 'http://localhost:8005/api/v1';

const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/backend/:path*',
        destination: `${internalApi}/:path*`,
      },
    ];
  },
};

export default nextConfig;
