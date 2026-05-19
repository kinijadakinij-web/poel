"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuthContext";
import { useTrading } from "@/hooks/useTradingContext";
import LoginModal from "@/components/ui/LoginModal";

gsap.registerPlugin(ScrollTrigger);

export default function HeroSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);
  const [showLogin, setShowLogin] = useState(false);

  const { isAuthenticated } = useAuth();
  const { state, balance } = useTrading();
  const router = useRouter();

  useGSAP(
    () => {
      if (!titleRef.current) return;

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top center",
          toggleActions: "play none none reverse",
        },
      });

      tl.fromTo(
        titleRef.current,
        { opacity: 0, y: 80, skewY: 4 },
        { opacity: 1, y: 0, skewY: 0, duration: 1.4, ease: "power4.out" }
      ).fromTo(
        subtitleRef.current,
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" },
        "-=0.8"
      );
    },
    { scope: sectionRef }
  );

  const handleCTA = () => {
    if (isAuthenticated) {
      router.push("/dashboard");
    } else {
      setShowLogin(true);
    }
  };

  // Live stats to show under hero
  const winRate =
    state.trade_count > 0
      ? Math.round((state.win_count / state.trade_count) * 100)
      : state.winrate ?? 0;

  const pnlPositive = state.total_pnl_pct >= 0;

  return (
    <>
      <section
        ref={sectionRef}
        className="relative min-h-screen flex items-center justify-center z-10"
        style={{ paddingTop: "10vh", paddingBottom: "10vh" }}
      >
        <div className="text-center px-4 max-w-4xl mx-auto">
          {/* Eyebrow */}
          <motion.div
            initial={{ opacity: 0, letterSpacing: "1em" }}
            animate={{ opacity: 1, letterSpacing: "0.4em" }}
            transition={{ duration: 2, ease: "easeOut" }}
            className="text-[9px] font-mono text-white/25 mb-10 tracking-[0.4em] uppercase"
          >
            AI-Powered
          </motion.div>

          {/* Title */}
          <h1
            ref={titleRef}
            className="font-display text-7xl sm:text-9xl lg:text-[10rem] font-black tracking-tighter text-white leading-[0.9] mb-10"
            style={{ textShadow: "0 0 120px rgba(96,165,250,0.2)" }}
          >
            SONNET
            <br />
            <span className="italic text-transparent bg-clip-text bg-gradient-to-r from-blue-300 via-violet-300 to-blue-300">
              Trade
            </span>
          </h1>

          <div ref={subtitleRef} className="space-y-8">
            {/* Description */}
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8, duration: 1 }}
              className="text-sm sm:text-base text-white/35 max-w-sm mx-auto font-mono leading-relaxed tracking-wide"
            >
              Autonomous signal generation via multi-timeframe void analysis.
              MEXC perpetual futures. Zero latency execution.
            </motion.p>

            {/* Status badges */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.2, duration: 0.8 }}
              className="flex items-center justify-center gap-4 flex-wrap"
            >
              <div className="glass px-5 py-2.5 rounded-full text-[10px] font-mono text-white/40 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80] inline-block animate-pulse" />
                ONLINE
              </div>
              <div
                className="px-5 py-2.5 rounded-full text-[10px] font-mono flex items-center gap-2"
                style={{
                  background: "rgba(212,168,71,0.06)",
                  border: "1px solid rgba(212,168,71,0.2)",
                  color: "#d4a847",
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{ backgroundColor: "#d4a847" }}
                />
                PREMIUM TIER
              </div>
            </motion.div>

            {/* Live stats bar */}
            {state.trade_count > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 1.6, duration: 0.8 }}
                className="flex items-center justify-center gap-6 flex-wrap"
              >
                {[
                  {
                    label: "SIGNALS TODAY",
                    value: state.active_signal_count,
                    color: "#60a5fa",
                  },
                  {
                    label: "WIN RATE",
                    value: `${winRate}%`,
                    color: winRate >= 60 ? "#d4a847" : "#fff",
                  },
                  {
                    label: "TOTAL PnL",
                    value: `${pnlPositive ? "+" : ""}${state.total_pnl_pct.toFixed(1)}%`,
                    color: pnlPositive ? "#4ade80" : "#f87171",
                  },
                  {
                    label: "TRADES",
                    value: state.trade_count,
                    color: "#fff",
                  },
                ].map((s) => (
                  <div key={s.label} className="text-center">
                    <div
                      className="text-base font-bold font-mono"
                      style={{ color: s.color }}
                    >
                      {s.value}
                    </div>
                    <div className="text-[8px] font-mono text-white/25 tracking-widest mt-0.5">
                      {s.label}
                    </div>
                  </div>
                ))}
              </motion.div>
            )}

            {/* CTA */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 1.8, duration: 0.7 }}
              className="flex items-center justify-center gap-3 flex-wrap"
            >
              <button
                onClick={handleCTA}
                className="group relative px-7 py-3.5 rounded-xl text-[11px] font-mono font-bold tracking-widest transition-all duration-300"
                style={{
                  background:
                    "linear-gradient(135deg, rgba(212,168,71,0.15) 0%, rgba(212,168,71,0.06) 100%)",
                  border: "1px solid rgba(212,168,71,0.35)",
                  color: "#d4a847",
                  boxShadow: "0 0 24px rgba(212,168,71,0.08)",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.boxShadow =
                    "0 0 40px rgba(212,168,71,0.2)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "rgba(212,168,71,0.6)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.boxShadow =
                    "0 0 24px rgba(212,168,71,0.08)";
                  (e.currentTarget as HTMLElement).style.borderColor =
                    "rgba(212,168,71,0.35)";
                }}
              >
                <span className="flex items-center gap-2">
                  {isAuthenticated ? "OPEN DASHBOARD" : "GET ACCESS"}
                  <span className="group-hover:translate-x-1 transition-transform inline-block">
                    →
                  </span>
                </span>
              </button>

              {/* Secondary: View Signals (visible even without login) */}
              <button
                onClick={() =>
                  document
                    .getElementById("live-logic")
                    ?.scrollIntoView({ behavior: "smooth" })
                }
                className="px-6 py-3.5 rounded-xl glass text-[11px] font-mono text-white/40 hover:text-white/70 hover:bg-white/5 transition-all duration-300 border border-white/10 tracking-widest"
              >
                VIEW SIGNALS ↓
              </button>
            </motion.div>
          </div>

          {/* Scroll hint */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 2.8, duration: 1 }}
            className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pointer-events-none"
          >
            <div className="text-[9px] font-mono text-white/20 tracking-[0.3em]">
              SCROLL
            </div>
            <div
              className="w-[1px] h-10 bg-gradient-to-b from-white/20 to-transparent"
              style={{ animation: "float 2s ease-in-out infinite alternate" }}
            />
          </motion.div>
        </div>
      </section>

      <AnimatePresence>
        {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      </AnimatePresence>
    </>
  );
}
