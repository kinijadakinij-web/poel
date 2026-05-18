"use client";

import { useRef, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { useTrading } from "@/hooks/useTradingContext";
import PnLPoster from "@/components/ui/SignalPoster";
import GlassCard from "@/components/ui/GlassCard";

gsap.registerPlugin(ScrollTrigger);

export default function PnLShowcaseSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const { state } = useTrading();
  const [selectedSignal, setSelectedSignal] = useState(state.signals.find((s) => s.result));

  useEffect(() => {
    const closed = state.signals.find((s) => s.result && s.pnl_pct != null);
    if (closed) setSelectedSignal(closed);
  }, [state.signals]);

  useGSAP(() => {
    gsap.fromTo(
      sectionRef.current,
      { opacity: 0 },
      {
        opacity: 1,
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top 70%",
          toggleActions: "play none none reverse",
        },
      }
    );
  }, { scope: sectionRef });

  const latestPnl = state.total_pnl_pct;
  const isProfit = latestPnl >= 0;
  const isHighWinRate = state.winrate >= 60;

  return (
    <section
      ref={sectionRef}
      className="relative min-h-screen flex items-center justify-center z-10 px-4"
      style={{ paddingTop: "8rem", paddingBottom: "8rem" }}
    >
      <div className="max-w-6xl mx-auto w-full grid lg:grid-cols-2 gap-10 items-center">
        <div>
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-12"
          >
            <div className="text-[9px] font-mono text-white/25 tracking-[0.4em] uppercase mb-6">
              Performance Report
            </div>
            <h2
              className="font-display text-6xl sm:text-8xl font-black italic tracking-tighter mb-3 leading-none"
              style={{
                color: isProfit ? "#4ade80" : "#f87171",
                textShadow: `0 0 80px ${isProfit ? "rgba(74,222,128,0.25)" : "rgba(248,113,113,0.25)"}`,
              }}
            >
              {isProfit ? "+" : ""}
              {latestPnl.toFixed(2)}%
            </h2>
            <p className="text-[10px] font-mono text-white/25 tracking-[0.3em]">
              TOTAL PORTFOLIO RETURN
            </p>
          </motion.div>

          {/* Stats grid */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            {/* Win Rate — gold if high */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className={`shimmer-card rounded-2xl p-6 text-center ${isHighWinRate ? "shimmer-gold glass-gold" : "glass"}`}
              style={isHighWinRate ? { animation: "gold-pulse 3s ease-in-out infinite" } : {}}
            >
              <div
                className="text-3xl font-bold font-mono mb-1"
                style={{ color: isHighWinRate ? "#d4a847" : "#ffffff" }}
              >
                {state.winrate}%
              </div>
              <div
                className="text-[9px] font-mono tracking-widest"
                style={{ color: isHighWinRate ? "rgba(212,168,71,0.6)" : "rgba(255,255,255,0.3)" }}
              >
                WIN RATE
              </div>
              {isHighWinRate && (
                <div className="text-[8px] font-mono mt-1" style={{ color: "rgba(212,168,71,0.5)" }}>
                  ◆ ELITE
                </div>
              )}
            </motion.div>

            {/* Total trades */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.15 }}
              className="glass shimmer-card rounded-2xl p-6 text-center"
            >
              <div className="text-3xl font-bold font-mono text-white mb-1">{state.trade_count}</div>
              <div className="text-[9px] font-mono text-white/30 tracking-widest">TOTAL TRADES</div>
            </motion.div>

            {/* Wins */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="glass shimmer-card rounded-2xl p-6 text-center"
            >
              <div className="text-3xl font-bold font-mono mb-1" style={{ color: "#4ade80" }}>
                {state.win_count}
              </div>
              <div className="text-[9px] font-mono text-white/30 tracking-widest">WINS</div>
            </motion.div>

            {/* Losses */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.25 }}
              className="glass shimmer-card rounded-2xl p-6 text-center"
            >
              <div className="text-3xl font-bold font-mono mb-1" style={{ color: "#f87171" }}>
                {state.loss_count}
              </div>
              <div className="text-[9px] font-mono text-white/30 tracking-widest">LOSSES</div>
            </motion.div>
          </div>

          {/* Total PnL USDT — gold accent */}
          {state.total_pnl_usdt !== 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: 0.3 }}
              className="glass-gold shimmer-card shimmer-gold rounded-2xl p-5 flex items-center justify-between"
            >
              <div className="text-[9px] font-mono tracking-widest" style={{ color: "rgba(212,168,71,0.6)" }}>
                TOTAL PROFIT (USDT)
              </div>
              <div className="text-xl font-bold font-mono" style={{ color: "#d4a847" }}>
                ${state.total_pnl_usdt.toFixed(2)}
              </div>
            </motion.div>
          )}
        </div>

        <div className="flex justify-center">
          <AnimatePresence mode="wait">
            {selectedSignal && (
              <motion.div
                key={selectedSignal.id}
                initial={{ opacity: 0, scale: 0.9, rotateY: -15 }}
                animate={{ opacity: 1, scale: 1, rotateY: 0 }}
                exit={{ opacity: 0, scale: 0.9, rotateY: 15 }}
                transition={{ type: "spring", damping: 20 }}
                style={{ perspective: 1000 }}
              >
                <PnLPoster signal={selectedSignal} leverage={10} entryUsdt={100} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
