'use client';

/**
 * AuthGuard — DISABLED for development.
 * To re-enable login, uncomment the original logic below.
 */
export default function AuthGuard({
    children,
    minRole,
}: {
    children: React.ReactNode;
    minRole?: 'admin' | 'manager' | 'lead' | 'contributor';
}) {
    // Auth disabled — render children directly
    return <>{children}</>;
}

/*
// ── ORIGINAL AUTH GUARD (uncomment to re-enable login) ──

import { useAuth } from '@/lib/auth';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function AuthGuard({
    children,
    minRole,
}: {
    children: React.ReactNode;
    minRole?: 'admin' | 'manager' | 'lead' | 'contributor';
}) {
    const { isAuthenticated, loading, user } = useAuth();
    const router = useRouter();

    const ROLE_HIERARCHY: Record<string, number> = {
        admin: 4,
        manager: 3,
        lead: 2,
        contributor: 1,
    };

    useEffect(() => {
        if (!loading && !isAuthenticated) {
            router.replace('/login');
        }
    }, [loading, isAuthenticated, router]);

    if (loading) {
        return (
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                minHeight: '100vh', background: 'var(--bg-primary, #0a0a0f)',
                color: 'var(--text-muted, #6b7280)', fontSize: 14,
            }}>
                <div style={{ textAlign: 'center' }}>
                    <div style={{
                        width: 32, height: 32, border: '3px solid rgba(99,102,241,0.2)',
                        borderTopColor: '#6366f1', borderRadius: '50%',
                        animation: 'spin 0.8s linear infinite',
                        margin: '0 auto 12px',
                    }} />
                    Loading...
                </div>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    if (!isAuthenticated) return null;

    if (minRole && user) {
        const userLevel = ROLE_HIERARCHY[user.role] || 0;
        const requiredLevel = ROLE_HIERARCHY[minRole] || 0;
        if (userLevel < requiredLevel) {
            return (
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    minHeight: '100vh', background: 'var(--bg-primary, #0a0a0f)',
                    color: '#ef4444', fontSize: 14,
                }}>
                    <div style={{ textAlign: 'center' }}>
                        <p style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Access Denied</p>
                        <p style={{ color: 'var(--text-muted, #6b7280)' }}>
                            You need <strong>{minRole}</strong> role or higher. Your role: <strong>{user.role}</strong>
                        </p>
                    </div>
                </div>
            );
        }
    }

    return <>{children}</>;
}
*/

