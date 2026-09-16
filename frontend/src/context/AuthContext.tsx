import { createContext, useContext, useState, type ReactNode } from 'react';
import { api, setToken } from '../api/client';

interface AuthState {
  username: string;
  role: string;
  displayName: string;
}

interface AuthContextValue {
  user: AuthState | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthState | null>(() => {
    const raw = localStorage.getItem('cip_user');
    return raw ? JSON.parse(raw) : null;
  });

  async function login(username: string, password: string) {
    const res = await api.login(username, password);
    setToken(res.token);
    const authState = { username: res.username, role: res.role, displayName: res.display_name };
    localStorage.setItem('cip_user', JSON.stringify(authState));
    setUser(authState);
  }

  function logout() {
    setToken(null);
    localStorage.removeItem('cip_user');
    sessionStorage.removeItem('cip_case_context');
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
