"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { useTrading } from "@/hooks/useTradingContext";
import { motion, AnimatePresence } from "framer-motion";
import { getTradeHistory } from "@/lib/api";
import { useAuth } from "@/hooks/useAuthContext";
import PosterButton from "@/components/ui/SignalPoster";
import { TableRowSkeleton } from "@/components/ui/Skeleton";

interface TradeHistoryTableProps {
  limit?: number;
  compact?: boolean;
}

function formatPrice(n: number | undefined) {
  if (n === undefined || n === null) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}

function formatDate(ts: number | null | undefined) {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// ── CSV Export ────────────────────────────────────────────────────────────────
function exportToCSV(data: any[]) {
  if (!data.length) return;

  const headers = [
    "Date",
    "Pair",
    "Direction",
    "Entry",
    "TP1",
    "TP2",
    "MAX TP",
    "Close Price",
    "Result",
    "PnL %",
    "PnL USDT",
  ];

  const rows = data.map((s) => [
    formatDate(s.closed_at ?? s.timestamp),
    s.symbol.replace("_USDT", ""),
    s.decision,
    s.entry ?? "",
    s.tp1 ?? "",
    s.tp2 ?? "",
    s.tp_max ?? "",
    s.closed_price ?? "",
    s.result ?? "",
    s.pnl_pct != null ? s.pnl_pct.toFixed(2) : "",
    s.pnl_usdt != null ? s.pnl_usdt.toFixed(2) : "",
  ]);

  const csvContent = [headers, ...rows]
    .map((row) => row.map((cell) => `"${cell}"`).join(","))
    .join("\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `sonnetrade_history_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

// ─────────────────────────────────────────────────────────────────────────────

export default function TradeHistoryTable({
  limit = 20,
  compact = false,
}: TradeHistoryTableProps) {
  const { state, balance } = useTrading();
  const { userId, isAuthenticated } = useAuth();
  const [apiHistory, setApiHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // ── Fetch history ──────────────────────────────────────────────────────────
  const fetchHistory = useCallback(() => {
    setLoading(true);
    getTradeHistory(100, isAuthenticated ? userId || undefined : undefined)
      .then((res) => setApiHistory(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isAuthenticated, userId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Re-fetch when reset is detected
  useEffect(() => {
    if (
      state.trade_count === 0 &&
      state.win_count === 0 &&
      state.loss_count === 0
    ) {
      setApiHistory([]);
      fetchHistory();
    }
  }, [state.trade_count, state.win_count, state.loss_count, fetchHistory]);

  // ── Merge API + WS state ───────────────────────────────────────────────────
  const history = useMemo(() => {
    const map = new Map<string, any>();
    apiHistory.forEach((s) => map.set(s.id, s));
    state.signals.forEach((s) => {
      if (
        s.result === "TP" ||
        s.result === "SL" ||
        s.status === "CLOSED"
      ) {
        map.set(s.id, s);
      }
    });
    return Array.from(map.values())
      .sort(
        (a, b) =>
          (b.closed_at ?? b.timestamp ?? 0) -
          (a.closed_at ?? a.timestamp ?? 0)
      )
      .slice(0, limit);
  }, [apiHistory, state.signals, limit]);

  const headers = compact
    ? ["PAIR", "DIR", "ENTRY", "CLOSE", "PnL %", ""]
    : ["PAIR", "DIR", "ENTRY", "TP1", "TP2", "MAX", "CLOSE", "PnL %", ""];

  // ── Skeleton ───────────────────────────────────────────────────────────────
  if (loading && history.length === 0) {
    return (
      <div className="overflow-x-auto -mx-2 px-2 space-y-0">
        <table className="w-full min-w-[500px]">
          <thead>
            <tr className="border-b border-white/5">
              {headers.map((h) => (
                <th
                  key={h}
                  className="text-left py-2 px-2 text-[8px] font-mono text-white/20 tracking-widest"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <TableRowSkeleton key={i} cols={headers.length} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Toolbar: refresh + export */}
      {!compact && (
        <div className="flex items-center justify-between px-1">
          <span className="text-[9px] font-mono text-white/20 tracking-widest">
            {history.length} records
          </span>
          <div className="flex items-center gap-2">
            {/* Refresh */}
            <button
              onClick={fetchHistory}
              disabled={loading}
              className="px-3 py-1.5 rounded-lg glass border border-white/10 text-[9px] font-mono text-white/40 hover:text-white/70 hover:bg-white/5 transition-colors disabled:opacity-40"
              title="Refresh history"
            >
              {loading ? "..." : "↻ REFRESH"}
            </button>

            {/* Export CSV */}
            <button
              onClick={() => exportToCSV(history)}
              disabled={history.length === 0}
              className="px-3 py-1.5 rounded-lg bg-[#d4a847]/8 border border-[#d4a847]/25 text-[9px] font-mono text-[#d4a847]/70 hover:text-[#d4a847] hover:bg-[#d4a847]/15 transition-colors disabled:opacity-30"
              title="Export as CSV"
            >
              ↓ EXPORT CSV
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto -mx-2 px-2">
        <table className="w-full min-w-[500px]">
          <thead>
            <tr className="border-b border-white/5">
              {headers.map((h) => (
                <th
                  key={h}
                  className="text-left py-2 px-2 text-[8px] font-mono text-white/20 tracking-widest"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <AnimatePresence>
              {history.map((sig, i) => (
                <motion.tr
                  key={sig.id || i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="border-b border-white/[0.02] hover:bg-white/[0.02] transition-colors"
                >
                  <td className="py-2.5 px-2 text-[10px] font-mono text-white font-medium">
                    {sig.symbol.replace("_USDT", "")}
                  </td>
                  <td className="py-2.5 px-2">
                    <span
                      className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                        sig.decision === "LONG"
                          ? "bg-[#4ade80]/10 text-[#4ade80]"
                          : "bg-[#f87171]/10 text-[#f87171]"
                      }`}
                    >
                      {sig.decision}
                    </span>
                  </td>
                  <td className="py-2.5 px-2 text-[10px] font-mono text-white/60">
                    ${formatPrice(sig.entry)}
                  </td>
                  {!compact && (
                    <>
                      <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]">
                        ${formatPrice(sig.tp1)}
                      </td>
                      <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]/80">
                        ${formatPrice(sig.tp2)}
                      </td>
                      <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]/60">
                        ${formatPrice(sig.tp_max)}
                      </td>
                    </>
                  )}
                  <td className="py-2.5 px-2 text-[10px] font-mono text-white/60">
                    ${formatPrice(sig.closed_price)}
                  </td>
                  <td
                    className={`py-2.5 px-2 text-[10px] font-mono font-bold ${
                      (sig.pnl_pct || 0) >= 0
                        ? "text-[#4ade80]"
                        : "text-[#f87171]"
                    }`}
                  >
                    {(sig.pnl_pct || 0) >= 0 ? "+" : ""}
                    {sig.pnl_pct?.toFixed(2)}%
                  </td>
                  <td className="py-2.5 px-2">
                    <PosterButton
                      signal={sig}
                      leverage={balance.leverage}
                      entryUsdt={balance.entry_usdt}
                      allowForClosed={true}
                    />
                  </td>
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>

        {history.length === 0 && !loading && (
          <div className="text-center py-8">
            <p className="text-[10px] font-mono text-white/20 tracking-widest">
              NO TRADE HISTORY
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
