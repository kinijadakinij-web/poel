"use client";

import React, { createContext, useContext, useReducer, useEffect, useCallback } from "react";
import { useAuth } from "./useAuthContext";
import { getBotState, getBalance } from "@/lib/api";
import type { Signal, BotState, BalanceInfo, WSEvent } from "@/lib/types";

interface TradingContextType {
  state: BotState;
  balance: BalanceInfo;
  latestTheme: "profit" | "loss" | "neutral";
  dispatch: React.Dispatch<Action>;
}

type Action =
  | { type: "SET_STATE"; payload: Partial<BotState> }
  | { type: "SET_BALANCE"; payload: BalanceInfo }
  | { type: "ADD_SIGNAL"; payload: Signal }
  | { type: "UPDATE_SIGNAL"; payload: Signal }
  | { type: "CLOSE_SIGNAL"; payload: Signal }
  | { type: "SET_THEME"; payload: "profit" | "loss" | "neutral" };

const initialState: BotState = {
  status: "IDLE",
  signals: [],
  trade_count: 0,
  win_count: 0,
  loss_count: 0,
  no_trade_count: 0,
  total_pnl_pct: 0,
  total_pnl_usdt: 0,
  symbols_scanned: 0,
  active_signal_count: 0,
  max_active_signals: 20,
  winrate: 0,
  balance: 1000,
};

const initialBalance: BalanceInfo = {
  balance: 1000,
  initial_balance: 1000,
  leverage: 10,
  entry_usdt: 100,
};

function reducer(state: BotState, action: Action): BotState {
  switch (action.type) {
    case "SET_STATE":
      return { ...state, ...action.payload };
    case "ADD_SIGNAL":
      return {
        ...state,
        signals: [action.payload, ...state.signals].slice(0, 500),
        active_signal_count: state.active_signal_count + 1,
      };
    case "UPDATE_SIGNAL": {
      const idx = state.signals.findIndex((s) => s.id === action.payload.id);
      if (idx === -1) return state;
      const next = [...state.signals];
      next[idx] = { ...next[idx], ...action.payload };
      return { ...state, signals: next };
    }
    case "CLOSE_SIGNAL": {
      const existing = state.signals.find((s) => s.id === action.payload.id);
      const alreadyCounted = existing?.status === "CLOSED";
      let nextSignals;
      if (existing) {
        nextSignals = state.signals.map((s) =>
          s.id === action.payload.id
            ? ({ ...s, ...action.payload, status: "CLOSED" as const } as Signal)
            : s
        );
      } else {
        nextSignals = [
          { ...action.payload, status: "CLOSED" as const } as Signal,
          ...state.signals,
        ].slice(0, 500);
      }
      if (alreadyCounted) {
        return { ...state, signals: nextSignals };
      }
      const pnl = action.payload.pnl_pct || 0;
      return {
        ...state,
        signals: nextSignals,
        trade_count: state.trade_count + 1,
        win_count: pnl >= 0 ? state.win_count + 1 : state.win_count,
        loss_count: pnl < 0 ? state.loss_count + 1 : state.loss_count,
        total_pnl_pct: state.total_pnl_pct + pnl,
        total_pnl_usdt: state.total_pnl_usdt + (action.payload.pnl_usdt || 0),
        active_signal_count: Math.max(0, state.active_signal_count - 1),
      };
    }
    case "SET_THEME":
      return state;
    default:
      return state;
  }
}

const TradingContext = createContext<TradingContextType | null>(null);

export function TradingProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, userId, userData } = useAuth();
  const [state, dispatch] = useReducer(reducer, initialState);
  const [balance, setBalance] = React.useState<BalanceInfo>(initialBalance);
  const [latestTheme, setLatestTheme] = React.useState<"profit" | "loss" | "neutral">("neutral");

  useEffect(() => {
    if (isAuthenticated && userData) {
      setBalance({
        balance: userData.balance,
        initial_balance: userData.initial_balance,
        leverage: userData.leverage,
        entry_usdt: userData.margin,
      });
    } else {
      setBalance(initialBalance);
    }
  }, [isAuthenticated, userData]);

  useEffect(() => {
    const wsHost = "web-production-e78a1.up.railway.app";
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProto}//${wsHost}/api/bot/ws`;
    let ws: WebSocket | null = null;
    let reconnectTimer: NodeJS.Timeout;

    const connect = () => {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        if (isAuthenticated && userId) {
          ws?.send(JSON.stringify({ type: "auth", user_id: userId }));
        }
      };
      ws.onmessage = (evt) => {
        try {
          const msg: WSEvent = JSON.parse(evt.data);
          handleEvent(msg);
        } catch {}
      };
      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
    };

    const handleEvent = (msg: WSEvent) => {
      switch (msg.event) {
        case "signal":
          dispatch({ type: "ADD_SIGNAL", payload: msg.data });
          break;
        case "signal_closed":
          dispatch({ type: "CLOSE_SIGNAL", payload: msg.data });
          setLatestTheme(getThemeFromPnl(msg.data.pnl_pct));
          break;
        case "signal_invalidated":
          dispatch({
            type: "UPDATE_SIGNAL",
            payload: {
              id: msg.data.id,
              status: "INVALIDATED",
              result: "INVALIDATED",
            } as Signal,
          });
          break;
        case "price_tick": {
          dispatch({
            type: "UPDATE_SIGNAL",
            payload: {
              id: msg.data.id,
              current_price: msg.data.price,
              entry_hit: msg.data.entry_hit,
            } as Signal,
          });
          break;
        }
        case "balance_update":
          setBalance(msg.data);
          break;
        case "reset_all":
          dispatch({ type: "SET_STATE", payload: initialState });
          break;
      }
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [isAuthenticated, userId]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [stateData, balanceData] = await Promise.all([
          getBotState(isAuthenticated ? userId || undefined : undefined),
          getBalance(isAuthenticated ? userId || undefined : undefined),
        ]);
        dispatch({ type: "SET_STATE", payload: stateData });
        setBalance(balanceData.data);
      } catch (e) {
        console.error("Failed to fetch initial data:", e);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [isAuthenticated, userId]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", latestTheme);
  }, [latestTheme]);

  return (
    <TradingContext.Provider value={{ state, balance, latestTheme, dispatch }}>
      {children}
    </TradingContext.Provider>
  );
}

export function useTrading() {
  const ctx = useContext(TradingContext);
  if (!ctx) throw new Error("useTrading must be used within TradingProvider");
  return ctx;
}

function getThemeFromPnl(pnl?: number | null): "profit" | "loss" | "neutral" {
  if (pnl == null) return "neutral";
  return pnl >= 0 ? "profit" : "loss";
}