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

export interface IntegrationType {
  name: string;
  version: string;
  min_core_version: string;
  description: string;
  capabilities: Array<{
    id: string;
    verbs: string[];
    targets: string[];
    dry_run?: string;
  }>;
  config_fields: Array<{
    name: string;
    type: string;
    title?: string;
    default?: any;
    required?: boolean;
    secret?: boolean;
  }>;
  secret_fields: Array<{
    name: string;
    type: string;
    title?: string;
    secret?: boolean;
  }>;
}

export interface IntegrationInstance {
  id: number;
  name: string;
  display_name: string;
  type_name: string;
  enabled: boolean;
  health_status: string;
  state: string;
  config: Record<string, any>;
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

  // Integration API methods
  async getIntegrationTypes(): Promise<IntegrationType[]> {
    return this.request<IntegrationType[]>('/v1/integrations/types');
  }

  async syncIntegrationTypes(): Promise<{status: string; message: string}> {
    return this.request('/v1/integrations/types/sync', { method: 'POST' });
  }

  async getIntegrationInstances(): Promise<IntegrationInstance[]> {
    return this.request<IntegrationInstance[]>('/v1/integrations/instances');
  }

  async createIntegrationInstance(data: {
    type_name: string;
    name: string;
    display_name: string;
    config: Record<string, any>;
    secrets: Record<string, string>;
    enabled?: boolean;
  }): Promise<IntegrationInstance> {
    return this.request<IntegrationInstance>('/v1/integrations/instances', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async updateIntegrationInstance(id: number, data: {
    type_name: string;
    name: string;
    display_name: string;
    config: Record<string, any>;
    secrets: Record<string, string>;
    enabled?: boolean;
  }): Promise<IntegrationInstance> {
    return this.request<IntegrationInstance>(`/v1/integrations/instances/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async deleteIntegrationInstance(id: number): Promise<void> {
    return this.request<void>(`/v1/integrations/instances/${id}`, {
      method: 'DELETE'
    });
  }

  async testIntegrationInstance(id: number): Promise<{status: string; message: string}> {
    return this.request<{status: string; message: string}>(`/v1/integrations/instances/${id}/test`, {
      method: 'POST'
    });
  }

  // WebSocket connection helper - cookies are included automatically
  createWebSocket(): WebSocket {
    const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.host;
    return new WebSocket(`${wsUrl}//${wsHost}/ws`);
  }
}

export const apiService = new ApiService();