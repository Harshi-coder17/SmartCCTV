import { useState, useEffect, useRef, useCallback } from 'react';
import type { Alert } from '../types';
import { getAccessToken } from '../api/client';

export type WSConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

interface UseWebSocketReturn {
  alerts: Alert[];
  connectionState: WSConnectionState;
  clearAlerts: () => void;
}

const MAX_ALERTS = 50;
const BASE_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 30000;
const WS_URL = (() => {
  const base = import.meta.env.VITE_WS_URL ?? '';
  if (base) return base;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/alerts`;
})();

export function useWebSocket(): UseWebSocketReturn {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [connectionState, setConnectionState] = useState<WSConnectionState>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const isMountedRef = useRef(true);

  const clearAlerts = useCallback(() => setAlerts([]), []);

  const connect = useCallback(() => {
    if (!isMountedRef.current) return;

    const token = getAccessToken();
    const url = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;

    setConnectionState((prev) =>
      reconnectAttemptRef.current > 0 ? 'reconnecting' : 'connecting'
    );

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        reconnectAttemptRef.current = 0;
        setConnectionState('connected');
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!isMountedRef.current) return;
        try {
          const payload = JSON.parse(event.data as string);
          // Handle ping/pong
          if (payload.type === 'ping') {
            ws.send(JSON.stringify({ type: 'pong' }));
            return;
          }
          // Handle alert payload
          const alert = payload as Alert;
          if (!alert.alert_id) return;
          setAlerts((prev) => {
            const filtered = prev.filter((a) => a.alert_id !== alert.alert_id);
            const updated = [alert, ...filtered];
            return updated.slice(0, MAX_ALERTS);
          });
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        if (!isMountedRef.current) return;
        setConnectionState('reconnecting');
      };

      ws.onclose = () => {
        if (!isMountedRef.current) return;
        wsRef.current = null;
        setConnectionState('disconnected');
        scheduleReconnect();
      };
    } catch {
      scheduleReconnect();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const scheduleReconnect = useCallback(() => {
    if (!isMountedRef.current) return;
    const delay = Math.min(
      BASE_RECONNECT_MS * Math.pow(2, reconnectAttemptRef.current),
      MAX_RECONNECT_MS
    );
    reconnectAttemptRef.current += 1;
    reconnectTimerRef.current = setTimeout(() => {
      if (isMountedRef.current) connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    isMountedRef.current = true;
    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { alerts, connectionState, clearAlerts };
}
