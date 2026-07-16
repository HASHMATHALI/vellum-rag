import React, { createContext, useState, useEffect } from 'react';
import axios from 'axios';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'user' | 'admin';
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  updateUser: (fullName: string) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchUser = async () => {
      const savedToken = localStorage.getItem('token');
      if (savedToken) {
        axios.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`;
        setToken(savedToken);
      } else {
        delete axios.defaults.headers.common['Authorization'];
        setToken(null);
      }

      try {
        const response = await axios.get('/api/auth/profile');
        setUser(response.data);
      } catch (error) {
        console.error('Session restoration failed:', error);
        // Default fallback mock guest user (e.g. backend offline/warmup)
        setUser({
          id: 1,
          email: "guest@vellum.ai",
          full_name: "Guest User",
          role: "user"
        });
        setToken(null);
      } finally {
        setLoading(false);
      }
    };
    fetchUser();
  }, []);

  const login = async (email: string, password: string) => {
    setLoading(true);
    try {
      const response = await axios.post('/api/auth/login', { email, password });
      const { access_token, user: loggedUser } = response.data;
      localStorage.setItem('token', access_token);
      axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
      setToken(access_token);
      setUser(loggedUser);
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  const register = async (email: string, password: string, fullName: string) => {
    setLoading(true);
    try {
      await axios.post('/api/auth/register', {
        email,
        password,
        full_name: fullName
      });
      // Automatically log in user after successful registration
      await login(email, password);
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    delete axios.defaults.headers.common['Authorization'];
    setToken(null);
    setUser({
      id: 1,
      email: "guest@vellum.ai",
      full_name: "Guest User",
      role: "user"
    });
  };

  const updateUser = (fullName: string) => {
    if (user) {
      setUser({ ...user, full_name: fullName });
    }
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
};
