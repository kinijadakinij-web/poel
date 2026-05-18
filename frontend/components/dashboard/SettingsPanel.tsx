"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/hooks/useAuthContext";
import { updateUserData } from "@/lib/auth";
import { startBot, stopBot, getBotState } from "@/lib/api";

export default function SettingsPanel() {
  const { userData, userId, refreshUser } = useAuth();
  const [leverage, setLeverage] = useState(userData?.leverage || 10);
  const [margin, setMargin] = useState(userData?.margin || 100);
  const [isRunning, setIsRunning] = useState(false);
  const [saved, setSaved] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Sync state dari server saat mount & interval
  useEffect(() => {
    if (!userId) return;
    
    const checkState = async () => {
      try {
        const state = await getBotState(userId);
        setIsRunning(state.running || state.status === "RUNNING");
      } catch (e) {
        // silent fail
      }
    };
    
    checkState();
    const interval = setInterval(checkState, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, [userId]);

  useEffect(() => {
    if (userData) {
      setLeverage(userData.leverage);
      setMargin(userData.margin);
    }
  }, [userData]);

  const handleSave = () => {
    if (!userId) return;
    updateUserData(userId, { leverage, margin });
    refreshUser();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleStart = async () => {
    if (!userId) {
      setBotError("Please login first");
      return;
    }
    setLoading(true);
    setBotError(null);
    try {
      const res = await startBot(
        { symbol: "ALL", tp_pct: 0.004, sl_pct: 0.002, interval: 60 },
        userId
      );
      if (res.ok) {
        setIsRunning(true);
      } else {
        setBotError(res.reason || "Failed to start");
      }
    } catch (e: any) {
      setBotError(e.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    if (!userId) return;
    setLoading(true);
    setBotError(null);
    try {
      const res = await stopBot(userId);
      if (res.ok) {
        setIsRunning(false);
      } else {
        setBotError(res.reason || "Failed to stop");
      }
    } catch (e: any) {
      setBotError(e.message || "Network error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass rounded-2xl p-4 sm:p-6 space-y-4 sm:space-y-6">
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between text-xs font-mono text-white/60">
            <span>Leverage</span>
            <span className="text-[#d4a847]">{leverage}x</span>
          </div>
          <input
            type="range"
            min="1"
            max="100"
            value={leverage}
            onChange={(e) => setLeverage(Number(e.target.value))}
            className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer"
            style={{ accentColor: "#d4a847" }}
          />
          <div className="flex justify-between text-[9px] font-mono text-white/20">
            <span>1x</span>
            <span>100x</span>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-xs font-mono text-white/60">
            <span>Margin per Trade</span>
            <span className="text-[#d4a847]">${margin}</span>
          </div>
          <input
            type="number"
            min="10"
            value={margin}
            onChange={(e) => setMargin(Number(e.target.value))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-white focus:outline-none focus:border-[#d4a847]/50 transition-colors"
          />
        </div>
      </div>

      <div className="pt-4 border-t border-white/5 flex gap-3">
        <button
          onClick={handleStart}
          disabled={isRunning || loading}
          className="flex-1 py-3 rounded-lg bg-[#4ade80]/10 border border-[#4ade80]/30 text-[#4ade80] text-xs font-mono font-bold tracking-widest hover:bg-[#4ade80]/20 transition-colors disabled:opacity-50"
        >
          {loading && !isRunning ? "STARTING..." : isRunning ? "RUNNING" : "START BOT"}
        </button>
        <button
          onClick={handleStop}
          disabled={!isRunning || loading}
          className="flex-1 py-3 rounded-lg bg-[#f87171]/10 border border-[#f87171]/30 text-[#f87171] text-xs font-mono font-bold tracking-widest hover:bg-[#f87171]/20 transition-colors disabled:opacity-50"
        >
          {loading && isRunning ? "STOPPING..." : "STOP BOT"}
        </button>
      </div>

      {botError && (
        <p className="text-[10px] font-mono text-[#f87171] text-center">
          {botError}
        </p>
      )}

      <button
        onClick={handleSave}
        className="w-full py-3 rounded-lg bg-white/5 border border-white/10 text-xs font-mono text-white/60 hover:bg-white/10 hover:text-white transition-colors"
      >
        {saved ? "SAVED ✓" : "SAVE SETTINGS"}
      </button>
    </div>
  );
}
