import React, { useEffect, useState } from 'react';
import type { TrackSighting } from '../types';
import { getTrackSightings } from '../api/client';

interface TrackTimelineProps {
  trackId: string;
  onSightingClick?: (sighting: TrackSighting) => void;
}

function formatSightingTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const ConfidenceBadge: React.FC<{ confidence: number; linkType?: string }> = ({ confidence, linkType }) => {
  const color = confidence >= 0.8 ? '#22C55E' : confidence >= 0.6 ? '#EAB308' : '#EF4444';
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 3,
      }}
    >
      {/* Connector line */}
      <div
        style={{
          height: 20,
          width: 2,
          backgroundColor: 'var(--border-bright)',
          position: 'relative',
        }}
        aria-hidden="true"
      />

      {/* Confidence badge */}
      <div
        style={{
          padding: '3px 8px',
          backgroundColor: `${color}15`,
          border: `1px solid ${color}40`,
          borderRadius: 10,
          fontSize: 10,
          fontWeight: 700,
          fontFamily: 'var(--mono)',
          color,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
        {(confidence * 100).toFixed(0)}%
        {linkType && (
          <span style={{ color: `${color}80`, fontWeight: 400, marginLeft: 2 }}>
            {linkType}
          </span>
        )}
      </div>

      {/* Connector line continued */}
      <div style={{ height: 20, width: 2, backgroundColor: 'var(--border-bright)' }} aria-hidden="true" />
    </div>
  );
};

interface SightingNodeProps {
  sighting: TrackSighting;
  index: number;
  isFirst: boolean;
  isLast: boolean;
  onClick?: () => void;
}

const SightingNode: React.FC<SightingNodeProps> = ({ sighting, index, isFirst, isLast, onClick }) => {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '12px 14px',
        backgroundColor: hovered ? 'var(--accent-dim)' : 'var(--bg-elevated)',
        border: `1px solid ${hovered ? 'rgba(0,212,170,0.3)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 150ms',
        position: 'relative',
      }}
    >
      {/* Index bubble */}
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          backgroundColor: isFirst ? 'var(--accent)' : isLast ? 'var(--critical)' : 'var(--bg-surface)',
          border: `2px solid ${isFirst ? 'var(--accent)' : isLast ? 'var(--critical)' : 'var(--border-bright)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          fontWeight: 700,
          fontFamily: 'var(--mono)',
          color: isFirst ? '#0A0E1A' : isLast ? '#fff' : 'var(--text-secondary)',
          flexShrink: 0,
        }}
        aria-hidden="true"
      >
        {index + 1}
      </div>

      {/* Camera icon */}
      <div style={{ flexShrink: 0, color: 'var(--text-dim)', paddingTop: 5 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <path d="M23 7l-7 5 7 5V7z" />
          <rect x="1" y="5" width="15" height="14" rx="2" />
        </svg>
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {sighting.camera_name}
          </span>
          <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)', flexShrink: 0 }}>
            {formatSightingTime(sighting.timestamp)}
          </span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
          {sighting.zone_name && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <polygon points="3,6 9,3 15,6 21,3 21,18 15,21 9,18 3,21" />
              </svg>
              {sighting.zone_name}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text-secondary)' }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
            {sighting.location.lat.toFixed(4)}, {sighting.location.lon.toFixed(4)}
          </div>
        </div>

        {/* Confidence */}
        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ height: 4, width: 60, backgroundColor: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${sighting.confidence * 100}%`,
                backgroundColor: sighting.confidence >= 0.8 ? 'var(--low)' : sighting.confidence >= 0.6 ? 'var(--medium)' : 'var(--critical)',
                borderRadius: 2,
              }}
            />
          </div>
          <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--text-dim)' }}>
            {(sighting.confidence * 100).toFixed(0)}% conf.
          </span>
        </div>
      </div>
    </div>
  );
};

export const TrackTimeline: React.FC<TrackTimelineProps> = ({ trackId, onSightingClick }) => {
  const [sightings, setSightings] = useState<TrackSighting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getTrackSightings(trackId)
      .then((data) => setSightings(data.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load track sightings'))
      .finally(() => setLoading(false));
  }, [trackId]);

  if (loading) {
    return (
      <div style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)', fontSize: 12 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" style={{ animation: 'spin 0.8s linear infinite' }} aria-hidden="true">
          <path d="M21 12a9 9 0 11-6.219-8.56" />
        </svg>
        Loading track sightings...
      </div>
    );
  }

  if (error) {
    return <div style={{ padding: 20, fontSize: 12, color: 'var(--critical)' }}>{error}</div>;
  }

  if (sightings.length === 0) {
    return (
      <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontSize: 12 }}>
        No sightings recorded for this track.
      </div>
    );
  }

  const totalDuration = sightings.length > 1
    ? Math.round((new Date(sightings[sightings.length - 1].timestamp).getTime() - new Date(sightings[0].timestamp).getTime()) / 1000)
    : 0;

  return (
    <div>
      {/* Header stats */}
      <div
        style={{
          display: 'flex',
          gap: 16,
          padding: '10px 14px',
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          marginBottom: 16,
        }}
      >
        {[
          { label: 'Cameras', value: String(new Set(sightings.map((s) => s.camera_id)).size) },
          { label: 'Sightings', value: String(sightings.length) },
          { label: 'Duration', value: totalDuration > 60 ? `${Math.floor(totalDuration / 60)}m ${totalDuration % 60}s` : `${totalDuration}s` },
        ].map(({ label, value }) => (
          <div key={label} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{value}</div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Track ID */}
      <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 14, fontFamily: 'var(--mono)' }}>
        Track ID: {trackId}
      </div>

      {/* Timeline */}
      <div>
        {sightings.map((sighting, idx) => (
          <div key={sighting.sighting_id}>
            <SightingNode
              sighting={sighting}
              index={idx}
              isFirst={idx === 0}
              isLast={idx === sightings.length - 1}
              onClick={onSightingClick ? () => onSightingClick(sighting) : undefined}
            />
            {idx < sightings.length - 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', margin: '0 0' }}>
                <ConfidenceBadge
                  confidence={sightings[idx + 1].reid_confidence ?? sighting.confidence}
                  linkType={sightings[idx + 1].reid_link_type}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div
        style={{
          marginTop: 14,
          padding: '8px 12px',
          backgroundColor: 'var(--bg-elevated)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--border)',
          display: 'flex',
          gap: 16,
          fontSize: 10,
          color: 'var(--text-dim)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: 'var(--accent)' }} aria-hidden="true" />
          First Sighting
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: 'var(--critical)' }} aria-hidden="true" />
          Last Sighting
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--low)" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
          </svg>
          ReID Confidence
        </div>
      </div>
    </div>
  );
};
