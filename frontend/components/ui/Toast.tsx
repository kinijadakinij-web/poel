"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  ReactNode,
} from "react";
import { motion, AnimatePresence } from "framer-motion";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────
type ToastType = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextType {
  toast: (message: string, type?: ToastType) => void;
}

// ─────────────────────────────────────────────
// Context
// ─────────────────────────────────────────────
const ToastContext = createContext<ToastContextType | null>(null);

// ─────────────────────────────────────────────
// Provider
// ─────────────────────────────────────────────
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts((prev) => [...prev.slice(-4), { id, type, message }]); // max 5 on screen
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}

      {/* Portal-style overlay — always on top */}
      <div className="fixed top-4 right-4 z-[300] flex flex-col gap-2 pointer-events-none">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <ToastCard key={t.id} item={t} onClose={() => remove(t.id)} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

// ─────────────────────────────────────────────
// Single card
// ─────────────────────────────────────────────
const CONFIG: Record<
  ToastType,
  { icon: string; border: string; glow: string; text: string }
> = {
  success: {
    icon: "✓",
    border: "border-[#4ade80]/30",
    glow: "bg-[#4ade80]/8",
    text: "text-[#4ade80]",
  },
  error: {
    icon: "✕",
    border: "border-[#f87171]/30",
    glow: "bg-[#f87171]/8",
    text: "text-[#f87171]",
  },
  warning: {
    icon: "⚠",
    border: "border-[#d4a847]/30",
    glow: "bg-[#d4a847]/8",
    text: "text-[#d4a847]",
  },
  info: {
    icon: "ℹ",
    border: "border-[#60a5fa]/30",
    glow: "bg-[#60a5fa]/8",
    text: "text-[#60a5fa]",
  },
};

function ToastCard({
  item,
  onClose,
}: {
  item: ToastItem;
  onClose: () => void;
}) {
  const c = CONFIG[item.type];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 56, scale: 0.92 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 56, scale: 0.92, transition: { duration: 0.2 } }}
      transition={{ type: "spring", damping: 24, stiffness: 320 }}
      className={`
        pointer-events-auto flex items-start gap-3
        px-4 py-3 rounded-xl border backdrop-blur-xl
        glass ${c.border} ${c.glow}
        min-w-[220px] max-w-[300px] cursor-pointer
        shadow-[0_4px_24px_rgba(0,0,0,0.4)]
      `}
      onClick={onClose}
    >
      {/* Icon */}
      <span className={`text-sm font-bold mt-[1px] flex-shrink-0 ${c.text}`}>
        {c.icon}
      </span>

      {/* Message */}
      <p className="text-[11px] font-mono text-white/80 flex-1 leading-relaxed">
        {item.message}
      </p>

      {/* Close hint */}
      <span className="text-[10px] text-white/20 flex-shrink-0 mt-[1px]">×</span>
    </motion.div>
  );
}

// ─────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────
export function useToast(): (message: string, type?: ToastType) => void {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx.toast;
}
