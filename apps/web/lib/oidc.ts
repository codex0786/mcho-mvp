"use client";

export type RuntimePublicConfig = {
  oidcAuthority: string;
  oidcClientId: string;
  oidcResource: string;
  mapStyleUrl: string;
};

export type ApiPrincipal = {
  subject: string;
  issuer: string;
  identity: string;
  roles: string[];
};

export async function loadRuntimeConfig(): Promise<RuntimePublicConfig> {
  const response = await fetch("/api/public-config", { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) throw new Error("Unable to load deployment configuration.");
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object") throw new Error("Deployment configuration has an invalid format.");
  const value = payload as Record<string, unknown>;
  return {
    oidcAuthority: typeof value.oidcAuthority === "string" ? value.oidcAuthority.trim() : "",
    oidcClientId: typeof value.oidcClientId === "string" ? value.oidcClientId.trim() : "",
    oidcResource: typeof value.oidcResource === "string" ? value.oidcResource.trim() : "",
    mapStyleUrl: typeof value.mapStyleUrl === "string" ? value.mapStyleUrl.trim() : "",
  };
}

export function isOidcConfigured(config: RuntimePublicConfig | null): config is RuntimePublicConfig {
  return Boolean(config?.oidcAuthority && config.oidcClientId);
}

/**
 * Requests always use the same-origin BFF. The second parameter is retained as
 * a migration-compatible call-site marker; it is deliberately ignored and never
 * copied into an Authorization header. The BFF reads an HttpOnly cookie instead.
 */
export async function apiRequest<T>(
  path: string,
  _sessionMarker: string,
  init: RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("..")) {
    throw new Error("Invalid internal API path.");
  }
  const headers = new Headers(init.headers);
  headers.delete("Authorization");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/backend/api/v1${path}`, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "same-origin",
  });
  if (response.status === 401) throw new Error("Your MCHO session expired or is no longer valid. Sign in again.");
  if (response.status === 403) throw new Error("Your account does not have permission for this action.");
  if (!response.ok) {
    let message = `API request failed (HTTP ${response.status}).`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string") message = payload.detail;
      else if (Array.isArray(payload.detail)) {
        const details = payload.detail.map((item) => {
          if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") return item.msg;
          return null;
        }).filter((item): item is string => Boolean(item));
        if (details.length) message = details.join(" ");
      }
    } catch {
      // Keep the safe status-only message for non-JSON responses.
    }
    throw new Error(message);
  }
  return await response.json() as T;
}
