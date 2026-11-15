import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, setCsrfToken } from "./api";
import type { Session } from "./types";

interface Ctx {
  session: Session;
  can: (perm: string) => boolean;
  has: (feature: string) => boolean;
  refresh: () => Promise<void>;
  setUnread: (n: number) => void;
}

const SessionContext = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.get<Session>("/api/v1/session");
      setCsrfToken(s.csrf_token);
      setSession(s);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        window.location.href = "/app/signin?next=" + encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }
      setError(e instanceof Error ? e.message : "Couldn't load your account.");
    }
  }, []);

  useEffect(() => {
    refresh();
    const signedOut = () => (window.location.href = "/app/signin");
    window.addEventListener("cr:signed-out", signedOut);
    return () => window.removeEventListener("cr:signed-out", signedOut);
  }, [refresh]);

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center p-6 text-center text-stone-700 dark:text-stone-200">
        <div>
          <p className="font-semibold">{error}</p>
          <button className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white" onClick={() => location.reload()}>
            Try again
          </button>
        </div>
      </div>
    );
  }
  if (!session) {
    return <div className="min-h-screen grid place-items-center text-sm text-stone-500" role="status">Loading…</div>;
  }
  const value: Ctx = {
    session,
    can: (perm) => session.user.permissions.includes(perm),
    has: (feature) => !session.college?.plan || session.college.plan.features.includes(feature),
    refresh,
    setUnread: (n) => setSession((s) => (s ? { ...s, unread: n } : s)),
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

export const STAFF_PERMS = ["claims.review", "items.manage", "collection.verify"];
