"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "@/hooks/useAuthContext";

interface LoginModalProps {
  onClose: () => void;
}

export default function LoginModal({ onClose }: LoginModalProps) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [passkey, setPasskey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await login(username, passkey);
    setLoading(false);
    if (res.success) {
      onClose();
      window.location.reload(); // refresh biar state trading ke-update
    } else {
      setError(res.error || "Login failed");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        transition={{ type: "spring", damping: 25 }}
        className="glass-strong rounded-2xl p-8 w-full max-w-sm relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/30 hover:text-white/60 text-lg"
        >
          ×
        </button>

        <div className="text-center mb-8">
          <div className="text-[10px] font-mono text-[#d4a847] tracking-[0.3em] mb-2">
            SECURE ACCESS
          </div>
          <h2 className="font-display text-2xl font-bold text-white">
            Agent Login
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-[10px] font-mono text-white/40 tracking-widest uppercase">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
              placeholder="Enter username"
              required
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-mono text-white/40 tracking-widest uppercase">
              Passkey
            </label>
            <input
              type="password"
              value={passkey}
              onChange={(e) => setPasskey(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
              placeholder="••••••••"
              required
            />
          </div>

          {error && (
            <div className="text-[11px] font-mono text-[#f87171] bg-[#f87171]/5 border border-[#f87171]/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-[#d4a847]/10 border border-[#d4a847]/30 text-[#d4a847] text-xs font-mono font-bold tracking-widest hover:bg-[#d4a847]/20 transition-colors disabled:opacity-50"
          >
            {loading ? "AUTHENTICATING..." : "ACCESS DASHBOARD"}
          </button>
        </form>

        <div className="mt-6 pt-5 border-t border-white/5 text-center">
          <p className="text-[10px] font-mono text-white/30 mb-2">
            Don&apos;t have an account?
          </p>
          <a
            href="https://t.me/realsonnet"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-[11px] font-mono text-[#60a5fa] hover:text-[#93c5fd] transition-colors"
          >
            <span>Contact @realsonnet</span>
            <span>→</span>
          </a>
        </div>
      </motion.div>
    </motion.div>
  );
}
