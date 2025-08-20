import React, { useState, useEffect } from 'react';
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
import { toast } from 'sonner';

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
  const [integrationTypes, setIntegrationTypes] = useState<IntegrationType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [manifestDialogOpen, setManifestDialogOpen] = useState(false);
  const [manifestLoading, setManifestLoading] = useState(false);
  const [manifestText, setManifestText] = useState<string>("");
  const [manifestTypeId, setManifestTypeId] = useState<string>("");

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
      setIntegrationTypes(types);
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
      const result = await apiService.uploadIntegrationPackage(selectedFile);
      
      if (result.success) {
        toast.success(`Integration package uploaded: ${result.type_id}`);
        setUploadDialogOpen(false);
        setSelectedFile(null);
        // Reload types
        await loadIntegrationTypes();
      } else {
        throw new Error('Upload failed');
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveType = async (typeId: string) => {
    if (!confirm(`Remove integration type "${typeId}"? This will delete the folder and mark instances as unavailable.`)) {
      return;
    }
    
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
    
    return errorList.join(', ') || 'Unknown error';
  };

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
                </div>
              </div>
              
              <div className="flex justify-end gap-2">
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setUploadDialogOpen(false);
                    setSelectedFile(null);
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
                        {type.errors && (
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
