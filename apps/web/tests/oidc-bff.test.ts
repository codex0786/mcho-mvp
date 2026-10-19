import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, test } from "node:test";

import { generateKeyPair, exportJWK, SignJWT } from "jose";
import { NextRequest } from "next/server";

import { GET as oidcLogin } from "../app/api/auth/login/route";
import { GET as oidcCallback } from "../app/api/auth/callback/route";
import { POST as backendProxyPost } from "../app/api/backend/[...path]/route";

const originalEnv = { ...process.env };
let server: Server;
let issuer = "";
let clientId = "mcho-test-client";
let activeNonce = "";
let exchangedVerifier = "";
let tokenExchangeCount = 0;
let jwk: Record<string, unknown>;
let privateKey: CryptoKey;

function sendJson(res: import("node:http").ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(payload));
}

async function readRequestBody(req: import("node:http").IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

before(async () => {
  Reflect.set(process.env, "NODE_ENV", "test");
  const keyPair = await generateKeyPair("RS256");
  privateKey = keyPair.privateKey as CryptoKey;
  jwk = { ...await exportJWK(keyPair.publicKey), kid: "mcho-test-key", use: "sig", alg: "RS256", key_ops: ["verify"] };

  server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", `http://${req.headers.host}`);
    if (url.pathname === "/tenant/.well-known/openid-configuration") {
      sendJson(res, 200, {
        issuer,
        authorization_endpoint: `${issuer.replace("/tenant", "")}/authorize`,
        token_endpoint: `${issuer.replace("/tenant", "")}/token`,
        jwks_uri: `${issuer.replace("/tenant", "")}/jwks`,
      });
      return;
    }
    if (url.pathname === "/jwks") {
      sendJson(res, 200, { keys: [jwk] });
      return;
    }
    if (url.pathname === "/token" && req.method === "POST") {
      const body = new URLSearchParams(await readRequestBody(req));
      exchangedVerifier = body.get("code_verifier") ?? "";
      tokenExchangeCount += 1;
      const now = Math.floor(Date.now() / 1000);
      const idToken = await new SignJWT({ nonce: activeNonce })
        .setProtectedHeader({ alg: "RS256", kid: "mcho-test-key" })
        .setIssuer(issuer)
        .setAudience(clientId)
        .setSubject("test-user-123")
        .setIssuedAt(now)
        .setExpirationTime(now + 300)
        .sign(privateKey);
      sendJson(res, 200, {
        access_token: "api-access-token-test",
        token_type: "Bearer",
        expires_in: 300,
        id_token: idToken,
      });
      return;
    }
    sendJson(res, 404, { error: "not_found" });
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address() as AddressInfo;
  issuer = `http://127.0.0.1:${address.port}/tenant`;
  process.env.MCHO_OIDC_AUTHORITY = issuer;
  process.env.MCHO_OIDC_CLIENT_ID = clientId;
  process.env.MCHO_OIDC_RESOURCE = "mcho-api";
  process.env.MCHO_WEB_ORIGIN = "http://localhost:3000";
  process.env.MCHO_API_ORIGIN = "http://127.0.0.1:9999";
});

after(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
  for (const key of [
    "NODE_ENV", "MCHO_OIDC_AUTHORITY", "MCHO_OIDC_CLIENT_ID", "MCHO_OIDC_RESOURCE",
    "MCHO_WEB_ORIGIN", "MCHO_API_ORIGIN",
  ]) {
    if (originalEnv[key] === undefined) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

function getCookie(response: Response, name: string): string {
  const cookie = (response as { cookies?: { get: (cookieName: string) => { value: string } | undefined } })
    .cookies?.get(name);
  assert.ok(cookie, `Expected ${name} cookie`);
  return cookie.value;
}

test("OIDC login starts code flow with S256 PKCE and callback exchanges verifier server-side", async () => {
  const login = await oidcLogin(new NextRequest("http://localhost:3000/api/auth/login"));
  assert.equal(login.status, 302);
  const redirect = new URL(login.headers.get("location") ?? "");
  assert.equal(redirect.origin, issuer.replace("/tenant", ""));
  assert.equal(redirect.searchParams.get("client_id"), clientId);
  assert.equal(redirect.searchParams.get("response_type"), "code");
  assert.equal(redirect.searchParams.get("code_challenge_method"), "S256");
  assert.equal(redirect.searchParams.get("resource"), "mcho-api");
  assert.equal(redirect.searchParams.get("redirect_uri"), "http://localhost:3000/api/auth/callback");

  const state = getCookie(login, "mcho_oidc_state");
  const nonce = getCookie(login, "mcho_oidc_nonce");
  const verifier = getCookie(login, "mcho_oidc_verifier");
  activeNonce = nonce;
  assert.equal(login.cookies.get("mcho_oidc_state")?.httpOnly, true);
  assert.equal(login.cookies.get("mcho_oidc_verifier")?.path, "/api/auth/callback");

  const callbackUrl = new URL("http://localhost:3000/api/auth/callback");
  callbackUrl.searchParams.set("code", "one-time-auth-code");
  callbackUrl.searchParams.set("state", state);
  const cookieHeader = [
    `mcho_oidc_state=${state}`, `mcho_oidc_nonce=${nonce}`, `mcho_oidc_verifier=${verifier}`,
  ].join("; ");
  const callback = await oidcCallback(new NextRequest(callbackUrl, { headers: { cookie: cookieHeader } }));

  assert.equal(callback.status, 303);
  assert.equal(callback.headers.get("location"), "http://localhost:3000/analyst");
  assert.equal(exchangedVerifier, verifier);
  const accessCookie = callback.cookies.get("mcho_access_token");
  assert.ok(accessCookie);
  assert.equal(accessCookie.httpOnly, true);
  assert.equal(accessCookie.path, "/api/backend");
  assert.equal(accessCookie.value, "api-access-token-test");
  assert.ok((accessCookie.maxAge ?? 0) <= 300);
  assert.equal(callback.cookies.get("mcho_oidc_state")?.maxAge, 0);
});

test("OIDC callback rejects a state mismatch without exchanging the code", async () => {
  const login = await oidcLogin(new NextRequest("http://localhost:3000/api/auth/login"));
  const state = getCookie(login, "mcho_oidc_state");
  const nonce = getCookie(login, "mcho_oidc_nonce");
  const verifier = getCookie(login, "mcho_oidc_verifier");
  const before = tokenExchangeCount;
  const callbackUrl = new URL("http://localhost:3000/api/auth/callback?code=malicious-code&state=attacker-state");
  const response = await oidcCallback(new NextRequest(callbackUrl, {
    headers: { cookie: [
      `mcho_oidc_state=${state}`, `mcho_oidc_nonce=${nonce}`, `mcho_oidc_verifier=${verifier}`,
    ].join("; ") },
  }));
  assert.equal(response.status, 303);
  assert.match(response.headers.get("location") ?? "", /auth_error=invalid_state/);
  assert.equal(response.cookies.get("mcho_access_token"), undefined);
  assert.equal(tokenExchangeCount, before);
});

test("backend proxy ignores a browser-supplied bearer token and injects the HttpOnly-cookie token", async () => {
  const originalFetch = globalThis.fetch;
  let observedAuthorization = "";
  let observedCookie = "";
  let observedRequestId = "";
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    observedAuthorization = headers.get("authorization") ?? "";
    observedCookie = headers.get("cookie") ?? "";
    observedRequestId = headers.get("x-request-id") ?? "";
    return new Response(JSON.stringify({ accepted: true }), {
      status: 201,
      headers: { "content-type": "application/json", "x-request-id": "upstream-request-123" },
    });
  }) as typeof fetch;

  try {
    const request = new NextRequest("http://localhost:3000/api/backend/api/v1/events/drafts", {
      method: "POST",
      headers: {
        cookie: "mcho_access_token=trusted-cookie-token",
        authorization: "Bearer attacker-controlled-token",
        origin: "http://localhost:3000",
        "content-type": "application/json",
        "x-request-id": "client-request-456",
      },
      body: JSON.stringify({ summary: "test fixture" }),
    });
    const response = await backendProxyPost(request, {
      params: Promise.resolve({ path: ["api", "v1", "events", "drafts"] }),
    });
    assert.equal(response.status, 201);
    assert.equal(observedAuthorization, "Bearer trusted-cookie-token");
    assert.equal(observedCookie, "");
    assert.equal(observedRequestId, "client-request-456");
    assert.equal(response.headers.get("x-request-id"), "upstream-request-123");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("backend proxy rejects a cross-origin cookie-authenticated mutation", async () => {
  const originalFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = (async () => {
    upstreamCalls += 1;
    return new Response("should not be reached", { status: 200 });
  }) as typeof fetch;

  try {
    const request = new NextRequest("http://localhost:3000/api/backend/api/v1/events/drafts", {
      method: "POST",
      headers: {
        cookie: "mcho_access_token=trusted-cookie-token",
        origin: "https://attacker.example",
        "content-type": "application/json",
      },
      body: "{}",
    });
    const response = await backendProxyPost(request, {
      params: Promise.resolve({ path: ["api", "v1", "events", "drafts"] }),
    });
    assert.equal(response.status, 403);
    assert.equal(upstreamCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
