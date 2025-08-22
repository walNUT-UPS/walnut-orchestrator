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
  private csrfToken: string | null = null;

  private async getCsrfToken(): Promise<string | null> {
    if (this.csrfToken) {
      return this.csrfToken;
    }

    try {
      // Try to get CSRF token from meta tag first
      const metaTag = document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement;
      if (metaTag) {
        this.csrfToken = metaTag.content;
        return this.csrfToken;
      }

      // Otherwise fetch from API
      const response = await fetch('/api/csrf-token', { credentials: 'include' });
      if (response.ok) {
        const data = await response.json();
        this.csrfToken = data.csrf_token;
        return this.csrfToken;
      }
    } catch (e) {
      console.warn('Failed to get CSRF token:', e);
    }

    return null;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options?.headers,
    };

    // Add CSRF token for non-GET requests
    if (options?.method && options.method !== 'GET') {
      const csrfToken = await this.getCsrfToken();
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      credentials: 'include', // Include cookies for authentication
      headers,
      ...options,
    });

    // Clear CSRF token on 403 (CSRF failure) to force refresh
    if (response.status === 403) {
      this.csrfToken = null;
    }

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

  async uploadIntegrationPackage(file: File): Promise<{success: boolean; type_id?: string; message?: string; validation?: any; logs?: Array<{ts: string; level: string; message: string; step?: string}>; error?: string}> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${this.baseUrl}/integrations/types/upload`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    let data: any = null;
    try {
      data = await response.json();
    } catch (_) {
      // ignore
    }
    if (!response.ok) {
      // Bubble up server-provided logs/trace if available
      const msg = data?.error || data?.detail || `${response.status} ${response.statusText}`;
      const err: any = new Error(`Upload failed: ${typeof msg === 'string' ? msg : JSON.stringify(msg)}`);
      if (data?.logs) err.logs = data.logs;
      if (data?.trace) err.trace = data.trace;
      throw err;
    }
    return data;
  }

  async uploadIntegrationPackageStream(file: File): Promise<{ job_id: string }>{
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${this.baseUrl}/integrations/types/upload/stream`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Stream upload failed: ${response.status} ${response.statusText} ${text}`);
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

  async getInstanceInventory(instanceId: number, type?: string): Promise<{ items: Array<{ type: string; external_id: string; name: string; attrs?: any; labels?: any }> }> {
    const q = type ? `?type=${encodeURIComponent(type)}` : '';
    return this.request(`/integrations/instances/${instanceId}/inventory${q}`);
  }

  async getIntegrationManifest(typeId: string): Promise<{ type_id: string; path: string; manifest_yaml: string }>{
    return this.request(`/integrations/types/${encodeURIComponent(typeId)}/manifest`);
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

  async updateIntegrationInstance(instanceId: number, data: Partial<{ name: string; config: Record<string, any> }>): Promise<IntegrationInstance> {
    return this.request<IntegrationInstance>(`/integrations/instances/${instanceId}`, {
      method: 'PATCH',
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

  // WebSocket connection helper - prefer cookie-authenticated same-origin WS
  createWebSocket(): WebSocket {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${location.host}/ws`;
    // Cookies are automatically included for same-origin WS handshake via Vite proxy
    return new WebSocket(wsUrl);
  }

  // Users API (fastapi-users)
  async listUsers(): Promise<Array<{ id: string; email: string; is_active: boolean; is_verified: boolean; is_superuser: boolean }>> {
    return this.request('/admin/users');
  }

  async updateUser(id: string, data: Partial<{ email: string; password: string; is_active: boolean; is_superuser: boolean }>): Promise<any> {
    return this.request(`/users/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getSystemConfig(): Promise<any> {
    return this.request('/system/config');
  }


  // OIDC config endpoints
  async getOidcConfig(): Promise<{
    enabled: boolean;
    provider_name?: string;
    client_id?: string;
    has_client_secret: boolean;
    discovery_url?: string;
    admin_roles: string[];
    viewer_roles: string[];
    requires_restart: boolean;
  }> {
    return this.request('/system/oidc/config');
  }

  async updateOidcConfig(cfg: Partial<{
    enabled: boolean;
    provider_name: string;
    client_id: string;
    client_secret: string;
    discovery_url: string;
    admin_roles: string[];
    viewer_roles: string[];
  }>): Promise<any> {
    return this.request('/system/oidc/config', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    });
  }

  async testOidcConfig(cfg?: Partial<{
    enabled: boolean;
    provider_name: string;
    client_id: string;
    client_secret: string;
    discovery_url: string;
    admin_roles: string[];
    viewer_roles: string[];
  }>): Promise<{ status: string; details?: any }> {
    return this.request('/system/oidc/test', {
      method: 'POST',
      body: cfg ? JSON.stringify(cfg) : undefined,
    });
  }

  // Policies
  async listPolicies(): Promise<any[]> {
    return this.request('/policies');
  }

  async getPolicy(id: number): Promise<any> {
    return this.request(`/policies/${id}`);
  }

  async createPolicy(body: any): Promise<any> {
    return this.request('/policies', { method: 'POST', body: JSON.stringify(body) });
  }

  async updatePolicy(id: number, body: any): Promise<any> {
    return this.request(`/policies/${id}`, { method: 'PUT', body: JSON.stringify(body) });
  }

  async deletePolicy(id: number): Promise<void> {
    await this.request(`/policies/${id}`, { method: 'DELETE' });
  }

  async validatePolicy(body: any): Promise<{ errors: string[]; warnings: string[] }> {
    return this.request('/policies/validate', { method: 'POST', body: JSON.stringify(body) });
  }

  async testPolicy(body: any): Promise<{ status: string; plan: any[] }> {
    return this.request('/policies/test', { method: 'POST', body: JSON.stringify(body) });
  }

  async dryRunPolicy(id: number): Promise<any> {
    return this.request(`/policies/${id}/dry-run`, { method: 'POST' });
  }

  async createInversePolicy(id: number): Promise<any> {
    return this.request(`/policies/${id}/inverse`, { method: 'POST' });
  }

  // Host management
  async getHosts(): Promise<any[]> {
    return this.request('/hosts');
  }

  async getHostCapabilities(hostId: string): Promise<any[]> {
    return this.request(`/hosts/${hostId}/capabilities`);
  }

  async getHostInventory(hostId: string, refresh = false): Promise<any[]> {
    return this.request(`/hosts/${hostId}/inventory?refresh=${refresh}`);
  }
}

export const apiService = new ApiService();
