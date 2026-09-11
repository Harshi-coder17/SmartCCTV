import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Polygon, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Camera, Zone, Alert } from '../types';
import { getCameras, getZones, getAlerts } from '../api/client';
import { StatusDot } from './ui/StatusDot';
import { SeverityBadge } from './ui/SeverityBadge';

// Fix default icon issue in Leaflet + Vite
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

function createCameraIcon(healthState: string, hasAlert: boolean): L.DivIcon {
  const colors: Record<string, string> = {
    healthy: '#22C55E',
    degraded: '#EAB308',
    offline: '#EF4444',
    unknown: '#475569',
  };
  const color = colors[healthState] ?? '#475569';
  const pulseRing = hasAlert
    ? `<circle cx="12" cy="12" r="10" fill="none" stroke="#EF4444" stroke-width="1.5" opacity="0.6"><animate attributeName="r" from="10" to="16" dur="1.2s" repeatCount="indefinite"/><animate attributeName="opacity" from="0.6" to="0" dur="1.2s" repeatCount="indefinite"/></circle>`
    : '';

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">
      ${pulseRing ? `<svg x="2" y="0" width="24" height="24" viewBox="0 0 24 24">${pulseRing}</svg>` : ''}
      <path d="M14 1C7.9 1 3 5.9 3 12c0 8.3 11 22 11 22S25 20.3 25 12C25 5.9 20.1 1 14 1z" fill="${color}" stroke="rgba(0,0,0,0.4)" stroke-width="1"/>
      <circle cx="14" cy="12" r="5" fill="rgba(10,14,26,0.85)"/>
      <path d="M20 11l-6 4 6 4V11z" fill="${color}" stroke="none"/>
      <rect x="8" y="9" width="10" height="6" rx="1.5" fill="none" stroke="${color}" stroke-width="1.2"/>
    </svg>
  `;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [28, 36],
    iconAnchor: [14, 36],
    popupAnchor: [0, -36],
  });
}

const ZONE_COLORS: Record<string, string> = {
  critical: '#EF4444',
  high: '#F97316',
  medium: '#EAB308',
  low: '#22C55E',
};

function MapFitBounds({ cameras }: { cameras: Camera[] }) {
  const map = useMap();
  useEffect(() => {
    if (cameras.length > 0) {
      const bounds = L.latLngBounds(cameras.map((c) => [c.gps_lat, c.gps_lon]));
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [cameras, map]);
  return null;
}

interface SidePanelCamera {
  camera: Camera;
  recentAlerts: Alert[];
}

export const GISMap: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [sidePanel, setSidePanel] = useState<SidePanelCamera | null>(null);
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);

  useEffect(() => {
    Promise.all([
      getCameras().catch(() => [] as Camera[]),
      getZones().catch(() => [] as Zone[]),
      getAlerts({ disposition: 'pending' }, 1, 100).catch(() => ({ items: [] as Alert[], total: 0, page: 1, page_size: 100, total_pages: 1 })),
    ]).then(([cams, zns, alertRes]) => {
      setCameras(cams);
      setZones(zns);
      setAlerts(alertRes.items);
    }).finally(() => setLoading(false));
  }, []);

  const alertCameraIds = new Set(alerts.map((a) => a.camera_id));

  const handleCameraClick = (cam: Camera) => {
    const camAlerts = alerts.filter((a) => a.camera_id === cam.camera_id);
    setSidePanel({ camera: cam, recentAlerts: camAlerts });
    setSelectedZone(null);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-dim)' }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite' }} aria-hidden="true">
          <path d="M21 12a9 9 0 11-6.219-8.56" />
        </svg>
      </div>
    );
  }

  const defaultCenter: [number, number] = cameras.length > 0
    ? [cameras[0].gps_lat, cameras[0].gps_lon]
    : [28.6139, 77.2090];

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - var(--header-height))', position: 'relative' }}>
      {/* Map */}
      <div style={{ flex: 1 }}>
        <MapContainer
          center={defaultCenter}
          zoom={13}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            subdomains="abcd"
          />

          {cameras.length > 0 && <MapFitBounds cameras={cameras} />}

          {/* Zone polygons */}
          {zones.map((zone) => {
            const positions = zone.polygon_points.map((p) => [p.lat, p.lon] as [number, number]);
            const color = ZONE_COLORS[zone.sensitivity_level] ?? '#94A3B8';
            if (positions.length < 3) return null;
            return (
              <Polygon
                key={zone.zone_id}
                positions={positions}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.1,
                  weight: 2,
                  opacity: 0.6,
                  dashArray: '6 4',
                }}
                eventHandlers={{ click: () => { setSelectedZone(zone); setSidePanel(null); } }}
              >
                <Popup>
                  <div style={{ fontFamily: 'var(--font)', fontSize: 12, minWidth: 160 }}>
                    <strong style={{ color: 'var(--text-primary)' }}>{zone.name}</strong>
                    <div style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
                      Sensitivity: <span style={{ color }}>{zone.sensitivity_level.toUpperCase()}</span>
                    </div>
                    <div style={{ color: 'var(--text-dim)', marginTop: 2, fontSize: 11 }}>
                      {zone.is_active ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                </Popup>
              </Polygon>
            );
          })}

          {/* Camera markers */}
          {cameras.map((cam) => {
            const hasAlert = alertCameraIds.has(cam.camera_id);
            const icon = createCameraIcon(cam.health_state, hasAlert);
            return (
              <Marker
                key={cam.camera_id}
                position={[cam.gps_lat, cam.gps_lon]}
                icon={icon}
                eventHandlers={{ click: () => handleCameraClick(cam) }}
              >
                <Popup>
                  <div style={{ fontFamily: 'var(--font)', fontSize: 12, minWidth: 180 }}>
                    <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--mono)', marginBottom: 4 }}>
                      {cam.name}
                    </div>
                    <div style={{ color: 'var(--text-secondary)' }}>{cam.location_name}</div>
                    <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <StatusDot state={cam.health_state} showLabel size={7} />
                    </div>
                    {hasAlert && (
                      <div style={{ marginTop: 6, fontSize: 11, color: 'var(--critical)', fontWeight: 600 }}>
                        Active alert detected
                      </div>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          bottom: 24,
          left: 16,
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '12px 14px',
          zIndex: 1000,
          fontSize: 11,
          minWidth: 160,
        }}
      >
        <div style={{ fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontSize: 10 }}>
          Legend
        </div>
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Camera Health
          </div>
          {[
            { label: 'Healthy', color: '#22C55E' },
            { label: 'Degraded', color: '#EAB308' },
            { label: 'Offline', color: '#EF4444' },
          ].map(({ label, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} aria-hidden="true" />
              <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Zone Sensitivity
          </div>
          {Object.entries(ZONE_COLORS).map(([level, color]) => (
            <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <div
                style={{
                  width: 14,
                  height: 8,
                  backgroundColor: `${color}30`,
                  border: `1px solid ${color}`,
                  borderRadius: 2,
                  flexShrink: 0,
                }}
                aria-hidden="true"
              />
              <span style={{ color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{level}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Side panel */}
      {(sidePanel || selectedZone) && (
        <div
          style={{
            width: 300,
            backgroundColor: 'var(--bg-surface)',
            borderLeft: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            zIndex: 500,
          }}
        >
          <div
            style={{
              padding: '12px 14px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              {sidePanel ? 'Camera Details' : 'Zone Details'}
            </span>
            <button
              onClick={() => { setSidePanel(null); setSelectedZone(null); }}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--text-dim)',
                padding: 4,
                display: 'flex',
                alignItems: 'center',
              }}
              aria-label="Close panel"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div style={{ padding: 14, flex: 1 }}>
            {sidePanel && (
              <>
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'var(--mono)' }}>
                    {sidePanel.camera.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {sidePanel.camera.location_name}
                  </div>
                  <div style={{ marginTop: 8 }}>
                    <StatusDot state={sidePanel.camera.health_state} showLabel size={7} />
                  </div>
                </div>

                {[
                  { label: 'Type', value: sidePanel.camera.camera_type },
                  { label: 'GPS', value: `${sidePanel.camera.gps_lat.toFixed(4)}, ${sidePanel.camera.gps_lon.toFixed(4)}` },
                  { label: 'Expected FPS', value: String(sidePanel.camera.expected_fps) },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'baseline' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-primary)', fontFamily: 'var(--mono)' }}>{value}</span>
                  </div>
                ))}

                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                    Recent Alerts ({sidePanel.recentAlerts.length})
                  </div>
                  {sidePanel.recentAlerts.length === 0 ? (
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', fontStyle: 'italic' }}>No active alerts</div>
                  ) : (
                    sidePanel.recentAlerts.slice(0, 5).map((alert) => (
                      <div
                        key={alert.alert_id}
                        style={{
                          padding: '8px 10px',
                          backgroundColor: 'var(--bg-elevated)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius)',
                          marginBottom: 6,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <SeverityBadge severity={alert.severity} size="sm" showIcon={false} />
                          <span style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                            {alert.risk_score}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                          {alert.event_type.replace(/_/g, ' ')}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}

            {selectedZone && (
              <>
                <div style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {selectedZone.name}
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        padding: '2px 7px',
                        borderRadius: 3,
                        backgroundColor: `${ZONE_COLORS[selectedZone.sensitivity_level]}18`,
                        color: ZONE_COLORS[selectedZone.sensitivity_level],
                        border: `1px solid ${ZONE_COLORS[selectedZone.sensitivity_level]}40`,
                      }}
                    >
                      {selectedZone.sensitivity_level} sensitivity
                    </span>
                  </div>
                </div>
                {[
                  { label: 'Status', value: selectedZone.is_active ? 'Active' : 'Inactive' },
                  { label: 'Cameras', value: String(selectedZone.camera_ids.length) },
                  { label: 'Polygon Points', value: String(selectedZone.polygon_points.length) },
                ].map(({ label, value }) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{label}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-primary)' }}>{value}</span>
                  </div>
                ))}
                {selectedZone.description && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>Description</div>
                    <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                      {selectedZone.description}
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
