import type { NextConfig } from "next";

// Where the FastAPI backend lives. Baked in at build time (rewrites are compiled).
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
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
