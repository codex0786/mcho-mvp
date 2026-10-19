import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const response = NextResponse.json(
    {
      oidcAuthority: process.env.MCHO_OIDC_AUTHORITY ?? "",
      oidcClientId: process.env.MCHO_OIDC_CLIENT_ID ?? "",
      oidcResource: process.env.MCHO_OIDC_RESOURCE ?? "",
      mapStyleUrl: process.env.MCHO_MAP_STYLE_URL ?? process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "",
    },
    { status: 200 },
  );
  response.headers.set("Cache-Control", "no-store, max-age=0");
  response.headers.set("Pragma", "no-cache");
  return response;
}
