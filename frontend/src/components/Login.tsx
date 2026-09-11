import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthContext } from '../context/AuthContext';

export const Login: React.FC = () => {
  const { login, isLoading } = useAuthContext();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Username and password are required.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Authentication failed. Verify credentials.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: 'var(--bg-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Animated grid background */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(30,41,59,0.4) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30,41,59,0.4) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
          backgroundPosition: 'center center',
          pointerEvents: 'none',
        }}
      />

      {/* Radial glow */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: '30%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 600,
          height: 400,
          background: 'radial-gradient(ellipse at center, rgba(0,212,170,0.06) 0%, transparent 70%)',
          pointerEvents: 'none',
        }}
      />

      {/* Corner indicators */}
      {(['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const).map((corner) => (
        <div
          key={corner}
          aria-hidden="true"
          style={{
            position: 'absolute',
            ...(corner.includes('top') ? { top: 20 } : { bottom: 20 }),
            ...(corner.includes('left') ? { left: 20 } : { right: 20 }),
            width: 20,
            height: 20,
            borderTop: corner.includes('top') ? '2px solid rgba(0,212,170,0.3)' : 'none',
            borderBottom: corner.includes('bottom') ? '2px solid rgba(0,212,170,0.3)' : 'none',
            borderLeft: corner.includes('left') ? '2px solid rgba(0,212,170,0.3)' : 'none',
            borderRight: corner.includes('right') ? '2px solid rgba(0,212,170,0.3)' : 'none',
          }}
        />
      ))}

      {/* Login card */}
      <div
        style={{
          position: 'relative',
          width: 380,
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-bright)',
          borderRadius: 'var(--radius-lg)',
          padding: '40px 36px',
          boxShadow: '0 0 60px rgba(0,0,0,0.6)',
          animation: 'slideUp 300ms ease',
        }}
      >
        {/* Logo area */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 64,
              height: 64,
              backgroundColor: 'var(--accent-dim)',
              border: '1px solid rgba(0,212,170,0.3)',
              borderRadius: 12,
              marginBottom: 16,
            }}
          >
            <svg
              width="36"
              height="36"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.35C17.25 22.15 21 17.25 21 12V7L12 2z" />
              <path d="M9 12l2 2 4-4" strokeWidth="2" />
            </svg>
          </div>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: 'var(--text-primary)',
              letterSpacing: '0.03em',
              marginBottom: 4,
            }}
          >
            SmartCCTV
          </h1>
          <p
            style={{
              fontSize: 11,
              color: 'var(--text-dim)',
              letterSpacing: '0.12em',
              fontWeight: 500,
              textTransform: 'uppercase',
            }}
          >
            Border Intelligence Platform
          </p>
        </div>

        {/* Divider */}
        <div
          style={{
            height: 1,
            backgroundColor: 'var(--border)',
            marginBottom: 28,
          }}
        />

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: 18 }}>
            <label
              htmlFor="username"
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                letterSpacing: '0.08em',
                marginBottom: 6,
                textTransform: 'uppercase',
              }}
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              style={{
                width: '100%',
                backgroundColor: 'var(--bg-elevated)',
                border: `1px solid ${error ? 'var(--critical)' : 'var(--border-bright)'}`,
                borderRadius: 'var(--radius)',
                padding: '9px 12px',
                color: 'var(--text-primary)',
                fontSize: 13,
                fontFamily: 'var(--font)',
                outline: 'none',
                transition: 'border-color 150ms',
              }}
              onFocus={(e) => {
                if (!error) e.currentTarget.style.borderColor = 'var(--accent)';
              }}
              onBlur={(e) => {
                if (!error) e.currentTarget.style.borderColor = 'var(--border-bright)';
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label
              htmlFor="password"
              style={{
                display: 'block',
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-secondary)',
                letterSpacing: '0.08em',
                marginBottom: 6,
                textTransform: 'uppercase',
              }}
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              style={{
                width: '100%',
                backgroundColor: 'var(--bg-elevated)',
                border: `1px solid ${error ? 'var(--critical)' : 'var(--border-bright)'}`,
                borderRadius: 'var(--radius)',
                padding: '9px 12px',
                color: 'var(--text-primary)',
                fontSize: 13,
                fontFamily: 'var(--font)',
                outline: 'none',
                transition: 'border-color 150ms',
              }}
              onFocus={(e) => {
                if (!error) e.currentTarget.style.borderColor = 'var(--accent)';
              }}
              onBlur={(e) => {
                if (!error) e.currentTarget.style.borderColor = 'var(--border-bright)';
              }}
            />
          </div>

          {/* Error message */}
          {error && (
            <div
              role="alert"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                backgroundColor: 'var(--critical-dim)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 'var(--radius)',
                marginBottom: 16,
                animation: 'slideInTop 200ms ease',
              }}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--critical)"
                strokeWidth="2"
                strokeLinecap="round"
                aria-hidden="true"
                style={{ flexShrink: 0 }}
              >
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4m0 4h.01" />
              </svg>
              <span style={{ fontSize: 12, color: 'var(--critical)', flex: 1 }}>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || isLoading}
            style={{
              width: '100%',
              backgroundColor: submitting || isLoading ? 'rgba(0,212,170,0.5)' : 'var(--accent)',
              color: '#0A0E1A',
              border: 'none',
              borderRadius: 'var(--radius)',
              padding: '10px 14px',
              fontSize: 13,
              fontWeight: 700,
              fontFamily: 'var(--font)',
              letterSpacing: '0.04em',
              cursor: submitting || isLoading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              transition: 'background-color 150ms',
            }}
          >
            {submitting || isLoading ? (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  style={{ animation: 'spin 0.8s linear infinite' }}
                  aria-hidden="true"
                >
                  <path d="M21 12a9 9 0 11-6.219-8.56" />
                </svg>
                Authenticating...
              </>
            ) : (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" />
                </svg>
                Authenticate
              </>
            )}
          </button>
        </form>

        {/* Footer notice */}
        <div
          style={{
            marginTop: 24,
            paddingTop: 16,
            borderTop: '1px solid var(--border)',
            textAlign: 'center',
          }}
        >
          <p
            style={{
              fontSize: 10,
              color: 'var(--text-dim)',
              letterSpacing: '0.04em',
              lineHeight: 1.6,
            }}
          >
            RESTRICTED SYSTEM - Authorized personnel only.
            <br />
            All access is logged and monitored.
          </p>
        </div>
      </div>
    </div>
  );
};
