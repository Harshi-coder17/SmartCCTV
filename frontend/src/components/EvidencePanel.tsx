import React, { useEffect, useState } from 'react';
import type { EvidencePackage } from '../types';
import { getEvidencePackage, verifyEvidenceHash } from '../api/client';
import { Button } from './ui/Button';
import { RiskBreakdown } from './RiskBreakdown';
import type { Alert } from '../types';

interface EvidencePanelProps {
  alert: Alert;
}

type ClipTab = 'pre' | 'post';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export const EvidencePanel: React.FC<EvidencePanelProps> = ({ alert }) => {
  const [evidence, setEvidence] = useState<EvidencePackage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ClipTab>('pre');
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyResults, setVerifyResults] = useState<Record<string, boolean | null>>({});

  useEffect(() => {
    setLoading(true);
    setError(null);
    getEvidencePackage(alert.event_id)
      .then(setEvidence)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load evidence'))
      .finally(() => setLoading(false));
  }, [alert.event_id]);

  const handleVerify = async (component: string) => {
    if (!evidence) return;
    setVerifying(component);
    try {
      const result = await verifyEvidenceHash(evidence.package_id, component);
      setVerifyResults((prev) => ({ ...prev, [component]: result.is_valid }));
    } catch {
      setVerifyResults((prev) => ({ ...prev, [component]: false }));
    } finally {
      setVerifying(null);
    }
  };

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = `${BASE_URL}/evidence/${alert.event_id}/download`;
    link.download = `evidence_${alert.event_id}.zip`;
    link.click();
  };

  if (loading) {
    return (
      <div style={{ padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, color: 'var(--text-dim)' }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite' }} aria-hidden="true">
          <path d="M21 12a9 9 0 11-6.219-8.56" />
        </svg>
        Loading evidence package...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <div style={{ fontSize: 12, color: 'var(--critical)' }}>
          {error}
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 8 }}>
          Evidence package may not be generated yet. Check back shortly.
        </p>
      </div>
    );
  }

  const clipUrl =
    activeTab === 'pre'
      ? evidence?.pre_clip_url ?? `${BASE_URL}/evidence/${alert.event_id}/pre-clip`
      : evidence?.post_clip_url ?? `${BASE_URL}/evidence/${alert.event_id}/post-clip`;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', height: '100%', minHeight: 520 }}>
      {/* Left: Video player */}
      <div
        style={{
          backgroundColor: '#050810',
          display: 'flex',
          flexDirection: 'column',
          borderRight: '1px solid var(--border)',
        }}
      >
        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            gap: 0,
            borderBottom: '1px solid var(--border)',
            backgroundColor: 'var(--bg-surface)',
            flexShrink: 0,
          }}
        >
          {([
            { key: 'pre', label: 'Pre-Event' },
            { key: 'post', label: 'Post-Event' },
          ] as const).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              style={{
                padding: '10px 20px',
                border: 'none',
                borderBottom: activeTab === key ? '2px solid var(--accent)' : '2px solid transparent',
                backgroundColor: 'transparent',
                color: activeTab === key ? 'var(--accent)' : 'var(--text-secondary)',
                fontSize: 12,
                fontWeight: activeTab === key ? 600 : 400,
                cursor: 'pointer',
                fontFamily: 'var(--font)',
                transition: 'color 150ms',
              }}
            >
              {label}
            </button>
          ))}

          <div style={{ flex: 1 }} />

          {/* Timeline markers */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', fontSize: 10, color: 'var(--text-dim)' }}>
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: activeTab === 'pre' ? 'var(--medium)' : 'var(--critical)',
              }}
              aria-hidden="true"
            />
            {activeTab === 'pre' ? 'Before event' : 'During / After event'}
          </div>
        </div>

        {/* Video area */}
        <div style={{ flex: 1, position: 'relative' }}>
          <video
            key={clipUrl}
            controls
            style={{
              width: '100%',
              height: '100%',
              display: 'block',
              backgroundColor: '#050810',
              objectFit: 'contain',
            }}
          >
            <source src={clipUrl} type="video/mp4" />
            <source src={clipUrl} type="video/webm" />
            Your browser does not support the video tag.
          </video>
        </div>

        {/* Snapshot preview */}
        {evidence?.snapshot_url && (
          <div
            style={{
              padding: '10px 14px',
              borderTop: '1px solid var(--border)',
              flexShrink: 0,
              backgroundColor: 'var(--bg-surface)',
            }}
          >
            <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.06em', marginBottom: 6, textTransform: 'uppercase' }}>
              Snapshot Frame
            </div>
            <img
              src={evidence.snapshot_url}
              alt="Event snapshot"
              style={{ height: 60, maxWidth: '100%', objectFit: 'contain', borderRadius: 4, border: '1px solid var(--border)' }}
            />
          </div>
        )}
      </div>

      {/* Right: Metadata */}
      <div
        style={{
          padding: 16,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {/* Event ID + basic info */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>
            Event Identification
          </div>
          {[
            { label: 'Event ID', value: alert.event_id, mono: true },
            { label: 'Alert ID', value: alert.alert_id, mono: true },
            { label: 'Camera', value: alert.camera_name, mono: true },
            { label: 'Timestamp', value: new Date(alert.timestamp).toLocaleString(), mono: true },
            { label: 'Zone', value: alert.zone_name ?? 'N/A' },
          ].map(({ label, value, mono }) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
              <span style={{ fontSize: 11, color: 'var(--text-dim)', flexShrink: 0 }}>{label}</span>
              <span
                style={{
                  fontSize: 11,
                  color: 'var(--text-primary)',
                  fontFamily: mono ? 'var(--mono)' : 'var(--font)',
                  textAlign: 'right',
                  maxWidth: 190,
                  wordBreak: 'break-all',
                }}
              >
                {value}
              </span>
            </div>
          ))}
        </div>

        {/* Model versions */}
        {evidence?.model_versions && evidence.model_versions.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>
              Model Versions
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr>
                  {['Model', 'Version', 'Type'].map((h) => (
                    <th key={h} style={{ padding: '5px 6px', textAlign: 'left', color: 'var(--text-dim)', fontWeight: 600, borderBottom: '1px solid var(--border)', fontSize: 10, letterSpacing: '0.06em' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {evidence.model_versions.map((mv, i) => (
                  <tr key={i}>
                    <td style={{ padding: '5px 6px', color: mv.is_current ? 'var(--accent)' : 'var(--text-primary)', fontFamily: 'var(--mono)', fontSize: 10 }}>{mv.model_name}</td>
                    <td style={{ padding: '5px 6px', color: 'var(--text-secondary)', fontFamily: 'var(--mono)', fontSize: 10 }}>{mv.version}</td>
                    <td style={{ padding: '5px 6px', color: 'var(--text-dim)', fontSize: 10, textTransform: 'capitalize' }}>{mv.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Hash verification */}
        {evidence && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>
              Hash Verification
            </div>
            {Object.entries(evidence.hashes)
              .filter(([, v]) => v)
              .map(([key, hash]) => {
                const label = key.replace(/_sha256$/, '').replace(/_/g, ' ');
                const result = verifyResults[key];
                return (
                  <div
                    key={key}
                    style={{
                      marginBottom: 10,
                      padding: '8px 10px',
                      backgroundColor: 'var(--bg-elevated)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>
                        {label}
                      </span>
                      {result !== undefined && (
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            color: result ? 'var(--low)' : 'var(--critical)',
                            letterSpacing: '0.04em',
                          }}
                        >
                          {result ? 'Verified' : 'Hash Mismatch'}
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 9,
                        fontFamily: 'var(--mono)',
                        color: 'var(--text-dim)',
                        wordBreak: 'break-all',
                        marginBottom: 6,
                        lineHeight: 1.5,
                      }}
                    >
                      SHA-256: {hash}
                    </div>
                    <Button
                      size="sm"
                      variant={result === true ? 'ghost' : 'secondary'}
                      loading={verifying === key}
                      onClick={() => handleVerify(key)}
                    >
                      {result === true ? (
                        <>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--low)" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                            <path d="M9 11l3 3L22 4" />
                          </svg>
                          Re-Verify
                        </>
                      ) : 'Verify Integrity'}
                    </Button>
                  </div>
                );
              })}
          </div>
        )}

        {/* Evidence package status */}
        {evidence && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>
              Package Status
            </div>
            {[
              {
                label: 'Encryption',
                value: evidence.encryption_status === 'encrypted' ? 'Encrypted' : 'Unencrypted',
                ok: evidence.encryption_status === 'encrypted',
              },
              {
                label: 'Integrity',
                value: evidence.verification_status === 'verified' ? 'Verified' : evidence.verification_status,
                ok: evidence.verification_status === 'verified',
              },
              {
                label: 'Chain',
                value: evidence.chain_hash ? 'Present' : 'Not Available',
                ok: !!evidence.chain_hash,
              },
            ].map(({ label, value, ok }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={ok ? 'var(--low)' : 'var(--text-dim)'} strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                    {ok ? <path d="M9 11l3 3L22 4" /> : <circle cx="12" cy="12" r="10" />}
                  </svg>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{label}</span>
                </div>
                <span style={{ fontSize: 11, color: ok ? 'var(--low)' : 'var(--text-dim)', fontWeight: 500 }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Risk breakdown */}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>
            Risk Analysis
          </div>
          <RiskBreakdown breakdown={alert.factor_breakdown} riskScore={alert.risk_score} severity={alert.severity} />
        </div>

        {/* Download */}
        <Button variant="secondary" size="md" fullWidth onClick={handleDownload}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" />
          </svg>
          Download Evidence Bundle
        </Button>
      </div>
    </div>
  );
};
