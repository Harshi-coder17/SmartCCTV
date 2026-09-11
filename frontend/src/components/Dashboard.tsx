import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Alert, Camera } from '../types';
import { getCameras, getDashboardStats } from '../api/client';
import { useWSContext } from '../context/WSContext';
import { SeverityBadge } from './ui/SeverityBadge';
import { StatusDot } from './ui/StatusDot';
import { AlertFeed } from './AlertFeed';

interface Stats {
  active_alerts: number;
  cameras_online: number;
  total_cameras: number;
  events_today: number;
  false_positive_rate: number;
  alert_trend: number;
  event_trend: number;
}

interface StatCardProps {
  label: string;
  value: string | number;
  trend?: number;
  accentColor?: string;
  icon: React.ReactNode;
  subLabel?: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, trend, accentColor = 'var(--accent)', icon, subLabel }) => (
  <div
    style={{
      backgroundColor: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '18px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {label}
      </span>
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 'var(--radius)',
          backgroundColor: `${accentColor}18`,
          border: `1px solid ${accentColor}30`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: accentColor,
        }}
      >
        {icon}
      </div>
    </div>
    <div>
      <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--mono)', lineHeight: 1 }}>
        {value}
      </div>
      {subLabel && (
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>{subLabel}</div>
      )}
    </div>
    {trend !== undefined && (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke={trend >= 0 ? 'var(--critical)' : 'var(--low)'}
          strokeWidth="2.5"
          strokeLinecap="round"
          aria-hidden="true"
        >
          {trend >= 0 ? (
            <path d="M12 19V5m-7 7l7-7 7 7" />
          ) : (
            <path d="M12 5v14m-7-7l7 7 7-7" />
          )}
        </svg>
        <span style={{ fontSize: 11, color: trend >= 0 ? 'var(--critical)' : 'var(--low)' }}>
          {Math.abs(trend)}% vs last hour
        </span>
      </div>
    )}
  </div>
);

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { alerts } = useWSContext();
  const [stats, setStats] = useState<Stats | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    getDashboardStats()
      .then(setStats)
      .catch(() => {
        setStats({
          active_alerts: 0,
          cameras_online: 0,
          total_cameras: 0,
          events_today: 0,
          false_positive_rate: 0,
          alert_trend: 0,
          event_trend: 0,
        });
      })
      .finally(() => setStatsLoading(false));

    getCameras().then(setCameras).catch(() => setCameras([]));
  }, []);

  const liveAlerts = alerts.slice(0, 6);

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Page title */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.02em' }}>
            Operations Dashboard
          </h1>
          <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>
            Real-time border surveillance overview
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <StatusDot state="connected" showLabel label="System Nominal" size={7} />
        </div>
      </div>

      {/* Stat cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
        }}
      >
        <StatCard
          label="Active Alerts"
          value={statsLoading ? '--' : (stats?.active_alerts ?? 0)}
          trend={stats?.alert_trend}
          accentColor="var(--critical)"
          subLabel="Pending disposition"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01" />
            </svg>
          }
        />
        <StatCard
          label="Cameras Online"
          value={statsLoading ? '--' : `${stats?.cameras_online ?? 0}/${stats?.total_cameras ?? 0}`}
          accentColor="var(--low)"
          subLabel="Active streams"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M23 7l-7 5 7 5V7z" />
              <rect x="1" y="5" width="15" height="14" rx="2" />
            </svg>
          }
        />
        <StatCard
          label="Events Today"
          value={statsLoading ? '--' : (stats?.events_today ?? 0)}
          trend={stats?.event_trend}
          accentColor="var(--high)"
          subLabel="Detected incidents"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <rect x="3" y="4" width="18" height="18" rx="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          }
        />
        <StatCard
          label="False Positive Rate"
          value={statsLoading ? '--' : `${(stats?.false_positive_rate ?? 0).toFixed(1)}%`}
          accentColor="var(--medium)"
          subLabel="Last 7 days"
          icon={
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
            </svg>
          }
        />
      </div>

      {/* Middle row: AlertFeed + Camera tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Alert feed section */}
        <div
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 400,
            maxHeight: 480,
          }}
        >
          <div
            style={{
              padding: '14px 16px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
              Live Alert Feed
            </span>
            <button
              onClick={() => navigate('/alerts')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--accent)',
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'var(--font)',
              }}
            >
              View all
            </button>
          </div>
          <AlertFeed compact maxItems={8} />
        </div>

        {/* Camera status grid */}
        <div
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 400,
            maxHeight: 480,
          }}
        >
          <div
            style={{
              padding: '14px 16px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
              Camera Status
            </span>
            <button
              onClick={() => navigate('/cameras')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--accent)',
                fontSize: 11,
                cursor: 'pointer',
                fontFamily: 'var(--font)',
              }}
            >
              View all
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {cameras.length === 0 ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                No cameras registered
              </div>
            ) : (
              cameras.slice(0, 8).map((cam) => (
                <div
                  key={cam.camera_id}
                  onClick={() => navigate(`/cameras/${cam.camera_id}`)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '9px 12px',
                    backgroundColor: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    cursor: 'pointer',
                    transition: 'border-color 150ms',
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-bright)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
                >
                  <StatusDot state={cam.health_state} size={7} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cam.name}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cam.location_name}
                    </div>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em', flexShrink: 0 }}>
                    {cam.camera_type}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recent events table */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
        }}
      >
        <div
          style={{
            padding: '14px 16px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
            Recent Alerts
          </span>
          <button
            onClick={() => navigate('/alerts')}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent)',
              fontSize: 11,
              cursor: 'pointer',
              fontFamily: 'var(--font)',
            }}
          >
            View all alerts
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Severity', 'Event Type', 'Camera', 'Risk Score', 'Timestamp', 'Disposition'].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '10px 16px',
                      textAlign: 'left',
                      fontSize: 10,
                      fontWeight: 600,
                      color: 'var(--text-dim)',
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      borderBottom: '1px solid var(--border)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {liveAlerts.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                    No recent alerts
                  </td>
                </tr>
              ) : (
                liveAlerts.map((alert: Alert) => (
                  <tr
                    key={alert.alert_id}
                    style={{ cursor: 'pointer', transition: 'background-color 100ms' }}
                    onClick={() => navigate('/alerts')}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(0,212,170,0.04)'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent'; }}
                  >
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                      <SeverityBadge severity={alert.severity} size="sm" />
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-primary)' }}>
                      {alert.event_type.replace(/_/g, ' ')}
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--mono)' }}>
                      {alert.camera_name}
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 60, height: 4, backgroundColor: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                          <div
                            style={{
                              height: '100%',
                              width: `${alert.risk_score}%`,
                              backgroundColor: alert.risk_score >= 80 ? 'var(--critical)' : alert.risk_score >= 60 ? 'var(--high)' : alert.risk_score >= 40 ? 'var(--medium)' : 'var(--low)',
                              borderRadius: 2,
                            }}
                          />
                        </div>
                        <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-secondary)', minWidth: 28 }}>
                          {alert.risk_score}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                      {new Date(alert.timestamp).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 600,
                          padding: '2px 7px',
                          borderRadius: 3,
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          backgroundColor:
                            alert.disposition === 'pending'
                              ? 'rgba(234,179,8,0.12)'
                              : alert.disposition === 'confirmed'
                              ? 'rgba(239,68,68,0.12)'
                              : alert.disposition === 'false_positive'
                              ? 'rgba(34,197,94,0.12)'
                              : 'rgba(148,163,184,0.12)',
                          color:
                            alert.disposition === 'pending'
                              ? 'var(--medium)'
                              : alert.disposition === 'confirmed'
                              ? 'var(--critical)'
                              : alert.disposition === 'false_positive'
                              ? 'var(--low)'
                              : 'var(--text-secondary)',
                        }}
                      >
                        {alert.disposition.replace(/_/g, ' ')}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
