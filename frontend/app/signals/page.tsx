"use client";

import { useTrading } from "@/hooks/useTradingContext";
import SignalFeed from "@/components/ui/SignalFeed";
import Link from "next/link";
import { motion } from "framer-motion";

export default function SignalsPage() {
  const { state } = useTrading();

  return (
    <main className="relative min-h-screen bg-[#030303] pt-24 pb-20 px-4 sm:px-8">
      {/* Subtle bg */}
      <div className="fixed inset-0 -z-10 bg-[#030303]" />
      <div
        className="fixed inset-0 -z-10 opacity-20"
        style={{
          backgroundImage: "radial-gradient(circle at 50% 0%, #1e3a8a 0%, transparent 50%)",
        }}
      />

      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-10"
        >
          <Link
            href="/?section=live-logic"
            className="inline-flex items-center gap-2 text-[11px] font-mono text-white/30 hover:text-white/60 transition-colors mb-8 group"
          >
            <span className="group-hover:-translate-x-1 transition-transform">←</span>
            BACK TO HOME
          </Link>

          <div className="flex items-end justify-between">
            <div>
              <h1 className="font-display text-4xl sm:text-5xl font-bold text-white mb-3">
                Live Signals
              </h1>
              <p className="text-xs font-mono text-white/30 tracking-widest">
                REAL-TIME AI ANALYSIS STREAM
              </p>
            </div>
            <div className="text-right hidden sm:block">
              <div className="text-2xl font-bold font-mono text-white mb-1">
                {state.active_signal_count}
                <span className="text-white/20 text-lg">/{state.max_active_signals}</span>
              </div>
              <div className="text-[10px] font-mono text-white/30 tracking-widest">
                ACTIVE SIGNALS
              </div>
            </div>
          </div>
        </motion.div>

        {/* Stats bar */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8"
        >
          {[
            { label: "TOTAL SCANNED", value: state.symbols_scanned },
            { label: "TRADES", value: state.trade_count },
            { label: "WINS", value: state.win_count, color: "#4ade80" },
            { label: "LOSSES", value: state.loss_count, color: "#f87171" },
          ].map((stat) => (
            <div key={stat.label} className="glass rounded-xl p-4 text-center">
              <div className="text-xl font-bold font-mono mb-1" style={{ color: stat.color || "#fff" }}>
                {stat.value}
              </div>
              <div className="text-[9px] font-mono text-white/30 tracking-widest">{stat.label}</div>
            </div>
          ))}
        </motion.div>

        {/* Full Signal Feed */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="glass rounded-2xl p-6"
        >
          <SignalFeed limit={50} />
        </motion.div>
      </div>
    </main>
  );
}
