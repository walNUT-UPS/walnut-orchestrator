import React from 'react';
import { Button } from './ui/button';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from './ThemeProvider';

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  const toggleTheme = () => {
    // Toggle between light and dark, ignore system preference for simplicity
    if (theme === 'light' || resolvedTheme === 'light') {
      setTheme('dark');
    } else {
      setTheme('light');
    }
  };

  const getIcon = () => {
    // Show the icon for the NEXT theme that will be activated
    if (theme === 'light' || resolvedTheme === 'light') {
      return <Moon className="w-4 h-4" />; // Will switch to dark
    } else {
      return <Sun className="w-4 h-4" />; // Will switch to light
    }
  };

  const getAriaLabel = () => {
    if (theme === 'light' || resolvedTheme === 'light') {
      return 'Switch to dark mode';
    } else {
      return 'Switch to light mode';
    }
  };

  return (
    <Button 
      variant="ghost" 
      size="sm"
      onClick={toggleTheme}
      data-testid="theme-toggle"
      className="min-w-[44px] min-h-[44px]"
      aria-label={getAriaLabel()}
    >
      {getIcon()}
      <span className="sr-only">{getAriaLabel()}</span>
    </Button>
  );
}