"use client";

import { useRef } from "react";
import { motion } from "framer-motion";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger);

export default function HeroSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const subtitleRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
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
  }, { scope: sectionRef });

  return (
    <section
      ref={sectionRef}
      className="relative min-h-screen flex items-center justify-center z-10"
      style={{ paddingTop: "10vh", paddingBottom: "10vh" }}
    >
      <div className="text-center px-4 max-w-4xl mx-auto">
        <motion.div
          initial={{ opacity: 0, letterSpacing: "1em" }}
          animate={{ opacity: 1, letterSpacing: "0.4em" }}
          transition={{ duration: 2, ease: "easeOut" }}
          className="text-[9px] font-mono text-white/25 mb-10 tracking-[0.4em] uppercase"
        >
          AI-Powered
        </motion.div>

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
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8, duration: 1 }}
            className="text-sm sm:text-base text-white/35 max-w-sm mx-auto font-mono leading-relaxed tracking-wide"
          >
            Autonomous signal generation via multi-timeframe void analysis.
            MEXC perpetual futures. Zero latency execution.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.4, duration: 0.8 }}
            className="flex items-center justify-center gap-6"
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
        </div>

        {/* Scroll hint */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.5, duration: 1 }}
          className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <div className="text-[9px] font-mono text-white/20 tracking-[0.3em]">SCROLL</div>
          <div
            className="w-[1px] h-10 bg-gradient-to-b from-white/20 to-transparent"
            style={{ animation: "float 2s ease-in-out infinite alternate" }}
          />
        </motion.div>
      </div>
    </section>
  );
}
