'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
    const { login, isAuthenticated } = useAuth();
    const router = useRouter();

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    // Already logged in? Redirect
    if (isAuthenticated) {
        router.replace('/');
        return null;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            await login(email, password);
            router.replace('/');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Login failed');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#0a0a0f', fontFamily: "'Inter', -apple-system, sans-serif",
        }}>
            <div style={{
                width: 400, padding: 36, borderRadius: 16,
                background: '#13131a', border: '1px solid rgba(255,255,255,0.08)',
                boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}>
                {/* Logo */}
                <div style={{ textAlign: 'center', marginBottom: 32 }}>
                    <div style={{
                        width: 56, height: 56, borderRadius: 14, margin: '0 auto 16px',
                        background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        border: '1px solid rgba(99,102,241,0.3)',
                    }}>
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2">
                            <path d="M12 2L2 7l10 5 10-5-10-5z" />
                            <path d="M2 17l10 5 10-5" />
                            <path d="M2 12l10 5 10-5" />
                        </svg>
                    </div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e5e7eb', margin: 0 }}>
                        Company AI
                    </h1>
                    <p style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>
                        Enterprise Agent Platform
                    </p>
                </div>

                <form onSubmit={handleSubmit}>
                    {/* Email */}
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#9ca3af', marginBottom: 6 }}>
                        Email
                    </label>
                    <input
                        type="email"
                        value={email}
                        onChange={e => setEmail(e.target.value)}
                        placeholder="you@company.ai"
                        required
                        autoFocus
                        style={{
                            width: '100%', padding: '11px 14px', borderRadius: 8, fontSize: 14,
                            border: '1px solid rgba(255,255,255,0.1)', background: '#1a1a24',
                            color: '#e5e7eb', marginBottom: 16, boxSizing: 'border-box',
                            outline: 'none', transition: 'border-color 0.2s',
                        }}
                        onFocus={e => e.target.style.borderColor = 'rgba(99,102,241,0.5)'}
                        onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                    />

                    {/* Password */}
                    <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#9ca3af', marginBottom: 6 }}>
                        Password
                    </label>
                    <input
                        type="password"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        placeholder="Your password"
                        required
                        style={{
                            width: '100%', padding: '11px 14px', borderRadius: 8, fontSize: 14,
                            border: '1px solid rgba(255,255,255,0.1)', background: '#1a1a24',
                            color: '#e5e7eb', marginBottom: 20, boxSizing: 'border-box',
                            outline: 'none', transition: 'border-color 0.2s',
                        }}
                        onFocus={e => e.target.style.borderColor = 'rgba(99,102,241,0.5)'}
                        onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
                    />

                    {/* Error */}
                    {error && (
                        <div style={{
                            padding: '10px 14px', borderRadius: 8, marginBottom: 16,
                            background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                            color: '#ef4444', fontSize: 13,
                        }}>
                            {error}
                        </div>
                    )}

                    {/* Submit */}
                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            width: '100%', padding: '12px', borderRadius: 8, fontSize: 14, fontWeight: 600,
                            border: 'none',
                            background: loading ? '#4338ca' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                            color: '#fff', cursor: loading ? 'not-allowed' : 'pointer',
                            transition: 'opacity 0.2s',
                            opacity: loading ? 0.7 : 1,
                        }}
                    >
                        {loading ? 'Signing in...' : 'Sign In'}
                    </button>
                </form>

                {/* Footer */}
                <p style={{ textAlign: 'center', fontSize: 11, color: '#4b5563', marginTop: 20 }}>
                    Don&apos;t have an account? Contact your admin for an invite.
                </p>
            </div>
        </div>
    );
}
