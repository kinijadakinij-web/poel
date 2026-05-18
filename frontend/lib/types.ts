export interface Signal {
  id: string;
  symbol: string;
  timestamp: number;
  current_price: number;
  trend?: string;
  pattern?: string;
  decision: "LONG" | "SHORT" | "NO TRADE";
  entry?: number | null;
  tp?: number | null;
  sl?: number | null;
  invalidation?: number | null;
  reason?: string;
  confidence?: number;
  status?: "OPEN" | "CLOSED" | "INVALIDATED";
  result?: "TP" | "SL" | "AI_CLOSE" | "INVALIDATED" | "TIMEOUT" | null;
  pnl_pct?: number | null;
  pnl_usdt?: number | null;
  closed_at?: number | null;
  closed_price?: number | null;
  entry_hit?: boolean;
  last_ai_decision?: string;
  last_ai_reason?: string;
  last_ai_at?: number;
  sl_plus_count?: number;
  sl_plus_history?: Array<{
    from: number;
    to: number;
    price: number;
    at: number;
  }>;
}

export interface BotState {
  status: string;
  last_signal?: Signal;
  last_error?: string;
  signals: Signal[];
  trade_count: number;
  win_count: number;
  loss_count: number;
  no_trade_count: number;
  total_pnl_pct: number;
  total_pnl_usdt: number;
  current_symbol?: string;
  symbols_scanned: number;
  active_signal_count: number;
  max_active_signals: number;
  winrate: number;
  balance: number;
}

export interface BalanceInfo {
  balance: number;
  initial_balance: number;
  leverage: number;
  entry_usdt: number;
}

export type WSEvent = 
  | { event: "signal"; data: Signal }
  | { event: "signal_closed"; data: Signal & { balance: number } }
  | { event: "signal_invalidated"; data: { id: string; symbol: string; price: number; timestamp: number; reason?: string } }
  | { event: "price_tick"; data: { id: string; symbol: string; price: number; entry_hit: boolean; timestamp: number } }
  | { event: "balance_update"; data: BalanceInfo }
  | { event: "signal_ai_update"; data: { id: string; symbol: string; decision: string; reason: string; new_sl?: number; timestamp: number } }
  | { event: "signal_sl_updated"; data: { id: string; symbol: string; direction: string; old_sl: number; new_sl: number; price: number; reason: string; timestamp: number } }
  | { event: "reset_all"; data: Record<string, unknown> }
  | { event: "status" | "progress" | "error"; data: unknown };
