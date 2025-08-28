import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { 
  Upload,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  MoreVertical,
  Loader2,
  Folder,
  Eye,
  Trash2
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../ui/dialog';
import { 
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { apiService } from '../../services/api';
import { useConfirm } from '../ui/confirm';
import { toast } from 'sonner';
import { cn } from '../ui/utils';

interface IntegrationType {
  id: string;
  name: string;
  version: string;
  min_core_version: string;
  category: string;
  status: string;
  errors?: any;
  capabilities: any[];
  schema_connection: any;
  last_validated_at?: string;
  created_at: string;
  updated_at: string;
}

// Status color mapping
const getStatusColor = (status: string) => {
  switch (status) {
    case 'valid':
      return 'text-status-ok';
    case 'checking':
      return 'text-status-warn';
    case 'invalid':
      return 'text-status-error';
    case 'unavailable':
      return 'text-muted-foreground';
    default:
      return 'text-muted-foreground';
  }
};

const getStatusBadge = (status: string) => {
  switch (status) {
    case 'valid':
      return <Badge className="bg-status-ok/10 text-status-ok border-status-ok">Valid</Badge>;
    case 'checking':
      return <Badge className="bg-status-warn/10 text-status-warn border-status-warn">Checking...</Badge>;
    case 'invalid':
      return <Badge className="bg-status-error/10 text-status-error border-status-error">Invalid</Badge>;
    case 'unavailable':
      return <Badge variant="outline">Unavailable</Badge>;
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
};

export function IntegrationsSettingsScreen() {
  const confirmDialog = useConfirm();
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadLogs, setUploadLogs] = useState<Array<{ ts: string; level: string; message: string; step?: string }>>([]);
  const [streamJobId, setStreamJobId] = useState<string | null>(null);
  const wsRef = React.useRef<WebSocket | null>(null);
  const [streamStatus, setStreamStatus] = useState<"idle" | "connecting" | "streaming" | "fallback" | "done" | "error">("idle");
  const [uploadResult, setUploadResult] = useState<{ success: boolean; typeId?: string; installedPath?: string; errors?: any } | null>(null);
  const consoleRef = useRef<HTMLDivElement | null>(null);
  const [manifestDialogOpen, setManifestDialogOpen] = useState(false);
  const [manifestLoading, setManifestLoading] = useState(false);
  const [manifestText, setManifestText] = useState<string>("");
  const [manifestTypeId, setManifestTypeId] = useState<string>("");
  const [errorsDialogOpen, setErrorsDialogOpen] = useState(false);
  const [errorsTypeId, setErrorsTypeId] = useState<string>("");
  const [errorsPayload, setErrorsPayload] = useState<any>(null);

  const handleCopyManifest = async () => {
    try {
      await navigator.clipboard.writeText(manifestText);
      toast.success('Copied manifest');
    } catch (err) {
      // Fallback for browsers/environments without clipboard permission
      try {
        const ta = document.createElement('textarea');
        ta.value = manifestText;
        ta.style.position = 'fixed';
        ta.style.left = '-1000px';
        ta.style.top = '-1000px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (ok) {
          toast.success('Copied manifest');
        } else {
          toast.error('Copy failed');
        }
      } catch (e) {
        toast.error('Copy failed');
      }
    }
  };

  // Load integration types
  const loadIntegrationTypes = async (rescan = false) => {
    try {
      setIsLoading(true);
      setError(null);
      
      // If rescan is requested, set scanning state
      if (rescan) {
        setIsScanning(true);
        // Trigger rescan in background
        setTimeout(() => setIsScanning(false), 3000); // Mock 3 second scan
      }
      
      // Call the new API endpoint
      const types = await apiService.getIntegrationTypes(rescan);
      // Filter out unavailable integrations (deleted types that should not be shown)
      const availableTypes = types.filter(type => type.status !== 'unavailable');
      setIntegrationTypes(availableTypes);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load integration types');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadIntegrationTypes();
  }, []);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (!file.name.endsWith('.int')) {
        toast.error('Please select a .int file');
        return;
      }
      if (file.size > 10 * 1024 * 1024) { // 10MB limit
        toast.error('File too large (max 10MB)');
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    
    try {
      setIsUploading(true);
      setUploadLogs([]);
      setStreamStatus("connecting");
      
      // Start job first to get job_id
      let job_id: string | null = null;
      try {
        const started = await apiService.uploadIntegrationPackageStream(selectedFile);
        job_id = started.job_id;
        setStreamJobId(job_id);
      } catch (e) {
        console.error('Failed to start upload job:', e);
        return;
      }
      // Connect directly to job-scoped WebSocket
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
      const cookieStr = document.cookie || '';
      const token = (cookieStr.split('; ').find((c) => c.startsWith('walnut_access='))?.split('=')[1])
        || (cookieStr.split('; ').find((c) => c.startsWith('fastapiusersauth='))?.split('=')[1]);
      const wsUrl = `${protocol}://${location.host}/ws/integrations/jobs/${job_id}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      // Fallback to direct upload if stream cannot start
      const fallbackDirect = async () => {
        if (!isUploading) return;
        try {
          setStreamStatus("fallback");
          const result = await apiService.uploadIntegrationPackage(selectedFile);
          if (result.logs) setUploadLogs(result.logs);
          if (result.success) {
            toast.success(`Integration package uploaded: ${result.type_id}`);
            setUploadDialogOpen(false);
            setSelectedFile(null);
            await loadIntegrationTypes();
            setStreamStatus("done");
          } else {
            setStreamStatus("error");
            toast.error(result.message || 'Upload failed');
          }
        } catch (err: any) {
          setStreamStatus("error");
          if (err?.logs) setUploadLogs(err.logs);
          toast.error(err instanceof Error ? err.message : 'Upload failed');
        } finally {
          setIsUploading(false);
          if (wsRef.current) { try { wsRef.current.close(); } catch {} wsRef.current = null; }
        }
      };
      
      ws.onopen = () => {
        setStreamStatus('streaming');
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (!msg || !msg.type || !msg.data) return;
          if (msg.type === 'integration_job.event' && msg.data.job_id === job_id) {
            setUploadLogs((prev) => [...prev, { ts: msg.data.ts, level: msg.data.level, message: msg.data.message, step: msg.data.phase }]);
          }
          if (msg.type === 'integration_job.done' && msg.data.job_id === job_id) {
            ws.close();
            wsRef.current = null;
            if (msg.data.success) {
              toast.success(`Integration uploaded: ${msg.data.type_id}`);
              setStreamStatus("done");
              setUploadResult({ success: true, typeId: msg.data.type_id, installedPath: msg.data.installed_path });
              loadIntegrationTypes();
            } else {
              setStreamStatus("error");
              // stash server trace globally for the ServerTraceBlock to pick up
              (window as any).__walnut_last_upload_trace = msg.data.trace || null;
              setUploadResult({ success: false, typeId: msg.data.type_id, errors: msg.data.error || msg.data.errors });
              toast.error(`Upload failed: ${msg.data.error || 'Unknown error'}`);
            }
            setIsUploading(false);
          }
        } catch (e) {
          console.error('WebSocket message parsing error:', e);
        }
      };
      ws.onerror = () => { if (isUploading) fallbackDirect(); };
      // Safety timeout if WS doesn't open
      setTimeout(() => {
        if (isUploading && wsRef.current && wsRef.current.readyState !== WebSocket.OPEN) {
          try { wsRef.current.close(); } catch {}
          fallbackDirect();
        }
      }, 3000);
    } catch (err: any) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
      setIsUploading(false);
    }
  };

  const handleRemoveType = async (typeId: string) => {
    const ok = await confirmDialog({
      title: 'Remove integration type?',
      description: `Remove integration type "${typeId}"? This will delete the folder and mark instances as unavailable.`,
      confirmText: 'Remove',
      destructive: true,
    });
    if (!ok) return;
    
    try {
      await apiService.removeIntegrationType(typeId);
      toast.success(`Integration type "${typeId}" removed`);
      await loadIntegrationTypes();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to remove integration type');
    }
  };

  const handleRevalidateType = async (typeId: string) => {
    try {
      await apiService.revalidateIntegrationType(typeId);
      toast.success(`Integration type "${typeId}" revalidated`);
      await loadIntegrationTypes();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to revalidate integration type');
    }
  };

  const handleViewManifest = async (typeId: string) => {
    try {
      setManifestDialogOpen(true);
      setManifestLoading(true);
      setManifestText("");
      setManifestTypeId(typeId);
      const res = await apiService.getIntegrationManifest(typeId);
      setManifestText(res.manifest_yaml || "");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to load manifest');
      setManifestDialogOpen(false);
    } finally {
      setManifestLoading(false);
    }
  };

  const getErrorTooltip = (errors: any) => {
    if (!errors) return '';
    
    const errorList = [];
    if (errors.schema_error) errorList.push('Schema validation failed');
    if (errors.driver_missing) errorList.push('Driver file missing');
    if (errors.import_error) errorList.push('Driver import failed');
    if (errors.capability_mismatch) errorList.push('Capability method mismatch');
    if (errors.core_version_incompatible) {
      const req = errors.core_version_incompatible.required;
      const cur = errors.core_version_incompatible.current;
      errorList.push(`Core version incompatible (requires ${req}, current ${cur})`);
    }
    if (errors.validation_exception) errorList.push('Validation exception');
    
    return errorList.join(', ') || 'Unknown error';
  };

  const handleViewErrors = (typeId: string, errors: any) => {
    setErrorsTypeId(typeId);
    setErrorsPayload(errors);
    setErrorsDialogOpen(true);
  };

  // Auto-scroll console when new logs arrive
  useEffect(() => {
    if (!consoleRef.current) return;
    const el = consoleRef.current;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (nearBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [uploadLogs.length]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Integration Types</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage integration types from filesystem and uploaded packages
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            onClick={() => loadIntegrationTypes(true)} 
            disabled={isLoading || isScanning}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${isScanning ? 'animate-spin' : ''}`} />
            {isScanning ? 'Scanning...' : 'Rescan'}
          </Button>
          
          <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Upload className="w-4 h-4 mr-2" />
                Upload Package
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Upload Integration Package</DialogTitle>
                <DialogDescription>
                  Upload a .int file (ZIP archive) containing an integration plugin
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Select .int file</label>
                  <Input 
                    type="file" 
                    accept=".int" 
                    onChange={handleFileSelect}
                    className="cursor-pointer"
                  />
                </div>
                
                {selectedFile && (
                  <div className="p-3 bg-muted/20 rounded-lg">
                    <div className="flex items-center gap-2">
                      <Folder className="w-4 h-4" />
                      <span className="text-sm font-medium">{selectedFile.name}</span>
                      <Badge variant="outline" className="ml-auto">
                        {(selectedFile.size / 1024).toFixed(1)} KB
                      </Badge>
                    </div>
                  </div>
                )}
                
                <div className="bg-muted/20 p-3 rounded-lg">
                  <h4 className="text-sm font-medium mb-2">Upload Process:</h4>
                  <ul className="text-xs text-muted-foreground space-y-1">
                    <li>• Validates ZIP structure and content</li>
                    <li>• Checks plugin.yaml manifest</li>
                    <li>• Validates driver implementation</li>
                    <li>• Installs to ./integrations/&lt;id&gt;/</li>
                    <li>• Runs full validation pipeline</li>
                  </ul>
                  {isUploading && (
                    <div className="text-xs mt-2 text-muted-foreground">
                      {streamStatus === 'connecting' && 'Connecting to stream...'}
                      {streamStatus === 'streaming' && 'Streaming logs...'}
                      {streamStatus === 'fallback' && 'Stream unavailable; using direct upload...'}
                      {streamStatus === 'done' && 'Completed'}
                      {streamStatus === 'error' && 'Error occurred; see logs below'}
                      {streamJobId && <span className="ml-2 font-mono">job_id: {streamJobId}</span>}
                    </div>
                  )}
                </div>

                {/* Stepper */}
                <div className="flex items-center gap-2 text-xs">
                  {['upload','unpack','manifest','driver','install','registry','final'].map((p) => (
                    <div key={p} className="flex items-center gap-1">
                      <div className={`w-2.5 h-2.5 rounded-full ${uploadLogs.some(l => (l.step||'').includes(p) ) ? 'bg-emerald-500' : 'bg-border'}`}></div>
                      <span className="text-muted-foreground capitalize">{p}</span>
                      <span className="text-border">/</span>
                    </div>
                  ))}
                </div>

                {/* Console controls */}
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => {
                    const text = uploadLogs.map(l => `${new Date(l.ts).toISOString()} [${l.level.toUpperCase()}] ${l.step?`[${l.step}]`:''} ${l.message}`).join('\n');
                    navigator.clipboard.writeText(text);
                  }}>Copy All</Button>
                  <Button variant="outline" size="sm" onClick={() => {
                    const blob = new Blob([JSON.stringify(uploadLogs, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url; a.download = `upload-logs-${Date.now()}.json`; a.click(); URL.revokeObjectURL(url);
                  }}>Download Logs</Button>
                  <Button variant="outline" size="sm" onClick={() => setUploadLogs([])}>Clear</Button>
                </div>

                {uploadLogs.length > 0 && (
                  <div className="max-h-56 overflow-auto rounded-md border border-border bg-background font-mono text-xs" id="upload-console" ref={consoleRef}>
                    <table className="w-full">
                      <tbody>
                        {uploadLogs.map((l, idx) => (
                          <tr key={idx} className="border-b border-border/50">
                            <td className="px-2 py-1 whitespace-nowrap text-muted-foreground">{new Date(l.ts).toLocaleTimeString()}</td>
                            <td className="px-2 py-1 whitespace-nowrap uppercase">
                              <span className={
                                l.level === 'error' ? 'text-red-600 dark:text-red-400' :
                                l.level === 'warn' ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'
                              }>{l.level}</span>
                            </td>
                            <td className="px-2 py-1">
                              <span className="text-muted-foreground">{l.step ? `[${l.step}] ` : ''}</span>{l.message}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Server trace toggle (when available) */}
                {uploadLogs.length > 0 && (
                  <ServerTraceBlock logs={uploadLogs} streamJobId={streamJobId} />
                )}

                {/* Summary banner on completion */}
                {uploadResult && (
                  <div className={`rounded-md border p-3 ${uploadResult.success ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-red-500/40 bg-red-500/5'}`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium">
                          {uploadResult.success ? 'Integration uploaded and registered' : 'Integration upload completed with errors'}
                        </div>
                        {uploadResult.typeId && (
                          <div className="text-xs text-muted-foreground">Type ID: <span className="font-mono">{uploadResult.typeId}</span></div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button size="sm" variant="outline" onClick={() => {
                          setUploadDialogOpen(false);
                          setSelectedFile(null);
                        }}>Open in Settings</Button>
                        {uploadResult.typeId && (
                          <Button size="sm" variant="destructive" onClick={async () => {
                            try {
                              await apiService.removeIntegrationType(uploadResult.typeId!);
                              toast.success('Integration removed');
                              await loadIntegrationTypes();
                              setUploadDialogOpen(false);
                            } catch (e:any) {
                              toast.error(e?.message || 'Failed to remove integration');
                            }
                          }}>Remove</Button>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              
              <div className="flex justify-end gap-2">
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setUploadDialogOpen(false);
                    setSelectedFile(null);
                    setUploadLogs([]);
                    setStreamJobId(null);
                    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
                  }}
                >
                  Cancel
                </Button>
                <Button 
                  onClick={handleUpload} 
                  disabled={!selectedFile || isUploading}
                >
                  {isUploading ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Uploading...</>
                  ) : (
                    <>Upload Package</>
                  )}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Loading integration types...</span>
        </div>
      )}
      
      {/* Error State */}
      {error && (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <XCircle className="w-12 h-12 text-status-error mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Error Loading Integration Types</h3>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={() => loadIntegrationTypes()} variant="outline">
              <RefreshCw className="w-4 h-4 mr-2" />
              Try Again
            </Button>
          </div>
        </div>
      )}
      
      {/* Empty State */}
      {!isLoading && !error && integrationTypes.length === 0 && (
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center mx-auto mb-4">
              <Upload className="w-6 h-6 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold mb-2">No Integration Types</h3>
            <p className="text-muted-foreground mb-4">
              No integration types found. Upload a package or place folders in ./integrations/
            </p>
            <Button onClick={() => setUploadDialogOpen(true)}>
              <Upload className="w-4 h-4 mr-2" />
              Upload Package
            </Button>
          </div>
        </div>
      )}
      
      {/* Integration Types Table */}
      {!isLoading && !error && integrationTypes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <span>Integration Types</span>
              <Badge variant="outline">{integrationTypes.length}</Badge>
            </CardTitle>
            <CardDescription>
              Validated plugins that can be instantiated as connections in the Hosts tab
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Capabilities</TableHead>
                    <TableHead>Last Validated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {integrationTypes.map((type) => (
                    <TableRow key={type.id} className="hover:bg-muted/50">
                      <TableCell>
                        <div className="space-y-1">
                          <div className="font-medium">{type.name}</div>
                          <div className="font-mono text-xs text-muted-foreground">{type.id}</div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">v{type.version}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{type.category}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {type.status === 'valid' ? (
                            <CheckCircle2 className="w-4 h-4 text-status-ok" />
                          ) : type.status === 'checking' ? (
                            <Loader2 className="w-4 h-4 animate-spin text-status-warn" />
                          ) : type.status === 'invalid' ? (
                            <XCircle className="w-4 h-4 text-status-error" />
                          ) : (
                            <AlertTriangle className="w-4 h-4 text-muted-foreground" />
                          )}
                          {getStatusBadge(type.status)}
                        </div>
                        {type.status === 'invalid' && type.errors && (
                          <div className="text-xs text-status-error mt-1" title={getErrorTooltip(type.errors)}>
                            {getErrorTooltip(type.errors)}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1 max-w-48">
                          {type.capabilities.slice(0, 3).map((cap, index) => (
                            <Badge key={index} variant="outline" className="text-xs">
                              {cap.id}
                            </Badge>
                          ))}
                          {type.capabilities.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{type.capabilities.length - 3}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {type.last_validated_at ? (
                          new Date(type.last_validated_at).toLocaleString()
                        ) : (
                          'Never'
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button data-testid="type-actions-trigger" variant="ghost" size="sm">
                              <MoreVertical className="w-4 h-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleRevalidateType(type.id)}>
                              <RefreshCw className="w-4 h-4 mr-2" />
                              Revalidate
                            </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleViewManifest(type.id)}>
                            <Eye className="w-4 h-4 mr-2" />
                            View Manifest
                          </DropdownMenuItem>
                            {type.status === 'invalid' && type.errors && (
                              <DropdownMenuItem onClick={() => handleViewErrors(type.id, type.errors)}>
                                <AlertTriangle className="w-4 h-4 mr-2" />
                                View Errors
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem 
                              onClick={() => handleRemoveType(type.id)}
                              className="text-destructive"
                            >
                              <Trash2 className="w-4 h-4 mr-2" />
                              Remove
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
      
      {/* Info Panel */}
      <Dialog open={manifestDialogOpen} onOpenChange={setManifestDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Manifest: {manifestTypeId}</DialogTitle>
            <DialogDescription>plugin.yaml</DialogDescription>
          </DialogHeader>
          <div className="border rounded-md bg-muted/20 max-h-[60vh] overflow-auto">
            {manifestLoading ? (
              <div className="p-4 text-sm text-muted-foreground flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading manifest...
              </div>
            ) : (
              <pre className="p-4 text-xs whitespace-pre-wrap break-all">
                {manifestText}
              </pre>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={handleCopyManifest}
              disabled={!manifestText}
            >
              Copy
            </Button>
            <Button onClick={() => setManifestDialogOpen(false)}>Close</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Errors Panel */}
      <Dialog open={errorsDialogOpen} onOpenChange={setErrorsDialogOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Validation Errors: {errorsTypeId}</DialogTitle>
            <DialogDescription>Details from the validator and driver import</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {errorsPayload ? (
              <>
                {/* Summary line derived from tooltip */}
                <div className="text-sm text-status-error">{getErrorTooltip(errorsPayload)}</div>
                {/* Known traces */}
                {errorsPayload.trace && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Trace</div>
                    <pre className="bg-muted/30 border rounded p-3 text-xs overflow-auto max-h-72 whitespace-pre-wrap">{errorsPayload.trace}</pre>
                  </div>
                )}
                {errorsPayload.import_error_trace && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Import Error Trace</div>
                    <pre className="bg-muted/30 border rounded p-3 text-xs overflow-auto max-h-72 whitespace-pre-wrap">{errorsPayload.import_error_trace}</pre>
                  </div>
                )}
                {errorsPayload.validation_error_trace && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Validation Error Trace</div>
                    <pre className="bg-muted/30 border rounded p-3 text-xs overflow-auto max-h-72 whitespace-pre-wrap">{errorsPayload.validation_error_trace}</pre>
                  </div>
                )}
                {/* Raw errors JSON as last resort */}
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Raw Errors</div>
                  <pre className="bg-muted/30 border rounded p-3 text-xs overflow-auto max-h-72 whitespace-pre-wrap">{JSON.stringify(errorsPayload, null, 2)}</pre>
                </div>
              </>
            ) : (
              <div className="text-muted-foreground text-sm">No error details.</div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How Integration Types Work</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-muted-foreground space-y-2">
            <p>Integration types define reusable plugins that can be instantiated as connections:</p>
            <ul className="space-y-1 ml-4">
              <li>• <strong>Types</strong> are validated plugins from ./integrations/&lt;slug&gt;/ folders</li>
              <li>• <strong>Instances</strong> are configured connections created in the Hosts tab</li>
              <li>• Only "Valid" types can be used to create instances</li>
              <li>• Upload .int packages or place folders manually in the filesystem</li>
              <li>• Use "Rescan" to discover new types or validate changes</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ServerTraceBlock({ logs, streamJobId }: { logs: Array<{ ts: string; level: string; message: string; step?: string }>; streamJobId: string | null }) {
  // We attach server traces via error done messages; log rows won't contain trace, so we show a collapsible area fed by latest error toast if present
  const [open, setOpen] = React.useState(false);
  const [trace, setTrace] = React.useState<string | null>(null);

  React.useEffect(() => {
    // The frontend sets error toast but not trace here; to carry trace, we stash it on window during WS done or direct error
    const anyWin = window as any;
    if (anyWin.__walnut_last_upload_trace) {
      setTrace(anyWin.__walnut_last_upload_trace as string);
    }
  }, [logs, streamJobId]);

  if (!trace) return null;

  return (
    <div className="rounded-md border border-border bg-muted/10 p-2">
      <button
        className={cn('text-xs underline text-muted-foreground hover:text-foreground')}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? 'Hide server trace' : 'View server trace'}
      </button>
      {open && (
        <pre className="mt-2 text-xs bg-background border border-border rounded-md p-3 overflow-auto max-h-56">
          {trace}
        </pre>
      )}
    </div>
  );
}
