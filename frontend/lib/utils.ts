import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs === 0) return "0";
  if (abs >= 10000) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (abs >= 1) return n.toFixed(4);
  if (abs >= 0.01) return n.toFixed(6);
  if (abs >= 0.0001) return n.toFixed(8);
  return n.toPrecision(4);
}

export function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function getThemeFromPnl(pnl?: number | null): "profit" | "loss" | "neutral" {
  if (pnl == null) return "neutral";
  return pnl >= 0 ? "profit" : "loss";
}
