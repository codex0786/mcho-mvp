import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// Browser requests are same-origin (BFF proxy, auth routes) except MapLibre styles,
// tiles and glyphs, whose host is runtime configuration (MCHO_MAP_STYLE_URL), and a
// direct API origin when NEXT_PUBLIC_API_BASE_URL is absolute (local Compose).
function apiOrigin(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!configured || !/^https?:\/\//i.test(configured)) return null;
  try {
    return new URL(configured).origin;
  } catch {
    return null;
  }
}

function contentSecurityPolicy(): string {
  const connect = ["'self'", "https:"];
  const origin = apiOrigin();
  if (origin && !origin.startsWith("https:")) connect.push(origin);
  if (isDev) connect.push("ws:", "http://localhost:*", "http://127.0.0.1:*");
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    // Next.js injects inline bootstrap scripts; dev mode also needs eval for fast refresh.
    "script-src": ["'self'", "'unsafe-inline'", ...(isDev ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", "https:"],
    "font-src": ["'self'", "data:", "https:"],
    "connect-src": connect,
    // MapLibre runs its tile parser in a blob: worker.
    "worker-src": ["'self'", "blob:"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  return Object.entries(directives).map(([name, values]) => `${name} ${values.join(" ")}`).join("; ");
}

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy() },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
