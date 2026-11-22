import React, { createContext, useContext, useEffect } from 'react';

// The app has a single dark theme (gray / silver / yellow). Light mode was removed on purpose.
type Theme = 'dark';

interface ThemeContextType {
  theme: Theme;
}

const ThemeContext = createContext<ThemeContextType>({ theme: 'dark' });

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  useEffect(() => {
    document.documentElement.classList.add('dark');
    try {
      localStorage.removeItem('theme'); // drop the old light/dark preference
    } catch {
      /* storage may be unavailable */
    }
  }, []);

  return <ThemeContext.Provider value={{ theme: 'dark' }}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => useContext(ThemeContext);
