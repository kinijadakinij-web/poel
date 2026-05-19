"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/hooks/useAuthContext";

interface LoginModalProps {
  onClose: () => void;
}

// Shake animation keyframes for the form on error
const shakeVariants = {
  idle: { x: 0 },
  shake: {
    x: [0, -10, 10, -8, 8, -4, 4, 0],
    transition: { duration: 0.5, ease: "easeInOut" },
  },
};

// Eye icon — open / closed
function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    // Eye open
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M1 12S5 4 12 4s11 8 11 8-4 8-11 8S1 12 1 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  ) : (
    // Eye closed
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

export default function LoginModal({ onClose }: LoginModalProps) {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [passkey, setPasskey] = useState("");
  const [showPasskey, setShowPasskey] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [shaking, setShaking] = useState(false);

  // Auto-focus username field on open
  const usernameRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const t = setTimeout(() => usernameRef.current?.focus(), 80);
    return () => clearTimeout(t);
  }, []);

  const triggerShake = () => {
    setShaking(true);
    setTimeout(() => setShaking(false), 600);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    const res = await login(username, passkey);
    setLoading(false);

    if (res.success) {
      onClose();
      window.location.reload();
    } else {
      setError(res.error || "Login failed");
      triggerShake();
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
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/30 hover:text-white/60 text-xl leading-none transition-colors"
          aria-label="Close"
        >
          ×
        </button>

        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-[10px] font-mono text-[#d4a847] tracking-[0.3em] mb-2">
            SECURE ACCESS
          </div>
          <h2 className="font-display text-2xl font-bold text-white">
            Agent Login
          </h2>
        </div>

        {/* Form with shake animation */}
        <motion.form
          onSubmit={handleSubmit}
          className="space-y-5"
          variants={shakeVariants}
          animate={shaking ? "shake" : "idle"}
        >
          {/* Username */}
          <div className="space-y-2">
            <label className="text-[10px] font-mono text-white/40 tracking-widest uppercase">
              Username
            </label>
            <input
              ref={usernameRef}
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
              placeholder="Enter username"
              autoComplete="username"
              required
            />
          </div>

          {/* Passkey with show/hide toggle */}
          <div className="space-y-2">
            <label className="text-[10px] font-mono text-white/40 tracking-widest uppercase">
              Passkey
            </label>
            <div className="relative">
              <input
                type={showPasskey ? "text" : "password"}
                value={passkey}
                onChange={(e) => setPasskey(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 pr-11 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-[#d4a847]/50 transition-colors"
                placeholder="••••••••"
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                onClick={() => setShowPasskey((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/70 transition-colors"
                aria-label={showPasskey ? "Hide passkey" : "Show passkey"}
                tabIndex={-1}
              >
                <EyeIcon open={showPasskey} />
              </button>
            </div>
          </div>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="text-[11px] font-mono text-[#f87171] bg-[#f87171]/5 border border-[#f87171]/20 rounded-lg px-3 py-2"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-[#d4a847]/10 border border-[#d4a847]/30 text-[#d4a847] text-xs font-mono font-bold tracking-widest hover:bg-[#d4a847]/20 transition-colors disabled:opacity-50"
          >
            {loading ? "AUTHENTICATING..." : "ACCESS DASHBOARD"}
          </button>
        </motion.form>

        {/* Footer */}
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
