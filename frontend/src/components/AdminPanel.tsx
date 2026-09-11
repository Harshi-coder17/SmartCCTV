import React, { useEffect, useState } from 'react';
import type { Zone, ModelVersion } from '../types';
import { getZones, getModelVersions } from '../api/client';

type AdminTab = 'zones' | 'personnel' | 'watchlist' | 'models' | 'topology';

const TAB_LABELS: { id: AdminTab; label: string }[] = [
  { id: 'zones', label: 'Zones' },
  { id: 'personnel', label: 'Personnel' },
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'models', label: 'Model Registry' },
  { id: 'topology', label: 'Camera Topology' },
];

const SENS_COLOR: Record<string, string> = {
  low: 'var(--low)',
  medium: 'var(--medium)',
  high: 'var(--high)',
  critical: 'var(--critical)',
};

/* ─── Zones Tab ───────────────────────────────────────────────────── */
function ZonesTab() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getZones().then(setZones).catch(() => null).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>{zones.length} zones configured</span>
        <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Draw polygons with scripts/zone_editor.py</span>
      </div>
      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : zones.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>No zones configured.</p>
      ) : zones.map((zone) => (
        <div key={zone.zone_id} style={{
          padding: '14px 16px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius)',
          border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 16,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 13 }}>{zone.name}</span>
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
                background: `${SENS_COLOR[zone.sensitivity_level] ?? 'var(--text-dim)'}20`,
                color: SENS_COLOR[zone.sensitivity_level] ?? 'var(--text-dim)',
                border: `1px solid ${SENS_COLOR[zone.sensitivity_level] ?? 'var(--text-dim)'}40`,
              }}>
                {String(zone.sensitivity_level).toUpperCase()}
              </span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              {zone.camera_ids?.length ?? 0} camera(s)
              {zone.description && ` | ${zone.description}`}
            </div>
          </div>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: zone.is_active ? 'var(--low)' : 'var(--text-dim)',
          }} />
        </div>
      ))}
    </div>
  );
}

/* ─── Personnel Tab ───────────────────────────────────────────────── */
function PersonnelTab() {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [name, setName] = useState('');
  const [designation, setDesignation] = useState('');
  const [authLevel, setAuthLevel] = useState(1);
  const [file, setFile] = useState<File | null>(null);

  async function enroll(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !name) return;
    setUploading(true);
    setMessage('');
    try {
      const form = new FormData();
      form.append('face_image', file);
      const url = `/admin/personnel/?name=${encodeURIComponent(name)}&designation=${encodeURIComponent(designation)}&authorization_level=${authLevel}`;
      const resp = await fetch(url, { method: 'POST', body: form, credentials: 'include' });
      const data = await resp.json() as { message: string; person_id?: string };
      setMessage(resp.ok ? `Enrolled successfully. ID: ${data.person_id ?? ''}` : `Error: ${data.message}`);
      if (resp.ok) { setName(''); setDesignation(''); setFile(null); }
    } catch {
      setMessage('Network error. Check backend is running.');
    } finally {
      setUploading(false);
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%', padding: '8px 10px', background: 'var(--bg-elevated)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius)',
    color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 11, fontWeight: 600, color: 'var(--text-dim)',
    display: 'block', marginBottom: 5, letterSpacing: '0.06em',
  };

  return (
    <div style={{ maxWidth: 480 }}>
      <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 20 }}>
        Enroll authorized personnel with a face image. Embeddings are stored encrypted.
      </p>
      <form onSubmit={(e) => void enroll(e)} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={labelStyle}>FULL NAME</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required style={fieldStyle} />
        </div>
        <div>
          <label style={labelStyle}>DESIGNATION / RANK</label>
          <input value={designation} onChange={(e) => setDesignation(e.target.value)} style={fieldStyle} />
        </div>
        <div>
          <label style={labelStyle}>AUTHORIZATION LEVEL (1-5)</label>
          <input type="number" min={1} max={5} value={authLevel}
            onChange={(e) => setAuthLevel(Number(e.target.value))} style={fieldStyle} />
        </div>
        <div>
          <label style={labelStyle}>FACE IMAGE</label>
          <input type="file" accept="image/*" required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ color: 'var(--text-secondary)', fontSize: 12 }} />
        </div>
        <button type="submit" disabled={uploading} style={{
          padding: '9px 18px', background: 'var(--accent)', border: 'none',
          borderRadius: 'var(--radius)', color: '#000', fontSize: 13, fontWeight: 700,
          cursor: uploading ? 'wait' : 'pointer', fontFamily: 'var(--font)',
        }}>
          {uploading ? 'Enrolling...' : 'Enroll Personnel'}
        </button>
        {message && (
          <p style={{ fontSize: 12, color: message.startsWith('Error') || message.startsWith('Network') ? 'var(--critical)' : 'var(--low)' }}>
            {message}
          </p>
        )}
      </form>
    </div>
  );
}

/* ─── Watchlist Tab ───────────────────────────────────────────────── */
function WatchlistTab() {
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [label, setLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const fieldStyle: React.CSSProperties = {
    width: '100%', padding: '8px 10px', background: 'var(--bg-elevated)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius)',
    color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)',
  };

  async function addEntry(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !label) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('face_image', file);
      const resp = await fetch(
        `/admin/watchlist/?label=${encodeURIComponent(label)}&notes=${encodeURIComponent(notes)}`,
        { method: 'POST', body: form, credentials: 'include' }
      );
      const data = await resp.json() as { message: string; watchlist_id?: string };
      setMessage(resp.ok ? `Added: ${data.watchlist_id ?? 'OK'}` : `Error: ${data.message}`);
      if (resp.ok) { setLabel(''); setNotes(''); setFile(null); }
    } catch {
      setMessage('Network error');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div style={{ maxWidth: 480 }}>
      <div style={{
        padding: '10px 14px', marginBottom: 20, borderRadius: 'var(--radius)',
        background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
        fontSize: 12, color: 'var(--critical)',
      }}>
        Watchlist entries trigger CRITICAL alerts on facial match. Handle with care.
      </div>
      <form onSubmit={(e) => void addEntry(e)} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: 5 }}>LABEL / IDENTIFIER</label>
          <input value={label} onChange={(e) => setLabel(e.target.value)} required style={fieldStyle} />
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: 5 }}>NOTES</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3}
            style={{ ...fieldStyle, resize: 'vertical' as const }} />
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', display: 'block', marginBottom: 5 }}>FACE IMAGE</label>
          <input type="file" accept="image/*" required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ color: 'var(--text-secondary)', fontSize: 12 }} />
        </div>
        <button type="submit" disabled={uploading} style={{
          padding: '9px 18px', background: 'var(--critical)', border: 'none',
          borderRadius: 'var(--radius)', color: '#fff', fontSize: 13, fontWeight: 700,
          cursor: uploading ? 'wait' : 'pointer', fontFamily: 'var(--font)',
        }}>
          {uploading ? 'Adding...' : 'Add to Watchlist'}
        </button>
        {message && <p style={{ fontSize: 12, color: message.startsWith('Error') ? 'var(--critical)' : 'var(--low)' }}>{message}</p>}
      </form>
    </div>
  );
}

/* ─── Model Registry Tab ──────────────────────────────────────────── */
function ModelsTab() {
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getModelVersions().then(setVersions).catch(() => null).finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : versions.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>No models registered. Auto-registered on first startup.</p>
      ) : versions.map((v, idx) => (
        <div key={`${v.model_name}-${v.version}-${idx}`} style={{
          padding: '14px 16px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius)',
          border: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: 13 }}>{v.model_name}</span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent)' }}>{v.version}</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
              background: v.is_current ? 'rgba(34,197,94,0.12)' : 'rgba(71,85,105,0.2)',
              color: v.is_current ? 'var(--low)' : 'var(--text-dim)',
            }}>
              {v.is_current ? 'ACTIVE' : 'INACTIVE'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
            Type: {v.type} | Deployed: {new Date(v.deployed_at).toLocaleString()}
          </div>
          {v.accuracy_metrics && Object.keys(v.accuracy_metrics).length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, fontFamily: 'var(--mono)' }}>
              {Object.entries(v.accuracy_metrics).map(([k, val]) => `${k}: ${val}`).join(' | ')}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ─── Topology Tab ────────────────────────────────────────────────── */
function TopologyTab() {
  const [topo, setTopo] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/admin/topology/', { credentials: 'include' })
      .then((r) => r.json() as Promise<Record<string, unknown>>)
      .then(setTopo)
      .catch(() => null)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 16 }}>
        Camera adjacency graph used for cross-camera ReID and movement timeline correlation.
      </p>
      {loading ? (
        <div className="skeleton" style={{ height: 200 }} />
      ) : !topo ? (
        <p style={{ fontSize: 12, color: 'var(--critical)' }}>Failed to load topology</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {Object.entries(topo).map(([cid, neighbors]) => (
            <div key={cid} style={{
              padding: '12px 14px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius)',
              border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--accent)', fontWeight: 700, minWidth: 80 }}>{cid}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--border-bright)" strokeWidth="2" aria-hidden="true">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {!Array.isArray(neighbors) || (neighbors as string[]).length === 0 ? (
                  <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>no adjacent cameras</span>
                ) : (neighbors as string[]).map((n) => (
                  <span key={n} style={{
                    padding: '2px 8px', borderRadius: 3, fontSize: 11, fontFamily: 'var(--mono)',
                    background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(0,212,170,0.2)',
                  }}>{n}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── AdminPanel Root ─────────────────────────────────────────────── */
export const AdminPanel: React.FC = () => {
  const [tab, setTab] = useState<AdminTab>('zones');

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>Admin Panel</h2>
        <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>System configuration, personnel management, and model governance</p>
      </div>

      <div style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        {TAB_LABELS.map(({ id, label }) => (
          <button key={id} onClick={() => setTab(id)} style={{
            padding: '8px 16px', background: 'transparent', border: 'none',
            borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
            color: tab === id ? 'var(--accent)' : 'var(--text-secondary)',
            fontSize: 12, fontWeight: tab === id ? 700 : 400, cursor: 'pointer',
            fontFamily: 'var(--font)', marginBottom: -1, transition: 'color 150ms',
          }}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {tab === 'zones' && <ZonesTab />}
        {tab === 'personnel' && <PersonnelTab />}
        {tab === 'watchlist' && <WatchlistTab />}
        {tab === 'models' && <ModelsTab />}
        {tab === 'topology' && <TopologyTab />}
      </div>
    </div>
  );
};
