import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ThemeProvider } from './components/ThemeProvider';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { TopBar } from './components/TopBar';
import { OverviewScreen } from './components/screens/OverviewScreen';
import { EventsScreen } from './components/screens/EventsScreen';
import { OrchestrationScreen } from './components/screens/OrchestrationScreen';
import { IntegrationsScreen } from './components/screens/IntegrationsScreen';
import { HostsScreen } from './components/screens/HostsScreen';
import { SettingsScreen } from './components/screens/SettingsScreen';
import { Toaster } from './components/ui/sonner';

// Main dashboard component that includes routing
function DashboardApp() {
  const location = useLocation();
  const systemStatus: 'ok' | 'warn' | 'error' = 'ok'; // This should come from system health API
  const alertCount = 3; // This should come from alerts API

  // Extract active tab from current route
  const getActiveTabFromPath = (pathname: string) => {
    const path = pathname.slice(1); // Remove leading slash
    const tab = path.charAt(0).toUpperCase() + path.slice(1);
    return ['Overview', 'Events', 'Orchestration', 'Hosts', 'Settings'].includes(tab) 
      ? tab 
      : 'Overview';
  };

  const activeTab = getActiveTabFromPath(location.pathname);

  return (
    <div className="min-h-screen bg-background">
      <TopBar 
        activeTab={activeTab}
        systemStatus={systemStatus}
        alertCount={alertCount}
      />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<OverviewScreen />} />
          <Route path="/events" element={<EventsScreen />} />
          <Route path="/orchestration" element={<OrchestrationScreen />} />
          <Route path="/hosts" element={<HostsScreen />} />
          <Route path="/settings/*" element={<SettingsScreen />} />
        </Routes>
      </main>
      <Toaster 
        position="bottom-right"
        richColors
        closeButton
        expand={false}
        visibleToasts={4}
      />
    </div>
  );
}

// Main App component with all providers
function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="walnut-theme">
      <AuthProvider>
        <Router>
          <ProtectedRoute>
            <DashboardApp />
          </ProtectedRoute>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;