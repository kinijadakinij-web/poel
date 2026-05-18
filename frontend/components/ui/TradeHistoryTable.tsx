"use client";

import { useEffect, useState, useMemo } from "react";
import { useTrading } from "@/hooks/useTradingContext";
import { motion, AnimatePresence } from "framer-motion";
import { getTradeHistory } from "@/lib/api";
import { useAuth } from "@/hooks/useAuthContext";
import PosterButton from "@/components/ui/SignalPoster";

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

export default function TradeHistoryTable({ limit = 20, compact = false }: TradeHistoryTableProps) {
  const { state, balance } = useTrading();
  const { userId, isAuthenticated } = useAuth();
  const [apiHistory, setApiHistory] = useState<any[]>([]);

  useEffect(() => {
    let mounted = true;
    getTradeHistory(100, isAuthenticated ? userId || undefined : undefined)
      .then((res) => {
        if (!mounted) return;
        setApiHistory(res.data || []);
      })
      .catch(() => {});
    return () => { mounted = false; };
  }, [isAuthenticated, userId]);

  useEffect(() => {
    if (state.trade_count === 0 && state.win_count === 0 && state.loss_count === 0) {
      setApiHistory([]);
      getTradeHistory(100, isAuthenticated ? userId || undefined : undefined)
        .then((res) => setApiHistory(res.data || []))
        .catch(() => {});
    }
  }, [state.trade_count, state.win_count, state.loss_count, isAuthenticated, userId]);

  const history = useMemo(() => {
    const map = new Map<string, any>();
    apiHistory.forEach((s) => map.set(s.id, s));
    state.signals.forEach((s) => {
      if (s.result === "TP" || s.result === "SL" || s.status === "CLOSED") {
        map.set(s.id, s);
      }
    });
    return Array.from(map.values())
      .sort((a, b) => (b.closed_at || b.timestamp || 0) - (a.closed_at || a.timestamp || 0))
      .slice(0, limit);
  }, [apiHistory, state.signals, limit]);

  const headers = compact
    ? ["PAIR", "DIR", "ENTRY", "CLOSE", "PnL %", ""]
    : ["PAIR", "DIR", "ENTRY", "TP1", "TP2", "MAX", "CLOSE", "PnL %", ""];

  return (
    <div className="overflow-x-auto -mx-2 px-2">
      <table className="w-full min-w-[500px]">
        <thead>
          <tr className="border-b border-white/5">
            {headers.map((h) => (
              <th key={h} className="text-left py-2 px-2 text-[8px] font-mono text-white/20 tracking-widest">{h}</th>
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
                <td className="py-2.5 px-2 text-[10px] font-mono text-white font-medium">{sig.symbol.replace("_USDT", "")}</td>
                <td className="py-2.5 px-2">
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${sig.decision === "LONG" ? "bg-[#4ade80]/10 text-[#4ade80]" : "bg-[#f87171]/10 text-[#f87171]"}`}>
                    {sig.decision}
                  </span>
                </td>
                <td className="py-2.5 px-2 text-[10px] font-mono text-white/60">${formatPrice(sig.entry)}</td>
                {!compact && (
                  <>
                    <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]">${formatPrice(sig.tp1)}</td>
                    <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]/80">${formatPrice(sig.tp2)}</td>
                    <td className="py-2.5 px-2 text-[10px] font-mono text-[#d4a847]/60">${formatPrice(sig.tp_max)}</td>
                  </>
                )}
                <td className="py-2.5 px-2 text-[10px] font-mono text-white/60">${formatPrice(sig.closed_price)}</td>
                <td className={`py-2.5 px-2 text-[10px] font-mono font-bold ${(sig.pnl_pct || 0) >= 0 ? "text-[#4ade80]" : "text-[#f87171]"}`}>
                  {(sig.pnl_pct || 0) >= 0 ? "+" : ""}{sig.pnl_pct?.toFixed(2)}%
                </td>
                <td className="py-2.5 px-2">
                  <PosterButton signal={sig} leverage={balance.leverage} entryUsdt={balance.entry_usdt} allowForClosed={true} />
                </td>
              </motion.tr>
            ))}
          </AnimatePresence>
        </tbody>
      </table>
      {history.length === 0 && (
        <div className="text-center py-8">
          <p className="text-[10px] font-mono text-white/20 tracking-widest">NO TRADE HISTORY</p>
        </div>
      )}
    </div>
  );
}