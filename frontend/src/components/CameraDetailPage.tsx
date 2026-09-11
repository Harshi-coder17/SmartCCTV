import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import type { Camera, CameraHealth, Zone } from '../types';
import { getCamera, getCameraHealth, getZones } from '../api/client';
import { StatusDot } from './ui/StatusDot';
import { Button } from './ui/Button';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export const CameraDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [camera, setCamera] = useState<Camera | null>(null);
  const [health, setHealth] = useState<CameraHealth | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);
  const [calibrating, setCalibrating] = useState(false);
  const [calibMessage, setCalibMessage] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadData = useCallback(async () => {
    if (!id) return;
    try {
      const [camData, allZones] = await Promise.all([
        getCamera(id),
        getZones().catch(() => []),
      ]);
      setCamera(camData);
      setZones(allZones.filter((z) => z.camera_ids?.includes(id)));

      try {
        const healthData = await getCameraHealth(id);
        setHealth(healthData);
      } catch {
        // Health endpoint may return 404 if no health record yet
      }
    } catch {
      // Handled in render
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void loadData();
    const interval = setInterval(() => {
      if (id) {
        getCameraHealth(id).then(setHealth).catch(() => null);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [loadData, id]);

  const handleCalibrate = async () => {
    if (!id) return;
    setCalibrating(true);
    setCalibMessage(null);
    try {
      const resp = await fetch(`/cameras/${id}/calibrate`, {
        method: 'POST',
        credentials: 'include',
      });
      if (resp.ok) {
        setCalibMessage('Background anchor refreshed successfully');
        setRefreshKey((k) => k + 1);
      } else {
        setCalibMessage('Calibration failed');
      }
    } catch {
      setCalibMessage('Network error during calibration');
    } finally {
      setCalibrating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="skeleton" style={{ height: 40, width: 240 }} />
        <div className="skeleton" style={{ height: 480 }} />
      </div>
    );
  }

  if (!camera) {
    return (
      <div style={{ padding: 32, textAlign: 'center' }}>
        <h3 style={{ color: 'var(--critical)', marginBottom: 12 }}>Camera Not Found</h3>
        <p style={{ color: 'var(--text-dim)', marginBottom: 20 }}>Camera identifier {id} does not exist in registry.</p>
        <Button variant="secondary" onClick={() => navigate('/cameras')}>Back to Cameras</Button>
      </div>
    );
  }

  const streamUrl = `${BASE_URL}/cameras/${camera.camera_id}/stream?t=${refreshKey}`;

  return (
    <div style={{ padding: '20px 24px', height: '100%', display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button variant="ghost" size="sm" onClick={() => navigate('/cameras')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Back
          </Button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <StatusDot state={camera.health_state} size={10} />
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>
              {camera.name}
            </h2>
            <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--accent)', background: 'var(--accent-dim)', padding: '2px 8px', borderRadius: 4 }}>
              {camera.camera_id}
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button variant="secondary" size="sm" onClick={() => setRefreshKey((k) => k + 1)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M23 4v6h-6" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
            Refresh Feed
          </Button>
          <Button variant="primary" size="sm" onClick={() => void handleCalibrate()} disabled={calibrating}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            {calibrating ? 'Calibrating...' : 'Calibrate Anchor'}
          </Button>
        </div>
      </div>

      {calibMessage && (
        <div style={{
          padding: '8px 12px',
          borderRadius: 'var(--radius)',
          fontSize: 12,
          background: calibMessage.includes('failed') || calibMessage.includes('error') ? 'var(--critical-dim)' : 'var(--accent-dim)',
          color: calibMessage.includes('failed') || calibMessage.includes('error') ? 'var(--critical)' : 'var(--accent)',
          border: `1px solid ${calibMessage.includes('failed') || calibMessage.includes('error') ? 'var(--critical)' : 'var(--accent)'}40`,
        }}>
          {calibMessage}
        </div>
      )}

      {/* Main Grid: Stream on Left, Telemetry on Right */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, flex: 1, minHeight: 480 }}>
        {/* Stream viewport */}
        <div style={{
          backgroundColor: '#050810',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute',
            top: 12,
            left: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            backgroundColor: 'rgba(10,14,26,0.85)',
            padding: '4px 10px',
            borderRadius: 4,
            border: '1px solid var(--border)',
            zIndex: 2,
          }}>
            <StatusDot state={camera.health_state} size={8} />
            <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--accent)', fontWeight: 600 }}>
              LIVE STREAM: {camera.camera_id}
            </span>
          </div>

          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#030508' }}>
            <img
              src={streamUrl}
              alt={`Live feed for ${camera.name}`}
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              onError={(e) => {
                const target = e.currentTarget;
                target.style.display = 'none';
                const parent = target.parentElement;
                if (parent && !parent.querySelector('.stream-error-fallback')) {
                  const errDiv = document.createElement('div');
                  errDiv.className = 'stream-error-fallback';
                  errDiv.style.cssText = 'color: var(--text-dim); font-size: 13px; text-align: center; padding: 20px;';
                  errDiv.textContent = 'Stream feed connecting or inactive';
                  parent.appendChild(errDiv);
                }
              }}
            />
          </div>

          <div style={{
            padding: '8px 14px',
            backgroundColor: 'var(--bg-surface)',
            borderTop: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: 11,
            color: 'var(--text-dim)',
          }}>
            <span>Orientation: {camera.orientation ?? 0} deg</span>
            <span>Target FPS: {camera.expected_fps}</span>
            <span>Type: {camera.camera_type}</span>
          </div>
        </div>

        {/* Telemetry & Health Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
          {/* Health Stats */}
          <div style={{
            padding: 16,
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
          }}>
            <h3 style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
              Health & Performance
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div style={{ padding: 10, backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase' }}>Actual FPS</div>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--text-primary)', marginTop: 4 }}>
                  {health ? health.fps_actual.toFixed(1) : camera.expected_fps}
                </div>
              </div>
              <div style={{ padding: 10, backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase' }}>Sharpness</div>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)', marginTop: 4 }}>
                  {health ? health.sharpness_score.toFixed(1) : '100.0'}
                </div>
              </div>
              <div style={{ padding: 10, backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase' }}>Blank Frame</div>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--low)', marginTop: 4 }}>
                  {health ? health.blank_frame_score.toFixed(2) : '0.00'}
                </div>
              </div>
              <div style={{ padding: 10, backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase' }}>State</div>
                <div style={{ fontSize: 14, fontWeight: 700, textTransform: 'uppercase', color: camera.health_state === 'healthy' ? 'var(--low)' : 'var(--high)', marginTop: 6 }}>
                  {camera.health_state}
                </div>
              </div>
            </div>
          </div>

          {/* Location & Coordinate Details */}
          <div style={{
            padding: 16,
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
          }}>
            <h3 style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 12 }}>
              Coordinates & Deployment
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { label: 'Location Name', value: camera.location_name },
                { label: 'Latitude', value: camera.gps_lat.toFixed(6) },
                { label: 'Longitude', value: camera.gps_lon.toFixed(6) },
                { label: 'Active Status', value: camera.is_active ? 'Online' : 'Decommissioned' },
              ].map(({ label, value }) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                  <span style={{ color: 'var(--text-dim)' }}>{label}</span>
                  <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--mono)' }}>{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Associated Zones */}
          <div style={{
            padding: 16,
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
          }}>
            <h3 style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>
              Covered Zones ({zones.length})
            </h3>
            {zones.length === 0 ? (
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>No specific zones mapped to this feed.</span>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {zones.map((zone) => (
                  <div key={zone.zone_id} style={{
                    padding: '8px 10px',
                    backgroundColor: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{zone.name}</span>
                    <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--accent)', textTransform: 'uppercase' }}>
                      {zone.sensitivity_level}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
