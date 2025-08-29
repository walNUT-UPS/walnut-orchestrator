/**
 * Pure functions to convert raw UPS telemetry points into health segments
 */
import type { UPSTelemetryPoint, HealthSegment, HealthState } from './types';

/**
 * Derive health state from a single telemetry point
 * Centralized policy for state determination
 */
export function deriveHealthState(
  point: UPSTelemetryPoint,
  nowMs: number,
  heartbeatTimeoutMs: number
): HealthState {
  // Red: power issues (critical)
  if (point.onBattery || !point.linePower) {
    return 'red';
  }
  
  // For historical data points, we don't check heartbeat staleness against current time
  // since the lastHeartbeat is the sample timestamp itself. Only check heartbeat staleness
  // for the most recent samples.
  const sampleMs = new Date(point.ts).getTime();
  const lastHeartbeatMs = new Date(point.lastHeartbeat).getTime();
  
  // If this is recent data (within heartbeat timeout of now), check heartbeat staleness
  if (nowMs - sampleMs <= heartbeatTimeoutMs) {
    // Amber: heartbeat/communication issues (degraded)
    if (nowMs - lastHeartbeatMs > heartbeatTimeoutMs) {
      return 'amber';
    }
  }
  // For older historical data, don't apply heartbeat staleness check since we're looking at past data
  
  // Green: all good (normal) - UPS was online with line power
  if (point.online && point.linePower && !point.onBattery) {
    return 'green';
  }
  
  // If UPS was offline but not on battery (e.g., communication issue at that time)
  if (!point.online && point.linePower && !point.onBattery) {
    return 'amber';
  }
  
  // Default to grey for unknown states
  return 'grey';
}

/**
 * Convert array of telemetry points to health segments
 * Handles state transitions and merges consecutive identical states
 */
export function deriveHealthSegments(
  points: UPSTelemetryPoint[],
  nowMs: number,
  heartbeatTimeoutMs: number,
  windowStartMs: number,
  windowEndMs: number
): HealthSegment[] {
  if (points.length === 0) {
    // Empty window shows grey
    return [{ startTs: windowStartMs, endTs: windowEndMs, state: 'grey' }];
  }
  
  // Sort points by timestamp
  const sortedPoints = [...points].sort((a, b) => 
    new Date(a.ts).getTime() - new Date(b.ts).getTime()
  );
  
  const segments: HealthSegment[] = [];
  let currentStartTs = windowStartMs;
  
  for (let i = 0; i < sortedPoints.length; i++) {
    const point = sortedPoints[i];
    const pointTs = new Date(point.ts).getTime();
    
    // Skip points outside our window
    if (pointTs < windowStartMs) continue;
    if (pointTs > windowEndMs) break;
    
    const state = deriveHealthState(point, nowMs, heartbeatTimeoutMs);
    
    // If this is not the first point, create a segment up to this point
    if (currentStartTs < pointTs) {
      // For the first segment, derive state from previous point if available
      let segmentState: HealthState = 'grey';
      if (i > 0) {
        const prevPoint = sortedPoints[i - 1];
        segmentState = deriveHealthState(prevPoint, nowMs, heartbeatTimeoutMs);
      } else {
        // Use current point's state for the initial segment
        segmentState = state;
      }
      
      segments.push({
        startTs: currentStartTs,
        endTs: pointTs,
        state: segmentState
      });
    }
    
    currentStartTs = pointTs;
  }
  
  // Create final segment to end of window
  if (currentStartTs < windowEndMs) {
    const lastPoint = sortedPoints[sortedPoints.length - 1];
    let lastState = deriveHealthState(lastPoint, nowMs, heartbeatTimeoutMs);
    // If the last heartbeat is stale, treat the tail as no-data (grey)
    try {
      const lastHbMs = new Date(lastPoint.lastHeartbeat).getTime();
      if (nowMs - lastHbMs > heartbeatTimeoutMs) {
        lastState = 'grey';
      }
    } catch {
      // ignore parsing errors; keep derived state
    }
    
    segments.push({
      startTs: currentStartTs,
      endTs: windowEndMs,
      state: lastState
    });
  }
  
  // Merge consecutive segments with same state
  const merged = mergeConsecutiveSegments(segments);
  
  // Clip to window bounds
  return clipToWindow(merged, windowStartMs, windowEndMs);
}

/**
 * Merge consecutive segments that have the same state
 * Reduces visual noise and improves performance
 */
export function mergeConsecutiveSegments(segments: HealthSegment[]): HealthSegment[] {
  if (segments.length <= 1) return segments;
  
  const merged: HealthSegment[] = [];
  let current = segments[0];
  
  for (let i = 1; i < segments.length; i++) {
    const next = segments[i];
    
    if (current.state === next.state && current.endTs === next.startTs) {
      // Merge: extend current segment
      current = {
        startTs: current.startTs,
        endTs: next.endTs,
        state: current.state
      };
    } else {
      // No merge: push current and start new
      merged.push(current);
      current = next;
    }
  }
  
  // Add final segment
  merged.push(current);
  
  return merged;
}

/**
 * Clip segments to fit within time window
 * Removes segments outside window and trims overlapping ones
 */
export function clipToWindow(
  segments: HealthSegment[], 
  windowStartMs: number, 
  windowEndMs: number
): HealthSegment[] {
  return segments
    .filter(segment => segment.endTs > windowStartMs && segment.startTs < windowEndMs)
    .map(segment => ({
      ...segment,
      startTs: Math.max(segment.startTs, windowStartMs),
      endTs: Math.min(segment.endTs, windowEndMs),
    }));
}

/**
 * Helper to calculate time ranges for different window durations
 */
export function getTimeWindow(duration: '6h' | '12h' | '24h', nowMs: number = Date.now()): {
  startMs: number;
  endMs: number;
  durationMs: number;
} {
  const hours = parseInt(duration.replace('h', ''));
  const durationMs = hours * 60 * 60 * 1000;
  
  return {
    startMs: nowMs - durationMs,
    endMs: nowMs,
    durationMs,
  };
}
