'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import AuthGuard from '@/components/AuthGuard';
import { useAuth } from '@/lib/auth';

const ROLE_LEVEL: Record<string, number> = { admin: 4, manager: 3, lead: 2, contributor: 1 };

interface NavItem {
    label: string;
    href: string;
    icon: React.ReactNode;
    minRole?: string; // minimum role to see this item
}

const NAV_ITEMS: NavItem[] = [
    {
        label: 'Overview',
        href: '/',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
            </svg>
        ),
    },
    {
        label: 'Traces',
        href: '/traces',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
        ),
    },
    {
        label: 'Approvals',
        href: '/approvals',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 11l3 3L22 4" />
                <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
        ),
    },
    {
        label: 'Policies',
        href: '/policies',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
        ),
    },
    {
        label: 'Agents',
        href: '/agents',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="8" r="5" />
                <path d="M20 21a8 8 0 10-16 0" />
            </svg>
        ),
    },
    {
        label: 'Playground',
        href: '/playground',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            </svg>
        ),
    },
    {
        label: 'Users',
        href: '/users',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 00-3-3.87" />
                <path d="M16 3.13a4 4 0 010 7.75" />
            </svg>
        ),
        minRole: 'manager',
    },
    {
        label: 'Configurations',
        href: '/configurations',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v4" />
                <path d="M12 18v4" />
                <path d="M4.93 4.93l2.83 2.83" />
                <path d="M16.24 16.24l2.83 2.83" />
                <path d="M2 12h4" />
                <path d="M18 12h4" />
                <path d="M4.93 19.07l2.83-2.83" />
                <path d="M16.24 7.76l2.83-2.83" />
            </svg>
        ),
        minRole: 'admin',
    },
    {
        label: 'Settings',
        href: '/settings',
        icon: (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
            </svg>
        ),
        minRole: 'admin',
    },
];

export default function AdminLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const pathname = usePathname();
    const { user, logout } = useAuth();

    return (
        <AuthGuard>
            <div style={{ display: 'flex', minHeight: '100vh' }}>
                {/* Sidebar */}
                <aside
                    style={{
                        width: 240,
                        background: 'var(--bg-secondary)',
                        borderRight: '1px solid var(--border)',
                        display: 'flex',
                        flexDirection: 'column',
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        bottom: 0,
                        zIndex: 50,
                    }}
                >
                    {/* Logo */}
                    <div
                        style={{
                            padding: '20px 16px',
                            borderBottom: '1px solid var(--border)',
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div
                                style={{
                                    width: 32,
                                    height: 32,
                                    borderRadius: 8,
                                    background: 'linear-gradient(135deg, var(--accent), #8b5cf6)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 14,
                                    fontWeight: 700,
                                    color: 'white',
                                }}
                            >
                                AI
                            </div>
                            <div>
                                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                                    Governance
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    Admin Dashboard
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Nav */}
                    <nav style={{ padding: '12px 8px', flex: 1 }}>
                        <div
                            style={{
                                fontSize: 10,
                                fontWeight: 600,
                                textTransform: 'uppercase',
                                letterSpacing: '0.08em',
                                color: 'var(--text-muted)',
                                padding: '8px 12px 4px',
                            }}
                        >
                            Navigation
                        </div>
                        {NAV_ITEMS
                            .filter((item) => {
                                if (!item.minRole) return true;
                                const userLevel = ROLE_LEVEL[user?.role || ''] || 0;
                                const requiredLevel = ROLE_LEVEL[item.minRole] || 0;
                                return userLevel >= requiredLevel;
                            })
                            .map((item) => {
                                const isActive =
                                    item.href === '/'
                                        ? pathname === '/'
                                        : pathname.startsWith(item.href);
                                return (
                                    <Link
                                        key={item.href}
                                        href={item.href}
                                        className={`sidebar-link ${isActive ? 'active' : ''}`}
                                        style={{ marginBottom: 2 }}
                                    >
                                        {item.icon}
                                        {item.label}
                                    </Link>
                                );
                            })}
                    </nav>

                    {/* User info + Logout */}
                    <div
                        style={{
                            padding: '12px 16px',
                            borderTop: '1px solid var(--border)',
                        }}
                    >
                        {user && (
                            <div style={{ marginBottom: 8 }}>
                                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', lineHeight: 1.3 }}>
                                    {user.name}
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    {user.department} · {user.role}
                                </div>
                            </div>
                        )}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                                <div className="pulse-dot" style={{ background: 'var(--success)' }} />
                                Online
                            </div>
                            <button
                                onClick={logout}
                                style={{
                                    padding: '4px 10px', borderRadius: 6, fontSize: 11,
                                    border: '1px solid var(--border)', background: 'transparent',
                                    color: 'var(--text-muted)', cursor: 'pointer',
                                }}
                            >
                                Logout
                            </button>
                        </div>
                    </div>
                </aside>

                {/* Main content */}
                <main
                    style={{
                        flex: 1,
                        marginLeft: 240,
                        padding: '24px 32px',
                        minHeight: '100vh',
                    }}
                >
                    {children}
                </main>
            </div>
        </AuthGuard>
    );
}
