import React, { useState } from 'react';
import { Search, Settings, Bell, Moon, Sun, Menu, LayoutGrid, List, Filter, AlertTriangle, Gauge } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Toggle } from './ui/toggle';
import { Separator } from './ui/separator';

export function TopBar() {
  const [isDark, setIsDark] = useState(false);
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [activeFilters, setActiveFilters] = useState<string[]>(['Connected']);
  const [currentPage, setCurrentPage] = useState('Overview');

  const navigationItems = [
    'Overview',
    'Events', 
    'Orchestration',
    'Integrations',
    'Hosts'
  ];

  const filterOptions = [
    { label: 'Connected', variant: 'default' as const },
    { label: 'Disconnected', variant: 'secondary' as const },
    { label: 'Error', variant: 'destructive' as const },
    { label: 'Proxmox', variant: 'outline' as const },
    { label: 'TrueNAS', variant: 'outline' as const },
    { label: 'Tapo', variant: 'outline' as const },
  ];

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
              <Button
                key={item}
                variant={currentPage === item ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setCurrentPage(item)}
                className="px-4"
              >
                {item}
              </Button>
            ))}
          </nav>

          {/* Mobile Navigation Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="lg:hidden">
                <Menu className="h-4 w-4" />
                <span className="ml-2">{currentPage}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-48">
              {navigationItems.map((item) => (
                <DropdownMenuItem
                  key={item}
                  onClick={() => setCurrentPage(item)}
                  className={currentPage === item ? "bg-accent" : ""}
                >
                  {item}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Right Section - Status & Actions */}
        <div className="flex items-center gap-3">
          {/* Connected Status */}
          <div className="hidden sm:flex items-center gap-2">
            <div className="w-2 h-2 bg-green-500 rounded-full"></div>
            <span className="text-sm text-muted-foreground">Connected</span>
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
          <Button variant="ghost" size="sm" className="p-2">
            <Bell className="h-4 w-4" />
          </Button>

          {/* Settings */}
          <Button variant="ghost" size="sm" className="p-2">
            <Settings className="h-4 w-4" />
          </Button>

          {/* User Avatar */}
          <div className="w-8 h-8 bg-gray-500 rounded-full flex items-center justify-center">
            <span className="text-white text-sm">AD</span>
          </div>
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