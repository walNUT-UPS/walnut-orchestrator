/**
 * Hook for fetching and managing UPS health timeline data
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiService, UPSTelemetryResponse } from '../../services/api';
import { deriveHealthSegments, getTimeWindow } from './deriveSegments';
import type { HealthSegment, UPSTelemetryPoint } from './types';

interface UseHealthDataOptions {
  /** Time window duration */
  duration: '6h' | '12h' | '24h';
  /** Polling interval in milliseconds (default: 15000 = 15s) */
  pollInterval?: number;
  /** Enable automatic polling */
  enabled?: boolean;
}

interface UseHealthDataResult {
  /** Processed health segments ready for rendering */
  segments: HealthSegment[];
  /** Raw telemetry data */
  telemetryData: UPSTelemetryResponse | null;
  /** Loading state */
  loading: boolean;
  /** Error state */
  error: string | null;
  /** Timestamp of last successful fetch */
  lastFetch: number | null;
  /** Manual refresh function */
  refresh: () => Promise<void>;
  /** Whether data is currently being fetched */
  fetching: boolean;
}

export function useHealthData(options: UseHealthDataOptions): UseHealthDataResult {
  const { duration, pollInterval = 15000, enabled = true } = options;
  
  const [telemetryData, setTelemetryData] = useState<UPSTelemetryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [fetching, setFetching] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<number | null>(null);
  
  // Use ref to track current duration for polling
  const currentDurationRef = useRef(duration);
  currentDurationRef.current = duration;
  
  const fetchTelemetryData = useCallback(async () => {
    try {
      setFetching(true);
      setError(null);
      
      const hours = parseInt(currentDurationRef.current.replace('h', ''));
      const response = await apiService.getUPSTelemetry(hours);
      
      setTelemetryData(response);
      setLastFetch(Date.now());
      setLoading(false);
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch health data';
      setError(errorMessage);
      setLoading(false);
      
      // Don't clear existing data on error, just log it
      console.warn('Health data fetch failed:', errorMessage);
    } finally {
      setFetching(false);
    }
  }, []);
  
  const refresh = useCallback(async () => {
    await fetchTelemetryData();
  }, [fetchTelemetryData]);
  
  // Initial fetch and setup polling
  useEffect(() => {
    if (!enabled) return;
    
    // Initial fetch
    fetchTelemetryData();
    
    // Setup polling
    const interval = setInterval(() => {
      fetchTelemetryData();
    }, pollInterval);
    
    return () => clearInterval(interval);
  }, [enabled, fetchTelemetryData, pollInterval]);
  
  // Refetch when duration changes
  useEffect(() => {
    if (enabled && !loading) {
      fetchTelemetryData();
    }
  }, [duration, enabled, fetchTelemetryData, loading]);
  
  // Derive health segments from telemetry data
  const segments: HealthSegment[] = React.useMemo(() => {
    if (!telemetryData) {
      // Return grey segment for entire window when no data
      const now = Date.now();
      const { startMs, endMs } = getTimeWindow(duration, now);
      return [{ startTs: startMs, endTs: endMs, state: 'grey' }];
    }
    
    try {
      const now = new Date(telemetryData.now).getTime();
      const { startMs, endMs } = getTimeWindow(duration, now);
      
      // Convert API format to internal format
      const points: UPSTelemetryPoint[] = telemetryData.points.map(point => ({
        ts: point.ts,
        online: point.online,
        linePower: point.linePower,
        onBattery: point.onBattery,
        lastHeartbeat: point.lastHeartbeat,
      }));
      
      return deriveHealthSegments(
        points,
        now,
        telemetryData.heartbeatTimeoutMs,
        startMs,
        endMs
      );
    } catch (err) {
      console.error('Error deriving health segments:', err);
      // Fallback to grey segment
      const now = Date.now();
      const { startMs, endMs } = getTimeWindow(duration, now);
      return [{ startTs: startMs, endTs: endMs, state: 'grey' }];
    }
  }, [telemetryData, duration]);
  
  return {
    segments,
    telemetryData,
    loading,
    error,
    lastFetch,
    refresh,
    fetching,
  };
}

export default useHealthData;