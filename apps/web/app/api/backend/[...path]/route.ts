import { NextRequest, NextResponse } from "next/server";
import { isSameOriginMutation } from "../../../../lib/oidc-server";

type RouteContext = { params: Promise<{ path: string[] }> };

const ALLOWED_METHODS = new Set(["GET", "POST", "PATCH"]);

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const origin = process.env.MCHO_API_ORIGIN?.trim();
  if (!origin) {
    return Response.json(
      { detail: "Backend API origin is not configured for this deployment." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (!ALLOWED_METHODS.has(request.method)) {
    return Response.json({ detail: "Method not allowed." }, { status: 405 });
  }

  const { path } = await context.params;
  if (!Array.isArray(path) || path.length < 2 || path[0] !== "api" || path[1] !== "v1"
      || path.some((part) => !part || part === "." || part === ".." || part.includes("/"))) {
    return Response.json({ detail: "Not found." }, { status: 404 });
  }

  let target: URL;
  try {
    const normalizedOrigin = origin.endsWith("/") ? origin : `${origin}/`;
    target = new URL(`${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, normalizedOrigin);
    const isLocalComposeTarget = target.hostname === "api" && target.port === "8000";
    if (target.protocol !== "https:" && process.env.NODE_ENV === "production" && !isLocalComposeTarget) {
      return Response.json({ detail: "Backend API origin must use HTTPS in production (except the internal local-Compose API service)." }, { status: 503 });
    }
  } catch {
    return Response.json({ detail: "Backend API origin is invalid." }, { status: 503 });
  }

  const sessionToken = request.cookies.get("mcho_access_token")?.value ?? "";
  if (request.method !== "GET" && sessionToken && !isSameOriginMutation(request)) {
    return Response.json(
      { detail: "Cross-origin state-changing request rejected." },
      { status: 403, headers: { "Cache-Control": "no-store" } },
    );
  }

  // Only forward headers the upstream API needs. Never trust a browser-provided
  // Authorization header: the bearer token comes only from the HttpOnly session cookie.
  const headers = new Headers();
  for (const key of ["content-type", "accept", "x-request-id"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);

  try {
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
    // An HTML error page (the host's edge challenge or a wake failure) is not API data:
    // answer with a retryable JSON 503 instead of passing the page or its status through.
    const upstreamType = upstream.headers.get("content-type") ?? "";
    if (upstream.status >= 400 && upstreamType.includes("text/html")) {
      await upstream.body?.cancel();
      return Response.json(
        { detail: "The data server is waking up or busy; try again shortly." },
        { status: 503, headers: { "Cache-Control": "no-store", "Retry-After": "10" } },
      );
    }
    const responseHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    const requestId = upstream.headers.get("x-request-id");
    if (requestId) responseHeaders.set("x-request-id", requestId);
    responseHeaders.set("cache-control", "no-store");
    const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
    if (upstream.status === 401 && sessionToken) {
      response.cookies.set("mcho_access_token", "", {
        httpOnly: true,
        secure: request.nextUrl.protocol === "https:",
        sameSite: "lax",
        path: "/api/backend",
        maxAge: 0,
      });
    }
    return response;
  } catch {
    return Response.json(
      { detail: "Backend API is temporarily unavailable." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
