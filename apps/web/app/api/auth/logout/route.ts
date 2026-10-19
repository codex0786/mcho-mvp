import { NextRequest, NextResponse } from "next/server";

import { isSameOriginMutation } from "../../../../lib/oidc-server";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isSameOriginMutation(request)) {
    return NextResponse.json({ detail: "Cross-origin logout request rejected." }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const response = NextResponse.json({ signedOut: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set("mcho_access_token", "", {
    httpOnly: true,
    secure: request.nextUrl.protocol === "https:",
    sameSite: "lax",
    path: "/api/backend",
    maxAge: 0,
  });
  return response;
}
