"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { useTrading } from "@/hooks/useTradingContext";
import { ChartSkeleton } from "@/components/ui/Skeleton";

const W = 460;
const H = 130;
const PAD_X = 8;
const PAD_Y = 16;

export default function PnLChart() {
  const { state } = useTrading();

  // Build cumulative PnL series from closed signals
  const data = useMemo(() => {
    const closed = [...state.signals]
      .filter((s) => s.status === "CLOSED" && s.pnl_pct != null)
      .sort(
        (a, b) =>
          (a.closed_at ?? a.timestamp ?? 0) -
          (b.closed_at ?? b.timestamp ?? 0)
      );

    let cum = 0;
    const points = [{ trade: 0, pnl: 0 }]; // start at zero
    closed.forEach((s, i) => {
      cum += s.pnl_pct ?? 0;
      points.push({ trade: i + 1, pnl: cum });
    });
    return points;
  }, [state.signals]);

  const isLoading = state.trade_count > 0 && data.length <= 1;

  if (isLoading) return <ChartSkeleton height={H} />;

  if (data.length <= 1) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ height: H }}
      >
        <p className="text-[10px] font-mono text-white/20 tracking-widest">
          AWAITING TRADE DATA
        </p>
      </div>
    );
  }

  const n = data.length;
  const yValues = data.map((d) => d.pnl);
  const minY = Math.min(0, ...yValues);
  const maxY = Math.max(0, ...yValues);
  const rangeY = maxY - minY || 1;

  const toX = (i: number) =>
    PAD_X + (i / (n - 1)) * (W - PAD_X * 2);
  const toY = (v: number) =>
    H - PAD_Y - ((v - minY) / rangeY) * (H - PAD_Y * 2);

  const zeroY = toY(0);
  const lastPnl = yValues[yValues.length - 1];
  const isPositive = lastPnl >= 0;
  const lineColor = isPositive ? "#4ade80" : "#f87171";
  const areaOpacity = isPositive ? "rgba(74,222,128,0.07)" : "rgba(248,113,113,0.07)";

  // Build SVG path
  const pathD = data
    .map((d, i) => `${i === 0 ? "M" : "L"}${toX(i)},${toY(d.pnl)}`)
    .join(" ");

  const areaD =
    `M${toX(0)},${zeroY} ` +
    data.map((d, i) => `L${toX(i)},${toY(d.pnl)}`).join(" ") +
    ` L${toX(n - 1)},${zeroY} Z`;

  // Max drawup / drawdown label
  const maxVal = Math.max(...yValues);
  const minVal = Math.min(...yValues);

  return (
    <div className="w-full space-y-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        preserveAspectRatio="none"
        style={{ height: H }}
      >
        {/* Grid lines */}
        {[minY, 0, maxY].map((v, i) => {
          const y = toY(v);
          if (y < 0 || y > H) return null;
          return (
            <line
              key={i}
              x1={PAD_X}
              y1={y}
              x2={W - PAD_X}
              y2={y}
              stroke={v === 0 ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.04)"}
              strokeWidth={v === 0 ? 1 : 0.5}
              strokeDasharray={v === 0 ? "4,4" : "2,4"}
            />
          );
        })}

        {/* Area fill */}
        <path d={areaD} fill={areaOpacity} />

        {/* Animated line */}
        <motion.path
          d={pathD}
          fill="none"
          stroke={lineColor}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1.4, ease: "easeOut" }}
        />

        {/* Dots at min and max */}
        {yValues.indexOf(maxVal) > 0 && (
          <circle
            cx={toX(yValues.indexOf(maxVal))}
            cy={toY(maxVal)}
            r="2.5"
            fill="#4ade80"
            opacity={0.7}
          />
        )}
        {minVal < 0 && yValues.indexOf(minVal) > 0 && (
          <circle
            cx={toX(yValues.indexOf(minVal))}
            cy={toY(minVal)}
            r="2.5"
            fill="#f87171"
            opacity={0.7}
          />
        )}

        {/* Current value dot — pulsing */}
        <motion.circle
          cx={toX(n - 1)}
          cy={toY(lastPnl)}
          r="3.5"
          fill={lineColor}
          animate={{ r: [3, 4.5, 3] }}
          transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
        />
      </svg>

      {/* Footer */}
      <div className="flex justify-between items-center px-1">
        <div className="flex items-center gap-3">
          <span className="text-[9px] font-mono text-white/20">
            {data.length - 1} trades
          </span>
          {minVal < 0 && (
            <span className="text-[9px] font-mono text-[#f87171]/50">
              max DD {minVal.toFixed(1)}%
            </span>
          )}
        </div>
        <span
          className={`text-[11px] font-mono font-bold ${
            isPositive ? "text-[#4ade80]" : "text-[#f87171]"
          }`}
        >
          {isPositive ? "+" : ""}
          {lastPnl.toFixed(2)}%
        </span>
      </div>
    </div>
  );
}
