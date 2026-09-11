import React from 'react';
import type { HealthState } from '../../types';

interface StatusDotProps {
  state: HealthState | 'connected' | 'reconnecting' | 'disconnected' | 'connecting';
  size?: number;
  showLabel?: boolean;
  label?: string;
}

const STATE_CONFIG: Record<string, { color: string; label: string; pulse: boolean }> = {
  healthy: { color: '#22C55E', label: 'Healthy', pulse: true },
  connected: { color: '#22C55E', label: 'Live', pulse: true },
  degraded: { color: '#EAB308', label: 'Degraded', pulse: true },
  reconnecting: { color: '#EAB308', label: 'Reconnecting', pulse: true },
  connecting: { color: '#EAB308', label: 'Connecting', pulse: true },
  offline: { color: '#EF4444', label: 'Offline', pulse: false },
  disconnected: { color: '#EF4444', label: 'Disconnected', pulse: false },
  unknown: { color: '#475569', label: 'Unknown', pulse: false },
};

export const StatusDot: React.FC<StatusDotProps> = ({
  state,
  size = 8,
  showLabel = false,
  label,
}) => {
  const cfg = STATE_CONFIG[state] ?? STATE_CONFIG['unknown'];
  const ringSize = size * 2.5;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
      }}
      aria-label={`Status: ${label ?? cfg.label}`}
    >
      <span
        style={{
          position: 'relative',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: ringSize,
          height: ringSize,
        }}
      >
        {cfg.pulse && (
          <span
            style={{
              position: 'absolute',
              width: size,
              height: size,
              borderRadius: '50%',
              backgroundColor: cfg.color,
              opacity: 0.5,
              animation: 'pulse-ring 1.8s ease-out infinite',
            }}
          />
        )}
        <span
          style={{
            position: 'relative',
            width: size,
            height: size,
            borderRadius: '50%',
            backgroundColor: cfg.color,
            display: 'block',
            flexShrink: 0,
            animation: cfg.pulse ? 'pulse-dot 2s ease-in-out infinite' : 'none',
          }}
        />
      </span>
      {showLabel && (
        <span
          style={{
            fontSize: '11px',
            fontWeight: 500,
            color: cfg.color,
            letterSpacing: '0.04em',
            userSelect: 'none',
          }}
        >
          {label ?? cfg.label}
        </span>
      )}
    </span>
  );
};
