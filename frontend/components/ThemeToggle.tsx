import React from 'react';
import { Button } from './ui/button';
import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from './ThemeProvider';

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  const toggleTheme = () => {
    // Cycle: system -> light -> dark -> system
    if (theme === 'system') {
      setTheme('light');
    } else if (theme === 'light') {
      setTheme('dark');
    } else {
      setTheme('system');
    }
  };

  const getIcon = () => {
    // Show current mode indicator: system (monitor), light (sun), dark (moon)
    if (theme === 'system') return <Monitor className="w-4 h-4" />;
    return theme === 'light' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />;
  };

  const getAriaLabel = () => {
    return `Theme: ${theme} (resolved ${resolvedTheme}). Click to cycle`;
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
