"use client";

import { useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuthContext";
import LoginModal from "@/components/ui/LoginModal";
import TradeHistoryTable from "@/components/ui/TradeHistoryTable";
import GlassCard from "@/components/ui/GlassCard";

gsap.registerPlugin(ScrollTrigger);

export default function HistorySection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [showLogin, setShowLogin] = useState(false);
  const { isAuthenticated } = useAuth();

  useGSAP(() => {
    gsap.fromTo(
      sectionRef.current,
      { opacity: 0 },
      {
        opacity: 1,
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top 80%",
          end: "top 30%",
          scrub: 1,
        },
      }
    );
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      className="relative min-h-screen flex flex-col justify-center z-10 px-4 sm:px-8 lg:px-16 py-24 metallic-grid"
    >
      <div className="max-w-5xl mx-auto w-full">
        <div className="mb-12 text-center">
          <h2 className="text-4xl sm:text-5xl font-bold text-white mb-4 tracking-tight">
            Trade History
          </h2>
          <p className="text-xs font-mono text-white/30 tracking-widest">
            VERIFIED EXECUTION LOG
          </p>
        </div>

        <GlassCard className="max-w-4xl mx-auto">
          {/* Preview: max 5 rows */}
          <TradeHistoryTable limit={5} compact />

          {/* CTA to full page */}
          <div className="mt-6 pt-5 border-t border-white/[0.06]">
            {isAuthenticated ? (
              <Link
                href="/history"
                className="group flex items-center justify-between w-full px-5 py-3 rounded-xl glass hover:bg-white/[0.06] hover:border-white/15 transition-all duration-300"
              >
                <div className="flex items-center gap-3">
                  <svg className="w-4 h-4 text-white/40 group-hover:text-white/70" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-xs font-mono text-white/60 group-hover:text-white/90 transition-colors">
                    View Full Trade History
                  </span>
                </div>
                <span className="text-white/30 group-hover:text-white/70 group-hover:translate-x-1 transition-all text-lg">
                  →
                </span>
              </Link>
            ) : (
              <button
                onClick={() => setShowLogin(true)}
                className="group flex items-center justify-between w-full px-5 py-3 rounded-xl glass hover:bg-white/[0.06] hover:border-white/15 transition-all duration-300 text-left"
              >
                <div className="flex items-center gap-3">
                  <svg className="w-4 h-4 text-white/40 group-hover:text-white/70" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="text-xs font-mono text-white/60 group-hover:text-white/90 transition-colors">
                    View Full Trade History
                  </span>
                </div>
                <span className="text-white/30 group-hover:text-white/70 group-hover:translate-x-1 transition-all text-lg">
                  →
                </span>
              </button>
            )}
          </div>
        </GlassCard>
      </div>

      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
    </section>
  );
}