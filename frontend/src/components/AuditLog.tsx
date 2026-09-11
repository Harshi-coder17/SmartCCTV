import React, { useEffect, useState, useCallback } from 'react';
import type { AuditLogEntry } from '../types';
import { getAuditLog } from '../api/client';

const PAGE_SIZE = 50;

// Map action enum values to display colors
const ACTION_COLORS: Record<string, string> = {
  LOGIN: 'var(--low)',
  LOGOUT: 'var(--text-dim)',
  ALERT_DISPOSITION: 'var(--accent)',
  CONFIG_CHANGE: 'var(--medium)',
  ADMIN_ACTION: 'var(--high)',
  EVIDENCE_ACCESS: 'var(--info)',
  EXPORT: 'var(--info)',
  MODEL_DEPLOY: 'var(--accent)',
  ZONE_MODIFY: 'var(--medium)',
  CAMERA_MODIFY: 'var(--medium)',
  PERSONNEL_ENROLL: 'var(--low)',
};

function ActionBadge({ action }: { action: string }) {
  const color = ACTION_COLORS[action] ?? 'var(--text-secondary)';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 3,
      fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600, letterSpacing: '0.04em',
      background: `${color}20`, color, border: `1px solid ${color}40`, whiteSpace: 'nowrap',
    }}>
      {action}
    </span>
  );
}

export const AuditLog: React.FC = () => {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [chainValid, setChainValid] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await getAuditLog(page, PAGE_SIZE);
      setEntries(resp.items);
      setTotal(resp.total);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { void load(); }, [load]);

  async function verifyChain() {
    try {
      const resp = await fetch('/evidence/chain-verify', { credentials: 'include' });
      const data = await resp.json() as { is_valid?: boolean; chain_valid?: boolean };
      setChainValid(data.is_valid ?? data.chain_valid ?? false);
    } catch {
      setChainValid(false);
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>Audit Log</h2>
          <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>Tamper-evident record of all operator and system actions</p>
        </div>
        <button
          onClick={() => void verifyChain()}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px',
            background: 'var(--accent-dim)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius)', color: 'var(--accent)', fontSize: 12,
            fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
            <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Verify Chain
        </button>
      </div>

      {chainValid !== null && (
        <div style={{
          padding: '10px 14px', borderRadius: 'var(--radius)',
          background: chainValid ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${chainValid ? 'var(--low)' : 'var(--critical)'}`,
          color: chainValid ? 'var(--low)' : 'var(--critical)',
          fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
            {chainValid ? <path d="M9 12l2 2 4-4" /> : <path d="M6 18L18 6M6 6l12 12" />}
          </svg>
          {chainValid ? 'Hash chain verified - ledger integrity confirmed' : 'CHAIN INTEGRITY FAILURE - possible tampering detected'}
        </div>
      )}

      <div style={{
        flex: 1, overflow: 'hidden', background: 'var(--bg-surface)',
        border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>
                {['Timestamp', 'Action', 'Actor', 'Role', 'Target', 'IP'].map((h) => (
                  <th key={h} style={{
                    padding: '10px 12px', textAlign: 'left', fontSize: 10, fontWeight: 600,
                    letterSpacing: '0.08em', color: 'var(--text-dim)', borderBottom: '1px solid var(--border)',
                    position: 'sticky', top: 0, background: 'var(--bg-surface)', whiteSpace: 'nowrap',
                  }}>
                    {h.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 6 }).map((__, j) => (
                      <td key={j} style={{ padding: '9px 12px', borderBottom: '1px solid var(--border)' }}>
                        <div className="skeleton" style={{ height: 12, width: `${50 + (i * 11 + j * 13) % 40}%` }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '40px 12px', textAlign: 'center', color: 'var(--text-dim)' }}>
                    No audit records found
                  </td>
                </tr>
              ) : entries.map((entry) => (
                <tr key={entry.log_id}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,212,170,0.03)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                >
                  <td style={{ padding: '8px 12px', color: 'var(--text-dim)', fontFamily: 'var(--mono)', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {new Date(entry.timestamp).toLocaleString()}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <ActionBadge action={entry.action} />
                  </td>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
                    {entry.actor_username ?? entry.actor_id ?? 'system'}
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-dim)', fontSize: 11 }}>
                    {entry.actor_role ?? '-'}
                  </td>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
                    {entry.target_type ?? '-'}/{entry.target_id ?? '-'}
                  </td>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)' }}>
                    {entry.ip_address ?? '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 12px', borderTop: '1px solid var(--border)', flexShrink: 0,
          }}>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Page {page} of {totalPages} ({total} records)</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{
                padding: '4px 10px', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)',
                cursor: page <= 1 ? 'not-allowed' : 'pointer', fontSize: 11, fontFamily: 'var(--font)',
              }}>Prev</button>
              <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} style={{
                padding: '4px 10px', background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)',
                cursor: page >= totalPages ? 'not-allowed' : 'pointer', fontSize: 11, fontFamily: 'var(--font)',
              }}>Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
