"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@/hooks/useAuthContext";
import { useTrading } from "@/hooks/useTradingContext";
import {
  register,
  getBotState,
  startBot,
  stopBot,
  resetBot,
  apiFetch,
} from "@/lib/api";
import SignalFeed from "@/components/ui/SignalFeed";
import TradeHistoryTable from "@/components/ui/TradeHistoryTable";
import WinRateChart from "@/components/dashboard/WinRateChart";
import PnLChart from "@/components/dashboard/PnLChart";
import SettingsPanel from "@/components/dashboard/SettingsPanel";
import { StatCardSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useSignalNotifications } from "@/hooks/useSignalNotifications";
import Link from "next/link";

// ── Confirm modal (replaces window.confirm) ────────────────────────────────
function ConfirmModal({
  onConfirm,
  onCancel,
}: {
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[150] flex items-center justify-center bg-black/70 backdrop-blur-sm px-4"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0 }}
        transition={{ type: "spring", damping: 28 }}
        className="glass rounded-2xl p-6 w-full max-w-sm border border-[#f87171]/20"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-center mb-6">
          <div className="text-2xl mb-3">⚠️</div>
          <h3 className="font-display text-lg font-bold text-white mb-2">
            Reset Everything?
          </h3>
          <p className="text-[11px] font-mono text-white/40 leading-relaxed">
            This will stop the bot, clear all signals &amp; history, and reset
            balance to initial. This action cannot be undone.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-3 rounded-lg glass border border-white/10 text-[10px] font-mono text-white/50 hover:text-white/80 hover:bg-white/5 transition-colors"
          >
            CANCEL
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-3 rounded-lg bg-[#f87171]/10 border border-[#f87171]/30 text-[#f87171] text-[10px] font-mono font-bold tracking-widest hover:bg-[#f87171]/20 transition-colors"
          >
            RESET ALL
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { isAuthenticated, username, isAdmin, logout } = useAuth();
  const { state, balance, dispatch } = useTrading();
  const router = useRouter();
  const toast = useToast();

  // Attach signal notifications (TP / SL browser + in-app toasts)
  useSignalNotifications(toast);

  const [newUsername, setNewUsername] = useState("");
  const [newPasskey, setNewPasskey] = useState("");
  const [regLoading, setRegLoading] = useState(false);

  const [tokens, setTokens] = useState(["", "", "", "", ""]);
  const [tokenLoading, setTokenLoading] = useState(false);

  const [botRunning, setBotRunning] = useState(false);
  const [botLoading, setBotLoading] = useState(false);
  const [botTransitioning, setBotTransitioning] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // Whether initial data has loaded (for skeleton)
  const [initialLoaded, setInitialLoaded] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) router.replace("/");
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    const checkState = async () => {
      try {
        const st = await getBotState();
        setBotRunning(st.running || st.status === "RUNNING");
        setInitialLoaded(true);
      } catch {}
    };
    checkState();
    const iv = setInterval(checkState, 5000);
    return () => clearInterval(iv);
  }, [isAuthenticated]);

  if (!isAuthenticated) return null;

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPasskey.trim()) {
      toast("Username dan passkey wajib diisi", "warning");
      return;
    }
    setRegLoading(true);
    try {
      const res = await register({
        username: newUsername.trim(),
        passkey: newPasskey.trim(),
      });
      if (res.success) {
        toast(`User ${newUsername} berhasil dibuat!`, "success");
        setNewUsername("");
        setNewPasskey("");
      } else {
        toast(res.detail || "Gagal membuat user", "error");
      }
    } catch (err: any) {
      toast(err.message || "Error", "error");
    } finally {
      setRegLoading(false);
    }
  };

  const handleUpdateTokens = async () => {
    setTokenLoading(true);
    try {
      const data = await apiFetch("/api/admin/tokens", {
        method: "POST",
        body: JSON.stringify({ tokens }),
      });
      toast(data.message || "Tokens updated!", "success");
    } catch (e: any) {
      toast(e.message || "Gagal update token", "error");
    } finally {
      setTokenLoading(false);
    }
  };

  const handleStartBot = async () => {
    if (botTransitioning || botLoading) return;
    setBotTransitioning(true);
    setBotLoading(true);
    try {
      await new Promise((r) => setTimeout(r, 2000));
      const res = await startBot({
        symbol: "ALL",
        tp_pct: 0.004,
        sl_pct: 0.002,
        interval: 60,
      });
      if (res.ok) {
        setBotRunning(true);
        toast("Bot started successfully!", "success");
      } else {
        toast(res.reason || "Failed to start bot", "error");
      }
    } catch (e: any) {
      toast(e.message || "Network error", "error");
    } finally {
      setBotLoading(false);
      setBotTransitioning(false);
    }
  };

  const handleStopBot = async () => {
    if (botTransitioning || botLoading) return;
    setBotTransitioning(true);
    setBotLoading(true);
    try {
      const res = await stopBot();
      if (res.ok) {
        await new Promise((r) => setTimeout(r, 3000));
        setBotRunning(false);
        toast("Bot stopped.", "info");
      } else {
        toast(res.reason || "Failed to stop bot", "error");
      }
    } catch (e: any) {
      toast(e.message || "Network error", "error");
    } finally {
      setBotLoading(false);
      setBotTransitioning(false);
    }
  };

  const handleReset = async () => {
    setShowConfirm(false);
    setResetLoading(true);
    try {
      if (botRunning) {
        try {
          await stopBot();
          setBotRunning(false);
        } catch {}
      }
      const res = await resetBot();
      if (res.ok) {
        dispatch({
          type: "SET_STATE",
          payload: {
            signals: [],
            trade_count: 0,
            win_count: 0,
            loss_count: 0,
            no_trade_count: 0,
            total_pnl_pct: 0,
            total_pnl_usdt: 0,
            symbols_scanned: 0,
            active_signal_count: 0,
            status: "IDLE",
          } as any,
        });
        toast("Reset successful! Refreshing...", "success");
        setTimeout(() => window.location.reload(), 1500);
      } else {
        toast(`Reset failed: ${res.reason || "Unknown error"}`, "error");
      }
    } catch (e: any) {
      toast(`Reset error: ${e.message}`, "error");
    } finally {
      setResetLoading(false);
    }
  };

  const fmtBalance = (n: number) =>
    n.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });

  const pnlPositive = state.total_pnl_pct >= 0;

  // ── Stats row ──────────────────────────────────────────────────────────────
  const stats = [
    {
      label: "BALANCE",
      value: `$${fmtBalance(balance.balance)}`,
      color: "#d4a847",
      highlight: true,
    },
    {
      label: "INITIAL",
      value: `$${fmtBalance(balance.initial_balance)}`,
      color: "#fff",
    },
    {
      label: "LEVERAGE",
      value: `${balance.leverage}x`,
      color: "#60a5fa",
    },
    {
      label: "TOTAL TRADES",
      value: state.trade_count,
      color: "#fff",
    },
    {
      label: "WINS",
      value: state.win_count,
      color: "#4ade80",
    },
    {
      label: "LOSSES",
      value: state.loss_count,
      color: "#f87171",
    },
    {
      label: "TOTAL PnL",
      value: `${pnlPositive ? "+" : ""}${state.total_pnl_pct.toFixed(2)}%`,
      color: pnlPositive ? "#4ade80" : "#f87171",
    },
  ];

  return (
    <>
      {/* Confirm reset modal */}
      {showConfirm && (
        <ConfirmModal
          onConfirm={handleReset}
          onCancel={() => setShowConfirm(false)}
        />
      )}

      <main className="relative min-h-screen bg-[#030303] pt-20 sm:pt-24 pb-16 sm:pb-20 px-3 sm:px-6 lg:px-8">
        <div className="fixed inset-0 -z-10 bg-[#030303]" />
        <div
          className="fixed inset-0 -z-10 opacity-15"
          style={{
            backgroundImage:
              "radial-gradient(circle at 50% 0%, #1e3a8a 0%, transparent 50%)",
          }}
        />

        <div className="max-w-6xl mx-auto">
          {/* ── Header ── */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="mb-8 sm:mb-10 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4"
          >
            <div>
              <Link
                href="/?section=live-logic"
                className="inline-flex items-center gap-2 text-[11px] font-mono text-white/30 hover:text-white/60 transition-colors mb-4 sm:mb-6 group"
              >
                <span className="group-hover:-translate-x-1 transition-transform">
                  ←
                </span>
                BACK TO HOME
              </Link>
              <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-2">
                Trading Dashboard
              </h1>
              <p className="text-[10px] sm:text-xs font-mono text-white/30 tracking-widest">
                ACCOUNT: {username?.toUpperCase()}
                {isAdmin && (
                  <span className="ml-2 text-[#d4a847]">[ADMIN]</span>
                )}
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {isAdmin && (
                <>
                  <button
                    onClick={botRunning ? handleStopBot : handleStartBot}
                    disabled={botLoading || botTransitioning}
                    className={`px-4 py-2.5 rounded-lg text-[10px] font-mono font-bold tracking-wider transition-colors border ${
                      botRunning
                        ? "bg-[#f87171]/10 border-[#f87171]/30 text-[#f87171] hover:bg-[#f87171]/20"
                        : "bg-[#4ade80]/10 border-[#4ade80]/30 text-[#4ade80] hover:bg-[#4ade80]/20"
                    } disabled:opacity-50 disabled:cursor-not-allowed ${
                      botTransitioning ? "animate-pulse" : ""
                    }`}
                  >
                    {botLoading
                      ? botRunning
                        ? "STOPPING..."
                        : "STARTING..."
                      : botRunning
                      ? "STOP BOT"
                      : "START BOT"}
                  </button>

                  <button
                    onClick={() => setShowConfirm(true)}
                    disabled={resetLoading}
                    className="px-4 py-2.5 rounded-lg bg-[#f87171]/10 border border-[#f87171]/30 text-[#f87171] text-[10px] font-mono font-bold tracking-wider hover:bg-[#f87171]/20 transition-colors disabled:opacity-50"
                  >
                    {resetLoading ? "RESETTING..." : "RESET ALL"}
                  </button>
                </>
              )}
              <button
                onClick={logout}
                className="px-4 sm:px-5 py-2.5 rounded-lg glass text-[10px] font-mono text-white/50 hover:text-white/80 hover:bg-white/5 transition-colors border border-white/10"
              >
                LOGOUT
              </button>
            </div>
          </motion.div>

          {/* ── Stats row (with Total PnL) ── */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 sm:gap-3 mb-6 sm:mb-8"
          >
            {!initialLoaded
              ? Array.from({ length: 7 }).map((_, i) => (
                  <StatCardSkeleton key={i} />
                ))
              : stats.map((stat) => (
                  <div
                    key={stat.label}
                    className={`glass rounded-xl p-3 sm:p-4 text-center ${
                      stat.highlight
                        ? "border border-[#d4a847]/30 bg-[#d4a847]/5"
                        : ""
                    }`}
                  >
                    <div
                      className={`text-base sm:text-lg font-bold font-mono mb-1 ${
                        stat.highlight ? "text-[#d4a847]" : ""
                      }`}
                      style={{
                        color: stat.highlight ? undefined : stat.color || "#fff",
                      }}
                    >
                      {stat.value}
                    </div>
                    <div className="text-[8px] sm:text-[9px] font-mono text-white/30 tracking-widest">
                      {stat.label}
                    </div>
                  </div>
                ))}
          </motion.div>

          {/* ── Admin: Create User ── */}
          {isAdmin && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className="mb-6 sm:mb-8 glass rounded-2xl p-4 sm:p-6 border border-[#d4a847]/20"
            >
              <h3 className="text-[10px] sm:text-xs font-mono text-[#d4a847] tracking-[0.25em] uppercase mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#d4a847]" />
                Create New User
              </h3>
              <form
                onSubmit={handleRegister}
                className="flex flex-col sm:flex-row gap-3"
              >
                <input
                  type="text"
                  placeholder="Username"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="flex-1 min-w-0 bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
                />
                <input
                  type="password"
                  placeholder="Passkey"
                  value={newPasskey}
                  onChange={(e) => setNewPasskey(e.target.value)}
                  className="flex-1 min-w-0 bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
                />
                <button
                  type="submit"
                  disabled={regLoading}
                  className="px-6 py-3 rounded-lg bg-[#d4a847]/10 border border-[#d4a847]/30 text-[#d4a847] text-xs font-mono tracking-wider hover:bg-[#d4a847]/20 transition-colors disabled:opacity-50 whitespace-nowrap"
                >
                  {regLoading ? "CREATING..." : "CREATE USER"}
                </button>
              </form>
            </motion.div>
          )}

          {/* ── Admin: Qwen tokens ── */}
          {isAdmin && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="mb-6 sm:mb-8 glass rounded-2xl p-4 sm:p-6 border border-blue-500/20"
            >
              <h3 className="text-[10px] sm:text-xs font-mono text-blue-400 tracking-[0.25em] uppercase mb-4 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                Qwen AI Tokens
              </h3>
              <div className="space-y-3">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-[10px] font-mono text-white/30 w-8 pt-3">
                      #{i + 1}
                    </span>
                    <input
                      type="password"
                      placeholder={`Token ${i + 1}`}
                      value={tokens[i]}
                      onChange={(e) => {
                        const t = [...tokens];
                        t[i] = e.target.value;
                        setTokens(t);
                      }}
                      className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-xs text-white placeholder-white/20 focus:outline-none focus:border-blue-400/50 transition-colors"
                    />
                  </div>
                ))}
                <button
                  onClick={handleUpdateTokens}
                  disabled={tokenLoading}
                  className="w-full py-3 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs font-mono tracking-wider hover:bg-blue-500/20 transition-colors disabled:opacity-50"
                >
                  {tokenLoading ? "UPDATING..." : "UPDATE TOKENS"}
                </button>
              </div>
            </motion.div>
          )}

          {/* ── Main grid ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
            {/* Left: signals + history */}
            <div className="lg:col-span-2 space-y-4 sm:space-y-6">
              {/* Signals */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="glass rounded-2xl p-4 sm:p-6"
              >
                <h3 className="text-[10px] font-mono text-white/40 tracking-[0.25em] uppercase mb-4">
                  Live Signals
                </h3>
                <SignalFeed limit={10} compact />
              </motion.div>

              {/* History */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="glass rounded-2xl p-4 sm:p-6"
              >
                <h3 className="text-[10px] font-mono text-white/40 tracking-[0.25em] uppercase mb-4">
                  Trade History
                </h3>
                <TradeHistoryTable limit={20} compact />
              </motion.div>
            </div>

            {/* Right: win rate + PnL chart + settings */}
            <div className="space-y-4 sm:space-y-6">
              {/* Win Rate */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 }}
                className="glass rounded-2xl p-4 sm:p-6 flex flex-col items-center"
              >
                <h3 className="text-[10px] font-mono text-white/40 tracking-[0.25em] uppercase mb-4 self-start">
                  Win Rate
                </h3>
                <div className="w-full flex justify-center">
                  <WinRateChart
                    wins={state.win_count}
                    losses={state.loss_count}
                    size={180}
                  />
                </div>
              </motion.div>

              {/* PnL Equity Curve — NEW */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="glass rounded-2xl p-4 sm:p-6"
              >
                <h3 className="text-[10px] font-mono text-white/40 tracking-[0.25em] uppercase mb-4">
                  PnL Curve
                </h3>
                <PnLChart />
              </motion.div>

              {/* Settings */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35 }}
              >
                <h3 className="text-[10px] font-mono text-white/40 tracking-[0.25em] uppercase mb-3 sm:mb-4 px-1">
                  Bot Settings
                </h3>
                <SettingsPanel />
              </motion.div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
