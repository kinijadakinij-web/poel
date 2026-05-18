"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import { login as apiLogin, getMe, removeToken, getToken, setToken } from "@/lib/api";

export interface UserAccount {
  id: string;
  username: string;
  is_admin: boolean;
  leverage: number;
  margin: number;
  balance: number;
  initial_balance: number;
}

interface AuthContextType {
  isAuthenticated: boolean;
  username: string | null;
  userId: string | null;
  userData: UserAccount | null;
  isAdmin: boolean;
  login: (
    username: string,
    passkey: string
  ) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  refreshUser: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [userData, setUserData] = useState<UserAccount | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  const refreshUser = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setIsAuthenticated(false);
      setUsername(null);
      setUserId(null);
      setUserData(null);
      setIsAdmin(false);
      return;
    }

    try {
      const data = await getMe();
      if (data && data.id) {
        setIsAuthenticated(true);
        setUsername(data.username);
        setUserId(data.id);
        setUserData(data);
        setIsAdmin(data.is_admin);
        if (typeof window !== "undefined") {
          localStorage.setItem("agent-x-user", JSON.stringify(data));
        }
      } else {
        throw new Error("Invalid user data");
      }
    } catch {
      removeToken();
      setIsAuthenticated(false);
      setUsername(null);
      setUserId(null);
      setUserData(null);
      setIsAdmin(false);
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("agent-x-user");
      const token = getToken();
      if (saved && token) {
        try {
          const parsed = JSON.parse(saved);
          setUserData(parsed);
          setUsername(parsed.username);
          setUserId(parsed.id);
          setIsAdmin(parsed.is_admin);
          setIsAuthenticated(true);
        } catch {
          localStorage.removeItem("agent-x-user");
        }
      }
    }
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (username: string, passkey: string) => {
      try {
        const data = await apiLogin({ username, passkey });
        if (data.success) {
          setToken(data.token);                    // ← FIX: simpan token
          setIsAuthenticated(true);
          setUsername(data.user.username);
          setUserId(data.user.id);
          setUserData(data.user);
          setIsAdmin(data.user.is_admin);
          if (typeof window !== "undefined") {
            localStorage.setItem("agent-x-user", JSON.stringify(data.user));
          }
          return { success: true };
        }
        return { success: false, error: data.detail || "Login failed" };
      } catch (e: any) {
        return { success: false, error: e.message || "Network error" };
      }
    },
    []
  );

  const logout = useCallback(() => {
    removeToken();
    if (typeof window !== "undefined") {
      localStorage.removeItem("agent-x-user");
    }
    setIsAuthenticated(false);
    setUsername(null);
    setUserId(null);
    setUserData(null);
    setIsAdmin(false);
    window.location.href = "/";
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        username,
        userId,
        userData,
        isAdmin,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}