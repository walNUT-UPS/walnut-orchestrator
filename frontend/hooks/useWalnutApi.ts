import { useState, useEffect, useCallback } from 'react';
import { apiService, UPSStatus, SystemHealth, Event } from '../services/api';

export interface WalnutData {
  upsStatus: UPSStatus | null;
  systemHealth: SystemHealth | null;
  events: Event[];
  isLoading: boolean;
  error: string | null;
  wsConnected: boolean;
}

export function useWalnutApi() {
  const [data, setData] = useState<WalnutData>({
    upsStatus: null,
    systemHealth: null,
    events: [],
    isLoading: true,
    error: null,
    wsConnected: false,
  });

  const [ws, setWs] = useState<WebSocket | null>(null);

  // Fetch initial data
  const fetchData = useCallback(async () => {
    try {
      setData(prev => ({ ...prev, isLoading: true, error: null }));

      const [upsStatus, systemHealth, eventsResponse] = await Promise.all([
        apiService.getUPSStatus().catch(() => null),
        apiService.getSystemHealth().catch(() => null),
        apiService.getEvents(10).catch(() => ({ events: [], total: 0 })),
      ]);

      setData(prev => ({
        ...prev,
        upsStatus,
        systemHealth,
        events: eventsResponse.events || [],
        isLoading: false,
      }));
    } catch (error) {
      setData(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to fetch data',
        isLoading: false,
      }));
    }
  }, []);

  // WebSocket connection management
  useEffect(() => {
    let websocket: WebSocket | null = null;
    let reconnectTimeout: NodeJS.Timeout | null = null;

    const connectWebSocket = () => {
      try {
        websocket = apiService.createWebSocket();
        
        websocket.onopen = () => {
          console.log('WebSocket connected');
          setData(prev => ({ ...prev, wsConnected: true }));
          setWs(websocket);
        };

        websocket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            // Handle different message types from WebSocket
            switch (message.type) {
              case 'ups_status':
                setData(prev => ({ ...prev, upsStatus: message.data }));
                break;
              case 'system_health':
                setData(prev => ({ ...prev, systemHealth: message.data }));
                break;
              case 'event':
                setData(prev => ({ 
                  ...prev, 
                  events: [message.data, ...prev.events.slice(0, 9)] // Keep last 10 events
                }));
                break;
              default:
                console.log('Unknown WebSocket message type:', message.type);
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        websocket.onclose = () => {
          console.log('WebSocket disconnected');
          setData(prev => ({ ...prev, wsConnected: false }));
          setWs(null);
          
          // Attempt to reconnect after 5 seconds
          reconnectTimeout = setTimeout(() => {
            console.log('Attempting WebSocket reconnect...');
            connectWebSocket();
          }, 5000);
        };

        websocket.onerror = (error) => {
          console.error('WebSocket error:', error);
          setData(prev => ({ ...prev, wsConnected: false }));
        };

      } catch (error) {
        console.error('Failed to create WebSocket:', error);
        // Retry connection after 5 seconds
        reconnectTimeout = setTimeout(connectWebSocket, 5000);
      }
    };

    // Initial data fetch
    fetchData();
    
    // Start WebSocket connection
    connectWebSocket();

    // Cleanup
    return () => {
      if (websocket) {
        websocket.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
    };
  }, [fetchData]);

  // Manual refresh function
  const refresh = useCallback(() => {
    fetchData();
  }, [fetchData]);

  return {
    ...data,
    refresh,
    ws,
  };
}