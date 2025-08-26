/**
 * UniFi-style UPS Health Timeline Component
 * 
 * Displays a continuous health bar with green/amber/red/grey segments
 * representing UPS health state over time with accessibility features.
 */
import React, { useState, useMemo } from 'react';
import { cn } from '../ui/utils';
import { HEALTH_COLORS, HEALTH_LABELS, type HealthSegment, type HealthState } from './types';
import { getTimeWindow } from './deriveSegments';

interface HealthBarProps {
  /** Health segments to render */
  segments: HealthSegment[];
  /** Time window duration */
  duration: '6h' | '12h' | '24h';
  /** Current timestamp (for alignment) */
  nowMs?: number;
  /** Height of the timeline bar in pixels */
  height?: number;
  /** Additional CSS classes */
  className?: string;
  /** Show time axis labels */
  showTimeAxis?: boolean;
  /** Enable tooltips on hover */
  enableTooltips?: boolean;
}

interface VisualSegment extends HealthSegment {
  /** Percentage from left edge */
  leftPercent: number;
  /** Width as percentage of total */
  widthPercent: number;
}

const getSegmentColor = (state: HealthState): string => {
  switch (state) {
    case 'green': return 'var(--health-green)';
    case 'amber': return 'var(--health-amber)';
    case 'red': return 'var(--health-red)';
    case 'grey': return 'var(--health-grey)';
    default: return 'var(--health-grey)';
  }
};

const getSegmentPatternClass = (state: HealthState): string => {
  switch (state) {
    case 'amber': return 'health-pattern-amber';
    case 'red': return 'health-pattern-red';
    default: return '';
  }
};

const formatTooltipTime = (startTs: number, endTs: number): string => {
  const start = new Date(startTs);
  const end = new Date(endTs);
  
  const formatTime = (date: Date) => date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
  
  return `${formatTime(start)} — ${formatTime(end)}`;
};

export const HealthBar: React.FC<HealthBarProps> = ({
  segments,
  duration,
  nowMs = Date.now(),
  height = 12,
  className,
  showTimeAxis = true,
  enableTooltips = true,
}) => {
  const [hoveredSegment, setHoveredSegment] = useState<VisualSegment | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  
  // Calculate time window and visual segments
  const { windowStart, windowEnd, visualSegments } = useMemo(() => {
    const { startMs, endMs } = getTimeWindow(duration, nowMs);
    const totalDurationMs = endMs - startMs;
    
    const visual: VisualSegment[] = segments
      .filter(segment => segment.endTs > startMs && segment.startTs < endMs)
      .map(segment => {
        const clampedStart = Math.max(segment.startTs, startMs);
        const clampedEnd = Math.min(segment.endTs, endMs);
        
        const leftPercent = ((clampedStart - startMs) / totalDurationMs) * 100;
        const widthPercent = ((clampedEnd - clampedStart) / totalDurationMs) * 100;
        
        return {
          ...segment,
          leftPercent,
          widthPercent,
        };
      })
      .filter(segment => segment.widthPercent > 0);
    
    return {
      windowStart: startMs,
      windowEnd: endMs,
      visualSegments: visual,
    };
  }, [segments, duration, nowMs]);
  
  // Generate time axis ticks
  const timeTicks = useMemo(() => {
    if (!showTimeAxis) return [];
    
    const ticks = [];
    const tickCount = 6; // Show 6 evenly spaced ticks
    const totalDuration = windowEnd - windowStart;
    
    for (let i = 0; i <= tickCount; i++) {
      const tickTime = windowStart + (i * totalDuration / tickCount);
      const position = (i / tickCount) * 100;
      
      let label: string;
      if (i === tickCount) {
        label = 'Now';
      } else {
        const hoursAgo = Math.floor((nowMs - tickTime) / (60 * 60 * 1000));
        label = hoursAgo === 0 ? 'Now' : `${hoursAgo}h`;
      }
      
      ticks.push({
        position,
        label,
        timestamp: tickTime,
      });
    }
    
    return ticks;
  }, [windowStart, windowEnd, nowMs, showTimeAxis]);
  
  const handleSegmentHover = (event: React.MouseEvent, segment: VisualSegment) => {
    if (!enableTooltips) return;
    
    const rect = event.currentTarget.getBoundingClientRect();
    setTooltipPosition({
      x: event.clientX,
      y: rect.top,
    });
    setHoveredSegment(segment);
  };
  
  const handleSegmentFocus = (event: React.FocusEvent, segment: VisualSegment) => {
    if (!enableTooltips) return;
    
    const rect = event.currentTarget.getBoundingClientRect();
    setTooltipPosition({
      x: rect.left + (rect.width / 2),
      y: rect.top,
    });
    setHoveredSegment(segment);
  };
  
  const clearTooltip = () => {
    setHoveredSegment(null);
  };
  
  return (
    <div className={cn('relative', className)}>
      {/* Health Bar Container */}
      <div 
        className="relative bg-muted rounded-md border border-border overflow-hidden"
        style={{ height: `${height}px` }}
        role="img"
        aria-label={`UPS health timeline for last ${duration}`}
      >
        {/* Background track */}
        <div className="absolute inset-0 bg-muted" />
        
        {/* Health segments */}
        {visualSegments.map((segment, index) => (
          <div
            key={index}
            className={cn(
              'absolute top-0 h-full transition-opacity duration-150 cursor-pointer',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
              getSegmentPatternClass(segment.state)
            )}
            style={{
              left: `${segment.leftPercent}%`,
              width: `${segment.widthPercent}%`,
              backgroundColor: getSegmentColor(segment.state),
            }}
            data-state={segment.state}
            tabIndex={0}
            role="button"
            aria-label={`${HEALTH_LABELS[segment.state]} from ${formatTooltipTime(segment.startTs, segment.endTs)}`}
            onMouseEnter={(e) => handleSegmentHover(e, segment)}
            onMouseMove={(e) => handleSegmentHover(e, segment)}
            onMouseLeave={clearTooltip}
            onFocus={(e) => handleSegmentFocus(e, segment)}
            onBlur={clearTooltip}
          />
        ))}
      </div>
      
      {/* Time Axis */}
      {showTimeAxis && (
        <div className="relative mt-2 mb-4 md:mb-5">
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
      )}
      
      {/* Tooltip */}
      {enableTooltips && hoveredSegment && (
        <div
          className="fixed z-50 bg-popover border border-border rounded-md shadow-lg p-3 pointer-events-none"
          style={{
            left: tooltipPosition.x + 10,
            top: tooltipPosition.y - 60,
            transform: 'translateY(-100%)',
          }}
        >
          <div className="space-y-1">
            <div className="text-micro font-medium">
              {formatTooltipTime(hoveredSegment.startTs, hoveredSegment.endTs)}
            </div>
            <div className="text-micro text-muted-foreground">
              Status: {HEALTH_LABELS[hoveredSegment.state]}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default HealthBar;
