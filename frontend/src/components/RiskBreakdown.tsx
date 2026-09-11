import React from 'react';
import type { FactorBreakdown, SeverityLevel } from '../types';

interface RiskBreakdownProps {
  breakdown: FactorBreakdown;
  riskScore: number;
  severity: SeverityLevel;
}

const SEVERITY_COLOR: Record<SeverityLevel, string> = {
  LOW: '#22C55E',
  MEDIUM: '#EAB308',
  HIGH: '#F97316',
  CRITICAL: '#EF4444',
};

interface FactorRowProps {
  name: string;
  triggered: boolean;
  score?: number;
  maxScore?: number;
  description: string;
}

const FactorRow: React.FC<FactorRowProps> = ({ name, triggered, score = 0, maxScore = 30, description }) => (
  <div
    style={{
      padding: '8px 10px',
      backgroundColor: triggered ? 'rgba(239,68,68,0.06)' : 'transparent',
      border: `1px solid ${triggered ? 'rgba(239,68,68,0.2)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      marginBottom: 6,
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <div
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: triggered ? 'var(--critical)' : 'var(--text-dim)',
            flexShrink: 0,
          }}
          aria-hidden="true"
        />
        <span style={{ fontSize: 11, fontWeight: triggered ? 600 : 400, color: triggered ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
          {name}
        </span>
      </div>
      <span
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: triggered ? 'var(--critical)' : 'var(--text-dim)',
          letterSpacing: '0.04em',
        }}
      >
        {triggered ? `+${score}` : '0'}
      </span>
    </div>
    {triggered && (
      <div style={{ paddingLeft: 14 }}>
        <div style={{ height: 3, backgroundColor: 'var(--border)', borderRadius: 2, overflow: 'hidden', marginBottom: 4 }}>
          <div
            style={{
              height: '100%',
              width: `${Math.min((score / maxScore) * 100, 100)}%`,
              backgroundColor: 'var(--critical)',
              borderRadius: 2,
              transition: 'width 600ms ease',
            }}
          />
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.4 }}>{description}</div>
      </div>
    )}
  </div>
);

function buildExplanation(breakdown: FactorBreakdown): string {
  const parts: string[] = [];
  if (breakdown.zone_violation) parts.push('subject entered a restricted zone');
  if (breakdown.no_traceable_origin) parts.push('no traceable point of origin could be established');
  if (breakdown.route_anomaly) parts.push('movement path deviates from expected patterns');
  if (breakdown.off_hours) parts.push('activity occurred during off-hours');
  if (breakdown.behavior_signals) parts.push('anomalous behavioral signals were detected');
  if (parts.length === 0) return 'Low-confidence detection based on minor behavioral cues. No primary risk factors triggered.';
  return `Alert triggered because: ${parts.join(', ')}. Combined risk score indicates ${breakdown.severity.toLowerCase()} threat level.`;
}

export const RiskBreakdown: React.FC<RiskBreakdownProps> = ({ breakdown, riskScore, severity }) => {
  const color = SEVERITY_COLOR[severity];
  const scorePct = Math.min(riskScore, 100);

  return (
    <div>
      {/* Large score display */}
      <div style={{ textAlign: 'center', marginBottom: 16 }}>
        <div
          style={{
            fontSize: 48,
            fontWeight: 800,
            fontFamily: 'var(--mono)',
            color,
            lineHeight: 1,
            letterSpacing: '-0.02em',
          }}
        >
          {riskScore}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Risk Score
        </div>
      </div>

      {/* Severity band bar */}
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            position: 'relative',
            height: 10,
            borderRadius: 5,
            overflow: 'hidden',
            background: 'linear-gradient(to right, #22C55E 0%, #EAB308 40%, #F97316 70%, #EF4444 100%)',
          }}
          role="progressbar"
          aria-valuenow={riskScore}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Risk score: ${riskScore}`}
        >
          {/* Pointer */}
          <div
            style={{
              position: 'absolute',
              top: -2,
              left: `calc(${scorePct}% - 7px)`,
              width: 14,
              height: 14,
              borderRadius: '50%',
              backgroundColor: color,
              border: '2px solid var(--bg-surface)',
              boxShadow: `0 0 6px ${color}80`,
              transition: 'left 600ms ease',
            }}
            aria-hidden="true"
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          {['Low', 'Medium', 'High', 'Critical'].map((l) => (
            <span key={l} style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: '0.04em' }}>{l}</span>
          ))}
        </div>
      </div>

      {/* Identity Tier */}
      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--text-dim)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: 8,
            paddingBottom: 4,
            borderBottom: '1px solid var(--border)',
          }}
        >
          Identity Tier
        </div>
        <FactorRow
          name="Zone Violation"
          triggered={breakdown.zone_violation}
          score={25}
          description="Subject was detected inside a restricted or high-sensitivity zone."
        />
        <FactorRow
          name="No Traceable Origin"
          triggered={breakdown.no_traceable_origin}
          score={30}
          description="ReID system could not establish a known entry point or identity."
        />
        <FactorRow
          name="Unknown Identity"
          triggered={breakdown.identity_score > 70}
          score={Math.round(breakdown.identity_score * 0.3)}
          maxScore={30}
          description={`Identity confidence: ${breakdown.identity_score.toFixed(0)}% - Person not in authorized personnel list.`}
        />
      </div>

      {/* Behavioral Context */}
      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            color: 'var(--text-dim)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: 8,
            paddingBottom: 4,
            borderBottom: '1px solid var(--border)',
          }}
        >
          Behavioral Context
        </div>
        <FactorRow
          name="Route Anomaly"
          triggered={breakdown.route_anomaly}
          score={20}
          description="Movement trajectory does not match typical or permitted routes."
        />
        <FactorRow
          name="Off-Hours Activity"
          triggered={breakdown.off_hours}
          score={15}
          description="Movement detected outside permitted operating hours."
        />
        <FactorRow
          name="Behavior Signals"
          triggered={breakdown.behavior_signals}
          score={Math.round(breakdown.behavior_score * 0.2)}
          maxScore={20}
          description={`Behavior anomaly score: ${breakdown.behavior_score.toFixed(0)}% - Includes loitering, erratic movement, or suspicious posture.`}
        />
      </div>

      {/* Multipliers */}
      {(breakdown.zone_sensitivity_multiplier || breakdown.time_factor_multiplier) && (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: 'var(--text-dim)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              marginBottom: 8,
              paddingBottom: 4,
              borderBottom: '1px solid var(--border)',
            }}
          >
            Context Multipliers
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 10px',
              backgroundColor: 'var(--bg-elevated)',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              fontSize: 11,
            }}
          >
            <span style={{ color: 'var(--text-secondary)' }}>
              Zone x{(breakdown.zone_sensitivity_multiplier ?? 1).toFixed(1)}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>&times;</span>
            <span style={{ color: 'var(--text-secondary)' }}>
              Time x{(breakdown.time_factor_multiplier ?? 1).toFixed(1)}
            </span>
            <span style={{ color: 'var(--text-dim)' }}>=</span>
            <span style={{ color, fontWeight: 700, fontFamily: 'var(--mono)' }}>
              x{((breakdown.zone_sensitivity_multiplier ?? 1) * (breakdown.time_factor_multiplier ?? 1)).toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* Explanation */}
      <div
        style={{
          padding: '10px 12px',
          backgroundColor: 'var(--accent-dim)',
          border: '1px solid rgba(0,212,170,0.2)',
          borderRadius: 'var(--radius)',
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.06em', marginBottom: 5 }}>
          WHY THIS ALERT?
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
          {breakdown.explanation ?? buildExplanation(breakdown)}
        </p>
      </div>
    </div>
  );
};
