import React from 'react';
import type { SeverityLevel } from '../../types';

interface SeverityBadgeProps {
  severity: SeverityLevel;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
}

const SEVERITY_CONFIG: Record<
  SeverityLevel,
  { color: string; bg: string; border: string; label: string; iconPath: string }
> = {
  CRITICAL: {
    color: '#EF4444',
    bg: 'rgba(239, 68, 68, 0.12)',
    border: 'rgba(239, 68, 68, 0.35)',
    label: 'CRITICAL',
    iconPath: 'M12 2L2 19h20L12 2zm0 4l7.5 13h-15L12 6zm0 5v4m0 2v1',
  },
  HIGH: {
    color: '#F97316',
    bg: 'rgba(249, 115, 22, 0.12)',
    border: 'rgba(249, 115, 22, 0.35)',
    label: 'HIGH',
    iconPath: 'M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z',
  },
  MEDIUM: {
    color: '#EAB308',
    bg: 'rgba(234, 179, 8, 0.12)',
    border: 'rgba(234, 179, 8, 0.35)',
    label: 'MEDIUM',
    iconPath: 'M12 8v4m0 4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z',
  },
  LOW: {
    color: '#22C55E',
    bg: 'rgba(34, 197, 94, 0.12)',
    border: 'rgba(34, 197, 94, 0.35)',
    label: 'LOW',
    iconPath: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
};

const SIZE_CONFIG = {
  sm: { fontSize: '10px', padding: '2px 6px', iconSize: 10, gap: 4 },
  md: { fontSize: '11px', padding: '3px 8px', iconSize: 12, gap: 5 },
  lg: { fontSize: '12px', padding: '4px 10px', iconSize: 14, gap: 6 },
};

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({
  severity,
  size = 'md',
  showIcon = true,
}) => {
  const cfg = SEVERITY_CONFIG[severity];
  const sz = SIZE_CONFIG[size];

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: sz.gap,
        padding: sz.padding,
        fontSize: sz.fontSize,
        fontFamily: 'var(--font)',
        fontWeight: 700,
        letterSpacing: '0.07em',
        color: cfg.color,
        backgroundColor: cfg.bg,
        border: `1px solid ${cfg.border}`,
        borderRadius: '3px',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      {showIcon && (
        <svg
          width={sz.iconSize}
          height={sz.iconSize}
          viewBox="0 0 24 24"
          fill="none"
          stroke={cfg.color}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d={cfg.iconPath} />
        </svg>
      )}
      {cfg.label}
    </span>
  );
};
