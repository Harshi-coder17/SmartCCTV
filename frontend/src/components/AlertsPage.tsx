import React, { useEffect, useState, useCallback } from 'react';
import type { Alert, AlertFilters, SeverityLevel, DispositionStatus, Camera, EventType } from '../types';
import { getAlerts, getCameras, bulkDisposeAlerts } from '../api/client';
import { DataTable, type ColumnDef } from './ui/DataTable';
import { SeverityBadge } from './ui/SeverityBadge';
import { Button } from './ui/Button';
import { Modal } from './ui/Modal';
import { EvidencePanel } from './EvidencePanel';

const SEVERITY_OPTIONS: SeverityLevel[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const DISPOSITION_OPTIONS: DispositionStatus[] = ['pending', 'confirmed', 'false_positive', 'inconclusive'];
const EVENT_TYPE_OPTIONS: EventType[] = [
  'perimeter_intrusion', 'no_traceable_origin', 'route_anomaly',
  'off_hours_activity', 'behavior_anomaly', 'unknown_identity',
  'group_clustering', 'vehicle_intrusion',
];

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

export const AlertsPage: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<AlertFilters>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [evidenceAlert, setEvidenceAlert] = useState<Alert | null>(null);
  const PAGE_SIZE = 20;

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getAlerts(filters, page, PAGE_SIZE);
      setAlerts(result.items);
      setTotal(result.total);
    } catch {
      setAlerts([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  useEffect(() => {
    getCameras().then(setCameras).catch(() => setCameras([]));
  }, []);

  const handleBulkDispose = async (disposition: string) => {
    if (selectedIds.size === 0) return;
    setBulkLoading(true);
    try {
      await bulkDisposeAlerts(Array.from(selectedIds), disposition);
      setSelectedIds(new Set());
      await fetchAlerts();
    } catch {
      // Pass
    } finally {
      setBulkLoading(false);
    }
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(alerts, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `alerts_export_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns: ColumnDef<Alert>[] = [
    {
      key: 'severity',
      header: 'Severity',
      sortable: true,
      width: 100,
      render: (row) => <SeverityBadge severity={(row as Alert).severity} size="sm" />,
    },
    {
      key: 'event_type',
      header: 'Event Type',
      sortable: true,
      render: (row) => (
        <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
          {(row as Alert).event_type.replace(/_/g, ' ')}
        </span>
      ),
    },
    {
      key: 'camera_name',
      header: 'Camera',
      sortable: true,
      render: (row) => (
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
          {(row as Alert).camera_name}
        </span>
      ),
    },
    {
      key: 'risk_score',
      header: 'Risk Score',
      sortable: true,
      width: 120,
      render: (row) => {
        const a = row as Alert;
        const color = a.risk_score >= 80 ? 'var(--critical)' : a.risk_score >= 60 ? 'var(--high)' : a.risk_score >= 40 ? 'var(--medium)' : 'var(--low)';
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 50, height: 4, backgroundColor: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${a.risk_score}%`, backgroundColor: color, borderRadius: 2 }} />
            </div>
            <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-secondary)', minWidth: 26 }}>{a.risk_score}</span>
          </div>
        );
      },
    },
    {
      key: 'timestamp',
      header: 'Time',
      sortable: true,
      render: (row) => (
        <span title={new Date((row as Alert).timestamp).toLocaleString()} style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)' }}>
          {relativeTime((row as Alert).timestamp)}
        </span>
      ),
    },
    {
      key: 'disposition',
      header: 'Disposition',
      sortable: true,
      render: (row) => {
        const a = row as Alert;
        const COLOR: Record<string, string> = {
          pending: 'var(--medium)',
          confirmed: 'var(--critical)',
          false_positive: 'var(--low)',
          inconclusive: 'var(--text-secondary)',
        };
        return (
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '2px 7px',
              borderRadius: 3,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: COLOR[a.disposition] ?? 'var(--text-dim)',
              backgroundColor: `${COLOR[a.disposition] ?? 'var(--text-dim)'}18`,
              border: `1px solid ${COLOR[a.disposition] ?? 'var(--text-dim)'}30`,
            }}
          >
            {a.disposition.replace(/_/g, ' ')}
          </span>
        );
      },
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={(e) => {
            e.stopPropagation();
            setEvidenceAlert(row as Alert);
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          Evidence
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Alert Management</h1>
          <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{total} total alerts</p>
        </div>
        <Button variant="secondary" size="sm" onClick={handleExport}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          Export JSON
        </Button>
      </div>

      {/* Filters */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: '14px 16px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'flex-end',
        }}
      >
        {/* Severity filter */}
        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            Severity
          </label>
          <div style={{ display: 'flex', gap: 4 }}>
            {SEVERITY_OPTIONS.map((s) => {
              const active = filters.severity?.includes(s);
              const colors: Record<string, string> = { LOW: '#22C55E', MEDIUM: '#EAB308', HIGH: '#F97316', CRITICAL: '#EF4444' };
              return (
                <button
                  key={s}
                  onClick={() =>
                    setFilters((f) => ({
                      ...f,
                      severity: active ? f.severity?.filter((x) => x !== s) : [...(f.severity ?? []), s],
                    }))
                  }
                  style={{
                    padding: '4px 8px',
                    fontSize: 10,
                    fontWeight: 700,
                    fontFamily: 'var(--font)',
                    letterSpacing: '0.06em',
                    cursor: 'pointer',
                    borderRadius: 3,
                    backgroundColor: active ? `${colors[s]}20` : 'var(--bg-elevated)',
                    border: `1px solid ${active ? colors[s] : 'var(--border)'}`,
                    color: active ? colors[s] : 'var(--text-dim)',
                    transition: 'all 150ms',
                  }}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>

        {/* Camera filter */}
        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            Camera
          </label>
          <select
            value={filters.camera_id ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, camera_id: e.target.value || undefined }))}
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '5px 8px',
              color: 'var(--text-primary)',
              fontSize: 11,
              fontFamily: 'var(--font)',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="">All Cameras</option>
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>{c.name}</option>
            ))}
          </select>
        </div>

        {/* Disposition filter */}
        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            Disposition
          </label>
          <select
            value={filters.disposition ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, disposition: (e.target.value as DispositionStatus) || undefined }))}
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '5px 8px',
              color: 'var(--text-primary)',
              fontSize: 11,
              fontFamily: 'var(--font)',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="">All Dispositions</option>
            {DISPOSITION_OPTIONS.map((d) => (
              <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>

        {/* Date from */}
        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            From
          </label>
          <input
            type="date"
            value={filters.date_from ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value || undefined }))}
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '5px 8px',
              color: 'var(--text-primary)',
              fontSize: 11,
              fontFamily: 'var(--font)',
              outline: 'none',
              colorScheme: 'dark',
            }}
          />
        </div>

        {/* Date to */}
        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            To
          </label>
          <input
            type="date"
            value={filters.date_to ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value || undefined }))}
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              padding: '5px 8px',
              color: 'var(--text-primary)',
              fontSize: 11,
              fontFamily: 'var(--font)',
              outline: 'none',
              colorScheme: 'dark',
            }}
          />
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setFilters({});
            setPage(1);
          }}
        >
          Clear Filters
        </Button>
      </div>

      {/* Bulk actions */}
      {selectedIds.size > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '10px 16px',
            backgroundColor: 'var(--accent-dim)',
            border: '1px solid rgba(0,212,170,0.3)',
            borderRadius: 'var(--radius)',
            animation: 'slideInTop 200ms ease',
          }}
        >
          <span style={{ fontSize: 12, color: 'var(--accent)', fontWeight: 600 }}>
            {selectedIds.size} selected
          </span>
          <div style={{ flex: 1 }} />
          <Button size="sm" variant="danger" loading={bulkLoading} onClick={() => handleBulkDispose('confirmed')}>
            Confirm All
          </Button>
          <Button size="sm" variant="ghost" loading={bulkLoading} onClick={() => handleBulkDispose('false_positive')}>
            Mark False Positive
          </Button>
          <Button size="sm" variant="ghost" loading={bulkLoading} onClick={() => handleBulkDispose('inconclusive')}>
            Mark Inconclusive
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
            Cancel
          </Button>
        </div>
      )}

      {/* Table */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <DataTable<Alert>
          columns={columns}
          data={alerts}
          loading={loading}
          rowKey={(row) => row.alert_id}
          pageSize={PAGE_SIZE}
          totalCount={total}
          currentPage={page}
          onPageChange={(p) => setPage(p)}
          selectedRows={selectedIds}
          onRowSelect={(key, selected) => {
            setSelectedIds((prev) => {
              const next = new Set(prev);
              if (selected) next.add(key);
              else next.delete(key);
              return next;
            });
          }}
          onSelectAll={(selected) => {
            if (selected) setSelectedIds(new Set(alerts.map((a) => a.alert_id)));
            else setSelectedIds(new Set());
          }}
          emptyMessage="No alerts match the current filters."
        />
      </div>

      {/* Evidence modal */}
      {evidenceAlert && (
        <Modal
          isOpen
          onClose={() => setEvidenceAlert(null)}
          title={`Evidence - ${evidenceAlert.event_id}`}
          width={1100}
        >
          <EvidencePanel alert={evidenceAlert} />
        </Modal>
      )}
    </div>
  );
};
