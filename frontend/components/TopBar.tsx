import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Avatar, AvatarFallback } from './ui/avatar';
import { StatusPill } from './StatusPill';
import { ThemeToggle } from './ThemeToggle';
import { Settings, Bell, ChevronDown, LogOut, User } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { useAuth } from '../contexts/AuthContext';
import { toast } from 'sonner';

interface TopBarProps {
  activeTab: string;
  systemStatus: 'ok' | 'warn' | 'error';
  alertCount?: number;
}

const tabs = [
  { name: 'Overview', path: '/overview' },
  { name: 'Events', path: '/events' }, 
  { name: 'Orchestration', path: '/orchestration' },
  { name: 'Integrations', path: '/integrations' },
  { name: 'Hosts', path: '/hosts' },
  { name: 'Settings', path: '/settings' }
];

export function TopBar({ activeTab, systemStatus, alertCount = 0 }: TopBarProps) {
  const { user, logout } = useAuth();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await logout();
      toast.success('Signed out successfully');
    } catch (error) {
      toast.error('Failed to sign out');
    }
  };
  return (
    <div className="w-full bg-card border-b border-border">
      <div className="px-4 lg:px-6">
        <div className="flex items-center justify-between h-16">
          {/* Left: Logo + Navigation */}
          <div className="flex items-center space-x-2 lg:space-x-8">
            <div className="flex items-center space-x-2">
              <div className="w-6 h-6 bg-status-warn rounded-full flex items-center justify-center">
                <span className="text-xs font-bold text-black">🌰</span>
              </div>
              <span className="text-display">walNUT</span>
            </div>
            
            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center space-x-4">
              {tabs.map((tab) => {
                const isActive = location.pathname === tab.path;
                return (
                  <Link
                    key={tab.name}
                    to={tab.path}
                    className={`px-5 py-2.5 text-sm font-medium rounded-md transition-colors focus-ring ${
                      isActive
                        ? 'bg-accent text-accent-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                    }`}
                    aria-label={`Navigate to ${tab.name}`}
                    aria-current={isActive ? 'page' : undefined}
                  >
                    {tab.name}
                  </Link>
                );
              })}
            </nav>

            {/* Mobile Navigation Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild className="lg:hidden">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="min-w-[44px] min-h-[44px]"
                  aria-label="Open navigation menu"
                >
                  <span className="text-sm font-medium">{activeTab}</span>
                  <ChevronDown className="w-4 h-4 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent 
                align="start" 
                side="bottom"
                sideOffset={8}
                alignOffset={0}
                sticky="always"
                className="w-56"
              >
                {tabs.map((tab) => {
                  const isActive = location.pathname === tab.path;
                  return (
                    <DropdownMenuItem
                      key={tab.name}
                      asChild
                      className={isActive ? 'bg-accent' : ''}
                    >
                      <Link 
                        to={tab.path}
                        className="w-full"
                        aria-label={`Navigate to ${tab.name}`}
                        aria-current={isActive ? 'page' : undefined}
                      >
                        {tab.name}
                      </Link>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          {/* Right: Status, Theme, Alerts, Settings, User */}
          <div className="flex items-center space-x-2 lg:space-x-3">
            <StatusPill status={systemStatus} />
            
            <ThemeToggle />
            
            <Button 
              variant="ghost" 
              size="sm" 
              className="relative min-w-[44px] min-h-[44px]"
              aria-label={`Notifications${alertCount > 0 ? ` (${alertCount} alerts)` : ''}`}
            >
              <Bell className="w-4 h-4" />
              {alertCount > 0 && (
                <Badge 
                  variant="destructive" 
                  className="absolute -top-1 -right-1 h-4 w-4 p-0 text-xs"
                  aria-hidden="true"
                >
                  {alertCount}
                </Badge>
              )}
            </Button>

            <Button 
              variant="ghost" 
              size="sm" 
              className="hidden sm:flex min-w-[44px] min-h-[44px]"
              aria-label="Quick settings"
            >
              <Settings className="w-4 h-4" />
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="flex items-center space-x-2 min-w-[44px] min-h-[44px]"
                  aria-label="User menu"
                >
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="bg-status-neutral text-white text-xs">
                      {user?.email?.slice(0, 2).toUpperCase() || 'AD'}
                    </AvatarFallback>
                  </Avatar>
                  <ChevronDown className="w-3 h-3 hidden sm:block" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="flex items-center space-x-2 p-2">
                  <Avatar className="w-8 h-8">
                    <AvatarFallback className="bg-status-neutral text-white text-xs">
                      {user?.email?.slice(0, 2).toUpperCase() || 'AD'}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">{user?.email || 'Admin User'}</p>
                    <p className="text-xs text-muted-foreground">Administrator</p>
                  </div>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <User className="w-4 h-4 mr-2" />
                  Profile
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Settings className="w-4 h-4 mr-2" />
                  Account Settings
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
      </div>
    </div>
  );
}