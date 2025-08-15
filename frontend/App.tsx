import React, { useState } from 'react';
import { ThemeProvider } from './components/ThemeProvider';
import { TopBar } from './components/TopBar';
import { OverviewScreen } from './components/screens/OverviewScreen';
import { EventsScreen } from './components/screens/EventsScreen';
import { OrchestrationScreen } from './components/screens/OrchestrationScreen';
import { IntegrationsScreen } from './components/screens/IntegrationsScreen';
import { HostsScreen } from './components/screens/HostsScreen';
import { SettingsScreen } from './components/screens/SettingsScreen';
import { Toaster } from './components/ui/sonner';

function App() {
  const [activeTab, setActiveTab] = useState('Overview');
  const [systemStatus, setSystemStatus] = useState<'ok' | 'warn' | 'error'>('ok');
  const alertCount = 3;

  const renderActiveScreen = () => {
    switch (activeTab) {
      case 'Overview':
        return <OverviewScreen />;
      case 'Events':
        return <EventsScreen />;
      case 'Orchestration':
        return <OrchestrationScreen />;
      case 'Integrations':
        return <IntegrationsScreen />;
      case 'Hosts':
        return <HostsScreen />;
      case 'Settings':
        return <SettingsScreen />;
      default:
        return <OverviewScreen />;
    }
  };

  return (
    <ThemeProvider defaultTheme="dark" storageKey="walnut-theme">
      <div className="min-h-screen bg-background">
        <TopBar 
          activeTab={activeTab}
          onTabChange={setActiveTab}
          systemStatus={systemStatus}
          alertCount={alertCount}
        />
        <main className="flex-1">
          {renderActiveScreen()}
        </main>
        <Toaster 
          position="bottom-right"
          richColors
          closeButton
          expand={false}
          visibleToasts={4}
        />
      </div>
    </ThemeProvider>
  );
}

export default App;