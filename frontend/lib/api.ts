// api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

function getTimestamp() {
  return Date.now().toString();
}

export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<any> {
  const url = `${API_BASE}${path}`;
  const token = getToken();
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Timestamp": getTimestamp(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
      // X-API-Key dihapus — endpoint public tidak butuh key,
      // endpoint protected dijaga JWT
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }

  return res.json();
}

// ── Token helpers ──
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
  return apiFetch("/api/auth/register", { method: "POST", body: JSON.stringify(body) });
}
export async function login(body: { username: string; passkey: string }) {
  return apiFetch("/api/auth/login", { method: "POST", body: JSON.stringify(body) });
}
export async function getMe() {
  return apiFetch("/api/auth/me");
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
  return apiFetch(`/api/bot/start${qs}`, { method: "POST", body: JSON.stringify(config) });
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
