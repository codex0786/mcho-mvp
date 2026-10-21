import { createRemoteJWKSet, jwtVerify } from "jose";
import { NextRequest } from "next/server";

export type OidcMetadata = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
  end_session_endpoint?: string;
};

export type ServerOidcConfig = {
  authority: string;
  clientId: string;
  resource: string;
  // Auth0 issues a JWT access token for an API only when `audience` is sent.
  audience: string;
  webOrigin: string;
};

const SAFE_JWT_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"];

function normaliseIssuer(value: string): string {
  return value.replace(/\/$/, "");
}

function secureEndpoint(value: unknown, label: string): string {
  if (typeof value !== "string") throw new Error(`OIDC metadata is missing ${label}.`);
  const parsed = new URL(value);
  const localHttp = parsed.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && localHttp)) {
    throw new Error(`OIDC ${label} must use HTTPS.`);
  }
  if (parsed.username || parsed.password || parsed.hash) {
    throw new Error(`OIDC ${label} must not contain credentials or a fragment.`);
  }
  return parsed.toString();
}

export function getServerOidcConfig(request: NextRequest): ServerOidcConfig {
  const authority = (process.env.MCHO_OIDC_AUTHORITY ?? "").trim().replace(/\/$/, "");
  const clientId = (process.env.MCHO_OIDC_CLIENT_ID ?? "").trim();
  const resource = (process.env.MCHO_OIDC_RESOURCE ?? "").trim();
  const audience = (process.env.MCHO_OIDC_AUDIENCE ?? "").trim();
  const configuredOrigin = (process.env.MCHO_WEB_ORIGIN?.trim() || process.env.RENDER_EXTERNAL_URL?.trim() || "");
  const webOrigin = configuredOrigin || (process.env.NODE_ENV === "production" ? "" : request.nextUrl.origin);

  if (!authority || !clientId) {
    throw new Error("OIDC authority and client ID are not configured.");
  }
  const parsedAuthority = new URL(authority);
  const localHttp = parsedAuthority.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(parsedAuthority.hostname);
  if (parsedAuthority.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && localHttp)) {
    throw new Error("OIDC authority must use HTTPS.");
  }
  if (parsedAuthority.username || parsedAuthority.password || parsedAuthority.hash) {
    throw new Error("OIDC authority is invalid.");
  }
  if (!webOrigin) {
    throw new Error("MCHO_WEB_ORIGIN must be configured for a production deployment.");
  }
  const parsedOrigin = new URL(webOrigin);
  if (parsedOrigin.origin !== webOrigin.replace(/\/$/, "") || parsedOrigin.pathname !== "/" || parsedOrigin.search || parsedOrigin.hash) {
    throw new Error("MCHO_WEB_ORIGIN must be an origin only (scheme and host, no path).");
  }
  const localWebOrigin = parsedOrigin.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(parsedOrigin.hostname);
  if (process.env.NODE_ENV === "production" && parsedOrigin.protocol !== "https:" && !localWebOrigin) {
    throw new Error("MCHO_WEB_ORIGIN must use HTTPS in production (except local Compose on localhost).");
  }
  return { authority, clientId, resource, audience, webOrigin: parsedOrigin.origin };
}

export async function getOidcMetadata(authority: string): Promise<OidcMetadata> {
  const authorityUrl = new URL(authority.endsWith("/") ? authority : `${authority}/`);
  const discoveryUrl = new URL(".well-known/openid-configuration", authorityUrl);
  const response = await fetch(discoveryUrl, {
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(8_000),
    headers: { accept: "application/json" },
  });
  if (!response.ok) throw new Error("OIDC discovery request failed.");
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object") throw new Error("OIDC discovery response is invalid.");
  const record = payload as Record<string, unknown>;
  const issuer = secureEndpoint(record.issuer, "issuer");
  if (normaliseIssuer(issuer) !== normaliseIssuer(authority)) {
    throw new Error("OIDC discovery issuer does not match the configured authority.");
  }
  return {
    issuer,
    authorization_endpoint: secureEndpoint(record.authorization_endpoint, "authorization endpoint"),
    token_endpoint: secureEndpoint(record.token_endpoint, "token endpoint"),
    jwks_uri: secureEndpoint(record.jwks_uri, "JWKS URI"),
    ...(typeof record.end_session_endpoint === "string"
      ? { end_session_endpoint: secureEndpoint(record.end_session_endpoint, "end-session endpoint") }
      : {}),
  };
}

export async function verifyIdToken(idToken: string, metadata: OidcMetadata, clientId: string, nonce: string): Promise<void> {
  const keySet = createRemoteJWKSet(new URL(metadata.jwks_uri), { timeoutDuration: 8_000, cooldownDuration: 5_000, cacheMaxAge: 300_000 });
  const { payload } = await jwtVerify(idToken, keySet, {
    issuer: metadata.issuer,
    audience: clientId,
    algorithms: SAFE_JWT_ALGORITHMS,
    clockTolerance: 30,
  });
  if (typeof payload.nonce !== "string" || payload.nonce !== nonce) {
    throw new Error("ID token nonce validation failed.");
  }
  if (!payload.sub || typeof payload.sub !== "string") {
    throw new Error("ID token subject is missing.");
  }
}

export function expectedWebOrigin(request: NextRequest): string {
  const value = (process.env.MCHO_WEB_ORIGIN?.trim() || process.env.RENDER_EXTERNAL_URL?.trim() || "");
  if (value) {
    const parsed = new URL(value);
    const localHttp = parsed.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
    if (process.env.NODE_ENV === "production" && parsed.protocol !== "https:" && !localHttp) {
      throw new Error("MCHO_WEB_ORIGIN must use HTTPS in production.");
    }
    if (parsed.username || parsed.password || parsed.hash) throw new Error("MCHO_WEB_ORIGIN is invalid.");
    return parsed.origin;
  }
  if (process.env.NODE_ENV === "production") {
    throw new Error("MCHO_WEB_ORIGIN must be configured for a production deployment.");
  }
  return request.nextUrl.origin;
}

export function isSameOriginMutation(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).origin === expectedWebOrigin(request);
  } catch {
    return false;
  }
}
