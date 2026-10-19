"use client";

import { UserManager, WebStorageStateStore, type UserManagerSettings } from "oidc-client-ts";

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
  const response = await fetch("/api/public-config", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to load deployment configuration.");
  }
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== "object") {
    throw new Error("Deployment configuration has an invalid format.");
  }
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

export function createOidcUserManager(config: RuntimePublicConfig): UserManager {
  if (!isOidcConfigured(config)) {
    throw new Error("OIDC authority and client ID are required.");
  }

  const authorityUrl = new URL(config.oidcAuthority);
  if (
    window.location.protocol === "https:"
    && authorityUrl.protocol !== "https:"
  ) {
    throw new Error("The identity provider must use HTTPS on a secure deployment.");
  }
  if (authorityUrl.protocol !== "https:" && authorityUrl.hostname !== "localhost") {
    throw new Error("The identity-provider authority must use HTTPS.");
  }

  const sessionStore = new WebStorageStateStore({ store: window.sessionStorage });
  const settings: UserManagerSettings = {
    authority: authorityUrl.toString().replace(/\/$/, ""),
    client_id: config.oidcClientId,
    redirect_uri: new URL("/auth/callback", window.location.origin).toString(),
    post_logout_redirect_uri: new URL("/analyst", window.location.origin).toString(),
    response_type: "code",
    scope: "openid profile email",
    userStore: sessionStore,
    stateStore: sessionStore,
    automaticSilentRenew: false,
    monitorSession: false,
    loadUserInfo: false,
    filterProtocolClaims: true,
    extraQueryParams: config.oidcResource ? { resource: config.oidcResource } : undefined,
  };
  return new UserManager(settings);
}

export async function apiRequest<T>(
  path: string,
  accessToken: string,
  init: RequestInit = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("..")) {
    throw new Error("Invalid internal API path.");
  }
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/backend/api/v1${path}`, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "same-origin",
  });
  if (response.status === 401) {
    throw new Error("Your access token is expired or no longer valid. Sign in again.");
  }
  if (!response.ok) {
    let message = `API request failed (HTTP ${response.status}).`;
    try {
      const payload = await response.json() as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail)) {
        const details = payload.detail.map((item) => {
          if (item && typeof item === "object" && "msg" in item && typeof item.msg === "string") {
            return item.msg;
          }
          return null;
        }).filter((item): item is string => Boolean(item));
        if (details.length) message = details.join(" ");
      }
    } catch {
      // Preserve the safe status-only message for non-JSON upstream responses.
    }
    throw new Error(message);
  }
  return await response.json() as T;
}
