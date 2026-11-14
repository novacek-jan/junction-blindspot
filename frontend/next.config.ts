import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";
const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === "true";
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function originOf(url: string): string {
  try {
    return new URL(url).origin;
  } catch {
    throw new Error(`NEXT_PUBLIC_API_URL is not a valid URL: "${url}"`);
  }
}

// Production builds that talk to a real backend must use HTTPS.
if (!isDev && !useMocks && !apiUrl.startsWith("https://")) {
  throw new Error(
    `NEXT_PUBLIC_API_URL must be https:// in production builds (got "${apiUrl}"). ` +
      "Use NEXT_PUBLIC_USE_MOCKS=true or `next dev` for local work.",
  );
}

// connect-src: our own origin plus the backend API only. With mocks there is no backend to call.
const connectSrc = ["'self'", ...(useMocks ? [] : [originOf(apiUrl)]), ...(isDev ? ["ws:"] : [])];

// No nonces: the app is statically prerendered, so Next's inline bootstrap scripts need 'unsafe-inline'
// (see node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md, "Without Nonces").
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self'",
  `connect-src ${connectSrc.join(" ")}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const nextConfig: NextConfig = {
  devIndicators: { position: "bottom-right" },
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  productionBrowserSourceMaps: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
