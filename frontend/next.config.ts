import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  poweredByHeader: false,
  compress: true,
  generateEtags: false,
  pageExtensions: ['tsx', 'ts', 'jsx', 'js'],

  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },

  // `output: 'standalone'` is intentionally not set in OSS. The Dockerfile
  // ships the regular .next output and runs `next start`, which is the
  // simpler path for self-hosted single-tenant deployments. Switch to
  // standalone mode if you need a minimal production image.

  experimental: {
    optimizeServerReact: true,
  },

  // Server-side packages for library markdown processing
  serverExternalPackages: ['gray-matter', 'remark', 'remark-gfm', 'remark-html'],

  async headers() {
    // Backend origin used by the browser for fetch() calls.
    // Defaults to same-origin; set NEXT_PUBLIC_BASE_URL when the backend
    // runs on a different host (e.g. http://localhost:8000 in dev).
    const backendOrigin = process.env.NEXT_PUBLIC_BASE_URL || "'self'";
    const isDev = process.env.NODE_ENV !== 'production';

    // Defense-in-depth CSP, NOT a strict CSP.
    //
    // 'unsafe-inline' on script-src and style-src is currently required by
    // Next.js + assistant-ui's emotion-style runtime. Tightening to a strict
    // nonce-based CSP requires (a) middleware to inject a per-request nonce
    // and (b) pinning every third-party that ships inline <style> tags. That
    // work is tracked, not done.
    //
    // 'unsafe-eval' is dev-only here (Next's fast-refresh uses eval); the
    // production build runs without it.
    //
    // Net effect: the CSP blocks remote-script injection and frame-embedding
    // (frame-ancestors 'none'), restricts outbound XHR/fetch to same-origin
    // plus the configured backend, and forbids <object>/<embed>. It does NOT
    // block XSS-to-RCE inside the page when an inline-script payload finds
    // its way past DOMPurify — DOMPurify is the primary defense; CSP is the
    // fallback layer.
    const scriptSrc = isDev
      ? "'self' 'unsafe-inline' 'unsafe-eval'"
      : "'self' 'unsafe-inline'";
    const csp = [
      "default-src 'self'",
      `script-src ${scriptSrc}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      `connect-src 'self' blob: ${backendOrigin}`,
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join('; ');

    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), payment=()' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          { key: 'Content-Security-Policy', value: csp },
        ],
      },
      {
        source: '/_next/static/(.*)',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/images/(.*)',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=86400, stale-while-revalidate=31536000' },
        ],
      },
      {
        source: '/library/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, s-maxage=3600, stale-while-revalidate=86400' },
        ],
      },
    ];
  },

  async redirects() {
    return [
      // Deprecated routes → workspace (301 permanent)
      { source: '/chat', destination: '/workspace', permanent: true },
      { source: '/editor', destination: '/workspace', permanent: true },
      { source: '/thread', destination: '/workspace', permanent: true },
    ];
  },

  async rewrites() {
    return [
      { source: '/sitemap-library.xml', destination: '/api/sitemap/library' },
    ];
  },

  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
  },
};

export default nextConfig;
