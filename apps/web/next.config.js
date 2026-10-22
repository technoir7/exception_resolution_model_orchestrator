/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    experimental: {
        // An invoice PDF may be up to 10 MB (apps/api/services/intake.py).
        serverActions: { bodySizeLimit: '11mb' },
    },
}

module.exports = nextConfig
