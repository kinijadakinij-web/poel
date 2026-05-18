"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuthContext";
import { useState } from "react";
import LoginModal from "./LoginModal";
import { motion, AnimatePresence } from "framer-motion";

export default function TradingNav() {
  const { isAuthenticated, username, logout } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/dashboard") return null;

  return (
    <>
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="fixed top-0 left-0 right-0 z-50 px-4 sm:px-8 py-4"
      >
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link
            href="/"
            className="text-[11px] font-mono font-bold tracking-[0.3em] text-white/80 hover:text-white transition-colors"
          >
            SONNET<span className="text-[#d4a847]">RADE</span>
          </Link>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <>
                <span className="hidden sm:inline text-[10px] font-mono text-white/30 tracking-widest">
                  {username?.toUpperCase()}
                </span>
                <button
                  onClick={() => router.push("/dashboard")}
                  className="px-4 py-2 rounded-lg bg-[#d4a847]/10 border border-[#d4a847]/30 text-[10px] font-mono font-bold tracking-widest text-[#d4a847] hover:bg-[#d4a847]/20 transition-colors"
                >
                  DASHBOARD
                </button>
                <button
                  onClick={logout}
                  className="px-4 py-2 rounded-lg glass text-[10px] font-mono text-white/50 hover:text-white/80 hover:bg-white/5 transition-colors"
                >
                  LOGOUT
                </button>
              </>
            ) : (
              <>
                <span className="hidden sm:inline text-[10px] font-mono text-white/20 tracking-widest">
                  GLOBAL ACCOUNT
                </span>
                <button
                  onClick={() => setShowLogin(true)}
                  className="px-4 py-2 rounded-lg glass text-[10px] font-mono text-white/60 hover:text-white hover:bg-white/5 transition-colors border border-white/10"
                >
                  LOGIN
                </button>
              </>
            )}
          </div>
        </div>
      </motion.header>

      <AnimatePresence>
        {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
      </AnimatePresence>
    </>
  );
}