"use client";

import { useEffect, useRef } from "react";
import { useTrading } from "@/hooks/useTradingContext";

type ToastFn = (message: string, type?: "success" | "error" | "warning" | "info") => void;

/**
 * useSignalNotifications
 *
 * Watches the trading state for signal status changes and fires:
 *   1. In-app toast via the provided `toast` function
 *   2. Browser push notification (if permission granted)
 *
 * Usage:
 *   const toast = useToast();
 *   useSignalNotifications(toast);
 */
export function useSignalNotifications(toast: ToastFn) {
  const { state } = useTrading();

  // Track previous status per signal id → status
  const prevRef = useRef<Map<string, string>>(new Map());

  // Request browser notification permission once on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window)) return;
    if (Notification.permission === "default") {
      // Non-blocking — doesn't need to await
      Notification.requestPermission();
    }
  }, []);

  // Watch for status changes
  useEffect(() => {
    const prev = prevRef.current;

    state.signals.forEach((sig) => {
      const prevStatus = prev.get(sig.id);

      // Only fire when a signal JUST moved to CLOSED (wasn't CLOSED before)
      if (sig.status === "CLOSED" && prevStatus !== "CLOSED") {
        const symbol = sig.symbol.replace("_USDT", "");
        const pnl = sig.pnl_pct?.toFixed(2) ?? "0.00";
        const isWin = (sig.pnl_pct ?? 0) >= 0;

        if (sig.result === "TP") {
          const msg = `${symbol} ${sig.decision} — TP hit! +${pnl}%`;
          toast(`🎯 ${msg}`, "success");
          pushNotification("✅ Take Profit!", msg);
        } else if (sig.result === "SL") {
          const msg = `${symbol} ${sig.decision} — SL hit. ${pnl}%`;
          toast(`🛑 ${msg}`, "error");
          pushNotification("🛑 Stop Loss", msg);
        } else if (sig.result === "AI_CLOSE") {
          const msg = `${symbol} AI closed ${isWin ? "+" : ""}${pnl}%`;
          toast(`🤖 ${msg}`, isWin ? "success" : "warning");
          pushNotification("🤖 AI Close", msg);
        } else if (sig.result === "TIMEOUT") {
          const msg = `${symbol} signal expired`;
          toast(`⏱ ${msg}`, "info");
        }
      }

      // Update map to current status
      if (sig.status) {
        prev.set(sig.id, sig.status);
      }
    });
  }, [state.signals, toast]);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function pushNotification(title: string, body: string) {
  if (typeof window === "undefined") return;
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;

  try {
    new Notification(title, {
      body,
      icon: "/favicon.ico",
      tag: `sonnetrade-${Date.now()}`, // prevent stacking identical notifs
      silent: false,
    });
  } catch {
    // Some browsers block notifications from non-secure contexts — fail silently
  }
}
