const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname),
  eslint: {
    // Root monorepo eslint config can interfere; typecheck covers correctness.
    ignoreDuringBuilds: true,
  },
};

module.exports = nextConfig;
