/**
 * Auth state, app-wide.
 *
 * The server runs open by default, so `/me` returns the seeded admin even with
 * no token — which means `user` is almost always populated and the UI never has
 * to special-case "logged out" for the demo. When enforcement is on, a failed
 * `/me` leaves `user` null and screens can gate on that. `enforced` is read from
 * the server rather than assumed, so the frontend and backend can never disagree
 * about whether a login is actually required.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as api from "@/lib/api";
import type { AuthUser } from "@/lib/api";

interface AuthState {
  user: AuthUser | null;
  enforced: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [enforced, setEnforced] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const res = await api.getMe();
    if (res.ok) {
      setUser(res.data.user);
      setEnforced(res.data.auth_enforced);
    } else {
      setUser(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api.login(email, password);
      if (res.ok) {
        api.setToken(res.data.token);
        setUser(res.data.user);
        await refresh();
        return { ok: true };
      }
      return { ok: false, error: res.error };
    },
    [refresh],
  );

  const logout = useCallback(() => {
    api.setToken(null);
    void refresh();
  }, [refresh]);

  return (
    <AuthContext.Provider value={{ user, enforced, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
