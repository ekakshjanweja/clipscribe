import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.OCR_API_URL || "http://127.0.0.1:5001"}/:path*` }];
  },
};

export default nextConfig;
