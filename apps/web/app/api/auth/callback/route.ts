import { timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { getOidcMetadata, getServerOidcConfig, verifyIdToken } from "../../../../lib/oidc-server";

export const dynamic = "force-dynamic";

function securelyEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function clearPendingCookies(response: NextResponse, origin?: string): void {
  const secure = origin ? new URL(origin).protocol === "https:" : process.env.NODE_ENV === "production";
  const options = { httpOnly: true, secure, sameSite: "lax" as const, path: "/api/auth/callback", maxAge: 0 };
  response.cookies.set("mcho_oidc_state", "", options);
  response.cookies.set("mcho_oidc_nonce", "", options);
  response.cookies.set("mcho_oidc_verifier", "", options);
}

function errorRedirect(origin: string, reason: string): NextResponse {
  const response = NextResponse.redirect(new URL(`/analyst?auth_error=${encodeURIComponent(reason)}`, origin), 303);
  clearPendingCookies(response, origin);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  let webOrigin = "";
  try {
    const config = getServerOidcConfig(request);
    webOrigin = config.webOrigin;

    const params = request.nextUrl.searchParams;
    if (params.has("error")) return errorRedirect(webOrigin, "provider");
    const code = params.get("code") ?? "";
    const returnedState = params.get("state") ?? "";
    const expectedState = request.cookies.get("mcho_oidc_state")?.value ?? "";
    const nonce = request.cookies.get("mcho_oidc_nonce")?.value ?? "";
    const verifier = request.cookies.get("mcho_oidc_verifier")?.value ?? "";
    if (!code || !returnedState || !expectedState || !nonce || !verifier || !securelyEqual(returnedState, expectedState)) {
      return errorRedirect(webOrigin, "invalid_state");
    }

    const metadata = await getOidcMetadata(config.authority);
    const callback = new URL("/api/auth/callback", webOrigin);
    const form = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: callback.toString(),
      code_verifier: verifier,
    });
    if (config.resource) form.set("resource", config.resource);
    const tokenResponse = await fetch(metadata.token_endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: form,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    if (!tokenResponse.ok) return errorRedirect(webOrigin, "token_exchange");
    const tokenPayload: unknown = await tokenResponse.json();
    if (!tokenPayload || typeof tokenPayload !== "object") return errorRedirect(webOrigin, "token_response");
    const token = tokenPayload as Record<string, unknown>;
    const accessToken = token.access_token;
    const idToken = token.id_token;
    const expiresIn = token.expires_in;
    if (
      typeof accessToken !== "string" || !accessToken || accessToken.length > 16_000
      || typeof idToken !== "string" || !idToken
      || typeof expiresIn !== "number" || !Number.isFinite(expiresIn) || expiresIn <= 0
      || String(token.token_type ?? "").toLowerCase() !== "bearer"
    ) {
      return errorRedirect(webOrigin, "token_response");
    }
    await verifyIdToken(idToken, metadata, config.clientId, nonce);

    const lifetime = Math.min(3600, Math.max(1, Math.floor(expiresIn)));
    const response = NextResponse.redirect(new URL("/analyst", webOrigin), 303);
    response.cookies.set("mcho_access_token", accessToken, {
      httpOnly: true,
      secure: new URL(webOrigin).protocol === "https:",
      sameSite: "lax",
      path: "/api/backend",
      maxAge: lifetime,
    });
    clearPendingCookies(response, webOrigin || undefined);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  } catch {
    const response = NextResponse.json(
      { detail: "Sign-in could not be completed. Check identity-provider configuration and server logs." },
      { status: 400, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } },
    );
    clearPendingCookies(response);
    return response;
  }
}
