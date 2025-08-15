import React from 'react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Avatar, AvatarFallback } from './ui/avatar';
import { StatusPill } from './StatusPill';
import { ThemeToggle } from './ThemeToggle';
import { Settings, Bell, ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface TopBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  systemStatus: 'ok' | 'warn' | 'error';
  alertCount?: number;
}

const tabs = [
  'Overview',
  'Events', 
  'Orchestration',
  'Integrations',
  'Hosts',
  'Settings'
];

export function TopBar({ activeTab, onTabChange, systemStatus, alertCount = 0 }: TopBarProps) {
  return (
    <div className="w-full bg-card border-b border-border">
      <div className="container-grid">
        <div className="flex items-center justify-between h-16">
          {/* Left: Logo + Navigation */}
          <div className="flex items-center space-x-8">
            <div className="flex items-center space-x-2">
              <div className="w-6 h-6 bg-status-warn rounded-full flex items-center justify-center">
                <span className="text-xs font-bold text-black">🌰</span>
              </div>
              <span className="text-display">walNUT</span>
            </div>
            
            <nav className="flex items-center space-x-2">
              {tabs.map((tab) => (
                <button
                  key={tab}
                  onClick={() => onTabChange(tab)}
                  className={`px-4 py-2 text-sm font-medium rounded-md transition-colors focus-ring ${
                    activeTab === tab
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </nav>
          </div>

          {/* Right: Status, Theme, Alerts, Settings, User */}
          <div className="flex items-center space-x-2">
            <StatusPill status={systemStatus} />
            
            <ThemeToggle />
            
            <Button variant="ghost" size="sm" className="relative">
              <Bell className="w-4 h-4" />
              {alertCount > 0 && (
                <Badge 
                  variant="destructive" 
                  className="absolute -top-1 -right-1 h-4 w-4 p-0 text-xs"
                >
                  {alertCount}
                </Badge>
              )}
            </Button>

            <Button variant="ghost" size="sm">
              <Settings className="w-4 h-4" />
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="flex items-center space-x-2">
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="bg-status-neutral text-white text-xs">
                      AD
                    </AvatarFallback>
                  </Avatar>
                  <ChevronDown className="w-3 h-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Profile</DropdownMenuItem>
                <DropdownMenuItem>Account Settings</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem>Sign Out</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </div>
    </div>
  );
}