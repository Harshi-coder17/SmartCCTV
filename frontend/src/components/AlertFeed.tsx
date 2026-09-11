import React, { useState } from 'react';
import type { Alert, EventType } from '../types';
import { useWSContext } from '../context/WSContext';
import { SeverityBadge } from './ui/SeverityBadge';
import { StatusDot } from './ui/StatusDot';
import { Button } from './ui/Button';
import { disposeAlert } from '../api/client';

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const EVENT_TYPE_LABELS: Record<EventType, string> = {
  perimeter_intrusion: 'Zone Intrusion',
  no_traceable_origin: 'No Origin Trace',
  route_anomaly: 'Route Anomaly',
  off_hours_activity: 'Night Movement',
  behavior_anomaly: 'Behavior Anomaly',
  unknown_identity: 'Unknown Identity',
  group_clustering: 'Group Clustering',
  vehicle_intrusion: 'Vehicle Intrusion',
};

function getFactorTags(alert: Alert): string[] {
  const tags: string[] = [];
  const fb = alert.factor_breakdown;
  if (fb.zone_violation) tags.push('Zone Violation');
  if (fb.no_traceable_origin) tags.push('No Origin');
  if (fb.route_anomaly) tags.push('Route Anomaly');
  if (fb.off_hours) tags.push('Night Activity');
  if (fb.behavior_signals) tags.push('Behavior Signal');
  return tags;
}

interface AlertCardProps {
  alert: Alert;
  onDispose: (alertId: string, disposition: string) => Promise<void>;
  onSelect?: () => void;
  compact?: boolean;
}

const AlertCard: React.FC<AlertCardProps> = ({ alert, onDispose, onSelect, compact = false }) => {
  const [disposing, setDisposing] = useState<string | null>(null);
  const tags = getFactorTags(alert);

  const severityBorderColor: Record<string, string> = {
    CRITICAL: 'var(--critical)',
    HIGH: 'var(--high)',
    MEDIUM: 'var(--medium)',
    LOW: 'var(--low)',
  };

  const handleDispose = async (disposition: string) => {
    setDisposing(disposition);
    try {
      await onDispose(alert.alert_id, disposition);
    } finally {
      setDisposing(null);
    }
  };

  return (
    <div
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${severityBorderColor[alert.severity] ?? 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: compact ? '10px 12px' : '12px 14px',
        animation: 'slideInTop 250ms ease',
        transition: 'border-color 150ms',
      }}
    >
      {/* Top row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <SeverityBadge severity={alert.severity} size="sm" />
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
            {EVENT_TYPE_LABELS[alert.event_type] ?? alert.event_type.replace(/_/g, ' ')}
          </span>
        </div>
        <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--mono)', whiteSpace: 'nowrap', flexShrink: 0 }}>
          {timeAgo(alert.timestamp)}
        </span>
      </div>

      {/* Camera + risk */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M23 7l-7 5 7 5V7z" />
            <rect x="1" y="5" width="15" height="14" rx="2" />
          </svg>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'var(--mono)' }}>
            {alert.camera_name}
          </span>
        </div>
        <div style={{ height: 10, width: 1, backgroundColor: 'var(--border)' }} aria-hidden="true" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div
            style={{
              width: 40,
              height: 4,
              backgroundColor: 'var(--border)',
              borderRadius: 2,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${alert.risk_score}%`,
                backgroundColor: severityBorderColor[alert.severity],
                borderRadius: 2,
              }}
            />
          </div>
          <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-secondary)', fontWeight: 600 }}>
            {alert.risk_score}
          </span>
        </div>
      </div>

      {/* Factor tags */}
      {!compact && tags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
          {tags.map((tag) => (
            <span
              key={tag}
              style={{
                fontSize: 10,
                padding: '2px 6px',
                backgroundColor: 'rgba(0,212,170,0.08)',
                border: '1px solid rgba(0,212,170,0.2)',
                borderRadius: 3,
                color: 'var(--accent)',
                fontWeight: 500,
                letterSpacing: '0.03em',
              }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      {!compact && alert.disposition === 'pending' && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <Button
            size="sm"
            variant="danger"
            loading={disposing === 'confirmed'}
            onClick={() => handleDispose('confirmed')}
          >
            Confirm
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={disposing === 'false_positive'}
            onClick={() => handleDispose('false_positive')}
          >
            False Positive
          </Button>
          <Button
            size="sm"
            variant="ghost"
            loading={disposing === 'inconclusive'}
            onClick={() => handleDispose('inconclusive')}
          >
            Inconclusive
          </Button>
          {onSelect && (
            <Button size="sm" variant="secondary" onClick={onSelect} style={{ marginLeft: 'auto' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                <polyline points="17,8 12,3 7,8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Evidence
            </Button>
          )}
        </div>
      )}

      {!compact && alert.disposition !== 'pending' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M9 11l3 3L22 4" />
            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
          </svg>
          <span style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'capitalize' }}>
            Disposition: {alert.disposition.replace(/_/g, ' ')}
          </span>
        </div>
      )}
    </div>
  );
};

interface AlertFeedProps {
  compact?: boolean;
  maxItems?: number;
}

export const AlertFeed: React.FC<AlertFeedProps> = ({ compact = false, maxItems = 50 }) => {
  const { alerts, connectionState } = useWSContext();
  const [localAlerts, setLocalAlerts] = useState<Alert[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  React.useEffect(() => {
    setLocalAlerts(alerts.slice(0, maxItems));
  }, [alerts, maxItems]);

  const handleDispose = async (alertId: string, disposition: string) => {
    await disposeAlert(alertId, disposition);
    setLocalAlerts((prev) =>
      prev.map((a) => (a.alert_id === alertId ? { ...a, disposition: disposition as Alert['disposition'] } : a))
    );
  };

  const wsStateMap: Record<string, string> = {
    connected: 'connected',
    connecting: 'connecting',
    reconnecting: 'reconnecting',
    disconnected: 'disconnected',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Connection status bar */}
      {!compact && (
        <div
          style={{
            padding: '8px 14px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-surface)',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <StatusDot
              state={wsStateMap[connectionState] as 'connected' | 'reconnecting' | 'disconnected' | 'connecting'}
              showLabel
              size={7}
            />
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              {localAlerts.length} alert{localAlerts.length !== 1 ? 's' : ''} shown
            </span>
          </div>
          {connectionState === 'disconnected' && (
            <span style={{ fontSize: 10, color: 'var(--critical)', letterSpacing: '0.04em' }}>
              Feed interrupted - reconnecting
            </span>
          )}
        </div>
      )}

      {/* Feed list */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: compact ? '8px' : '12px',
          display: 'flex',
          flexDirection: 'column',
          gap: compact ? 6 : 8,
        }}
      >
        {localAlerts.length === 0 ? (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-dim)',
              fontSize: 12,
              gap: 10,
            }}
          >
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--border-bright)" strokeWidth="1.5" aria-hidden="true">
              <path d="M22 17H2a3 3 0 00.5-1.65v-5.7C2.5 5.2 7 2 12 2s9.5 3.2 9.5 7.65v5.7A3 3 0 0022 17z" />
              <path d="M13.73 21a2 2 0 01-3.46 0" />
            </svg>
            <span>No alerts in feed</span>
          </div>
        ) : (
          localAlerts.map((alert) => (
            <AlertCard
              key={alert.alert_id}
              alert={alert}
              onDispose={handleDispose}
              onSelect={compact ? undefined : () => setSelectedAlert(alert)}
              compact={compact}
            />
          ))
        )}
      </div>
    </div>
  );
};
