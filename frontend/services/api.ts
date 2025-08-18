/**
 * API service for walNUT frontend
 * Handles communication with the backend REST API
 */

export interface UPSStatus {
  timestamp: string;
  battery_percent?: number;
  runtime_seconds?: number;
  load_percent?: number;
  input_voltage?: number;
  output_voltage?: number;
  status?: string;
}

export interface UPSHealthSummary {
  period_hours: number;
  avg_battery?: number;
  min_battery?: number;
  max_battery?: number;
  time_on_battery_seconds?: number;
  samples_count: number;
  last_updated: string;
}

export interface Event {
  id: number;
  timestamp: string;
  event_type: string;
  description: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  metadata?: Record<string, any>;
}

export interface SystemHealth {
  status: string;
  timestamp: string;
  components: Record<string, any>;
  uptime_seconds: number;
  last_power_event?: string;
}

class ApiService {
  private baseUrl = '/api';

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      credentials: 'include', // Include cookies for authentication
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (response.status === 401) {
      // Don't redirect here - let the auth context handle it
      throw new Error('Authentication required');
    }

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  // UPS API methods
  async getUPSStatus(): Promise<UPSStatus> {
    return this.request<UPSStatus>('/ups/status');
  }

  async getUPSHealth(hours: number = 24): Promise<UPSHealthSummary> {
    return this.request<UPSHealthSummary>(`/ups/health?hours=${hours}`);
  }

  async getUPSSamples(limit: number = 100, offset: number = 0, since?: string) {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });
    
    if (since) {
      params.set('since', since);
    }

    return this.request(`/ups/samples?${params.toString()}`);
  }

  // Events API methods
  async getEvents(limit: number = 50, offset: number = 0): Promise<{events: Event[]; total: number}> {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
    });

    return this.request(`/events?${params.toString()}`);
  }

  // System API methods
  async getSystemHealth(): Promise<SystemHealth> {
    return this.request<SystemHealth>('/system/health');
  }

  async getSystemStatus(): Promise<{status: string; timestamp: string; service: string}> {
    return this.request('/system/status');
  }

  // WebSocket connection helper - cookies are included automatically
  createWebSocket(): WebSocket {
    const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.host;
    return new WebSocket(`${wsUrl}//${wsHost}/ws`);
  }
}

export const apiService = new ApiService();