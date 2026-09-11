import React, { createContext, useContext, type ReactNode } from 'react';
import type { Alert } from '../types';
import type { WSConnectionState } from '../hooks/useWebSocket';
import { useWebSocket } from '../hooks/useWebSocket';

interface WSContextValue {
  alerts: Alert[];
  connectionState: WSConnectionState;
  clearAlerts: () => void;
}

const WSContext = createContext<WSContextValue | null>(null);

export function WSProvider({ children }: { children: ReactNode }) {
  const ws = useWebSocket();
  return <WSContext.Provider value={ws}>{children}</WSContext.Provider>;
}

export function useWSContext(): WSContextValue {
  const ctx = useContext(WSContext);
  if (!ctx) throw new Error('useWSContext must be used within WSProvider');
  return ctx;
}
