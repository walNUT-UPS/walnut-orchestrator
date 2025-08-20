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
  id: string;
  name: string;
  version: string;
  min_core_version: string;
  category: string;
  status: string;
  errors?: any;
  capabilities: Array<{
    id: string;
    verbs: string[];
    targets: string[];
    dry_run?: string;
  }>;
  schema_connection: any;
  last_validated_at?: string;
  created_at: string;
  updated_at: string;
}

export interface LegacyIntegrationType {
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
  instance_id: number;
  type_id: string;
  name: string;
  config: Record<string, any>;
  state: string;
  last_test?: string;
  latency_ms?: number;
  flags?: string[];
  created_at: string;
  updated_at: string;
  type_name?: string;
  type_category?: string;
}

export interface LegacyIntegrationInstance {
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

  // New Integration API methods (Architecture v2)
  async getIntegrationTypes(rescan: boolean = false): Promise<IntegrationType[]> {
    const params = rescan ? '?rescan=true' : '';
    return this.request<IntegrationType[]>(`/integrations/types${params}`);
  }

  async uploadIntegrationPackage(file: File): Promise<{success: boolean; type_id: string; message: string; validation: any}> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${this.baseUrl}/integrations/types/upload`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  async removeIntegrationType(typeId: string): Promise<{success: boolean; message: string}> {
    return this.request<{success: boolean; message: string}>(`/integrations/types/${typeId}`, {
      method: 'DELETE'
    });
  }

  async revalidateIntegrationType(typeId: string): Promise<{success: boolean; message: string; result: any}> {
    return this.request<{success: boolean; message: string; result: any}>(`/integrations/types/${typeId}/validate`, {
      method: 'POST'
    });
  }

  async getIntegrationInstances(): Promise<IntegrationInstance[]> {
    return this.request<IntegrationInstance[]>('/integrations/instances');
  }

  async createIntegrationInstance(data: {
    type_id: string;
    name: string;
    config: Record<string, any>;
    secrets?: Record<string, string>;
  }): Promise<IntegrationInstance> {
    return this.request<IntegrationInstance>('/integrations/instances', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async deleteIntegrationInstance(instanceId: number): Promise<{success: boolean; message: string}> {
    return this.request<{success: boolean; message: string}>(`/integrations/instances/${instanceId}`, {
      method: 'DELETE'
    });
  }

  async testIntegrationInstance(instanceId: number): Promise<{success: boolean; status: string; latency_ms?: number; message?: string}> {
    return this.request<{success: boolean; status: string; latency_ms?: number; message?: string}>(`/integrations/instances/${instanceId}/test`, {
      method: 'POST'
    });
  }

  // Legacy Integration API methods (for backward compatibility)
  async getLegacyIntegrationTypes(): Promise<LegacyIntegrationType[]> {
    return this.request<LegacyIntegrationType[]>('/v1/integrations/types');
  }

  async syncLegacyIntegrationTypes(): Promise<{status: string; message: string}> {
    return this.request('/v1/integrations/types/sync', { method: 'POST' });
  }

  async getLegacyIntegrationInstances(): Promise<LegacyIntegrationInstance[]> {
    return this.request<LegacyIntegrationInstance[]>('/v1/integrations/instances');
  }

  async createLegacyIntegrationInstance(data: {
    type_name: string;
    name: string;
    display_name: string;
    config: Record<string, any>;
    secrets: Record<string, string>;
    enabled?: boolean;
  }): Promise<LegacyIntegrationInstance> {
    return this.request<LegacyIntegrationInstance>('/v1/integrations/instances', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  async testLegacyIntegrationInstance(id: number): Promise<{status: string; message: string}> {
    return this.request<{status: string; message: string}>(`/v1/integrations/instances/${id}/test`, {
      method: 'POST'
    });
  }

  // Get JWT token from cookies for WebSocket authentication
  private getJWTTokenFromCookie(): string | null {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'fastapiusersauth') { // Default fastapi-users cookie name
        return decodeURIComponent(value);
      }
    }
    return null;
  }

  // WebSocket connection helper - needs JWT token for authentication
  createWebSocket(): WebSocket {
    const token = this.getJWTTokenFromCookie();
    if (!token) {
      throw new Error('No authentication token available for WebSocket connection');
    }

    // Connect to backend server (port 8000) with JWT token
    const wsUrl = 'ws://localhost:8000/ws';
    const wsWithToken = `${wsUrl}?token=${encodeURIComponent(token)}`;
    
    return new WebSocket(wsWithToken);
  }
}

export const apiService = new ApiService();