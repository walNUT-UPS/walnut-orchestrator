import { TopBar } from './components/TopBar';

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <TopBar />
      
      {/* Main Content Area */}
      <div className="p-6">
        <div className="max-w-6xl mx-auto">
          <div className="bg-card border border-border rounded-lg p-6 shadow-sm">
            <h1 className="mb-4">Dashboard Content</h1>
            <p className="text-muted-foreground mb-4">
              The redesigned top bar features a cleaner navigation system that collapses to a dropdown on mobile devices. 
              The Cards/Table view toggle has been compressed into a unified toggle button, and Settings has been removed 
              from the main navigation while keeping the settings button on the right.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Sample cards to demonstrate the interface */}
              {[...Array(6)].map((_, i) => (
                <div key={i} className="bg-background border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium">Node {i + 1}</h3>
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    Status: Connected
                  </p>
                  <div className="text-xs text-muted-foreground">
                    Last seen: 2 minutes ago
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}