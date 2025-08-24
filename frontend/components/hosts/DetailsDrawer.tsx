import React, { useState, useEffect, useMemo } from 'react';
import { X, RefreshCw, Search } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Badge } from '../ui/badge';
import { Card, CardContent } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { toast } from 'sonner';
import { apiService, IntegrationInstance } from '../../services/api';
import { Switch } from '../ui/switch';
import { Label } from '../ui/label';

interface InventoryItem {
  type: string;
  external_id: string;
  name: string;
  attrs?: any;
  labels?: any;
}

interface InventoryResponse {
  items: InventoryItem[];
  next_page?: number;
}

interface InventorySummary {
  vm?: number;
  stack_member?: number;
  port?: number;
  [key: string]: number | undefined;
}

interface CachedData {
  data: InventoryItem[];
  timestamp: number;
  hasMore: boolean;
  nextPage?: number;
}

interface DetailsDrawerProps {
  instance: IntegrationInstance | null;
  open: boolean;
  onClose: () => void;
}

const CACHE_TTL_MS = 30 * 1000; // 30 seconds

export function DetailsDrawer({ instance, open, onClose }: DetailsDrawerProps) {
  const [activeTab, setActiveTab] = useState('vms');
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);
  
  // Cache structure: instanceId -> type -> activeOnly -> CachedData
  const [cache, setCache] = useState<Record<number, Record<string, Record<string, CachedData>>>>({});

  // Reset state when instance changes
  useEffect(() => {
    if (instance) {
      setActiveTab('vms');
      setFilter('');
      setActiveOnly(true);
    }
  }, [instance?.instance_id]);

  // Load summary when drawer opens
  useEffect(() => {
    if (open && instance) {
      loadSummary();
    }
  }, [open, instance?.instance_id]);

  // Load data when active tab or filters change
  useEffect(() => {
    if (open && instance && summary) {
      loadTabData(activeTab);
    }
  }, [activeTab, activeOnly, open, instance?.instance_id, summary]);

  const loadSummary = async () => {
    if (!instance) return;
    
    try {
      setLoading(true);
      const summaryData = await apiService.getInstanceInventorySummary(instance.instance_id);
      setSummary(summaryData);
    } catch (error) {
      console.error('Failed to load inventory summary:', error);
      toast.error('Failed to load inventory summary');
    } finally {
      setLoading(false);
    }
  };

  const getCacheKey = (type: string, activeOnlyFlag: boolean) => 
    `${type}_${activeOnlyFlag}`;

  const getCachedData = (type: string, activeOnlyFlag: boolean): CachedData | null => {
    if (!instance) return null;
    
    const instanceCache = cache[instance.instance_id];
    if (!instanceCache) return null;
    
    const typeCache = instanceCache[type];
    if (!typeCache) return null;
    
    const key = getCacheKey(type, activeOnlyFlag);
    const cachedData = typeCache[key];
    
    if (!cachedData) return null;
    
    // Check if cache is still valid
    const now = Date.now();
    if (now - cachedData.timestamp > CACHE_TTL_MS) {
      return null;
    }
    
    return cachedData;
  };

  const setCachedData = (type: string, activeOnlyFlag: boolean, data: InventoryItem[], hasMore: boolean, nextPage?: number) => {
    if (!instance) return;
    
    setCache(prev => ({
      ...prev,
      [instance.instance_id]: {
        ...prev[instance.instance_id],
        [type]: {
          ...prev[instance.instance_id]?.[type],
          [getCacheKey(type, activeOnlyFlag)]: {
            data,
            timestamp: Date.now(),
            hasMore,
            nextPage
          }
        }
      }
    }));
  };

  const loadTabData = async (type: string, page: number = 1, append: boolean = false) => {
    if (!instance) return;
    
    // For pagination, always load fresh
    if (page === 1 && !append) {
      // Check cache first
      const cached = getCachedData(type, activeOnly);
      if (cached) {
        return;
      }
    }

    try {
      if (page === 1) setLoading(true);
      
      const response = await apiService.getInstanceInventory(
        instance.instance_id,
        type === 'vms' ? 'vm' : type === 'stack' ? 'stack-member' : 'port',
        activeOnly,
        page,
        50, // page_size
        false // refresh
      );

      const newData = response.items || [];
      
      if (append) {
        // Append to existing cache
        const existing = getCachedData(type, activeOnly);
        if (existing) {
          const combined = [...existing.data, ...newData];
          setCachedData(type, activeOnly, combined, !!response.next_page, response.next_page);
        }
      } else {
        // Replace cache
        setCachedData(type, activeOnly, newData, !!response.next_page, response.next_page);
      }
    } catch (error) {
      console.error(`Failed to load ${type} data:`, error);
      toast.error(`Failed to load ${type} data`);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!instance) return;
    
    try {
      setRefreshing(true);
      
      // Clear cache for current tab
      setCache(prev => {
        const newCache = { ...prev };
        if (newCache[instance.instance_id]?.[activeTab]) {
          delete newCache[instance.instance_id][activeTab][getCacheKey(activeTab, activeOnly)];
        }
        return newCache;
      });
      
      // Reload data with refresh flag
      const response = await apiService.getInstanceInventory(
        instance.instance_id,
        activeTab === 'vms' ? 'vm' : activeTab === 'stack' ? 'stack-member' : 'port',
        activeOnly,
        1,
        50,
        true // refresh
      );

      const newData = response.items || [];
      setCachedData(activeTab, activeOnly, newData, !!response.next_page, response.next_page);
      
      toast.success('Data refreshed');
    } catch (error) {
      console.error('Failed to refresh data:', error);
      toast.error('Failed to refresh data');
    } finally {
      setRefreshing(false);
    }
  };

  const handleLoadMore = () => {
    if (!instance) return;
    
    const cached = getCachedData(activeTab, activeOnly);
    if (cached?.nextPage) {
      loadTabData(activeTab, cached.nextPage, true);
    }
  };

  // Filter data based on search input
  const getFilteredData = (type: string): InventoryItem[] => {
    if (!instance) return [];
    
    const cached = getCachedData(type, activeOnly);
    const data = cached?.data || [];
    
    if (!filter.trim()) return data;
    
    const filterLower = filter.toLowerCase().trim();
    return data.filter(item => 
      item.external_id.toLowerCase().includes(filterLower) ||
      item.name.toLowerCase().includes(filterLower)
    );
  };

  // Determine which tabs to show based on summary
  const availableTabs = useMemo(() => {
    if (!summary) return ['vms'];
    
    const tabs = [];
    
    // Always show VMs for Proxmox
    tabs.push('vms');
    
    // Show Stack only if there are stack members
    if ((summary.stack_member || 0) > 0) {
      tabs.push('stack');
    }
    
    // Always show Ports (they'll be filtered by active_only)
    tabs.push('ports');
    
    return tabs;
  }, [summary]);

  const currentData = getFilteredData(activeTab);
  const cachedInfo = instance ? getCachedData(activeTab, activeOnly) : null;

  if (!instance) return null;

  return (
    <Sheet open={open} onOpenChange={onClose}>
      <SheetContent className="w-[35%] min-w-[400px] max-w-[600px] overflow-hidden flex flex-col">
        <SheetHeader className="flex-shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-lg font-semibold">
              {instance.name} — Details
            </SheetTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-8 w-8 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </SheetHeader>

        {loading && !summary ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-sm text-muted-foreground">Loading...</div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
              <div className="flex-shrink-0 space-y-4 pb-4">
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="vms">VMs</TabsTrigger>
                  {availableTabs.includes('stack') && (
                    <TabsTrigger value="stack">Stack</TabsTrigger>
                  )}
                  <TabsTrigger value="ports">Ports</TabsTrigger>
                </TabsList>

                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                    <Input
                      placeholder="Filter by ID or name..."
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                      className="pl-9 h-8"
                    />
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="h-8"
                  >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
                  </Button>
                </div>

                {activeTab === 'ports' && (
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="active-only"
                      checked={activeOnly}
                      onCheckedChange={setActiveOnly}
                    />
                    <Label htmlFor="active-only" className="text-sm">
                      Active only
                    </Label>
                  </div>
                )}
              </div>

              <div className="flex-1 min-h-0 overflow-hidden">
                <TabsContent value="vms" className="h-full">
                  <VMsTab
                    data={currentData}
                    loading={loading}
                    hasMore={cachedInfo?.hasMore || false}
                    onLoadMore={handleLoadMore}
                  />
                </TabsContent>

                {availableTabs.includes('stack') && (
                  <TabsContent value="stack" className="h-full">
                    <StackTab
                      data={currentData}
                      loading={loading}
                      hasMore={cachedInfo?.hasMore || false}
                      onLoadMore={handleLoadMore}
                    />
                  </TabsContent>
                )}

                <TabsContent value="ports" className="h-full">
                  <PortsTab
                    data={currentData}
                    loading={loading}
                    hasMore={cachedInfo?.hasMore || false}
                    onLoadMore={handleLoadMore}
                  />
                </TabsContent>
              </div>
            </Tabs>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

// VM Tab Component
function VMsTab({ data, loading, hasMore, onLoadMore }: {
  data: InventoryItem[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
}) {
  if (loading && data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Loading VMs...
        </CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No VMs found.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-background">
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((vm) => (
              <TableRow key={vm.external_id} className="py-2">
                <TableCell className="font-mono text-sm">{vm.external_id}</TableCell>
                <TableCell>{vm.name}</TableCell>
                <TableCell>
                  <Badge variant={getStatusVariant(vm.attrs?.status)}>
                    {vm.attrs?.status || 'unknown'}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {hasMore && (
        <div className="flex-shrink-0 p-4 border-t">
          <Button onClick={onLoadMore} variant="outline" size="sm" className="w-full">
            View more
          </Button>
        </div>
      )}
    </div>
  );
}

// Stack Tab Component
function StackTab({ data, loading, hasMore, onLoadMore }: {
  data: InventoryItem[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
}) {
  if (loading && data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Loading stack members...
        </CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No stack members found.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-background">
            <TableRow>
              <TableHead>Member ID</TableHead>
              <TableHead>Model</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((member) => (
              <TableRow key={member.external_id} className="py-2">
                <TableCell className="font-mono text-sm">{member.external_id}</TableCell>
                <TableCell>{member.attrs?.model || 'Unknown'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {hasMore && (
        <div className="flex-shrink-0 p-4 border-t">
          <Button onClick={onLoadMore} variant="outline" size="sm" className="w-full">
            View more
          </Button>
        </div>
      )}
    </div>
  );
}

// Ports Tab Component  
function PortsTab({ data, loading, hasMore, onLoadMore }: {
  data: InventoryItem[];
  loading: boolean;
  hasMore: boolean;
  onLoadMore: () => void;
}) {
  if (loading && data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Loading ports...
        </CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No ports found.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-background">
            <TableRow>
              <TableHead>Label</TableHead>
              <TableHead>Port ID</TableHead>
              <TableHead>PoE</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((port) => (
              <TableRow key={port.external_id} className="py-2">
                <TableCell>{port.name}</TableCell>
                <TableCell className="font-mono text-sm">{port.external_id}</TableCell>
                <TableCell>
                  {port.attrs?.poe_enabled ? 'Y' : 'N'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {hasMore && (
        <div className="flex-shrink-0 p-4 border-t">
          <Button onClick={onLoadMore} variant="outline" size="sm" className="w-full">
            View more
          </Button>
        </div>
      )}
    </div>
  );
}

// Helper function to get status badge variant
function getStatusVariant(status?: string) {
  switch (status?.toLowerCase()) {
    case 'running':
      return 'default';
    case 'stopped':
      return 'secondary';
    case 'paused':
      return 'outline';
    default:
      return 'destructive';
  }
}