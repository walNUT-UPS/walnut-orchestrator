import { useState } from 'react';
import { PolicyEditor } from './components/PolicyEditor';
import { Button } from './components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from './components/ui/card';
import { Badge } from './components/ui/badge';
import { Zap, Shield, Activity } from 'lucide-react';

export default function App() {
  const [isPolicyEditorOpen, setIsPolicyEditorOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-slate-900">walNUT</h1>
                <p className="text-sm text-slate-600">UPS Orchestration Dashboard</p>
              </div>
            </div>
            <Button onClick={() => setIsPolicyEditorOpen(true)}>
              New Policy
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-2">Policy Management</h2>
          <p className="text-slate-600">
            Configure automated responses to UPS events and system conditions.
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <Card className="shadow-sm">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-600">Active Policies</p>
                  <p className="text-2xl font-semibold text-slate-900">12</p>
                </div>
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Shield className="w-6 h-6 text-blue-600" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-600">Triggered Today</p>
                  <p className="text-2xl font-semibold text-slate-900">3</p>
                </div>
                <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                  <Activity className="w-6 h-6 text-green-600" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-600">UPS Devices</p>
                  <p className="text-2xl font-semibold text-slate-900">8</p>
                </div>
                <div className="w-12 h-12 bg-amber-100 rounded-lg flex items-center justify-center">
                  <Zap className="w-6 h-6 text-amber-600" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Policies List */}
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Smart Plug Control</CardTitle>
                <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Active</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-slate-600 mb-4 text-sm">
                Automatically shutdown non-critical devices when UPS battery drops below 20%.
              </p>
              <div className="space-y-2 mb-4">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Trigger:</span>
                  <span className="font-mono text-slate-900">ups.battery ≤ 20%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Targets:</span>
                  <span className="text-slate-900">5 devices</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setIsPolicyEditorOpen(true)}
                  className="flex-1"
                >
                  Edit
                </Button>
                <Button variant="ghost" size="sm">
                  Disable
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Critical Alert</CardTitle>
                <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Active</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-slate-600 mb-4 text-sm">
                Send immediate notifications when UPS switches to battery power.
              </p>
              <div className="space-y-2 mb-4">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Trigger:</span>
                  <span className="font-mono text-slate-900">ups.status = battery</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Actions:</span>
                  <span className="text-slate-900">Slack, Email</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setIsPolicyEditorOpen(true)}
                  className="flex-1"
                >
                  Edit
                </Button>
                <Button variant="ghost" size="sm">
                  Disable
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm hover:shadow-md transition-shadow">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Maintenance Mode</CardTitle>
                <Badge variant="secondary">Disabled</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-slate-600 mb-4 text-sm">
                Gracefully shutdown all managed hosts during extended power outages.
              </p>
              <div className="space-y-2 mb-4">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Trigger:</span>
                  <span className="font-mono text-slate-900">ups.runtime ≤ 5min</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Targets:</span>
                  <span className="text-slate-900">12 hosts</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => setIsPolicyEditorOpen(true)}
                  className="flex-1"
                >
                  Edit
                </Button>
                <Button variant="ghost" size="sm">
                  Enable
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <PolicyEditor 
        open={isPolicyEditorOpen} 
        onOpenChange={setIsPolicyEditorOpen} 
      />
    </div>
  );
}