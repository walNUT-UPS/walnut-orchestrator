import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { StatusPill } from './StatusPill';
import { Progress } from './Progress';
import { cn } from './ui/utils';

interface MetricData {
  label: string;
  value: number;
  max: number;
  unit?: string;
  status?: 'ok' | 'warn' | 'error';
  inverse?: boolean; // For metrics where higher is better
}

interface MetricCardProps {
  title: string;
  status: 'ok' | 'warn' | 'error';
  metrics: MetricData[];
  meta?: {
    uptime?: string;
    lastUpdate?: string;
    driver?: string;
  };
  size?: 'M' | 'L';
  onClick?: () => void;
}

export function MetricCard({ 
  title, 
  status, 
  metrics, 
  meta, 
  size = 'M',
  onClick 
}: MetricCardProps) {
  const cardHeight = size === 'M' ? 'min-h-[var(--card-height-m)]' : 'min-h-[var(--card-height-l)]';
  
  return (
    <Card 
      className={cn(
        'card-standard hover:bg-accent/10 transition-all cursor-pointer',
        cardHeight,
        size === 'L' ? 'col-span-2' : '',
        'focus-ring'
      )}
      onClick={onClick}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.();
        }
      }}
    >
      <CardHeader className="pb-3 p-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-title">{title}</CardTitle>
          <StatusPill status={status} size="sm" />
        </div>
      </CardHeader>
      
      <CardContent className="p-4 pt-0 flex flex-col justify-between flex-1">
        {/* Metrics with Progress Bars */}
        <div className="space-y-3">
          {metrics.map((metric, index) => (
            <Progress
              key={index}
              value={metric.value}
              max={metric.max}
              label={metric.label}
              unit={metric.unit}
              variant="inline"
              size="md"
              threshold={{ warning: 70, critical: 90 }}
              inverse={metric.inverse}
            />
          ))}
        </div>

        {/* Meta Information */}
        {meta && (
          <div className="grid grid-cols-3 gap-4 pt-4 mt-auto border-t border-border">
            {meta.uptime && (
              <div className="text-micro">
                <div className="text-muted-foreground">Uptime</div>
                <div className="font-medium text-foreground tabular-nums">{meta.uptime}</div>
              </div>
            )}
            {meta.lastUpdate && (
              <div className="text-micro">
                <div className="text-muted-foreground">Last Update</div>
                <div className="font-medium text-foreground tabular-nums">{meta.lastUpdate}</div>
              </div>
            )}
            {meta.driver && (
              <div className="text-micro">
                <div className="text-muted-foreground">Driver</div>
                <div className="font-medium text-foreground">{meta.driver}</div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}