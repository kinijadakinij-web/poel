// pages/api/proxy/[...path].ts
// Server-side proxy — inject X-API-Key tanpa expose ke browser.
// Semua POST/PUT/DELETE dari frontend diarahkan ke sini.
//
// Env yang dibutuhkan (server-side only, BUKAN NEXT_PUBLIC_):
//   API_URL     = https://grthrrh-production.up.railway.app
//   API_KEY     = agx_prod_...  ← secret, hanya ada di server

import type { NextApiRequest, NextApiResponse } from "next";

const BACKEND = process.env.API_URL || "";
const API_KEY  = process.env.API_KEY  || "";  // ← BUKAN NEXT_PUBLIC_

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse
) {
  const { path } = req.query;
  const subPath = Array.isArray(path) ? path.join("/") : path || "";
  const qs = new URLSearchParams(
    req.query as Record<string, string>
  );
  // Hapus 'path' dari query string (itu parameter Next.js catch-all)
  qs.delete("path");
  const qsStr = qs.toString() ? `?${qs.toString()}` : "";

  const targetUrl = `${BACKEND}/api/${subPath}${qsStr}`;

  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,              // inject di server, tidak pernah ke browser
      "X-Timestamp": Date.now().toString(),
    };

    // Forward Authorization header dari client jika ada
    if (req.headers.authorization) {
      headers["Authorization"] = req.headers.authorization;
    }

    const backendRes = await fetch(targetUrl, {
      method: req.method,
      headers,
      body: req.method !== "GET" && req.method !== "HEAD"
        ? JSON.stringify(req.body)
        : undefined,
    });

    const data = await backendRes.json().catch(() => ({}));
    res.status(backendRes.status).json(data);
  } catch (err: any) {
    res.status(502).json({ detail: "Proxy error", error: err.message });
  }
}
