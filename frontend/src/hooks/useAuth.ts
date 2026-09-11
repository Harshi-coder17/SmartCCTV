import { useState, useCallback, useEffect } from 'react';
import type { User, UserRole } from '../types';
import { apiLogin, apiLogout, apiGetCurrentUser, setAccessToken, clearTokens } from '../api/client';

interface UseAuthReturn {
  currentUser: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: UserRole) => boolean;
}

const ROLE_HIERARCHY: Record<UserRole, number> = {
  viewer: 0,
  operator: 1,
  analyst: 2,
  admin: 3,
};

export function useAuth(): UseAuthReturn {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGetCurrentUser()
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch(() => {
        if (!cancelled) setCurrentUser(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    setIsLoading(true);
    try {
      const result = await apiLogin({ username, password });
      setAccessToken(result.access_token, result.expires_in ?? 3600);
      setCurrentUser(result.user);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // Swallow errors - clear tokens regardless
    } finally {
      clearTokens();
      setCurrentUser(null);
    }
  }, []);

  const hasRole = useCallback(
    (role: UserRole): boolean => {
      if (!currentUser) return false;
      return ROLE_HIERARCHY[currentUser.role] >= ROLE_HIERARCHY[role];
    },
    [currentUser]
  );

  return {
    currentUser,
    isAuthenticated: currentUser !== null,
    isLoading,
    error,
    login,
    logout,
    hasRole,
  };
}
