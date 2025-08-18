import React, { useState } from 'react';
import { IntegrationFlyout } from './components/IntegrationFlyout';
import { Button } from './components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Plus, Settings, Server, Webhook, Network } from 'lucide-react';

// Mock integration types
const integrationTypes = [
  {
    name: 'proxmox-ve',
    displayName: 'Proxmox VE',
    icon: Server,
    description: 'Virtual environment management platform',
    fields: [
      {
        name: 'host',
        label: 'Host/IP Address',
        type: 'text' as const,
        required: true,
        placeholder: 'proxmox.example.com',
        description: 'The hostname or IP address of your Proxmox VE server'
      },
      {
        name: 'port',
        label: 'Port',
        type: 'number' as const,
        defaultValue: 8006,
        placeholder: '8006',
        description: 'Port number for the Proxmox VE API (default: 8006)'
      },
      {
        name: 'node',
        label: 'Node Name',
        type: 'text' as const,
        required: true,
        placeholder: 'pve-node1',
        description: 'The name of the Proxmox node to connect to'
      },
      {
        name: 'apiToken',
        label: 'API Token',
        type: 'password' as const,
        required: true,
        placeholder: 'PVEAPIToken=user@pam!token=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
        description: 'Your Proxmox VE API token for authentication'
      },
      {
        name: 'verifySSL',
        label: 'Verify SSL Certificate',
        type: 'boolean' as const,
        defaultValue: true,
        description: 'Enable SSL certificate verification for secure connections'
      },
      {
        name: 'timeout',
        label: 'Connection Timeout (seconds)',
        type: 'number' as const,
        defaultValue: 30,
        placeholder: '30',
        description: 'Maximum time to wait for connection establishment'
      },
      {
        name: 'retries',
        label: 'Retry Attempts',
        type: 'number' as const,
        defaultValue: 3,
        placeholder: '3',
        description: 'Number of retry attempts for failed requests'
      }
    ]
  },
  {
    name: 'aos-cx',
    displayName: 'AOS-CX Switch',
    icon: Network,
    description: 'Aruba CX switch management',
    fields: [
      {
        name: 'host',
        label: 'Switch IP Address',
        type: 'text' as const,
        required: true,
        placeholder: '192.168.1.100'
      },
      {
        name: 'username',
        label: 'Username',
        type: 'text' as const,
        required: true,
        placeholder: 'admin'
      },
      {
        name: 'password',
        label: 'Password',
        type: 'password' as const,
        required: true
      }
    ]
  },
  {
    name: 'webhook',
    displayName: 'Webhook',
    icon: Webhook,
    description: 'HTTP webhook endpoint',
    fields: [
      {
        name: 'url',
        label: 'Webhook URL',
        type: 'text' as const,
        required: true,
        placeholder: 'https://api.example.com/webhook'
      },
      {
        name: 'secret',
        label: 'Secret Key',
        type: 'password' as const,
        placeholder: 'Optional webhook secret'
      }
    ]
  }
];

// Mock existing connections
const mockConnections = [
  {
    id: '1',
    name: 'Production Proxmox',
    type: 'proxmox-ve',
    status: 'connected',
    lastSeen: '2 minutes ago'
  },
  {
    id: '2',
    name: 'Core Switch 01',
    type: 'aos-cx',
    status: 'disconnected',
    lastSeen: '1 hour ago'
  },
  {
    id: '3',
    name: 'Monitoring Webhook',
    type: 'webhook',
    status: 'connected',
    lastSeen: '5 minutes ago'
  }
];

export default function App() {
  const [isFlyoutOpen, setIsFlyoutOpen] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState(null);
  const [flyoutMode, setFlyoutMode] = useState<'create' | 'edit'>('create');
  const [editingConnection, setEditingConnection] = useState(null);

  const handleCreateConnection = (integrationType: any) => {
    setSelectedIntegration(integrationType);
    setFlyoutMode('create');
    setEditingConnection(null);
    setIsFlyoutOpen(true);
  };

  const handleEditConnection = (connection: any) => {
    const integrationType = integrationTypes.find(type => type.name === connection.type);
    setSelectedIntegration(integrationType);
    setFlyoutMode('edit');
    setEditingConnection(connection);
    setIsFlyoutOpen(true);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'connected':
        return <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Connected</Badge>;
      case 'disconnected':
        return <Badge variant="destructive">Disconnected</Badge>;
      default:
        return <Badge variant="secondary">Unknown</Badge>;
    }
  };

  const getIntegrationIcon = (typeName: string) => {
    const type = integrationTypes.find(t => t.name === typeName);
    return type?.icon || Settings;
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Mock Dashboard Header */}
      <header className="border-b bg-card">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1>walNUT Integrations</h1>
              <p className="text-muted-foreground">
                Manage your infrastructure connections and integrations
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="outline">Import</Button>
              <Button onClick={() => setIsFlyoutOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Add Integration
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Integration Types */}
          <div className="space-y-6">
            <div>
              <h2>Available Integrations</h2>
              <p className="text-muted-foreground">
                Choose an integration type to create a new connection
              </p>
            </div>

            <div className="grid gap-4">
              {integrationTypes.map((type) => {
                const Icon = type.icon;
                return (
                  <Card key={type.name} className="cursor-pointer hover:shadow-md transition-shadow">
                    <CardHeader className="pb-3">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-md bg-primary/10">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div>
                          <CardTitle className="text-base">{type.displayName}</CardTitle>
                          <p className="text-sm text-muted-foreground">
                            {type.description}
                          </p>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <Button 
                        className="w-full"
                        onClick={() => handleCreateConnection(type)}
                      >
                        Create Connection
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>

          {/* Existing Connections */}
          <div className="space-y-6">
            <div>
              <h2>Active Connections</h2>
              <p className="text-muted-foreground">
                Manage your existing integration connections
              </p>
            </div>

            <div className="space-y-4">
              {mockConnections.map((connection) => {
                const Icon = getIntegrationIcon(connection.type);
                const integrationType = integrationTypes.find(type => type.name === connection.type);
                
                return (
                  <Card key={connection.id}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="p-2 rounded-md bg-muted">
                            <Icon className="h-4 w-4" />
                          </div>
                          <div>
                            <p>{connection.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {integrationType?.displayName} • Last seen {connection.lastSeen}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {getStatusBadge(connection.status)}
                          <Button 
                            size="sm" 
                            variant="outline"
                            onClick={() => handleEditConnection(connection)}
                          >
                            <Settings className="h-4 w-4 mr-2" />
                            Configure
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Integration Flyout */}
      <IntegrationFlyout
        isOpen={isFlyoutOpen}
        onClose={() => setIsFlyoutOpen(false)}
        integration={selectedIntegration}
        mode={flyoutMode}
        initialData={editingConnection ? {
          instanceName: editingConnection.name,
          description: `${editingConnection.type} connection`,
          host: 'proxmox.example.com',
          port: 8006,
          node: 'pve-node1',
          verifySSL: true,
          timeout: 30,
          retries: 3
        } : undefined}
      />
    </div>
  );
}