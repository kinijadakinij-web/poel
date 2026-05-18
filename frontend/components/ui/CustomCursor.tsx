"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

export default function CustomCursor() {
  const dotRef   = useRef<HTMLDivElement>(null);
  const trailRef = useRef<HTMLDivElement>(null);
  const pos      = useRef({ x: 0, y: 0 });
  const trailer  = useRef({ x: 0, y: 0 });
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(pointer: fine)");
    if (!mq.matches) return;
    setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const dot   = dotRef.current;
    const trail = trailRef.current;
    if (!dot || !trail) return;

    const onMove = (e: MouseEvent) => {
      pos.current = { x: e.clientX, y: e.clientY };
      gsap.to(dot, { x: e.clientX, y: e.clientY, duration: 0.08, ease: "power2.out" });
    };
    const onEnter = () => {
      gsap.to(dot,   { scale: 0.4, opacity: 0.6, duration: 0.3 });
      gsap.to(trail, { scale: 2.2, opacity: 0.15, duration: 0.4 });
    };
    const onLeave = () => {
      gsap.to(dot,   { scale: 1, opacity: 1, duration: 0.3 });
      gsap.to(trail, { scale: 1, opacity: 0.5, duration: 0.4 });
    };

    let raf: number;
    const animateTrailer = () => {
      trailer.current.x += (pos.current.x - trailer.current.x) * 0.1;
      trailer.current.y += (pos.current.y - trailer.current.y) * 0.1;
      gsap.set(trail, { x: trailer.current.x, y: trailer.current.y });
      raf = requestAnimationFrame(animateTrailer);
    };
    raf = requestAnimationFrame(animateTrailer);

    document.addEventListener("mousemove", onMove);
    const interactives = document.querySelectorAll("a,button,[role='button'],.shimmer-card");
    interactives.forEach(el => { el.addEventListener("mouseenter", onEnter); el.addEventListener("mouseleave", onLeave); });

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("mousemove", onMove);
      interactives.forEach(el => { el.removeEventListener("mouseenter", onEnter); el.removeEventListener("mouseleave", onLeave); });
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <>
      <div ref={dotRef} className="fixed top-0 left-0 z-[9999] pointer-events-none mix-blend-difference" style={{ transform: "translate(-50%,-50%)" }}>
        <div className="w-2 h-2 rounded-full bg-white" />
      </div>
      <div ref={trailRef} className="fixed top-0 left-0 z-[9998] pointer-events-none" style={{ transform: "translate(-50%,-50%)", opacity: 0.5 }}>
        <div className="w-8 h-8 rounded-full border border-white/40" />
      </div>
    </>
  );
}
