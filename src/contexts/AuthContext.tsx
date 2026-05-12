import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { authApi, getAuthToken, getStoredUser } from "@/lib/api-client";

export interface AuthUser {
  id: string;
  email?: string;
  username?: string;
  avatar_url?: string;
}

interface Session {
  access_token: string;
  user?: AuthUser;
}

interface AuthContextValue {
  user: AuthUser | null;
  session: Session | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const token = getAuthToken();
    const stored = getStoredUser() as AuthUser | null;

    if (token && stored) {
      setUser(stored);
      setSession({ access_token: token, user: stored });
    } else {
      setUser(null);
      setSession(null);
    }

    if (!token) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    authApi.getUser().then(({ data }) => {
      if (cancelled) return;
      if (data) {
        setUser(data as AuthUser);
        setSession({
          access_token: getAuthToken() || "",
          user: data as AuthUser,
        });
      } else {
        setUser(null);
        setSession(null);
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const signOut = useCallback(async () => {
    await authApi.logout();
    setUser(null);
    setSession(null);
    navigate("/", { replace: true });
  }, [navigate]);

  const refreshUser = useCallback(async () => {
    const { data } = await authApi.getUser();
    if (data) {
      setUser(data as AuthUser);
      setSession({ access_token: getAuthToken() || "", user: data as AuthUser });
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      session,
      loading,
      signOut,
      refreshUser,
    }),
    [user, session, loading, signOut, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
