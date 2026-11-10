import React, { createContext, useContext, useEffect, useState } from 'react';
import { api } from '../api/endpoints';
import { getAuthToken, onUnauthorized, setAuthToken } from '../api/client';
import type { UserInfo } from '../api/types';

interface AuthContextType {
  user: UserInfo | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(() => getAuthToken());
  const [user, setUser] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const logout = (): void => {
    setAuthToken(null);
    setTokenState(null);
    setUser(null);
  };

  useEffect(() => {
    const unsubscribe = onUnauthorized(() => {
      setTokenState(null);
      setUser(null);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadUser() {
      const currentToken = getAuthToken();
      if (!currentToken) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const userInfo = await api.auth.me();
        if (isMounted) {
          setUser(userInfo);
          setTokenState(currentToken);
        }
      } catch {
        if (isMounted) {
          logout();
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadUser();

    return () => {
      isMounted = false;
    };
  }, []);

  const login = async (email: string, password: string): Promise<void> => {
    setIsLoading(true);
    try {
      const response = await api.auth.login(email, password);
      setAuthToken(response.access_token);
      setTokenState(response.access_token);
      setUser(response.user);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        logout,
        isAuthenticated: !!token && !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
