"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { ReactNode } from "react";

export interface AuthUser {
  userId: string;
  name: string;
}

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Check session on mount
  useEffect(() => {
    checkSession();
  }, []);

  async function checkSession() {
    try {
      const res = await fetch("/api/auth/me");
      if (res.ok) {
        const data = await res.json();
        setUser({ userId: data.userId, name: data.name || "" });
      } else {
        setUser(null);
      }
    } catch {
      // Network error — not authenticated
    } finally {
      setIsLoading(false);
    }
  }

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      // best effort
    }
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, logout }}>
      {isLoading ? null : children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
