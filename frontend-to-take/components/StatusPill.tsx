import React from 'react';
import { cn } from './ui/utils';

interface StatusPillProps {
  status: 'ok' | 'warn' | 'error' | 'neutral';
  size?: 'sm' | 'md';
  variant?: 'default' | 'solid';
  children?: React.ReactNode;
  className?: string;
}

const statusConfig = {
  ok: {
    label: 'Connected',
    color: 'bg-status-ok',
    textColor: 'text-status-ok',
    solidBg: 'bg-green-100 dark:bg-green-900/20',
    solidText: 'text-green-800 dark:text-green-300'
  },
  warn: {
    label: 'Degraded',
    color: 'bg-status-warn',
    textColor: 'text-status-warn',
    solidBg: 'bg-amber-100 dark:bg-amber-900/20',
    solidText: 'text-amber-800 dark:text-amber-300'
  },
  error: {
    label: 'Offline',
    color: 'bg-status-error',
    textColor: 'text-status-error',
    solidBg: 'bg-red-100 dark:bg-red-900/20',
    solidText: 'text-red-800 dark:text-red-300'
  },
  neutral: {
    label: 'Unknown',
    color: 'bg-status-neutral',
    textColor: 'text-status-neutral',
    solidBg: 'bg-gray-100 dark:bg-gray-800',
    solidText: 'text-gray-800 dark:text-gray-300'
  }
};

export function StatusPill({ 
  status, 
  size = 'sm', 
  variant = 'default',
  children, 
  className 
}: StatusPillProps) {
  const config = statusConfig[status];
  
  const sizeClasses = {
    sm: {
      dot: 'w-2 h-2',
      text: 'text-micro',
      padding: 'px-2.5 py-1'
    },
    md: {
      dot: 'w-2.5 h-2.5',
      text: 'text-sm',
      padding: 'px-3 py-1.5'
    }
  };
  
  const { dot, text, padding } = sizeClasses[size];
  
  if (variant === 'solid') {
    return (
      <div className={cn(
        'inline-flex items-center space-x-2 rounded-md border font-medium',
        padding,
        text,
        config.solidBg,
        config.solidText,
        className
      )}>
        <div className={cn(dot, config.color, 'rounded-full')} />
        <span>{children || config.label}</span>
      </div>
    );
  }
  
  return (
    <div className={cn(
      'inline-flex items-center space-x-2 rounded-full bg-card border border-border',
      padding,
      text,
      className
    )}>
      <div className={cn(dot, config.color, 'rounded-full')} />
      <span className={config.textColor}>
        {children || config.label}
      </span>
    </div>
  );
}