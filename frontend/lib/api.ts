// api.ts — inline config (no external config file needed)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function getTimestamp() {
  return Date.now().toString();
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  const url = `${API_BASE}${path}`;
  const token = getToken();  // ← ambil token
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      "X-Timestamp": getTimestamp(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),  // ← auto-kirim token
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  return res.json();
}

// ── Token helpers (localStorage) ──
const TOKEN_KEY = "agentx_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

// ── Auth ──
export async function register(body: { username: string; passkey: string }) {
  return apiFetch("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function login(body: { username: string; passkey: string }) {
  return apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getMe() {
  const token = getToken();
  return apiFetch("/api/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
}

// ── Bot ──
export async function getBotState(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/bot/state${qs}`);
}

export async function startBot(
  config: { symbol: string; tp_pct: number; sl_pct: number; interval: number },
  userId?: string
) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/bot/start${qs}`, {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function stopBot(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/bot/stop${qs}`, { method: "POST" });
}

export async function resetBot(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/bot/reset${qs}`, { method: "POST" });
}

export async function getBotSignals(limit: number = 50, userId?: string) {
  const qs = userId ? `?user=${userId}&limit=${limit}` : `?limit=${limit}`;
  return apiFetch(`/api/bot/signals${qs}`);
}

export async function getBotStats(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/bot/stats${qs}`);
}

// ── Trading ──
export async function getBalance(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/trading/balance${qs}`);
}

export async function getPositions(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/trading/positions${qs}`);
}

export async function getTradeHistory(limit: number = 50, userId?: string) {
  const qs = userId ? `?user=${userId}&limit=${limit}` : `?limit=${limit}`;
  return apiFetch(`/api/trading/history${qs}`);
}

export async function getTradingSettings(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/trading/settings${qs}`);
}

export async function resetBalance(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/trading/reset-balance${qs}`, { method: "POST" });
}

// ── History ──
export async function getSignalHistory(limit: number = 100, userId?: string) {
  const qs = userId ? `?user=${userId}&limit=${limit}` : `?limit=${limit}`;
  return apiFetch(`/api/history/signals${qs}`);
}

export async function getSummary(userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/history/summary${qs}`);
}

export async function getSummaryBySymbol(symbol: string, userId?: string) {
  const qs = userId ? `?user=${userId}` : "";
  return apiFetch(`/api/history/summary/${symbol}${qs}`);
}