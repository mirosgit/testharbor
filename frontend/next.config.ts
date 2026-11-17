import type { NextConfig } from "next";

// Where the FastAPI backend lives. Baked in at build time (rewrites are compiled).
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

// Basic hardening. HSTS is added by the HTTPS reverse proxy (see docs/deployment.md).
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    // Next.js needs inline scripts/styles; everything is same-origin otherwise.
    // /docs (Swagger UI) is served by the backend with its own headers.
    value:
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
      "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; " +
      "base-uri 'self'; form-action 'self'; object-src 'none'",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/((?!docs|openapi.json|api/).*)", headers: securityHeaders }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      // Expose the backend's OpenAPI docs on the frontend origin too.
      { source: "/docs", destination: `${backend}/docs` },
      { source: "/openapi.json", destination: `${backend}/openapi.json` },
    ];
  },
};

export default nextConfig;
