import React, { useEffect, useState, useCallback } from 'react';
import type { Event, AlertFilters, SeverityLevel, Camera, EventType } from '../types';
import { getEvents, getCameras } from '../api/client';
import { DataTable, type ColumnDef } from './ui/DataTable';
import { SeverityBadge } from './ui/SeverityBadge';
import { RiskBreakdown } from './RiskBreakdown';

const SEVERITY_OPTIONS: SeverityLevel[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const EVENT_TYPE_OPTIONS: EventType[] = [
  'perimeter_intrusion', 'no_traceable_origin', 'route_anomaly',
  'off_hours_activity', 'behavior_anomaly', 'unknown_identity',
  'group_clustering', 'vehicle_intrusion',
];

const STATUS_COLORS: Record<string, string> = {
  active: 'var(--critical)',
  investigating: 'var(--high)',
  resolved: 'var(--low)',
};

export const EventsPage: React.FC = () => {
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Partial<AlertFilters>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const PAGE_SIZE = 20;

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getEvents(filters, page, PAGE_SIZE);
      setEvents(result.items);
      setTotal(result.total);
    } catch {
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);
  useEffect(() => { getCameras().then(setCameras).catch(() => {}); }, []);

  const columns: ColumnDef<Event>[] = [
    {
      key: 'expand',
      header: '',
      width: 36,
      render: (row) => {
        const ev = row as Event;
        const isExpanded = expandedId === ev.event_id;
        return (
          <button
            onClick={(e) => { e.stopPropagation(); setExpandedId(isExpanded ? null : ev.event_id); }}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-dim)',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
              transform: isExpanded ? 'rotate(90deg)' : 'none',
              transition: 'transform 200ms',
            }}
            aria-label={isExpanded ? 'Collapse row' : 'Expand row'}
            aria-expanded={isExpanded}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
        );
      },
    },
    {
      key: 'severity',
      header: 'Severity',
      sortable: true,
      width: 100,
      render: (row) => <SeverityBadge severity={(row as Event).severity} size="sm" />,
    },
    {
      key: 'event_type',
      header: 'Event Type',
      sortable: true,
      render: (row) => (
        <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
          {(row as Event).event_type.replace(/_/g, ' ')}
        </span>
      ),
    },
    {
      key: 'camera_name',
      header: 'Camera',
      sortable: true,
      render: (row) => (
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
          {(row as Event).camera_name}
        </span>
      ),
    },
    {
      key: 'zone_name',
      header: 'Zone',
      render: (row) => (
        <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          {(row as Event).zone_name ?? 'N/A'}
        </span>
      ),
    },
    {
      key: 'risk_score',
      header: 'Risk',
      sortable: true,
      width: 80,
      render: (row) => {
        const ev = row as Event;
        const color = ev.risk_score >= 80 ? 'var(--critical)' : ev.risk_score >= 60 ? 'var(--high)' : ev.risk_score >= 40 ? 'var(--medium)' : 'var(--low)';
        return <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color, fontWeight: 700 }}>{ev.risk_score}</span>;
      },
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      render: (row) => {
        const ev = row as Event;
        const color = STATUS_COLORS[ev.status] ?? 'var(--text-dim)';
        return (
          <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 3, textTransform: 'uppercase', letterSpacing: '0.06em', color, backgroundColor: `${color}18`, border: `1px solid ${color}30` }}>
            {ev.status}
          </span>
        );
      },
    },
    {
      key: 'timestamp',
      header: 'Time',
      sortable: true,
      render: (row) => (
        <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)' }}>
          {new Date((row as Event).timestamp).toLocaleString()}
        </span>
      ),
    },
    {
      key: 'duration_seconds',
      header: 'Duration',
      render: (row) => {
        const ev = row as Event;
        if (!ev.duration_seconds) return <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>Ongoing</span>;
        const m = Math.floor(ev.duration_seconds / 60);
        const s = ev.duration_seconds % 60;
        return (
          <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-secondary)' }}>
            {m > 0 ? `${m}m ` : ''}{s}s
          </span>
        );
      },
    },
  ];

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      <div>
        <h1 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>Event History</h1>
        <p style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 2 }}>{total} total events</p>
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
                  onClick={() => setFilters((f) => ({ ...f, severity: active ? f.severity?.filter((x) => x !== s) : [...(f.severity ?? []), s] }))}
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

        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            Event Type
          </label>
          <select
            value={filters.event_type ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, event_type: (e.target.value as EventType) || undefined }))}
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font)', cursor: 'pointer', outline: 'none' }}
          >
            <option value="">All Types</option>
            {EVENT_TYPE_OPTIONS.map((et) => (
              <option key={et} value={et}>{et.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            Camera
          </label>
          <select
            value={filters.camera_id ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, camera_id: e.target.value || undefined }))}
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font)', cursor: 'pointer', outline: 'none' }}
          >
            <option value="">All Cameras</option>
            {cameras.map((c) => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
          </select>
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            From
          </label>
          <input
            type="date"
            value={filters.date_from ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value || undefined }))}
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font)', outline: 'none', colorScheme: 'dark' }}
          />
        </div>

        <div>
          <label style={{ display: 'block', fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 5 }}>
            To
          </label>
          <input
            type="date"
            value={filters.date_to ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value || undefined }))}
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 4, padding: '5px 8px', color: 'var(--text-primary)', fontSize: 11, fontFamily: 'var(--font)', outline: 'none', colorScheme: 'dark' }}
          />
        </div>

        <button
          onClick={() => { setFilters({}); setPage(1); }}
          style={{ padding: '5px 12px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-dim)', fontSize: 11, fontFamily: 'var(--font)', cursor: 'pointer' }}
        >
          Clear
        </button>
      </div>

      {/* Table with expandable rows */}
      <div
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          flex: 1,
          overflow: 'hidden',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    style={{
                      padding: '10px 12px',
                      textAlign: col.align ?? 'left',
                      fontSize: 10,
                      fontWeight: 600,
                      letterSpacing: '0.08em',
                      color: 'var(--text-dim)',
                      borderBottom: '1px solid var(--border)',
                      whiteSpace: 'nowrap',
                      backgroundColor: 'var(--bg-surface)',
                      width: col.width,
                    }}
                  >
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i}>
                      {columns.map((col) => (
                        <td key={col.key} style={{ padding: '9px 12px', borderBottom: '1px solid var(--border)' }}>
                          <div className="skeleton" style={{ height: 14, width: `${55 + ((i * 11 + columns.indexOf(col) * 19) % 40)}%` }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : events.length === 0
                ? (
                  <tr>
                    <td colSpan={columns.length} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
                      No events found
                    </td>
                  </tr>
                )
                : events.map((event, idx) => (
                  <React.Fragment key={event.event_id}>
                    <tr
                      style={{
                        backgroundColor: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                        transition: 'background-color 100ms',
                        cursor: 'pointer',
                      }}
                      onClick={() => setExpandedId(expandedId === event.event_id ? null : event.event_id)}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = 'rgba(0,212,170,0.04)'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)'; }}
                    >
                      {columns.map((col) => (
                        <td key={col.key} style={{ padding: '9px 12px', borderBottom: '1px solid var(--border)', verticalAlign: 'middle' }}>
                          {col.render ? col.render(event, idx) : String((event as unknown as Record<string, unknown>)[col.key] ?? '')}
                        </td>
                      ))}
                    </tr>
                    {expandedId === event.event_id && (
                      <tr>
                        <td colSpan={columns.length} style={{ padding: 0, borderBottom: '1px solid var(--border)' }}>
                          <div
                            style={{
                              padding: '16px 20px',
                              backgroundColor: 'var(--bg-elevated)',
                              display: 'grid',
                              gridTemplateColumns: '1fr 320px',
                              gap: 20,
                              animation: 'slideUp 200ms ease',
                            }}
                          >
                            {/* Snapshot */}
                            <div>
                              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                                Snapshot
                              </div>
                              {event.evidence_package_id ? (
                                <img
                                  src={`/evidence/${event.event_id}/snapshot`}
                                  alt="Event snapshot"
                                  style={{ maxWidth: '100%', maxHeight: 200, objectFit: 'contain', borderRadius: 'var(--radius)', border: '1px solid var(--border)', display: 'block' }}
                                />
                              ) : (
                                <div
                                  style={{
                                    width: '100%',
                                    height: 120,
                                    backgroundColor: 'var(--bg-surface)',
                                    border: '1px dashed var(--border)',
                                    borderRadius: 'var(--radius)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    color: 'var(--text-dim)',
                                    fontSize: 11,
                                  }}
                                >
                                  No snapshot available
                                </div>
                              )}
                              <div style={{ marginTop: 12 }}>
                                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
                                  Alert IDs ({event.alert_ids.length})
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                  {event.alert_ids.slice(0, 5).map((id) => (
                                    <span key={id} style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-secondary)', padding: '2px 6px', backgroundColor: 'var(--bg-surface)', borderRadius: 3, border: '1px solid var(--border)' }}>
                                      {id.slice(0, 12)}...
                                    </span>
                                  ))}
                                  {event.alert_ids.length > 5 && (
                                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>+{event.alert_ids.length - 5} more</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            {/* Risk breakdown */}
                            <div>
                              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
                                Risk Summary
                              </div>
                              <RiskBreakdown
                                breakdown={event.factor_breakdown}
                                riskScore={event.risk_score}
                                severity={event.severity}
                              />
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              }
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {Math.ceil(total / PAGE_SIZE) > 1 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 12px',
              borderTop: '1px solid var(--border)',
            }}
          >
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              Page {page} of {Math.ceil(total / PAGE_SIZE)} ({total} records)
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                style={{ padding: '4px 10px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font)', cursor: page > 1 ? 'pointer' : 'not-allowed', opacity: page <= 1 ? 0.4 : 1 }}
              >
                Prev
              </button>
              <button
                disabled={page >= Math.ceil(total / PAGE_SIZE)}
                onClick={() => setPage((p) => p + 1)}
                style={{ padding: '4px 10px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font)', cursor: page < Math.ceil(total / PAGE_SIZE) ? 'pointer' : 'not-allowed', opacity: page >= Math.ceil(total / PAGE_SIZE) ? 0.4 : 1 }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
