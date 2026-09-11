import React, { type ButtonHTMLAttributes } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: React.ReactNode;
  fullWidth?: boolean;
}

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    backgroundColor: 'var(--accent)',
    color: '#0A0E1A',
    border: '1px solid var(--accent)',
    fontWeight: 600,
  },
  secondary: {
    backgroundColor: 'transparent',
    color: 'var(--text-primary)',
    border: '1px solid var(--border-bright)',
    fontWeight: 500,
  },
  danger: {
    backgroundColor: 'transparent',
    color: 'var(--critical)',
    border: '1px solid rgba(239, 68, 68, 0.4)',
    fontWeight: 500,
  },
  ghost: {
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    border: '1px solid transparent',
    fontWeight: 500,
  },
};

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: '4px 10px', fontSize: '11px', borderRadius: '4px', gap: 5, minHeight: 28 },
  md: { padding: '6px 14px', fontSize: '12px', borderRadius: '5px', gap: 6, minHeight: 34 },
  lg: { padding: '9px 20px', fontSize: '13px', borderRadius: '6px', gap: 8, minHeight: 40 },
};

const HOVER_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: { backgroundColor: 'rgba(0, 212, 170, 0.85)' },
  secondary: { backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--accent)' },
  danger: { backgroundColor: 'rgba(239, 68, 68, 0.12)' },
  ghost: { backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' },
};

export const Button: React.FC<ButtonProps> = ({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled,
  children,
  fullWidth = false,
  style,
  onMouseEnter,
  onMouseLeave,
  ...rest
}) => {
  const [hovered, setHovered] = React.useState(false);
  const isDisabled = disabled || loading;

  const baseStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    fontFamily: 'var(--font)',
    letterSpacing: '0.02em',
    transition: 'all 150ms ease',
    userSelect: 'none',
    outline: 'none',
    whiteSpace: 'nowrap',
    width: fullWidth ? '100%' : undefined,
    opacity: isDisabled ? 0.5 : 1,
    ...(hovered && !isDisabled ? HOVER_STYLES[variant] : {}),
    ...VARIANT_STYLES[variant],
    ...SIZE_STYLES[size],
    ...style,
  };

  return (
    <button
      {...rest}
      disabled={isDisabled}
      style={baseStyle}
      onMouseEnter={(e) => {
        setHovered(true);
        onMouseEnter?.(e);
      }}
      onMouseLeave={(e) => {
        setHovered(false);
        onMouseLeave?.(e);
      }}
    >
      {loading && (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
          aria-hidden="true"
        >
          <path d="M21 12a9 9 0 11-6.219-8.56" />
        </svg>
      )}
      {children}
    </button>
  );
};
