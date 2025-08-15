import React from 'react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { ToggleGroup, ToggleGroupItem } from './ui/toggle-group';
import { Tag } from './Tag';
import { Search, Grid3X3, Table, BarChart3, Settings2, AlertTriangle, X } from 'lucide-react';
import { cn } from './ui/utils';

interface SecondaryToolbarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  viewMode: 'cards' | 'table';
  onViewModeChange: (mode: 'cards' | 'table') => void;
  activeFilters: string[];
  onFilterToggle: (filter: string) => void;
  availableFilters: string[];
  showCharts?: boolean;
  onChartsToggle?: () => void;
}

export function SecondaryToolbar({
  searchValue,
  onSearchChange,
  viewMode,
  onViewModeChange,
  activeFilters,
  onFilterToggle,
  availableFilters,
  showCharts = false,
  onChartsToggle
}: SecondaryToolbarProps) {
  return (
    <div className="w-full bg-card border-b border-border">
      <div className="container-grid py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4 flex-1">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search name, ID, node (use ';' for OR)"
                value={searchValue}
                onChange={(e) => onSearchChange(e.target.value)}
                className="pl-10 h-8 bg-background focus-ring"
              />
            </div>

            {/* View Mode Toggle */}
            <ToggleGroup 
              type="single" 
              value={viewMode} 
              onValueChange={(value) => value && onViewModeChange(value as 'cards' | 'table')}
              className="border border-border rounded-md"
            >
              <ToggleGroupItem value="cards" size="sm" className="h-8">
                <Grid3X3 className="w-4 h-4" />
                <span className="ml-1 text-micro">Cards</span>
              </ToggleGroupItem>
              <ToggleGroupItem value="table" size="sm" className="h-8">
                <Table className="w-4 h-4" />
                <span className="ml-1 text-micro">Table</span>
              </ToggleGroupItem>
            </ToggleGroup>

            {/* Filter Pills */}
            <div className="flex items-center space-x-2 flex-wrap">
              <span className="text-micro text-muted-foreground">Filters:</span>
              {availableFilters.map((filter) => {
                const isActive = activeFilters.includes(filter);
                return (
                  <Button
                    key={filter}
                    variant={isActive ? "default" : "outline"}
                    size="sm"
                    onClick={() => onFilterToggle(filter)}
                    className={cn(
                      "h-8 text-xs focus-ring",
                      isActive && "bg-primary text-primary-foreground"
                    )}
                  >
                    {filter}
                    {isActive && (
                      <X className="w-3 h-3 ml-1" />
                    )}
                  </Button>
                );
              })}
            </div>
          </div>

          {/* Right side actions */}
          <div className="flex items-center space-x-2">
            {onChartsToggle && (
              <Button
                variant={showCharts ? "default" : "outline"}
                size="sm"
                className="h-8 focus-ring"
                onClick={onChartsToggle}
              >
                <BarChart3 className="w-4 h-4 mr-1" />
                <span className="text-micro">Charts</span>
              </Button>
            )}
            
            <Button variant="outline" size="sm" className="h-8 focus-ring">
              <Settings2 className="w-4 h-4 mr-1" />
              <span className="text-micro">Thresholds</span>
            </Button>
            
            <Button variant="outline" size="sm" className="h-8 focus-ring">
              <AlertTriangle className="w-4 h-4 mr-1" />
              <span className="text-micro">Alerts</span>
            </Button>
          </div>
        </div>

        {/* Active Filters Summary */}
        {activeFilters.length > 0 && (
          <div className="flex items-center space-x-2 mt-3 pt-3 border-t border-border flex-wrap gap-2">
            <span className="text-micro text-muted-foreground">Active:</span>
            {activeFilters.map((filter) => (
              <Tag 
                key={filter} 
                variant="neutral"
                size="sm"
                className="flex items-center space-x-1"
              >
                <span>{filter}</span>
                <button 
                  onClick={() => onFilterToggle(filter)}
                  className="ml-1 hover:bg-destructive/20 rounded-full p-0.5 focus-ring"
                  aria-label={`Remove ${filter} filter`}
                >
                  <X className="w-3 h-3" />
                </button>
              </Tag>
            ))}
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => activeFilters.forEach(filter => onFilterToggle(filter))}
              className="h-6 text-xs text-muted-foreground hover:text-foreground focus-ring"
            >
              Clear all
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}