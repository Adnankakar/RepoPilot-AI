import React, { createContext, useContext, useEffect, useState } from "react";
import {
  getMe,
  login as apiLogin,
  register as apiRegister,
  setToken,
  getToken,
  UserResponse,
} from "../api";

interface AuthContextValue {
  user: UserResponse | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser]       = useState<UserResponse | null>(null);
  // loading stays true until the stored token (if any) has been verified
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((me) => setUser(me))
      .catch(() => {
        // Expired / invalid token — clear storage so guards redirect cleanly
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  /**
   * login() — calls POST /api/auth/login, stores the token, then fetches /me.
   * Sets `user` synchronously before returning so that the calling component
   * can navigate immediately after `await login(...)` without waiting for
   * a re-render cycle. No navigate() call is made here — the page is
   * responsible for routing after login succeeds.
   */
  const login = async (email: string, password: string): Promise<void> => {
    const resp = await apiLogin(email, password);
    setToken(resp.access_token);
    const me = await getMe();
    setUser(me);
  };

  /**
   * register() — creates the account then immediately logs in.
   */
  const register = async (email: string, password: string): Promise<void> => {
    await apiRegister(email, password);
    await login(email, password);
  };

  const logout = (): void => {
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
