'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

interface InviteInfo {
    name: string;
    email: string;
    department: string;
    role: string;
    valid: boolean;
    message: string;
}

function InviteForm() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token') || '';

    const [info, setInfo] = useState<InviteInfo | null>(null);
    const [loading, setLoading] = useState(true);
    const [password, setPassword] = useState('');
    const [confirm, setConfirm] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    const [done, setDone] = useState(false);

    useEffect(() => {
        if (!token) {
            setLoading(false);
            return;
        }
        fetch(`${API_BASE}/auth/invite-info?token=${encodeURIComponent(token)}`)
            .then(r => r.json())
            .then(data => setInfo(data))
            .catch(() => setError('Failed to validate invite link'))
            .finally(() => setLoading(false));
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (password.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }
        if (password !== confirm) {
            setError('Passwords do not match');
            return;
        }

        try {
            setSubmitting(true);
            const res = await fetch(`${API_BASE}/auth/set-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, password }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Failed to set password');
            setDone(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to set password');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#0a0a0f', fontFamily: "'Inter', -apple-system, sans-serif",
        }}>
            <div style={{
                width: 420, padding: 36, borderRadius: 16,
                background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
                boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}>
                {/* Logo */}
                <div style={{ textAlign: 'center', marginBottom: 28 }}>
                    <div style={{
                        width: 48, height: 48, borderRadius: 12, margin: '0 auto 16px',
                        background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: '1px solid rgba(99,102,241,0.3)',
                    }}>
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2">
                            <circle cx="12" cy="8" r="5" />
                            <path d="M20 21a8 8 0 10-16 0" />
                        </svg>
                    </div>
                    <h1 style={{ fontSize: 20, fontWeight: 700, color: '#e5e7eb', margin: 0 }}>
                        Company AI
                    </h1>
                    <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
                        Enterprise Agent Platform
                    </p>
                </div>

                {loading ? (
                    <div style={{ textAlign: 'center', padding: 20, color: '#6b7280' }}>Validating invite link...</div>
                ) : !token ? (
                    <div style={{ textAlign: 'center', padding: 20, color: '#ef4444' }}>
                        No invite token provided. Check your link.
                    </div>
                ) : done ? (
                    /* ── Success ── */
                    <div style={{ textAlign: 'center' }}>
                        <div style={{
                            width: 56, height: 56, borderRadius: '50%', margin: '0 auto 16px',
                            background: 'rgba(34, 197, 94, 0.1)', display: 'flex',
                            alignItems: 'center', justifyContent: 'center',
                        }}>
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                                <path d="M9 11l3 3L22 4" />
                            </svg>
                        </div>
                        <h2 style={{ fontSize: 18, fontWeight: 600, color: '#e5e7eb', marginBottom: 8 }}>
                            Account Activated!
                        </h2>
                        <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 20 }}>
                            You can now login to the dashboard.
                        </p>
                        <a
                            href="/"
                            style={{
                                display: 'inline-block', padding: '10px 28px', borderRadius: 8,
                                background: '#6366f1', color: '#fff', fontWeight: 600, fontSize: 14,
                                textDecoration: 'none',
                            }}
                        >
                            Go to Dashboard
                        </a>
                    </div>
                ) : info && !info.valid ? (
                    /* ── Invalid token ── */
                    <div style={{ textAlign: 'center', padding: 20 }}>
                        <p style={{ color: '#ef4444', fontSize: 14, marginBottom: 8 }}>{info.message}</p>
                        {info.name && (
                            <p style={{ color: '#6b7280', fontSize: 13 }}>
                                Hi {info.name}, please contact your admin.
                            </p>
                        )}
                    </div>
                ) : info ? (
                    /* ── Set Password Form ── */
                    <>
                        <div style={{
                            padding: '12px 16px', borderRadius: 8, marginBottom: 20,
                            background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)',
                        }}>
                            <p style={{ fontSize: 13, color: '#a5b4fc', margin: 0 }}>
                                Welcome, <strong>{info.name}</strong>! Set your password to activate your account.
                            </p>
                            <p style={{ fontSize: 11, color: '#6b7280', margin: '4px 0 0' }}>
                                {info.department.charAt(0).toUpperCase() + info.department.slice(1)} · {info.role.charAt(0).toUpperCase() + info.role.slice(1)}
                            </p>
                        </div>

                        <form onSubmit={handleSubmit}>
                            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#9ca3af', marginBottom: 6 }}>
                                Password
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={e => setPassword(e.target.value)}
                                placeholder="At least 8 characters"
                                required
                                minLength={8}
                                style={{
                                    width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                    border: '1px solid rgba(255,255,255,0.1)', background: '#1a1a24',
                                    color: '#e5e7eb', marginBottom: 14, boxSizing: 'border-box',
                                }}
                            />

                            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#9ca3af', marginBottom: 6 }}>
                                Confirm Password
                            </label>
                            <input
                                type="password"
                                value={confirm}
                                onChange={e => setConfirm(e.target.value)}
                                placeholder="Re-enter password"
                                required
                                style={{
                                    width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                    border: '1px solid rgba(255,255,255,0.1)', background: '#1a1a24',
                                    color: '#e5e7eb', marginBottom: 20, boxSizing: 'border-box',
                                }}
                            />

                            {error && (
                                <div style={{
                                    padding: '8px 12px', borderRadius: 8, marginBottom: 14,
                                    background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                                    color: '#ef4444', fontSize: 12,
                                }}>
                                    {error}
                                </div>
                            )}

                            <button
                                type="submit"
                                disabled={submitting}
                                style={{
                                    width: '100%', padding: '12px', borderRadius: 8, fontSize: 14, fontWeight: 600,
                                    border: 'none', background: '#6366f1', color: '#fff',
                                    cursor: submitting ? 'not-allowed' : 'pointer',
                                    opacity: submitting ? 0.7 : 1,
                                }}
                            >
                                {submitting ? 'Activating...' : 'Set Password & Activate'}
                            </button>
                        </form>
                    </>
                ) : null}
            </div>
        </div>
    );
}

export default function InvitePage() {
    return (
        <Suspense fallback={
            <div style={{
                minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#0a0a0f', color: '#6b7280',
            }}>
                Loading...
            </div>
        }>
            <InviteForm />
        </Suspense>
    );
}
