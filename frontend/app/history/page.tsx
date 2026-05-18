"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import TradeHistoryTable from "@/components/ui/TradeHistoryTable";
import { useTrading } from "@/hooks/useTradingContext";
import { useAuth } from "@/hooks/useAuthContext";
import { getSummary } from "@/lib/api";

export default function HistoryPage() {
  const { state } = useTrading();
  const { isAuthenticated, userId } = useAuth();
  const [summary, setSummary] = useState({
    total_signals: 0,
    closed_trades: 0,
    wins: 0,
    losses: 0,
    winrate: 0,
    total_pnl_pct: 0,
  });

  useEffect(() => {
    getSummary(isAuthenticated ? userId || undefined : undefined)
      .then((data) => {
        if (data.data) setSummary(data.data);
      })
      .catch(() => {});
  }, [isAuthenticated, userId, state.trade_count]);

  return (
    <main className="relative min-h-screen bg-[#030303] pt-24 pb-20 px-4 sm:px-8">
      <div className="fixed inset-0 -z-10 bg-[#030303]" />
      <div className="fixed inset-0 -z-10 opacity-15" style={{ backgroundImage: "radial-gradient(circle at 80% 0%, #4c1d95 0%, transparent 50%)" }} />

      <div className="max-w-5xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} className="mb-10">
          <Link href="/?section=history" className="inline-flex items-center gap-2 text-[11px] font-mono text-white/30 hover:text-white/60 transition-colors mb-8 group">
            <span className="group-hover:-translate-x-1 transition-transform">←</span>BACK TO HOME
          </Link>
          <div className="flex items-end justify-between">
            <div>
              <h1 className="font-display text-4xl sm:text-5xl font-bold text-white mb-3">Trade History</h1>
              <p className="text-xs font-mono text-white/30 tracking-widest">COMPLETE EXECUTION LOG</p>
            </div>
            <div className="text-right hidden sm:block">
              <div className="text-2xl font-bold font-mono mb-1" style={{ color: summary.winrate >= 60 ? "#d4a847" : "#fff" }}>{summary.winrate}%</div>
              <div className="text-[10px] font-mono text-white/30 tracking-widest">ALL-TIME WIN RATE</div>
            </div>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.5 }} className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
          {[
            { label: "TOTAL", value: summary.total_signals },
            { label: "CLOSED", value: summary.closed_trades },
            { label: "WINS", value: summary.wins, color: "#4ade80" },
            { label: "LOSSES", value: summary.losses, color: "#f87171" },
            { label: "WIN RATE", value: `${summary.winrate}%`, color: summary.winrate >= 60 ? "#d4a847" : undefined },
            { label: "TOTAL PnL", value: `${summary.total_pnl_pct >= 0 ? "+" : ""}${summary.total_pnl_pct.toFixed(2)}%`, color: summary.total_pnl_pct >= 0 ? "#4ade80" : "#f87171" },
          ].map((stat) => (
            <div key={stat.label} className="glass rounded-xl p-4 text-center">
              <div className="text-lg font-bold font-mono mb-1" style={{ color: stat.color || "#fff" }}>{stat.value}</div>
              <div className="text-[9px] font-mono text-white/30 tracking-widest">{stat.label}</div>
            </div>
          ))}
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <TradeHistoryTable limit={100} />
        </motion.div>
      </div>
    </main>
  );
}