import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Camera } from '../types';
import { getCameras } from '../api/client';
import { StatusDot } from './ui/StatusDot';
import { Modal } from './ui/Modal';
import { Button } from './ui/Button';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

interface CameraTileProps {
  camera: Camera;
  onClick: () => void;
}

const healthBorderColor: Record<string, string> = {
  healthy: '#22C55E',
  degraded: '#EAB308',
  offline: '#EF4444',
  unknown: '#475569',
};

const CameraTile: React.FC<CameraTileProps> = ({ camera, onClick }) => {
  const [imgError, setImgError] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const streamUrl = `${BASE_URL}/cameras/${camera.camera_id}/stream?t=${refreshKey}`;

  return (
    <div
      onClick={onClick}
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: `1px solid ${healthBorderColor[camera.health_state] ?? 'var(--border)'}40`,
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        cursor: 'pointer',
        position: 'relative',
        aspectRatio: '16/10',
        display: 'flex',
        flexDirection: 'column',
        transition: 'border-color 200ms, box-shadow 200ms',
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = healthBorderColor[camera.health_state] ?? 'var(--border-bright)';
        (e.currentTarget as HTMLElement).style.boxShadow = `0 0 12px ${healthBorderColor[camera.health_state] ?? 'transparent'}20`;
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = `${healthBorderColor[camera.health_state] ?? 'var(--border)'}40`;
        (e.currentTarget as HTMLElement).style.boxShadow = 'none';
      }}
    >
      {/* Stream or placeholder */}
      <div style={{ flex: 1, position: 'relative', backgroundColor: '#050810', overflow: 'hidden' }}>
        {camera.health_state !== 'offline' && !imgError ? (
          <img
            src={streamUrl}
            alt={`Live feed: ${camera.name}`}
            onError={() => setImgError(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              color: 'var(--text-dim)',
            }}
          >
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
              <line x1="1" y1="1" x2="23" y2="23" />
              <path d="M21 21H3a2 2 0 01-2-2V8a2 2 0 012-2h3m3-3h6l2 3h4a2 2 0 012 2v9.34" />
            </svg>
            <span style={{ fontSize: 10, letterSpacing: '0.06em' }}>
              {camera.health_state === 'offline' ? 'OFFLINE' : 'STREAM UNAVAILABLE'}
            </span>
          </div>
        )}

        {/* Camera ID label */}
        <div
          style={{
            position: 'absolute',
            top: 8,
            left: 8,
            backgroundColor: 'rgba(10,14,26,0.8)',
            padding: '3px 7px',
            borderRadius: 3,
            fontSize: 10,
            fontFamily: 'var(--mono)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '0.06em',
          }}
        >
          {camera.name}
        </div>

        {/* Refresh button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            setImgError(false);
            setRefreshKey((k) => k + 1);
          }}
          title="Refresh stream"
          style={{
            position: 'absolute',
            top: 6,
            right: 6,
            backgroundColor: 'rgba(10,14,26,0.7)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            padding: 5,
            cursor: 'pointer',
            color: 'var(--text-dim)',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
            <path d="M23 4v6h-6" />
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
          </svg>
        </button>

        {/* Health indicator top-right overlay */}
        {camera.health_state !== 'healthy' && (
          <div
            style={{
              position: 'absolute',
              bottom: 6,
              right: 6,
              backgroundColor: 'rgba(10,14,26,0.8)',
              border: `1px solid ${healthBorderColor[camera.health_state]}40`,
              borderRadius: 3,
              padding: '2px 6px',
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.08em',
              color: healthBorderColor[camera.health_state],
              textTransform: 'uppercase',
            }}
          >
            {camera.health_state}
          </div>
        )}
      </div>

      {/* Bottom info strip */}
      <div
        style={{
          padding: '7px 10px',
          backgroundColor: 'rgba(10,14,26,0.7)',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <StatusDot state={camera.health_state} size={6} />
          <span
            style={{
              fontSize: 11,
              color: 'var(--text-secondary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {camera.location_name}
          </span>
        </div>
        <span style={{ fontSize: 10, color: 'var(--text-dim)', flexShrink: 0, marginLeft: 8 }}>
          {camera.camera_type}
        </span>
      </div>
    </div>
  );
};

interface CameraDetailModalProps {
  camera: Camera;
  onClose: () => void;
}

const CameraDetailModal: React.FC<CameraDetailModalProps> = ({ camera, onClose }) => {
  const navigate = useNavigate();
  const streamUrl = `${BASE_URL}/cameras/${camera.camera_id}/stream`;

  return (
    <Modal isOpen onClose={onClose} title={`${camera.name} - Live View`} width={900}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', height: 520 }}>
        {/* Stream */}
        <div style={{ backgroundColor: '#050810', position: 'relative' }}>
          <img
            src={streamUrl}
            alt={`Live stream: ${camera.name}`}
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
          />
          <div
            style={{
              position: 'absolute',
              top: 10,
              left: 10,
              backgroundColor: 'rgba(10,14,26,0.85)',
              padding: '4px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontFamily: 'var(--mono)',
              color: 'var(--accent)',
              letterSpacing: '0.06em',
              fontWeight: 600,
            }}
          >
            {camera.name} LIVE
          </div>
        </div>

        {/* Info panel */}
        <div
          style={{
            borderLeft: '1px solid var(--border)',
            padding: 16,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
              Camera Info
            </div>
            {[
              { label: 'ID', value: camera.camera_id },
              { label: 'Type', value: camera.camera_type },
              { label: 'Location', value: camera.location_name },
              { label: 'GPS', value: `${camera.gps_lat.toFixed(5)}, ${camera.gps_lon.toFixed(5)}` },
              { label: 'Expected FPS', value: String(camera.expected_fps) },
              { label: 'Status', value: camera.health_state },
            ].map(({ label, value }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
                <span style={{ fontSize: 11, color: 'var(--text-primary)', fontFamily: 'var(--mono)', textAlign: 'right', maxWidth: 160, wordBreak: 'break-all' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>

          <div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
              Capabilities
            </div>
            {camera.capability_profile && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {[
                  { label: 'Night Vision', value: camera.capability_profile.has_night_vision },
                  { label: 'Thermal', value: camera.capability_profile.has_thermal },
                  { label: 'PTZ', value: camera.capability_profile.has_ptz },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
                    <span style={{ fontSize: 11, color: value ? 'var(--low)' : 'var(--text-dim)' }}>
                      {value ? 'Yes' : 'No'}
                    </span>
                  </div>
                ))}
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Resolution</span>
                  <span style={{ fontSize: 11, color: 'var(--text-primary)', fontFamily: 'var(--mono)' }}>
                    {camera.capability_profile.resolution}
                  </span>
                </div>
              </div>
            )}
          </div>

          <Button
            variant="primary"
            size="sm"
            fullWidth
            onClick={() => { onClose(); navigate(`/cameras/${camera.camera_id}`); }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" />
            </svg>
            Full Camera View
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export const CameraGrid: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Camera | null>(null);

  useEffect(() => {
    getCameras()
      .then(setCameras)
      .catch(() => setCameras([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ aspectRatio: '16/10', borderRadius: 'var(--radius)' }} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Camera Grid</h1>
          <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>
            {cameras.filter((c) => c.health_state === 'healthy').length} of {cameras.length} cameras online
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          {[
            { label: 'Online', color: 'var(--low)', count: cameras.filter((c) => c.health_state === 'healthy').length },
            { label: 'Degraded', color: 'var(--medium)', count: cameras.filter((c) => c.health_state === 'degraded').length },
            { label: 'Offline', color: 'var(--critical)', count: cameras.filter((c) => c.health_state === 'offline').length },
          ].map(({ label, color, count }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color }} aria-hidden="true" />
              {count} {label}
            </div>
          ))}
        </div>
      </div>

      {cameras.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-dim)', fontSize: 13 }}>
          No cameras registered in the system.
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 16,
          }}
        >
          {cameras.map((cam) => (
            <CameraTile key={cam.camera_id} camera={cam} onClick={() => setSelected(cam)} />
          ))}
        </div>
      )}

      {selected && (
        <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
};
