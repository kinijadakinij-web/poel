"use client";

import { useRef, useEffect, useMemo, useCallback } from "react";
import { useTrading } from "@/hooks/useTradingContext";
import gsap from "gsap";
import OrbCore from "@/components/background/OrbCore";

const COINS = [
  { id: "bitcoin", name: "BTC", path: "/images/coins/bitcoin.png" },
  { id: "ethereum", name: "ETH", path: "/images/coins/ethereum.png" },
  { id: "solana", name: "SOL", path: "/images/coins/solana.png" },
  { id: "binancecoin", name: "BNB", path: "/images/coins/bnb.png" },
  { id: "dogecoin", name: "DOGE", path: "/images/coins/dogecoin.png" },
  { id: "cardano", name: "ADA", path: "/images/coins/cardano.png" },
  { id: "tron", name: "TRX", path: "/images/coins/tron.png" },
  { id: "chainlink", name: "LINK", path: "/images/coins/chainlink.png" },
  { id: "polkadot", name: "DOT", path: "/images/coins/polkadot.png" },
  { id: "litecoin", name: "LTC", path: "/images/coins/litecoin.png" },
  { id: "avalanche", name: "AVAX", path: "/images/coins/avalanche.png" },
];

interface OrbitingCoin {
  id: string;
  name: string;
  path: string;
  radius: number;
  speed: number;
  startAngle: number;
  size: number;
  tilt: number;
  yOffset: number;
  glowColor: string;
  ringIndex: number;
}

interface Particle {
  angle: number;
  radius: number;
  speed: number;
  size: number;
  ring: number;
  yOffset: number;
}

export default function QuantumCore({ section }: { section: number }) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const coreRef = useRef<HTMLDivElement>(null);
  const ring1Ref = useRef<HTMLDivElement>(null);
  const ring2Ref = useRef<HTMLDivElement>(null);
  const ring3Ref = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const particlesRef = useRef<HTMLDivElement[]>([]);
  const coinsRef = useRef<HTMLDivElement[]>([]);
  const { state, latestTheme } = useTrading();

  const isMobile = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 768;
  }, []);

  const color = useMemo(() => {
    return latestTheme === "profit" ? "#4ade80" : latestTheme === "loss" ? "#f87171" : "#60a5fa";
  }, [latestTheme]);

  const colorDim = useMemo(() => {
    return latestTheme === "profit" ? "rgba(74,222,128,0.2)" : latestTheme === "loss" ? "rgba(248,113,113,0.2)" : "rgba(96,165,250,0.2)";
  }, [latestTheme]);

  // Generate orbiting coins — luxury 3D orbit parameters
  const orbitingCoins = useMemo<OrbitingCoin[]>(() => {
    const glowColors = [
      "rgba(212,168,71,0.5)",   // gold
      "rgba(96,165,250,0.4)",   // blue
      "rgba(196,181,253,0.4)",  // violet
      "rgba(74,222,128,0.35)",  // green
    ];

    const coinCount = isMobile ? 6 : 16;
    
    return Array.from({ length: coinCount }).map((_, i) => {
      const coin = COINS[i % COINS.length];
      const ringIndex = i % 3;
      
      // Mobile: spread wider, not too center-focused
      const baseRadius = isMobile 
        ? (ringIndex === 0 ? 200 : ringIndex === 1 ? 140 : 90)
        : (ringIndex === 0 ? 280 : ringIndex === 1 ? 200 : 140);
      
      const radiusVariation = (Math.random() - 0.5) * (isMobile ? 30 : 40);
      
      return {
        ...coin,
        radius: baseRadius + radiusVariation,
        speed: 0.0003 + (Math.random() * 0.0004) + (ringIndex * 0.0002),
        startAngle: (i / coinCount) * Math.PI * 2 + (Math.random() * 0.5),
        size: isMobile ? 22 + Math.random() * 18 : 28 + Math.random() * 24,
        tilt: (Math.random() - 0.5) * 30,
        yOffset: (Math.random() - 0.5) * (isMobile ? 50 : 60),
        glowColor: glowColors[i % glowColors.length],
        ringIndex,
      };
    });
  }, [isMobile]);

  const particles = useMemo<Particle[]>(() => {
    const count = isMobile ? 10 : 24;
    const arr: Particle[] = [];
    for (let i = 0; i < count; i++) {
      arr.push({
        angle: (i / count) * Math.PI * 2,
        radius: isMobile ? 50 + Math.random() * 45 : 70 + Math.random() * 60,
        speed: 0.002 + Math.random() * 0.004,
        size: isMobile ? 1 + Math.random() * 1.5 : 1.5 + Math.random() * 2.5,
        ring: i % 3,
        yOffset: (Math.random() - 0.5) * (isMobile ? 30 : 40),
      });
    }
    return arr;
  }, [isMobile]);

  // GSAP section animations — coins included in timeline
  useEffect(() => {
    if (!wrapperRef.current || !coreRef.current) return;

    const tl = gsap.timeline({ defaults: { duration: 1.2, ease: "power3.inOut" } });
    const coinEls = coinsRef.current.filter(Boolean);

    switch (section) {
      case 0:
        tl.to(wrapperRef.current, { x: 0, scale: 1, rotateY: 0, rotateX: 0 }, 0)
          .to(coreRef.current, { scale: 1, opacity: 1 }, 0)
          .to(ring1Ref.current, { rotateX: 75, rotateZ: 0, scale: 1 }, 0)
          .to(ring2Ref.current, { rotateX: 45, rotateZ: 30, scale: 1 }, 0)
          .to(ring3Ref.current, { rotateX: 0, rotateZ: -20, scale: 1 }, 0)
          .to(coinEls, { scale: 1, opacity: 0.85, duration: 1.2, stagger: 0.02 }, 0);
        break;
      case 1:
        // Mobile: shift 25vw left to feel the movement
        tl.to(wrapperRef.current, { x: isMobile ? "-25vw" : "-20vw", scale: 0.9, rotateY: isMobile ? 10 : 15 }, 0)
          .to(coreRef.current, { scale: 0.7, opacity: 0.9 }, 0)
          .to(ring1Ref.current, { rotateX: 90, rotateZ: 45, scale: 1.3, y: -40 }, 0)
          .to(ring2Ref.current, { rotateX: 0, rotateZ: 90, scale: 1.1, y: 0 }, 0)
          .to(ring3Ref.current, { rotateX: 60, rotateZ: -60, scale: 0.9, y: 40 }, 0)
          .to(coinEls, { scale: 0.75, opacity: 0.6, duration: 1.2, stagger: 0.02 }, 0);
        break;
      case 2:
        tl.to(wrapperRef.current, { x: 0, scale: 0.85, rotateY: 0 }, 0)
          .to(coreRef.current, { scale: 0.5, opacity: 0.6 }, 0)
          .to(ring1Ref.current, { rotateX: 0, rotateZ: 0, scale: 1.5, opacity: 0.3 }, 0)
          .to(ring2Ref.current, { rotateX: 0, rotateZ: 30, scale: 1.2, opacity: 0.5 }, 0)
          .to(ring3Ref.current, { rotateX: 0, rotateZ: -15, scale: 1, opacity: 0.7 }, 0)
          .to(coinEls, { scale: 0.35, opacity: 0.15, duration: 1.2, stagger: 0.02 }, 0);
        break;
      case 3:
        tl.to(wrapperRef.current, { x: 0, scale: isMobile ? 1.02 : 1.15, rotateY: 0 }, 0)
          .to(coreRef.current, { scale: isMobile ? 1.05 : 1.3, opacity: 1 }, 0)
          .to(ring1Ref.current, { rotateX: 80, rotateZ: 180, scale: 1.2 }, 0)
          .to(ring2Ref.current, { rotateX: 50, rotateZ: -180, scale: 1.1 }, 0)
          .to(ring3Ref.current, { rotateX: 20, rotateZ: 360, scale: 1 }, 0)
          .to(coinEls, { scale: isMobile ? 1.02 : 1.2, opacity: 1, duration: 1.2, stagger: 0.02 }, 0);
        break;
    }
  }, [section, isMobile]);

  // Animation loop — particles + orbiting coins
  const animate = useCallback(() => {
    const time = Date.now();
    const w = 400;
    const h = 400;
    const cx = w / 2;
    const cy = h / 2;

    // Animate particles
    const positions = particles.map((p, i) => {
      const t = time * p.speed + p.angle;
      let r = p.radius;

      if (section === 1) r += Math.sin(t * 3) * 20;
      if (section === 2) r = (isMobile ? 35 : 60) + (i % 5) * (isMobile ? 15 : 25);
      if (section === 3) r += Math.sin(time * 0.005 + i) * 30;

      const x = cx + Math.cos(t) * r;
      const y = cy + Math.sin(t) * r * 0.6 + p.yOffset;

      const el = particlesRef.current[i];
      if (el) {
        el.style.transform = `translate(${x - cx}px, ${y - cy}px)`;
        el.style.opacity = section === 2 && i > (isMobile ? 5 : 12) ? "0.2" : "0.8";
      }

      return { x, y, size: p.size };
    });

    // SVG connection lines
    let pathData = "";
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        const dx = positions[i].x - positions[j].x;
        const dy = positions[i].y - positions[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        const threshold = section === 3 ? 120 : section === 1 ? 80 : 60;
        if (dist < threshold) {
          pathData += `M${positions[i].x},${positions[i].y} L${positions[j].x},${positions[j].y} `;
        }
      }
    }

    const pathEl = svgRef.current?.querySelector("path");
    if (pathEl) {
      pathEl.setAttribute("d", pathData);
      pathEl.setAttribute("stroke", colorDim);
      pathEl.setAttribute("stroke-width", section === 3 ? "1.5" : "0.8");
    }

    // Animate orbiting coins — luxury 3D orbit
    orbitingCoins.forEach((coin, i) => {
      const el = coinsRef.current[i];
      if (!el) return;

      const orbitTime = time * coin.speed + coin.startAngle;
      
      // 3D orbit calculation
      const x = Math.cos(orbitTime) * coin.radius;
      const z = Math.sin(orbitTime) * coin.radius;
      const y = coin.yOffset + Math.sin(orbitTime * 0.5) * (isMobile ? 15 : 20);
      
      // Scale & opacity based on z-depth
      const scale = 0.65 + ((z + coin.radius) / (coin.radius * 2)) * 0.7;
      const opacity = 0.35 + ((z + coin.radius) / (coin.radius * 2)) * 0.65;
      
      // 3D rotation
      const rotateY = orbitTime * (180 / Math.PI) + coin.tilt;
      const rotateX = Math.sin(orbitTime) * (isMobile ? 6 : 10);

      el.style.transform = `
        translate3d(${x}px, ${y}px, ${z}px) 
        scale(${scale}) 
        rotateY(${rotateY}deg) 
        rotateX(${rotateX}deg)
      `;
      el.style.opacity = String(opacity);
      el.style.zIndex = z > 0 ? "10" : "1";
    });
  }, [particles, orbitingCoins, section, colorDim, isMobile]);

  useEffect(() => {
    let raf: number;
    const loop = () => {
      animate();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [animate]);

  return (
    <div className="fixed inset-0 z-0 flex items-center justify-center pointer-events-none perspective-[1000px]">
      <div
        ref={wrapperRef}
        className="relative transition-none"
        style={{ 
          width: isMobile ? "clamp(280px, 85vw, 380px)" : "clamp(260px, 80vw, 400px)", 
          height: isMobile ? "clamp(280px, 85vw, 380px)" : "clamp(260px, 80vw, 400px)", 
          transformStyle: "preserve-3d", 
          willChange: "transform", 
          backfaceVisibility: "hidden" 
        }}
      >
        {/* Orbiting Coins — inside wrapper so they follow GSAP transforms */}
        <div className="absolute inset-0 flex items-center justify-center" style={{ transformStyle: "preserve-3d" }}>
          {orbitingCoins.map((coin, i) => (
            <div
              key={`orbit-coin-${i}`}
              ref={(el) => { if (el) coinsRef.current[i] = el; }}
              className="absolute"
              style={{
                width: coin.size,
                height: coin.size,
                transformStyle: "preserve-3d",
                willChange: "transform, opacity",
              }}
            >
              <div
                className="w-full h-full rounded-full relative overflow-hidden"
                style={{
                  boxShadow: `
                    0 0 ${coin.size * 0.6}px ${coin.glowColor},
                    0 0 ${coin.size * 1.2}px ${coin.glowColor},
                    inset 0 0 ${coin.size * 0.2}px rgba(255,255,255,0.15)
                  `,
                }}
              >
                <img
                  src={coin.path}
                  alt={coin.name}
                  className="w-full h-full object-contain rounded-full"
                  style={{
                    filter: "brightness(1.15) contrast(1.05) saturate(1.1)",
                  }}
                  draggable={false}
                />
                {/* Luxury gloss overlay */}
                <div
                  className="absolute inset-0 rounded-full pointer-events-none"
                  style={{
                    background: "linear-gradient(135deg, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.1) 40%, transparent 60%, rgba(255,255,255,0.2) 100%)",
                  }}
                />
                {/* Bottom reflection */}
                <div
                  className="absolute bottom-0 left-0 right-0 h-1/3 rounded-b-full pointer-events-none"
                  style={{
                    background: "linear-gradient(to top, rgba(255,255,255,0.15), transparent)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <svg
          ref={svgRef}
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 400 400"
          style={{ zIndex: 5 }}
        >
          <path
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={section === 0 ? 0.3 : section === 1 ? 0.5 : section === 2 ? 0.2 : 0.6}
          />
        </svg>

        <div
          ref={ring3Ref}
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            className="absolute rounded-full border transition-colors duration-700"
            style={{
              width: isMobile ? "clamp(160px, 78%, 300px)" : "clamp(180px, 80%, 320px)",
              height: isMobile ? "clamp(160px, 78%, 300px)" : "clamp(180px, 80%, 320px)",
              borderColor: colorDim,
              borderWidth: "1px",
              borderStyle: section === 2 ? "dashed" : "solid",
              boxShadow: `0 0 ${isMobile ? 20 : 40}px ${colorDim}`,
            }}
          />
          {[0, 120, 240].map((deg, i) => (
            <div
              key={`r3-${i}`}
              className="absolute w-2 h-2 rounded-full transition-colors duration-700"
              style={{
                backgroundColor: color,
                boxShadow: `0 0 ${isMobile ? 6 : 12}px ${color}`,
                top: "50%",
                left: "50%",
                marginLeft: "-4px",
                marginTop: "-4px",
                transform: `rotate(${deg}deg) translateX(${isMobile ? 150 : 160}px)`,
                animation: `orbitRing3 ${10 + i * 2}s linear infinite`,
              }}
            />
          ))}
        </div>

        <div
          ref={ring2Ref}
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            className="absolute rounded-full border transition-colors duration-700"
            style={{
              width: isMobile ? "clamp(115px, 58%, 210px)" : "clamp(135px, 60%, 240px)",
              height: isMobile ? "clamp(115px, 58%, 210px)" : "clamp(135px, 60%, 240px)",
              borderColor: color,
              borderWidth: "2px",
              opacity: 0.4,
              boxShadow: `inset 0 0 ${isMobile ? 15 : 30}px ${colorDim}`,
            }}
          />
          {Array.from({ length: 6 }).map((_, i) => {
            const angle = (i / 6) * Math.PI * 2;
            return (
              <div
                key={`r2-${i}`}
                className="absolute flex flex-col items-center gap-1 transition-opacity duration-500"
                style={{
                  top: `${50 + (isMobile ? 34 : 38) * Math.sin(angle)}%`,
                  left: `${50 + (isMobile ? 34 : 38) * Math.cos(angle)}%`,
                  transform: "translate(-50%, -50%)",
                  opacity: section === 1 ? 1 : 0.3,
                }}
              >
                <div className="w-1 h-1 rounded-full bg-white/60" />
                {section === 1 && (
                  <span className="text-[7px] font-mono text-white/40 whitespace-nowrap">
                    {["5m", "15m", "30m", "1h", "4h", "AI"][i]}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <div
          ref={ring1Ref}
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            className="absolute rounded-full border transition-colors duration-700"
            style={{
              width: isMobile ? "clamp(75px, 38%, 145px)" : "clamp(90px, 40%, 160px)",
              height: isMobile ? "clamp(75px, 38%, 145px)" : "clamp(90px, 40%, 160px)",
              borderColor: color,
              borderWidth: "1px",
              opacity: 0.6,
            }}
          />
          <div
            className="absolute w-full h-full"
            style={{
              animation: `spin ${section === 3 ? "3s" : "8s"} linear infinite ${section === 3 ? "reverse" : "normal"}`,
            }}
          >
            {[0, 90, 180, 270].map((deg) => (
              <div
                key={`r1-${deg}`}
                className="absolute w-1.5 h-1.5 rounded-full transition-colors duration-700"
                style={{
                  backgroundColor: color,
                  top: `${50 + 50 * Math.sin((deg * Math.PI) / 180)}%`,
                  left: `${50 + 50 * Math.cos((deg * Math.PI) / 180)}%`,
                  transform: "translate(-50%, -50%)",
                }}
              />
            ))}
          </div>
        </div>

        <div
          ref={coreRef}
          className="absolute inset-0 flex items-center justify-center"
          style={{ zIndex: 10 }}
        >
          <OrbCore 
            color={color} 
            section={section} 
            size={Math.min(isMobile ? 170 : 220, typeof window !== "undefined" ? window.innerWidth * (isMobile ? 0.5 : 0.55) : (isMobile ? 170 : 220))} 
          />
          {section === 1 && state.active_signal_count > 0 && (
            <div
              className="absolute -top-2 -right-2 w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold font-mono text-black"
              style={{ backgroundColor: color }}
            >
              {state.active_signal_count}
            </div>
          )}
        </div>

        {particles.map((p, i) => (
          <div
            key={`p-${i}`}
            ref={(el) => {
              if (el) particlesRef.current[i] = el;
            }}
            className="absolute top-1/2 left-1/2 rounded-full transition-colors duration-700 pointer-events-none"
            style={{
              backgroundColor: i % 4 === 0 ? color : "rgba(255,255,255,0.5)",
              boxShadow: i % 4 === 0 ? `0 0 ${isMobile ? 4 : 8}px ${color}` : "none",
              marginLeft: "-2px",
              marginTop: "-2px",
              width: `${p.size}px`,
              height: `${p.size}px`,
            }}
          />
        ))}

        {section === 1 && (
          <div className="absolute inset-0 pointer-events-none">
            {Array.from({ length: isMobile ? 3 : 5 }).map((_, i) => (
              <div
                key={`candle-${i}`}
                className="absolute w-[2px] rounded-full transition-colors duration-700"
                style={{
                  height: `${15 + Math.random() * 20}px`,
                  backgroundColor: i % 2 === 0 ? "rgba(74,222,128,0.4)" : "rgba(248,113,113,0.4)",
                  top: `${20 + i * (isMobile ? 22 : 15)}%`,
                  left: `${10 + i * (isMobile ? 28 : 20)}%`,
                  animation: `float ${3 + i}s ease-in-out ${i * 0.5}s infinite alternate`,
                }}
              />
            ))}
          </div>
        )}

        {section === 2 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-30">
            <svg width={isMobile ? 140 : 200} height={isMobile ? 140 : 200} viewBox="0 0 200 200" className="animate-[spin_60s_linear_infinite]">
              <defs>
                <pattern id="hex" width="28" height="48" patternUnits="userSpaceOnUse">
                  <path d="M14 0 L28 8 L28 24 L14 32 L0 24 L0 8 Z" fill="none" stroke={colorDim} strokeWidth="0.5" />
                </pattern>
              </defs>
              <rect width="200" height="200" fill="url(#hex)" />
            </svg>
          </div>
        )}

        {section === 3 && (
          <div className="absolute inset-0 pointer-events-none">
            {Array.from({ length: isMobile ? 5 : 8 }).map((_, i) => {
              const angle = (i / (isMobile ? 5 : 8)) * Math.PI * 2;
              return (
                <div
                  key={`burst-${i}`}
                  className="absolute top-1/2 left-1/2 h-[1px] origin-left transition-colors duration-700"
                  style={{
                    width: isMobile ? "120px" : "180px",
                    background: `linear-gradient(90deg, ${color}, transparent)`,
                    transform: `rotate(${angle}rad)`,
                    opacity: 0.3,
                    animation: `pulse 2s ease-in-out ${i * 0.25}s infinite`,
                  }}
                />
              );
            })}
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes orbitRing3 {
          from { transform: rotate(0deg) translateX(${isMobile ? 150 : 160}px) rotate(0deg); }
          to { transform: rotate(360deg) translateX(${isMobile ? 150 : 160}px) rotate(-360deg); }
        }
      `}</style>
    </div>
  );
}
