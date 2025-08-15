import React, { useState } from 'react';
import { cn } from './ui/utils';

export interface PowerSegment {
  start: Date;
  end: Date;
  status: 'online' | 'on-battery' | 'low-battery' | 'critical' | 'no-data';
  meta?: {
    batteryPercent?: number;
    inputVoltage?: number;
    loadWatts?: number;
  };
}

interface LinePower24hProps {
  segments: PowerSegment[];
  duration?: '6h' | '12h' | '24h';
  onZoomChange?: (duration: '6h' | '12h' | '24h') => void;
  showLegend?: boolean;
  className?: string;
}

const statusConfig = {
  'online': {
    label: 'Online',
    color: 'bg-status-ok',
    bgColor: 'bg-green-500'
  },
  'on-battery': {
    label: 'On Battery',
    color: 'bg-status-warn',
    bgColor: 'bg-amber-500'
  },
  'low-battery': {
    label: 'Low Battery',
    color: 'bg-status-error',
    bgColor: 'bg-red-500'
  },
  'critical': {
    label: 'Critical',
    color: 'bg-status-error',
    bgColor: 'bg-red-600'
  },
  'no-data': {
    label: 'No Data',
    color: 'bg-status-neutral',
    bgColor: 'bg-gray-400'
  }
};

export function LinePower24h({ 
  segments, 
  duration = '24h', 
  onZoomChange,
  showLegend = true,
  className 
}: LinePower24hProps) {
  const [hoveredSegment, setHoveredSegment] = useState<PowerSegment | null>(null);
  const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });

  // Calculate time bounds
  const now = new Date();
  const getDurationMs = () => {
    switch (duration) {
      case '6h': return 6 * 60 * 60 * 1000;
      case '12h': return 12 * 60 * 60 * 1000;
      case '24h': return 24 * 60 * 60 * 1000;
    }
  };
  
  const startTime = new Date(now.getTime() - getDurationMs());
  const totalDuration = getDurationMs();

  // Generate time ticks
  const getTimeTicks = () => {
    const ticks = [];
    const tickInterval = totalDuration / 6; // 6 ticks total
    
    for (let i = 0; i <= 6; i++) {
      const tickTime = new Date(startTime.getTime() + (i * tickInterval));
      const position = (i / 6) * 100;
      
      let label;
      if (i === 6) {
        label = 'Now';
      } else {
        const hoursAgo = Math.floor((now.getTime() - tickTime.getTime()) / (60 * 60 * 1000));
        label = hoursAgo === 0 ? 'Now' : `${hoursAgo}h`;
      }
      
      ticks.push({ position, label, time: tickTime });
    }
    
    return ticks;
  };

  const timeTicks = getTimeTicks();

  // Convert segments to visual segments
  const getVisualSegments = () => {
    return segments
      .filter(segment => segment.end > startTime && segment.start < now)
      .map(segment => {
        const segmentStart = Math.max(segment.start.getTime(), startTime.getTime());
        const segmentEnd = Math.min(segment.end.getTime(), now.getTime());
        
        const startPercent = ((segmentStart - startTime.getTime()) / totalDuration) * 100;
        const width = ((segmentEnd - segmentStart) / totalDuration) * 100;
        
        return {
          ...segment,
          startPercent,
          width,
          visualStart: segmentStart,
          visualEnd: segmentEnd
        };
      });
  };

  const visualSegments = getVisualSegments();

  // Get unique statuses for legend
  const legendStatuses = Array.from(new Set(segments.map(s => s.status)));

  const formatTooltipTime = (start: number, end: number) => {
    const startDate = new Date(start);
    const endDate = new Date(end);
    const formatTime = (date: Date) => date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    });
    return `${formatTime(startDate)}–${formatTime(endDate)}`;
  };

  const handleMouseMove = (e: React.MouseEvent, segment: PowerSegment) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHoverPosition({ x: e.clientX, y: rect.top });
    setHoveredSegment(segment);
  };

  return (
    <div className={cn('space-y-3', className)}>
      {/* Header with title and zoom controls */}
      <div className="flex items-center justify-between">
        <h3 className="text-title">Line Power Status — Last {duration.replace('h', ' hours')}</h3>
        
        {onZoomChange && (
          <div className="flex items-center bg-muted rounded-md p-1 space-x-1">
            {(['24h', '12h', '6h'] as const).map((d) => (
              <button
                key={d}
                onClick={() => onZoomChange(d)}
                className={cn(
                  'px-3 py-1 rounded text-micro font-medium transition-colors',
                  duration === d 
                    ? 'bg-background text-foreground shadow-sm' 
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {d}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="relative">
        {/* Timeline container */}
        <div className="relative h-4 bg-muted rounded-lg border border-border overflow-hidden">
          {visualSegments.map((segment, index) => (
            <div
              key={index}
              className={cn(
                'absolute top-0 h-full transition-opacity cursor-pointer',
                statusConfig[segment.status].bgColor,
                // Add stripe pattern for critical/low-battery states for accessibility
                (segment.status === 'critical' || segment.status === 'low-battery') && 'bg-stripe-red'
              )}
              style={{
                left: `${segment.startPercent}%`,
                width: `${segment.width}%`
              }}
              onMouseEnter={(e) => handleMouseMove(e, segment)}
              onMouseMove={(e) => handleMouseMove(e, segment)}
              onMouseLeave={() => setHoveredSegment(null)}
              tabIndex={0}
              role="button"
              aria-label={`${statusConfig[segment.status].label} from ${segment.start.toLocaleString()} to ${segment.end.toLocaleString()}`}
              onFocus={(e) => handleMouseMove(e, segment)}
              onBlur={() => setHoveredSegment(null)}
              className="focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            />
          ))}
        </div>

        {/* Time ticks */}
        <div className="relative mt-2">
          {timeTicks.map((tick, index) => (
            <div
              key={index}
              className="absolute transform -translate-x-1/2"
              style={{ left: `${tick.position}%` }}
            >
              <div className="w-px h-2 bg-border mx-auto" />
              <div className="text-micro text-muted-foreground mt-1 whitespace-nowrap">
                {tick.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      {showLegend && legendStatuses.length > 0 && (
        <div className="flex items-center space-x-4 text-micro">
          {legendStatuses.map((status) => (
            <div key={status} className="flex items-center space-x-2">
              <div className={cn('w-3 h-3 rounded-sm', statusConfig[status].bgColor)} />
              <span className="text-muted-foreground">{statusConfig[status].label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tooltip */}
      {hoveredSegment && (
        <div
          className="fixed z-50 bg-popover border border-border rounded-md shadow-lg p-3 pointer-events-none"
          style={{
            left: hoverPosition.x + 10,
            top: hoverPosition.y - 60,
            transform: 'translateY(-100%)'
          }}
        >
          <div className="space-y-1">
            <div className="text-micro font-medium">
              {formatTooltipTime(hoveredSegment.start.getTime(), hoveredSegment.end.getTime())}
            </div>
            <div className="text-micro text-muted-foreground">
              Status: {statusConfig[hoveredSegment.status].label}
            </div>
            {hoveredSegment.meta && (
              <div className="text-micro text-muted-foreground space-y-0.5">
                {hoveredSegment.meta.batteryPercent !== undefined && (
                  <div>Battery: {hoveredSegment.meta.batteryPercent}%</div>
                )}
                {hoveredSegment.meta.inputVoltage !== undefined && (
                  <div>Input: {hoveredSegment.meta.inputVoltage}V</div>
                )}
                {hoveredSegment.meta.loadWatts !== undefined && (
                  <div>Load: {hoveredSegment.meta.loadWatts}W</div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}