/**
 * Auth state, app-wide.
 *
 * **What is authoritative, and what is a cache.** The bearer token in
 * `localStorage` is a handle to a server-side session row; who you are, what
 * role you hold and what you may do come from `/api/auth/me` on every load and
 * from nowhere else. Nothing here derives a permission, and nothing trusts a
 * value the client could have written — which is the point of §43's "do not
 * hard-code authentication state" and "do not trust frontend roles".
 *
 * **`can()` is UX, not security.** Every gate it drives is mirrored by a
 * `require_permission` on the route behind it, so hiding a button and refusing
 * the request are two independent decisions and only the second one is the
 * boundary. Where they disagree the server wins, visibly: the API returns 403
 * and the page says so.
 *
 * **`authed` is distinct from `user`.** The server runs open by default, so
 * `/me` returns the seeded owner even with no token — `user` is populated for
 * an anonymous visitor and the route gate must not key off it. `authed` means
 * "a token is held in this browser", which is the deliberate sign-in the
 * console sits behind. `enforced` is read from the server rather than assumed,
 * so the two can never disagree about whether a login is actually required.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import * as api from "@/lib/api";
import type {
  AuthStatus,
  AuthUser,
  Organization,
  PermissionCode,
  SessionResponse,
  SignupPayload,
} from "@/lib/api";

/** Where to send someone after they sign in, when nothing else is pending.
 *  The server supplies this per role on `/me`; this is only the fallback for
 *  the moment before the first response lands. */
const FALLBACK_HOME = "/dashboard";

export interface AuthResult {
  ok: boolean;
  error?: string;
  /** Where the server says this role belongs. Callers navigate here rather
   *  than keeping their own role → route table. */
  home?: string;
}

interface AuthState {
  user: AuthUser | null;
  org: Organization | null;
  permissions: PermissionCode[];
  /** The dashboard for the current role, from the server. */
  home: string;
  enforced: boolean;
  loading: boolean;
  /** Whether the visitor has actually authenticated in *this* browser. */
  authed: boolean;
  /** What this deployment's auth is, readable before anyone signs in. */
  status: AuthStatus | null;
  /** Does the current identity hold every one of these permissions? */
  can: (...codes: PermissionCode[]) => boolean;
  login: (email: string, password: string) => Promise<AuthResult>;
  signup: (payload: SignupPayload) => Promise<AuthResult>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Apply a session payload the caller already has (a profile edit, say)
   *  without a second round trip to /me. */
  apply: (session: SessionResponse) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [org, setOrg] = useState<Organization | null>(null);
  const [permissions, setPermissions] = useState<PermissionCode[]>([]);
  const [home, setHome] = useState<string>(FALLBACK_HOME);
  const [enforced, setEnforced] = useState(false);
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState<boolean>(() => !!api.getToken());

  const apply = useCallback((session: SessionResponse) => {
    setUser(session.user);
    setOrg(session.org);
    setPermissions(session.permissions ?? []);
    setHome(session.home || FALLBACK_HOME);
    setEnforced(session.auth_enforced);
  }, []);

  const clear = useCallback(() => {
    setUser(null);
    setOrg(null);
    setPermissions([]);
    setHome(FALLBACK_HOME);
  }, []);

  const refresh = useCallback(async () => {
    const res = await api.getMe();
    if (res.ok) {
      apply(res.data);
    } else {
      clear();
      // A token that the server no longer accepts — revoked, expired, or
      // belonging to a disabled account — is dropped here rather than left to
      // 401 every subsequent call. This is the "session expired" state made
      // real instead of shown as a string.
      if (res.status === 401) api.setToken(null);
    }
    setAuthed(!!api.getToken());
    setLoading(false);
  }, [apply, clear]);

  useEffect(() => {
    void refresh();
    void (async () => {
      const s = await api.getAuthStatus();
      if (s.ok) setStatus(s.data);
    })();
  }, [refresh]);

  /**
   * Keep two tabs in step.
   *
   * `storage` fires in *other* tabs when this one writes the token, so signing
   * out in one tab signs out in the rest instead of leaving a second window
   * rendering a console whose every request 401s. §34 asks for the other
   * direction — a new tab inherits the session — which the same key gives for
   * free.
   */
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === "aegis.token") void refresh();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refresh]);

  /**
   * Roll the token over before it expires.
   *
   * Not a keep-alive: `/api/auth/refresh` revokes the current session and opens
   * a new one, so a token that leaks is good for one TTL rather than forever.
   * Scheduled at three quarters of the lifetime, and only while a token is
   * actually held, so an anonymous visitor never makes this call.
   */
  const timer = useRef<number | null>(null);
  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    if (!authed || !status?.token_ttl_s) return;
    const delay = Math.max(60_000, status.token_ttl_s * 750);
    timer.current = window.setTimeout(() => {
      void (async () => {
        const res = await api.refreshSession();
        if (res.ok && res.data.token) {
          api.setToken(res.data.token);
          apply(res.data);
        }
      })();
    }, delay);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [authed, status?.token_ttl_s, apply]);

  const finish = useCallback(
    (res: api.ApiResult<SessionResponse>): AuthResult => {
      if (!res.ok) return { ok: false, error: res.error };
      if (res.data.token) api.setToken(res.data.token);
      apply(res.data);
      setAuthed(!!api.getToken());
      setLoading(false);
      return { ok: true, home: res.data.home || FALLBACK_HOME };
    },
    [apply],
  );

  const login = useCallback(
    async (email: string, password: string) => finish(await api.login(email, password)),
    [finish],
  );

  const signup = useCallback(
    async (payload: SignupPayload) => finish(await api.signup(payload)),
    [finish],
  );

  /**
   * Sign out.
   *
   * The server call comes first and its failure is not fatal: whatever happens
   * to the session row, this browser must stop holding a credential. A logout
   * that can fail is a logout a worried user clicks twice.
   */
  const logout = useCallback(async () => {
    try {
      await api.logoutRequest();
    } catch {
      /* the local half below is the part that must always happen */
    }
    api.setToken(null);
    setAuthed(false);
    clear();
    await refresh();
  }, [clear, refresh]);

  const can = useCallback(
    (...codes: PermissionCode[]) => codes.every((c) => permissions.includes(c)),
    [permissions],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      org,
      permissions,
      home,
      enforced,
      loading,
      authed,
      status,
      can,
      login,
      signup,
      logout,
      refresh,
      apply,
    }),
    [user, org, permissions, home, enforced, loading, authed, status, can, login, signup, logout, refresh, apply],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
