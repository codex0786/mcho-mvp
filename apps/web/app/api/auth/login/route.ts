import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

import { getOidcMetadata, getServerOidcConfig } from "../../../../lib/oidc-server";

export const dynamic = "force-dynamic";

function randomUrlSafe(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  try {
    const config = getServerOidcConfig(request);
    const metadata = await getOidcMetadata(config.authority);
    const state = randomUrlSafe();
    const nonce = randomUrlSafe();
    const verifier = randomUrlSafe(48);
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const callback = new URL("/api/auth/callback", config.webOrigin);
    const authorize = new URL(metadata.authorization_endpoint);
    authorize.searchParams.set("client_id", config.clientId);
    authorize.searchParams.set("response_type", "code");
    authorize.searchParams.set("redirect_uri", callback.toString());
    authorize.searchParams.set("scope", "openid profile email");
    authorize.searchParams.set("state", state);
    authorize.searchParams.set("nonce", nonce);
    authorize.searchParams.set("code_challenge", challenge);
    authorize.searchParams.set("code_challenge_method", "S256");
    if (config.resource) authorize.searchParams.set("resource", config.resource);
    if (config.audience) authorize.searchParams.set("audience", config.audience);

    const response = NextResponse.redirect(authorize, 302);
    const secure = new URL(config.webOrigin).protocol === "https:";
    const options = { httpOnly: true, secure, sameSite: "lax" as const, path: "/api/auth/callback", maxAge: 600 };
    response.cookies.set("mcho_oidc_state", state, options);
    response.cookies.set("mcho_oidc_nonce", nonce, options);
    response.cookies.set("mcho_oidc_verifier", verifier, options);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    return response;
  } catch {
    // Do not redirect to an unvalidated Host header if deployment configuration is missing.
    return NextResponse.json(
      { detail: "OIDC sign-in is not configured or the identity provider is unavailable." },
      { status: 503, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } },
    );
  }
}
