import type { NextConfig } from "next";

// The browser only ever talks to this Next.js origin; /api/* is proxied to FastAPI.
// Same-origin requests let the backend's httpOnly session cookie work without CORS.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
