// app/api/proxy/[...path]/route.ts
// Server-side proxy — inject X-API-Key tanpa expose ke browser.
// Env (server-side only, BUKAN NEXT_PUBLIC_):
//   API_URL = https://grthrrh-production.up.railway.app
//   API_KEY = agx_prod_...

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.API_URL || "";
const API_KEY  = process.env.API_KEY  || "";

async function proxyRequest(req: NextRequest, params: { path: string[] }) {
  const subPath = params.path.join("/");
  const { searchParams } = new URL(req.url);
  const qs = searchParams.toString() ? `?${searchParams.toString()}` : "";
  const targetUrl = `${BACKEND}/api/${subPath}${qs}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
    "X-Timestamp": Date.now().toString(),
  };

  const auth = req.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.text()
      : undefined;

  const backendRes = await fetch(targetUrl, {
    method: req.method,
    headers,
    body,
  });

  const data = await backendRes.json().catch(() => ({}));
  return NextResponse.json(data, { status: backendRes.status });
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params);
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params);
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params);
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params);
}
export async function PATCH(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params);
}
