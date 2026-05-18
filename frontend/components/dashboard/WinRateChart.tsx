"use client";

interface WinRateChartProps {
  wins: number;
  losses: number;
  size?: number;
}

export default function WinRateChart({
  wins,
  losses,
  size = 200,
}: WinRateChartProps) {
  const total = wins + losses;
  const winRate = total > 0 ? (wins / total) * 100 : 0;
  const circumference = 2 * Math.PI * 80;
  const strokeDashoffset = circumference - (winRate / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-4">
      <svg
        width={size}
        height={size}
        viewBox="0 0 200 200"
        className="transform -rotate-90"
      >
        <circle
          cx="100"
          cy="100"
          r="80"
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth="12"
        />
        <circle
          cx="100"
          cy="100"
          r="80"
          fill="none"
          stroke={winRate >= 60 ? "#d4a847" : "#60a5fa"}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="text-center -mt-32 relative z-10">
        <div
          className="text-3xl font-bold font-mono"
          style={{ color: winRate >= 60 ? "#d4a847" : "#fff" }}
        >
          {winRate.toFixed(1)}%
        </div>
        <div className="text-[10px] font-mono text-white/30 tracking-widest mt-1">
          WIN RATE
        </div>
      </div>
      <div className="flex gap-6 mt-4">
        <div className="text-center">
          <div className="text-lg font-bold font-mono text-[#4ade80]">
            {wins}
          </div>
          <div className="text-[9px] font-mono text-white/30">WINS</div>
        </div>
        <div className="text-center">
          <div className="text-lg font-bold font-mono text-[#f87171]">
            {losses}
          </div>
          <div className="text-[9px] font-mono text-white/30">LOSSES</div>
        </div>
      </div>
    </div>
  );
}
