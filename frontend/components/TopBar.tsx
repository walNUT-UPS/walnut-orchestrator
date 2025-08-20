import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Search, Settings, Bell, Moon, Sun, Menu, LayoutGrid, List, Filter, AlertTriangle, Gauge, LogOut, User } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Avatar, AvatarFallback } from './ui/avatar';
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Toggle } from './ui/toggle';
import { Separator } from './ui/separator';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import { toast } from 'sonner';

interface TopBarProps {
  activeTab: string;
  systemStatus: 'ok' | 'warn' | 'error';
  alertCount?: number;
}

export function TopBar({ activeTab, systemStatus, alertCount = 0 }: TopBarProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [isDark, setIsDark] = useState(() => {
    return document.documentElement.classList.contains('dark');
  });
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters] = useState<string[]>([]);
  const [lastHealthAt, setLastHealthAt] = useState<Date | null>(null);

  const navigationItems = [
    { name: 'Overview', path: '/overview' },
    { name: 'Events', path: '/events' }, 
    { name: 'Orchestration', path: '/orchestration' },
    { name: 'Hosts', path: '/hosts' }
  ];

  // Filters are now handled only on the Events screen

  const handleLogout = async () => {
    try {
      await logout();
      toast.success('Signed out successfully');
    } catch (error) {
      toast.error('Failed to sign out');
    }
  };

  const toggleFilter = (_filter: string) => {};

  const toggleTheme = () => {
    setIsDark(!isDark);
    document.documentElement.classList.toggle('dark');
  };

  // Get current page from location
  const getCurrentPage = () => {
    const currentItem = navigationItems.find(item => item.path === location.pathname);
    return currentItem?.name || 'Overview';
  };

  const currentPage = getCurrentPage();

  // Poll system health to determine connection freshness
  React.useEffect(() => {
    let mounted = true;
    async function fetchHealth() {
      try {
        const health = await apiService.getSystemHealth();
        if (mounted && health?.timestamp) {
          setLastHealthAt(new Date(health.timestamp));
        }
      } catch (_) {
        // ignore
      }
    }
    fetchHealth();
    const id = setInterval(fetchHealth, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  const isFresh = React.useMemo(() => {
    if (!lastHealthAt) return false;
    const diff = Date.now() - lastHealthAt.getTime();
    return diff <= 60_000; // 1 minute
  }, [lastHealthAt]);
  
  return (
    <div className="w-full bg-background border-b border-border">
      {/* Main Header */}
      <div className="flex items-center justify-between px-4 py-3">
        {/* Left Section - Logo & Navigation */}
        <div className="flex items-center gap-6">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-orange-500 rounded-full flex items-center justify-center">
              <span className="text-white text-sm font-medium">w</span>
            </div>
            <span className="font-medium">walNUT</span>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex items-center gap-1">
            {navigationItems.map((item) => (
              <Link
                key={item.name}
                to={item.path}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  currentPage === item.name 
                    ? 'bg-secondary text-secondary-foreground' 
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
              >
                {item.name}
              </Link>
            ))}
          </nav>

          {/* Mobile Navigation Dropdown */}
          <div className="relative">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button data-testid="mobile-nav-trigger" variant="ghost" size="sm" className="lg:hidden">
                  <Menu className="h-4 w-4" />
                  <span className="ml-2">{currentPage}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent 
                align="start" 
                side="bottom" 
                sideOffset={4}
                className="w-48"
              >
              {navigationItems.map((item) => (
                <DropdownMenuItem
                  key={item.name}
                  asChild
                  className={currentPage === item.name ? "bg-accent" : ""}
                >
                  <Link to={item.path} className="w-full">
                    {item.name}
                  </Link>
                </DropdownMenuItem>
              ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Right Section - Status & Actions */}
        <div className="flex items-center gap-3">
          {/* System Status (connected if backend health < 1m old) */}
          <div className="hidden sm:flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${isFresh ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className={`text-sm ${isFresh ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
              {isFresh ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleTheme}
            className="p-2"
          >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>

          {/* Notifications */}
          <Button 
            variant="ghost" 
            size="sm" 
            className="p-2 relative"
            onClick={() => alert('Notifications panel not yet implemented')}
          >
            <Bell className="h-4 w-4" />
            {alertCount > 0 && (
              <Badge 
                variant="destructive" 
                className="absolute -top-1 -right-1 h-4 w-4 p-0 text-xs"
              >
                {alertCount}
              </Badge>
            )}
          </Button>

          {/* Settings */}
          <Link to="/settings">
            <Button variant="ghost" size="sm" className="p-2">
              <Settings className="h-4 w-4" />
            </Button>
          </Link>

          {/* User Avatar & Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button data-testid="avatar-menu-trigger" variant="ghost" size="sm" className="p-1">
                <Avatar className="w-8 h-8">
                  <AvatarFallback className="bg-gray-500 text-white text-sm">
                    {user?.email?.slice(0, 2).toUpperCase() || 'AD'}
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent 
              align="end" 
              side="bottom"
              sideOffset={4}
              className="w-56"
            >
              <div className="flex items-center space-x-2 p-2">
                <Avatar className="w-8 h-8">
                  <AvatarFallback className="bg-gray-500 text-white text-sm">
                    {user?.email?.slice(0, 2).toUpperCase() || 'AD'}
                  </AvatarFallback>
                </Avatar>
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium">{user?.email || 'Admin User'}</p>
                  <p className="text-xs text-muted-foreground">Administrator</p>
                </div>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => alert('Profile not yet implemented')}>
                <User className="w-4 h-4 mr-2" />
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link to="/settings">
                  <Settings className="w-4 h-4 mr-2" />
                  Account Settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="w-4 h-4 mr-2" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* TopBar secondary controls removed — pages own their own toolbars */}
    </div>
  );
}
