import React from 'react';
import { cn } from './ui/utils';

interface ProgressProps {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'inline';
  label?: string;
  unit?: string;
  threshold?: {
    warning: number;
    critical: number;
  };
  inverse?: boolean; // For metrics where higher is better (like success rate)
  className?: string;
}

export function Progress({ 
  value, 
  max = 100, 
  size = 'md', 
  variant = 'default',
  label,
  unit,
  threshold = { warning: 70, critical: 90 },
  inverse = false,
  className 
}: ProgressProps) {
  const percentage = Math.min((value / max) * 100, 100);
  
  // Determine status based on thresholds
  const getStatus = () => {
    if (inverse) {
      // For metrics where higher is better (success rate, uptime, etc.)
      if (percentage >= 90) return 'ok';
      if (percentage >= 70) return 'warn';
      return 'error';
    } else {
      // For metrics where lower is better (usage, load, etc.)
      if (percentage >= threshold.critical) return 'error';
      if (percentage >= threshold.warning) return 'warn';
      return 'ok';
    }
  };
  
  const status = getStatus();
  
  const sizeClasses = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3'
  };
  
  const statusColors = {
    ok: 'bg-status-ok',
    warn: 'bg-status-warn',
    error: 'bg-status-error'
  };
  
  if (variant === 'inline') {
    return (
      <div className={cn('flex items-center space-x-3', className)}>
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            {label && <span className="text-micro text-muted-foreground">{label}</span>}
            <span className="text-micro tabular-nums">
              {value}{unit || ''}
              {max !== 100 && ` / ${max}${unit || ''}`}
            </span>
          </div>
          <div className={cn('w-full bg-muted rounded-full', sizeClasses[size])}>
            <div
              className={cn('h-full rounded-full transition-all duration-300', statusColors[status])}
              style={{ width: `${percentage}%` }}
            />
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className={cn('space-y-2', className)}>
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-micro text-muted-foreground">{label}</span>
          <span className="text-micro tabular-nums">
            {value}{unit || ''}
            {max !== 100 && ` / ${max}${unit || ''}`}
          </span>
        </div>
      )}
      <div className={cn('w-full bg-muted rounded-full', sizeClasses[size])}>
        <div
          className={cn('h-full rounded-full transition-all duration-300', statusColors[status])}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}