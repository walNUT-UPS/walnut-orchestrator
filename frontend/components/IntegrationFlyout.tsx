import React, { useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Switch } from './ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { Label } from './ui/label';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Loader2, Eye, EyeOff, ChevronDown, ChevronRight, TestTube, Check, X } from 'lucide-react';

interface IntegrationField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'password' | 'boolean';
  required?: boolean;
  defaultValue?: string | number | boolean;
  placeholder?: string;
  description?: string;
}

interface Integration {
  name: string;
  displayName: string;
  fields: IntegrationField[];
}

interface IntegrationFlyoutProps {
  isOpen: boolean;
  onClose: () => void;
  integration: Integration | null;
  mode: 'create' | 'edit';
  initialData?: Record<string, any>;
}

export function IntegrationFlyout({ 
  isOpen, 
  onClose, 
  integration, 
  mode, 
  initialData = {} 
}: IntegrationFlyoutProps) {
  const [formData, setFormData] = useState({
    instanceName: initialData.instanceName || '',
    description: initialData.description || '',
    ...integration?.fields.reduce((acc, field) => ({
      ...acc,
      [field.name]: initialData[field.name] || field.defaultValue || ''
    }), {}) || {}
  });

  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleInputChange = (name: string, value: any) => {
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear error when user starts typing
    if (errors[name]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[name];
        return newErrors;
      });
    }
  };

  const togglePasswordVisibility = (fieldName: string) => {
    setShowPasswords(prev => ({
      ...prev,
      [fieldName]: !prev[fieldName]
    }));
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    // Validate instance name
    if (!formData.instanceName.trim()) {
      newErrors.instanceName = 'Instance name is required';
    }

    // Validate required integration fields
    integration?.fields.forEach(field => {
      if (field.required && !formData[field.name]) {
        newErrors[field.name] = `${field.label} is required`;
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleTestConnection = async () => {
    if (!validateForm()) return;

    setIsTestingConnection(true);
    setTestResult(null);

    // Simulate API call
    try {
      await new Promise(resolve => setTimeout(resolve, 2000));
      // Mock success/failure
      setTestResult(Math.random() > 0.3 ? 'success' : 'error');
    } catch (error) {
      setTestResult('error');
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleSave = () => {
    if (!validateForm()) return;
    
    console.log('Saving integration:', formData);
    onClose();
  };

  const renderField = (field: IntegrationField) => {
    const error = errors[field.name];
    const value = formData[field.name];

    switch (field.type) {
      case 'text':
      case 'number':
        return (
          <div key={field.name} className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor={field.name}>
                {field.label}
              </Label>
              {field.required && (
                <Badge variant="outline" className="text-xs px-1 py-0">
                  Required
                </Badge>
              )}
            </div>
            <Input
              id={field.name}
              type={field.type}
              value={value}
              onChange={(e) => handleInputChange(field.name, field.type === 'number' ? Number(e.target.value) : e.target.value)}
              placeholder={field.placeholder}
              className={error ? 'border-destructive' : ''}
            />
            {field.description && (
              <p className="text-sm text-muted-foreground">{field.description}</p>
            )}
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>
        );

      case 'password':
        return (
          <div key={field.name} className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor={field.name}>
                {field.label}
              </Label>
              {field.required && (
                <Badge variant="outline" className="text-xs px-1 py-0">
                  Required
                </Badge>
              )}
            </div>
            <div className="relative">
              <Input
                id={field.name}
                type={showPasswords[field.name] ? 'text' : 'password'}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                placeholder={field.placeholder}
                className={`pr-10 ${error ? 'border-destructive' : ''}`}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => togglePasswordVisibility(field.name)}
              >
                {showPasswords[field.name] ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {field.description && (
              <p className="text-sm text-muted-foreground">{field.description}</p>
            )}
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>
        );

      case 'boolean':
        return (
          <div key={field.name} className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Label htmlFor={field.name}>
                  {field.label}
                </Label>
                {field.required && (
                  <Badge variant="outline" className="text-xs px-1 py-0">
                    Required
                  </Badge>
                )}
              </div>
              <Switch
                id={field.name}
                checked={value}
                onCheckedChange={(checked) => handleInputChange(field.name, checked)}
              />
            </div>
            {field.description && (
              <p className="text-sm text-muted-foreground">{field.description}</p>
            )}
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  if (!integration) return null;

  // Split fields into main and advanced
  const mainFields = integration.fields.filter(field => 
    !['timeout', 'retries', 'heartbeatInterval'].includes(field.name)
  );
  const advancedFields = integration.fields.filter(field => 
    ['timeout', 'retries', 'heartbeatInterval'].includes(field.name)
  );

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent className="w-full sm:max-w-[640px] flex flex-col">
        <SheetHeader className="space-y-1">
          <SheetTitle>
            {mode === 'create' ? 'New Connection' : 'Edit Connection'}
          </SheetTitle>
          <SheetDescription>
            {integration.displayName}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto space-y-6 py-4">
          {/* Basic Information Section */}
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-lg">Basic Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label htmlFor="instanceName">Instance Name</Label>
                  <Badge variant="outline" className="text-xs px-1 py-0">
                    Required
                  </Badge>
                </div>
                <Input
                  id="instanceName"
                  value={formData.instanceName}
                  onChange={(e) => handleInputChange('instanceName', e.target.value)}
                  placeholder="Enter a unique name for this connection"
                  className={errors.instanceName ? 'border-destructive' : ''}
                />
                {errors.instanceName && (
                  <p className="text-sm text-destructive">{errors.instanceName}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={formData.description}
                  onChange={(e) => handleInputChange('description', e.target.value)}
                  placeholder="Optional description for this connection"
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>

          {/* Connection Settings Section */}
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-lg">Connection Settings</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {mainFields.map(renderField)}
            </CardContent>
          </Card>

          {/* Advanced Settings Section */}
          {advancedFields.length > 0 && (
            <Card>
              <Collapsible open={isAdvancedOpen} onOpenChange={setIsAdvancedOpen}>
                <CollapsibleTrigger className="w-full">
                  <CardHeader className="pb-4 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">Advanced Settings</CardTitle>
                      {isAdvancedOpen ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </div>
                  </CardHeader>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <CardContent className="space-y-4 pt-0">
                    {advancedFields.map(renderField)}
                  </CardContent>
                </CollapsibleContent>
              </Collapsible>
            </Card>
          )}
        </div>

        {/* Test Connection Result */}
        {testResult && (
          <div className={`flex items-center gap-2 px-4 py-2 rounded-md mb-4 ${
            testResult === 'success' 
              ? 'bg-green-50 text-green-800 border border-green-200' 
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}>
            {testResult === 'success' ? (
              <Check className="h-4 w-4" />
            ) : (
              <X className="h-4 w-4" />
            )}
            <span className="text-sm">
              {testResult === 'success' 
                ? 'Connection test successful!' 
                : 'Connection test failed. Please check your settings.'
              }
            </span>
          </div>
        )}

        {/* Footer Actions */}
        <Separator />
        <div className="flex items-center justify-between gap-3 pt-4">
          <Button
            variant="outline"
            onClick={handleTestConnection}
            disabled={isTestingConnection}
            className="flex items-center gap-2"
          >
            {isTestingConnection ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <TestTube className="h-4 w-4" />
            )}
            Test Connection
          </Button>
          
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave}>
              Save Connection
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}