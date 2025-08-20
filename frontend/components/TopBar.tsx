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
  const [activeFilters, setActiveFilters] = useState<string[]>(['Connected']);

  const navigationItems = [
    { name: 'Overview', path: '/overview' },
    { name: 'Events', path: '/events' }, 
    { name: 'Orchestration', path: '/orchestration' },
    { name: 'Hosts', path: '/hosts' }
  ];

  const filterOptions = [
    { label: 'Connected', variant: 'default' as const },
    { label: 'Disconnected', variant: 'secondary' as const },
    { label: 'Error', variant: 'destructive' as const },
    { label: 'Proxmox', variant: 'outline' as const },
    { label: 'TrueNAS', variant: 'outline' as const },
    { label: 'Tapo', variant: 'outline' as const },
  ];

  const handleLogout = async () => {
    try {
      await logout();
      toast.success('Signed out successfully');
    } catch (error) {
      toast.error('Failed to sign out');
    }
  };

  const toggleFilter = (filter: string) => {
    setActiveFilters(prev => 
      prev.includes(filter) 
        ? prev.filter(f => f !== filter)
        : [...prev, filter]
    );
  };

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
          {/* System Status */}
          <div className="hidden sm:flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              systemStatus === 'ok' ? 'bg-green-500' : 
              systemStatus === 'warn' ? 'bg-yellow-500' : 
              'bg-red-500'
            }`}></div>
            <span className="text-sm text-muted-foreground">
              {systemStatus === 'ok' ? 'Connected' : 
               systemStatus === 'warn' ? 'Warning' : 
               'Error'}
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
              <DropdownMenuItem>
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

      {/* Search & Controls Bar */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center gap-3 px-4 py-3 border-t border-border bg-muted/20">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search name, ID, node (u)"
            className="pl-10 bg-background"
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* View Toggle */}
          <div className="flex items-center bg-background border border-border rounded-md">
            <Toggle
              pressed={viewMode === 'cards'}
              onPressedChange={() => setViewMode('cards')}
              size="sm"
              className="rounded-r-none border-r border-border data-[state=on]:bg-accent"
            >
              <LayoutGrid className="h-4 w-4" />
            </Toggle>
            <Toggle
              pressed={viewMode === 'table'}
              onPressedChange={() => setViewMode('table')}
              size="sm"
              className="rounded-l-none data-[state=on]:bg-accent"
            >
              <List className="h-4 w-4" />
            </Toggle>
          </div>

          <Separator orientation="vertical" className="h-6 hidden lg:block" />

          {/* Filters Label */}
          <div className="hidden lg:flex items-center gap-1">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Filters:</span>
          </div>

          {/* Filter Buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            {filterOptions.map((option) => (
              <Badge
                key={option.label}
                variant={activeFilters.includes(option.label) ? option.variant : "outline"}
                className="cursor-pointer hover:bg-accent transition-colors"
                onClick={() => toggleFilter(option.label)}
              >
                {option.label}
              </Badge>
            ))}
          </div>

          <Separator orientation="vertical" className="h-6 hidden lg:block" />

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="gap-2">
              <Gauge className="h-4 w-4" />
              <span className="hidden sm:inline">Thresholds</span>
            </Button>
            
            <Button variant="ghost" size="sm" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              <span className="hidden sm:inline">Alerts</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
