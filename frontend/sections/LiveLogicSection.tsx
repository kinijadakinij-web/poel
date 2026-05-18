"use client";

import { useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuthContext";
import LoginModal from "@/components/ui/LoginModal";
import SignalFeed from "@/components/ui/SignalFeed";
import GlassCard from "@/components/ui/GlassCard";

gsap.registerPlugin(ScrollTrigger);

export default function LiveLogicSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [showLogin, setShowLogin] = useState(false);
  const { isAuthenticated } = useAuth();

  useGSAP(() => {
    if (!contentRef.current) return;
    const isMobile = window.innerWidth < 768;
    gsap.fromTo(
      contentRef.current,
      { opacity: 0, x: isMobile ? 0 : 80, y: isMobile ? 20 : 0 },
      {
        opacity: 1,
        x: 0,
        y: 0,
        ease: "power3.out",
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top center",
          end: "center center",
          scrub: 1,
        },
      }
    );
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      className="relative min-h-screen flex items-center justify-center lg:justify-end z-10 px-4 sm:px-8 lg:px-16 py-20"
    >
      <div ref={contentRef} className="w-full max-w-lg lg:ml-auto">
        <GlassCard>
          <div className="mb-6">
            <h2 className="font-display text-2xl sm:text-3xl font-bold text-white mb-2">
              Live Logic
            </h2>
            <p className="text-xs font-mono text-white/30 leading-relaxed">
              Real-time AI analysis stream from Qwen multi-agent system
            </p>
          </div>

          {/* Preview: max 3 signals */}
          <SignalFeed limit={3} compact />

          {/* CTA to full page */}
          <div className="mt-6 pt-5 border-t border-white/[0.06]">
            {isAuthenticated ? (
              <Link
                href="/signals"
                className="group flex items-center justify-between w-full px-5 py-3 rounded-xl glass hover:bg-white/[0.06] hover:border-white/15 transition-all duration-300"
              >
                <div className="flex items-center gap-3">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80] animate-pulse" />
                  <span className="text-xs font-mono text-white/60 group-hover:text-white/90 transition-colors">
                    View All Live Signals
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
                  <span className="w-1.5 h-1.5 rounded-full bg-[#4ade80] animate-pulse" />
                  <span className="text-xs font-mono text-white/60 group-hover:text-white/90 transition-colors">
                    View All Live Signals
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