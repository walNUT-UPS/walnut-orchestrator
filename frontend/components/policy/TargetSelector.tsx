import React from 'react';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Card, CardContent } from '../ui/card';
import { RefreshCw, Search } from 'lucide-react';
import { apiService } from '../../services/api';
import type { TargetSpec, Host, InventoryItem } from './types';

export function TargetSelector({
  targets,
  hosts,
  inventory,
  refreshingInventory,
  onChange,
  onRefreshInventory
}: {
  targets: TargetSpec;
  hosts: Host[];
  inventory: InventoryItem[];
  refreshingInventory: boolean;
  onChange: (targets: TargetSpec) => void;
  onRefreshInventory: (hostId: string) => void;
}) {
  const [searchQuery, setSearchQuery] = React.useState('');
  const [expandedTargets, setExpandedTargets] = React.useState<string[]>([]);
  const [targetTypes, setTargetTypes] = React.useState<string[]>([]);

  const selectedHost = hosts.find(h => h.id === targets.host_id);

  React.useEffect(() => {
    // Get unique target types from inventory
    if (inventory.length > 0) {
      const types = Array.from(new Set(inventory.map(item => item.type)));
      setTargetTypes(types);
    }
  }, [inventory]);

  React.useEffect(() => {
    // Parse selector value to show expanded targets
    if (targets.selector.value && targets.selector.mode === 'range') {
      try {
        const expanded = parseRangeSelector(targets.selector.value, inventory);
        setExpandedTargets(expanded);
      } catch {
        setExpandedTargets([]);
      }
    } else if (targets.selector.value && targets.selector.mode === 'list') {
      const items = targets.selector.value.split(',').map(s => s.trim());
      setExpandedTargets(items);
    } else {
      setExpandedTargets([]);
    }
  }, [targets.selector, inventory]);

  const parseRangeSelector = (rangeString: string, inventory: InventoryItem[]): string[] => {
    // Basic range parsing for VM IDs like "104,204,311-318"
    const parts = rangeString.split(',');
    const result: string[] = [];
    
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed.includes('-')) {
        const [start, end] = trimmed.split('-').map(s => parseInt(s.trim()));
        if (!isNaN(start) && !isNaN(end)) {
          for (let i = start; i <= end; i++) {
            result.push(i.toString());
          }
        }
      } else {
        result.push(trimmed);
      }
    }
    
    return result;
  };

  const getMatchingInventory = () => {
    if (!searchQuery) return inventory.filter(item => targets.target_type ? item.type === targets.target_type : true);
    
    return inventory.filter(item => {
      if (targets.target_type && item.type !== targets.target_type) return false;
      
      const searchLower = searchQuery.toLowerCase();
      return (
        item.name.toLowerCase().includes(searchLower) ||
        item.id.toLowerCase().includes(searchLower) ||
        Object.values(item.labels || {}).some(label => 
          String(label).toLowerCase().includes(searchLower)
        )
      );
    });
  };

  const addToSelector = (item: InventoryItem) => {
    const currentValue = targets.selector.value || '';
    const newValue = currentValue ? `${currentValue},${item.id}` : item.id;
    
    onChange({
      ...targets,
      selector: {
        ...targets.selector,
        mode: 'list',
        value: newValue
      }
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <Label>Host</Label>
          <select
            value={targets.host_id}
            onChange={(e) => onChange({ ...targets, host_id: e.target.value, target_type: '', selector: { mode: 'list', value: '' } })}
            className="w-full p-2 border rounded text-sm"
          >
            <option value="">Select host</option>
            {hosts.map(host => (
              <option key={host.id} value={host.id}>{host.name}</option>
            ))}
          </select>
          {selectedHost && (
            <div className="text-xs text-muted-foreground mt-1">
              {selectedHost.ip_address} • {selectedHost.os_type}
            </div>
          )}
        </div>
        
        <div>
          <Label>Target Type</Label>
          <select
            value={targets.target_type}
            onChange={(e) => onChange({ ...targets, target_type: e.target.value, selector: { mode: 'list', value: '' } })}
            className="w-full p-2 border rounded text-sm"
            disabled={!targets.host_id}
          >
            <option value="">Select type</option>
            {targetTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>
      </div>

      {targets.host_id && (
        <div className="flex items-center justify-between">
          <Label>Inventory</Label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRefreshInventory(targets.host_id)}
            disabled={refreshingInventory}
          >
            <RefreshCw className={`w-3 h-3 mr-1 ${refreshingInventory ? 'animate-spin' : ''}`} />
            {refreshingInventory ? 'Refreshing...' : 'Refresh'}
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div>
          <Label>Selector Mode</Label>
          <div className="flex gap-2 mt-1">
            {['list', 'range', 'query'].map((mode) => (
              <Button
                key={mode}
                variant={targets.selector.mode === mode ? 'default' : 'outline'}
                size="sm"
                onClick={() => onChange({ ...targets, selector: { ...targets.selector, mode: mode as any } })}
              >
                {mode}
              </Button>
            ))}
          </div>
        </div>
        
        <div className="lg:col-span-2">
          <Label>Selector Value</Label>
          <Input
            value={targets.selector.value}
            onChange={(e) => onChange({ ...targets, selector: { ...targets.selector, value: e.target.value } })}
            placeholder={
              targets.selector.mode === 'range' ? '104,204,311-318 or 1/1-1/4,1/A1-1/B4' :
              targets.selector.mode === 'list' ? 'comma,separated,ids' :
              'query expression'
            }
          />
          {expandedTargets.length > 0 && (
            <div className="mt-1">
              <Badge variant="secondary" className="text-xs">
                Expands to {expandedTargets.length} targets
              </Badge>
            </div>
          )}
        </div>
      </div>

      {inventory.length > 0 && (
        <Card>
          <CardContent className="p-4">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Search className="w-4 h-4 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search inventory..."
                  className="flex-1"
                />
              </div>
              
              <div className="max-h-64 overflow-auto space-y-1">
                {getMatchingInventory().slice(0, 50).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between p-2 border rounded hover:bg-muted/50 cursor-pointer"
                    onClick={() => addToSelector(item)}
                  >
                    <div className="flex-1">
                      <div className="font-medium text-sm">{item.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {item.id} • {item.type}
                        {item.labels && Object.keys(item.labels).length > 0 && (
                          <span className="ml-2">
                            {Object.entries(item.labels).slice(0, 2).map(([k, v]) => (
                              <Badge key={k} variant="outline" className="text-xs ml-1">
                                {k}:{String(v)}
                              </Badge>
                            ))}
                          </span>
                        )}
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" className="ml-2">
                      Add
                    </Button>
                  </div>
                ))}
              </div>
              
              {getMatchingInventory().length === 0 && (
                <div className="text-center text-muted-foreground py-4">
                  {inventory.length === 0 ? 'No inventory available' : 'No matching items found'}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

