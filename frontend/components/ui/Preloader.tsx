"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

export default function Preloader({ onComplete }: { onComplete: () => void }) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const logoRef = useRef<HTMLDivElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);
  const counterRef = useRef<HTMLSpanElement>(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    const tl = gsap.timeline();

    // Count up 0 → 100
    const counter = { val: 0 };
    tl.to(counter, {
      val: 100,
      duration: 2.2,
      ease: "power2.inOut",
      onUpdate() {
        setCount(Math.floor(counter.val));
      },
    }, 0);

    // Progress bar
    tl.fromTo(
      barRef.current,
      { scaleX: 0 },
      { scaleX: 1, duration: 2.2, ease: "power2.inOut", transformOrigin: "left center" },
      0
    );

    // Logo fade in
    tl.fromTo(
      logoRef.current,
      { opacity: 0, y: 20, letterSpacing: "0.5em" },
      { opacity: 1, y: 0, letterSpacing: "0.25em", duration: 1, ease: "power3.out" },
      0.2
    );

    // Subtitle
    tl.fromTo(
      subtitleRef.current,
      { opacity: 0 },
      { opacity: 1, duration: 0.6, ease: "power2.out" },
      0.8
    );

    // Exit: slide up
    tl.to(overlayRef.current, {
      yPercent: -100,
      duration: 0.9,
      ease: "power4.inOut",
      delay: 0.3,
      onComplete,
    });

    return () => { tl.kill(); };
  }, [onComplete]);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-[#030303]"
      style={{ willChange: "transform" }}
    >
      {/* Subtle grid */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Logo */}
      <div ref={logoRef} className="text-center mb-16" style={{ opacity: 0 }}>
        <div
          className="font-display text-6xl sm:text-7xl font-black text-white tracking-[0.25em] mb-3"
          style={{ textShadow: "0 0 80px rgba(212,168,71,0.4)" }}
        >
          QWEN
          <span style={{ color: "#d4a847" }}>-X</span>
        </div>
        <div ref={subtitleRef} className="text-[10px] font-mono text-white/30 tracking-[0.4em]" style={{ opacity: 0 }}>
          REALSONNET
        </div>
      </div>

      {/* Counter */}
      <div className="font-mono text-sm text-white/20 mb-4 tracking-widest">
        <span ref={counterRef}>{count}</span>
        <span className="text-white/10">%</span>
      </div>

      {/* Progress bar */}
      <div className="w-48 h-[1px] bg-white/10 overflow-hidden">
        <div
          ref={barRef}
          className="h-full"
          style={{
            background: "linear-gradient(90deg, rgba(212,168,71,0.8), #d4a847)",
            transformOrigin: "left center",
            transform: "scaleX(0)",
          }}
        />
      </div>
    </div>
  );
}
