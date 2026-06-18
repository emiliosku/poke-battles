import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, authLoginUrl, type UserProfile } from "./api";

interface AuthContextValue {
  user: UserProfile | null;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  login: (provider: "github" | "google") => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setError("");
    try {
      const result = await api.auth.me();
      setUser(result.user);
    } catch (err) {
      setUser(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const logout = async () => {
    await api.auth.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        refresh,
        login: (provider) => {
          window.location.href = authLoginUrl(provider);
        },
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
