import React, { useState } from 'react';
import { cn } from './ui/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';
import { formatTimeLocal } from '../utils/time';

export interface TimelineSegment {
  start: Date;
  end: Date;
  status: 'online' | 'on-battery' | 'critical' | 'no-data';
  meta?: {
    batteryPercent?: number;
    inputVoltage?: number;
    loadWatts?: number;
  };
}

interface TimelineProps {
  segments: TimelineSegment[];
  duration?: '6h' | '12h' | '24h';
  height?: number;
  showLegend?: boolean;
  className?: string;
  onZoomChange?: (duration: '6h' | '12h' | '24h') => void;
}

const statusConfig = {
  online: {
    label: 'Online',
    color: 'bg-status-ok',
    pattern: ''
  },
  'on-battery': {
    label: 'On Battery',
    color: 'bg-status-warn',
    pattern: ''
  },
  critical: {
    label: 'Critical',
    color: 'bg-status-error',
    pattern: 'bg-stripe-red'
  },
  'no-data': {
    label: 'No Data',
    color: 'bg-gray-300 dark:bg-gray-600',
    pattern: ''
  }
};

export function Timeline({ 
  segments, 
  duration = '24h', 
  height = 16,
  showLegend = true,
  className,
  onZoomChange 
}: TimelineProps) {
  const [hoveredSegment, setHoveredSegment] = useState<TimelineSegment | null>(null);

  const durationHours = {
    '6h': 6,
    '12h': 12,
    '24h': 24
  }[duration];

  const now = new Date();
  const startTime = new Date(now.getTime() - durationHours * 60 * 60 * 1000);
  const totalDuration = now.getTime() - startTime.getTime();

  const getSegmentPosition = (segment: TimelineSegment) => {
    const segmentStart = Math.max(segment.start.getTime(), startTime.getTime());
    const segmentEnd = Math.min(segment.end.getTime(), now.getTime());
    
    const left = ((segmentStart - startTime.getTime()) / totalDuration) * 100;
    const width = ((segmentEnd - segmentStart) / totalDuration) * 100;
    
    return { left: `${left}%`, width: `${width}%` };
  };

  const formatTooltipTime = (date: Date) => formatTimeLocal(date);

  const formatTooltipContent = (segment: TimelineSegment) => {
    const { status, meta } = segment;
    const config = statusConfig[status];
    
    return (
      <div className="space-y-1">
        <div className="font-medium">{config.label}</div>
        <div className="text-xs text-muted-foreground">
          {formatTooltipTime(segment.start)} - {formatTooltipTime(segment.end)}
        </div>
        {meta && (
          <div className="text-xs space-y-0.5">
            {meta.batteryPercent && <div>Battery: {meta.batteryPercent}%</div>}
            {meta.inputVoltage && <div>Input: {meta.inputVoltage}V</div>}
            {meta.loadWatts && <div>Load: {meta.loadWatts}W</div>}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header with zoom controls */}
      <div className="flex items-center justify-between">
        <h3 className="text-title">Line Power Status - Last {duration}</h3>
        <div className="flex items-center space-x-1 bg-muted p-1 rounded-md">
          {(['6h', '12h', '24h'] as const).map((option) => (
            <button
              key={option}
              onClick={() => onZoomChange?.(option)}
              className={cn(
                'px-2 py-1 text-xs rounded-sm transition-colors',
                duration === option
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      {/* Timeline bar */}
      <div className="space-y-2">
        <TooltipProvider>
          <div
            className="relative bg-muted rounded-sm overflow-hidden"
            style={{ height: `${height}px` }}
          >
            {segments.map((segment, index) => {
              const position = getSegmentPosition(segment);
              const config = statusConfig[segment.status];
              
              return (
                <Tooltip key={index}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        'absolute top-0 h-full transition-all duration-200 hover:brightness-110 cursor-pointer',
                        config.color,
                        config.pattern
                      )}
                      style={position}
                      onMouseEnter={() => setHoveredSegment(segment)}
                      onMouseLeave={() => setHoveredSegment(null)}
                    />
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    {formatTooltipContent(segment)}
                  </TooltipContent>
                </Tooltip>
              );
            })}
            
            {/* Now marker */}
            <div className="absolute top-0 right-0 w-0.5 h-full bg-foreground opacity-50" />
          </div>
        </TooltipProvider>

        {/* Time labels */}
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{durationHours}h ago</span>
          <span>now</span>
        </div>
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="flex items-center space-x-4 text-xs">
          {Object.entries(statusConfig).map(([status, config]) => (
            <div key={status} className="flex items-center space-x-1.5">
              <div
                className={cn('w-3 h-3 rounded-sm', config.color, config.pattern)}
              />
              <span className="text-muted-foreground">{config.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
