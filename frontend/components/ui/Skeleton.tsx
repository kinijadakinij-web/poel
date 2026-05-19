"use client";

// ─────────────────────────────────────────────
// Base pulse block
// ─────────────────────────────────────────────
export function SkeletonPulse({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-white/[0.06] ${className}`}
    />
  );
}

// ─────────────────────────────────────────────
// Stat card (used in dashboard top row)
// ─────────────────────────────────────────────
export function StatCardSkeleton() {
  return (
    <div className="glass rounded-xl p-3 sm:p-4 text-center space-y-2">
      <SkeletonPulse className="h-5 w-14 mx-auto" />
      <SkeletonPulse className="h-2 w-10 mx-auto" />
    </div>
  );
}

// ─────────────────────────────────────────────
// Signal card (used in SignalFeed)
// ─────────────────────────────────────────────
export function SignalCardSkeleton() {
  return (
    <div className="glass rounded-xl p-3 sm:p-4 border border-white/5 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          <SkeletonPulse className="h-4 w-12" />
          <SkeletonPulse className="h-4 w-10" />
        </div>
        <SkeletonPulse className="h-3 w-12" />
      </div>
      {/* Row 1 */}
      <div className="grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="text-center space-y-1">
            <SkeletonPulse className="h-2 w-8 mx-auto" />
            <SkeletonPulse className="h-3 w-14 mx-auto" />
          </div>
        ))}
      </div>
      {/* Row 2 */}
      <div className="grid grid-cols-3 gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="text-center space-y-1">
            <SkeletonPulse className="h-2 w-6 mx-auto" />
            <SkeletonPulse className="h-3 w-12 mx-auto" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Table row (used in TradeHistoryTable)
// ─────────────────────────────────────────────
export function TableRowSkeleton({ cols = 6 }: { cols?: number }) {
  return (
    <tr className="border-b border-white/[0.02]">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="py-2.5 px-2">
          <SkeletonPulse
            className={`h-3 ${i === 0 ? "w-12" : i === cols - 1 ? "w-6" : "w-full"}`}
          />
        </td>
      ))}
    </tr>
  );
}

// ─────────────────────────────────────────────
// Chart skeleton
// ─────────────────────────────────────────────
export function ChartSkeleton({ height = 120 }: { height?: number }) {
  return (
    <div
      className="w-full animate-pulse rounded-lg bg-white/[0.04] flex items-end gap-1 px-3 pb-3 pt-6"
      style={{ height }}
    >
      {Array.from({ length: 12 }).map((_, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm bg-white/[0.08]"
          style={{ height: `${20 + Math.sin(i * 0.8) * 40 + 40}%` }}
        />
      ))}
    </div>
  );
}
