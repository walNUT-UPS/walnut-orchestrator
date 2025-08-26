/**
 * Core types for UPS health timeline
 */

export type HealthState = "green" | "amber" | "red" | "grey";

export interface HealthEvent {
  /** ISO timestamp in ms precision */
  ts: string;
  /** Derived state at this instant */
  state: HealthState;
}

export interface HealthSegment {
  startTs: number;
  endTs: number;
  state: HealthState;
}

export interface UPSTelemetryPoint {
  /** ISO timestamp */
  ts: string;
  /** UPS is online and responding */
  online: boolean;
  /** Line power is available */
  linePower: boolean;
  /** UPS is running on battery */
  onBattery: boolean;
  /** Last heartbeat timestamp */
  lastHeartbeat: string;
}

export interface HealthDataResponse {
  /** Current timestamp */
  now: string;
  /** Heartbeat timeout threshold in milliseconds */
  heartbeatTimeoutMs: number;
  /** Raw telemetry points */
  points: UPSTelemetryPoint[];
}

export const HEALTH_COLORS = {
  green: "var(--health-green)",
  amber: "var(--health-amber)", 
  red: "var(--health-red)",
  grey: "var(--health-grey)",
} as const;

export const HEALTH_LABELS = {
  green: "Online",
  amber: "Degraded", 
  red: "Critical",
  grey: "No Data",
} as const;