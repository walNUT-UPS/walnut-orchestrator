import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: 'light' | 'dark';
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: Theme;
  storageKey?: string;
}

export function ThemeProvider({ 
  children, 
  defaultTheme = 'system',
  storageKey = 'walnut-theme'
}: ThemeProviderProps) {
  // Initialize from localStorage synchronously to avoid flash
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem(storageKey) as Theme | null;
      return stored || defaultTheme;
    } catch {
      return defaultTheme;
    }
  });
  // Resolve initial system theme synchronously
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>(() => {
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    const root = window.document.documentElement;
    
    // Remove existing theme classes
    root.classList.remove('light', 'dark');
    
    let effectiveTheme: 'light' | 'dark' = 'dark';
    
    if (theme === 'system') {
      effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } else {
      effectiveTheme = theme;
    }
    
    root.classList.add(effectiveTheme);
    setResolvedTheme(effectiveTheme);
    
    // Store theme preference
    try { localStorage.setItem(storageKey, theme); } catch {}
  }, [theme, storageKey]);

  useEffect(() => {
    // Listen for system theme changes (browser-compatible)
    const mql = window.matchMedia('(prefers-color-scheme: dark)');

    const onChange = () => {
      if (theme === 'system') {
        const newTheme = mql.matches ? 'dark' : 'light';
        setResolvedTheme(newTheme);
        const root = document.documentElement;
        root.classList.remove('light', 'dark');
        root.classList.add(newTheme);
      }
    };

    try {
      // Modern browsers
      if (typeof mql.addEventListener === 'function') {
        mql.addEventListener('change', onChange);
        return () => mql.removeEventListener('change', onChange);
      }
      // Fallback for older Safari/Firefox
      if (typeof (mql as any).addListener === 'function') {
        (mql as any).addListener(onChange);
        return () => (mql as any).removeListener(onChange);
      }
    } catch {}

    return () => {};
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
