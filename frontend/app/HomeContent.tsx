"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { useLenis } from "@/components/SmoothScroll";
import { useAuth } from "@/hooks/useAuthContext";
import AuroraBackground from "@/components/background/AuroraBackground";
import QuantumCore from "@/components/background/QuantumCore";
import LaTeXOverlay from "@/components/ui/LaTeXOverlay";
import Preloader from "@/components/ui/Preloader";
import HeroSection from "@/sections/HeroSection";
import LiveLogicSection from "@/sections/LiveLogicSection";
import HistorySection from "@/sections/HistorySection";
import PnLShowcaseSection from "@/sections/PnLShowcaseSection";

gsap.registerPlugin(ScrollTrigger);

const PRELOADER_KEY = "agent-x-loaded";

export default function HomeContent() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [section, setSection] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [showPreloader, setShowPreloader] = useState(false);

  const searchParams = useSearchParams();
  const targetSection = searchParams.get("section");
  const lenis = useLenis();
  const { isAuthenticated } = useAuth();

  // Cek sessionStorage & referrer — skip preloader kalau sudah pernah load
  // atau kalau user navigasi internal dari halaman lain
  useEffect(() => {
    if (typeof window === "undefined") return;

    const alreadyLoaded = sessionStorage.getItem(PRELOADER_KEY);
    const isInternalNav =
      document.referrer && document.referrer.includes(window.location.origin);

    if (alreadyLoaded || isInternalNav) {
      setLoaded(true);
      setShowPreloader(false);
      if (!alreadyLoaded) {
        sessionStorage.setItem(PRELOADER_KEY, "true");
      }
    } else {
      setShowPreloader(true);
    }
  }, []);

  // Scroll ke section target setelah load (dari navigasi internal)
  useEffect(() => {
    if (!loaded || !targetSection || !lenis) return;

    const timer = setTimeout(() => {
      const el = document.getElementById(targetSection);
      if (el) {
        lenis.scrollTo(el, { offset: 0, duration: 1.2 });
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [loaded, targetSection, lenis]);

  const handlePreloaderComplete = useCallback(() => {
    setLoaded(true);
    setShowPreloader(false);
    if (typeof window !== "undefined") {
      sessionStorage.setItem(PRELOADER_KEY, "true");
    }
  }, []);

  useGSAP(
    () => {
      if (!containerRef.current || !loaded) return;
      const sections = gsap.utils.toArray<HTMLElement>(".story-section");

      sections.forEach((sec, i) => {
        ScrollTrigger.create({
          trigger: sec,
          start: "top center",
          end: "bottom center",
          onEnter: () => setSection(i),
          onEnterBack: () => setSection(i),
        });
      });
    },
    { scope: containerRef, dependencies: [loaded] }
  );

  return (
    <>
      {showPreloader && <Preloader onComplete={handlePreloaderComplete} />}

      <main ref={containerRef} className="relative bg-[#030303]">
        <AuroraBackground />
        <QuantumCore section={section} />
        <LaTeXOverlay />

        <div className="relative z-10">
          <div className="story-section" id="hero">
            <HeroSection />
          </div>
          <div className="story-section" id="live-logic">
            <LiveLogicSection />
          </div>
          <div className="story-section" id="history">
            <HistorySection />
          </div>
          <div className="story-section" id="pnl">
            <PnLShowcaseSection />
          </div>
        </div>
      </main>
    </>
  );
}
