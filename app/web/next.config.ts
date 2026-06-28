import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",        // static export — served by FastAPI
  trailingSlash: true,     // /sessions/ instead of /sessions
  images: { unoptimized: true },
};

export default nextConfig;
