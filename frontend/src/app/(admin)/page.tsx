'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { api, DashboardData } from '@/lib/api';
import Link from 'next/link';

const ROLE_LEVEL: Record<string, number> = { admin: 4, manager: 3, lead: 2, contributor: 1 };

/* ── Shared Components ─────────────────────── */

function StatCard({
    label,
    value,
    sub,
    color,
    icon,
}: {
    label: string;
    value: string | number;
    sub?: string;
    color: string;
    icon: React.ReactNode;
}) {
    return (
        <div className="stat-card animate-slide-up">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 8 }}>
                        {label}
                    </div>
                    <div style={{ fontSize: 28, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
                    {sub && (
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div>
                    )}
                </div>
                <div
                    style={{
                        width: 40,
                        height: 40,
                        borderRadius: 10,
                        background: `${color}15`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color,
                    }}
                >
                    {icon}
                </div>
            </div>
        </div>
    );
}

function DeptCostBar({ department, cost, maxCost }: { department: string; cost: number; maxCost: number }) {
    const pct = maxCost > 0 ? (cost / maxCost) * 100 : 0;
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <div style={{ width: 80, fontSize: 12, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>
                {department}
            </div>
            <div style={{ flex: 1, height: 6, background: 'var(--bg-surface)', borderRadius: 3, overflow: 'hidden' }}>
                <div
                    style={{
                        width: `${pct}%`,
                        height: '100%',
                        background: 'linear-gradient(90deg, var(--accent), #8b5cf6)',
                        borderRadius: 3,
                        transition: 'width 0.8s ease',
                    }}
                />
            </div>
            <div style={{ width: 70, fontSize: 12, color: 'var(--text-primary)', textAlign: 'right', fontWeight: 500 }}>
                ${cost.toFixed(2)}
            </div>
        </div>
    );
}

function QuickActionCard({ label, href, icon, color }: { label: string; href: string; icon: string; color: string }) {
    return (
        <Link href={href} style={{ textDecoration: 'none' }}>
            <div
                className="card"
                style={{
                    padding: 20,
                    textAlign: 'center',
                    cursor: 'pointer',
                    transition: 'transform 0.2s, box-shadow 0.2s',
                    border: `1px solid ${color}25`,
                }}
                onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.boxShadow = `0 4px 12px ${color}20`;
                }}
                onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = 'none';
                }}
            >
                <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
            </div>
        </Link>
    );
}

/* ── Admin Overview: Full Governance ─────── */

function AdminOverview({ data }: { data: DashboardData }) {
    const totalTraces = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
    const failed = data.status_counts['failed'] || 0;
    const maxDeptCost = Math.max(...data.cost_by_department.map((d) => d.cost_usd), 0.01);

    return (
        <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Governance Dashboard</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Full system overview — all departments (last 24h)
                    </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div className="pulse-dot" style={{ background: 'var(--success)' }} />
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Live</span>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
                <StatCard
                    label="Total Traces"
                    value={totalTraces}
                    color="var(--accent)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                    }
                />
                <StatCard
                    label="Cost Today"
                    value={`$${data.cost.today_usd.toFixed(2)}`}
                    sub={`7d: $${data.cost.last7d_usd.toFixed(2)}`}
                    color="var(--success)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="12" y1="1" x2="12" y2="23" />
                            <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
                        </svg>
                    }
                />
                <StatCard
                    label="Failures"
                    value={failed}
                    color={failed > 0 ? 'var(--danger)' : 'var(--success)'}
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="15" y1="9" x2="9" y2="15" />
                            <line x1="9" y1="9" x2="15" y2="15" />
                        </svg>
                    }
                />
                <StatCard
                    label="Pending Approvals"
                    value={data.approval.pending}
                    color={data.approval.pending > 0 ? 'var(--warning)' : 'var(--text-muted)'}
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <polyline points="12 6 12 12 16 14" />
                        </svg>
                    }
                />
                <StatCard
                    label="Tool Denies"
                    value={data.tool_denies}
                    color={data.tool_denies > 0 ? 'var(--danger)' : 'var(--text-muted)'}
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        </svg>
                    }
                />
                <StatCard
                    label="Error Types"
                    value={data.top_errors.length}
                    color="var(--info)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                            <line x1="12" y1="9" x2="12" y2="13" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                    }
                />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="card" style={{ padding: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>
                        Cost by Department (7d)
                    </h3>
                    {data.cost_by_department.length === 0 ? (
                        <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 20 }}>
                            No cost data yet
                        </div>
                    ) : (
                        data.cost_by_department.map((d) => (
                            <DeptCostBar key={d.department} department={d.department} cost={d.cost_usd} maxCost={maxDeptCost} />
                        ))
                    )}
                </div>
                <div className="card" style={{ padding: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>
                        Top Errors (24h)
                    </h3>
                    {data.top_errors.length === 0 ? (
                        <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 20 }}>
                            🎉 No errors
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {data.top_errors.map((e) => (
                                <div
                                    key={e.error_code}
                                    style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        padding: '8px 12px',
                                        background: 'var(--bg-surface)',
                                        borderRadius: 8,
                                    }}
                                >
                                    <code style={{ fontSize: 12, color: 'var(--danger)' }}>{e.error_code}</code>
                                    <span className="badge badge-danger">{e.count}×</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

/* ── Manager Overview: Department Focus ──── */

function ManagerOverview({ data, department }: { data: DashboardData; department: string }) {
    const totalTraces = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
    const running = data.status_counts['running'] || 0;
    const completed = data.status_counts['completed'] || 0;
    const failed = data.status_counts['failed'] || 0;

    return (
        <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Department Dashboard</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        <span style={{ textTransform: 'capitalize', color: 'var(--accent)', fontWeight: 600 }}>{department}</span> — team performance (last 24h)
                    </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div className="pulse-dot" style={{ background: 'var(--success)' }} />
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Live</span>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
                <StatCard
                    label="Dept Traces"
                    value={totalTraces}
                    color="var(--accent)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                    }
                />
                <StatCard
                    label="Running"
                    value={running}
                    sub={`${completed} completed`}
                    color="var(--info)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <polyline points="12 6 12 12 16 14" />
                        </svg>
                    }
                />
                <StatCard
                    label="Dept Cost Today"
                    value={`$${data.cost.today_usd.toFixed(2)}`}
                    sub={`7d: $${data.cost.last7d_usd.toFixed(2)}`}
                    color="var(--success)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="12" y1="1" x2="12" y2="23" />
                            <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
                        </svg>
                    }
                />
                <StatCard
                    label="Failures"
                    value={failed}
                    color={failed > 0 ? 'var(--danger)' : 'var(--success)'}
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <line x1="15" y1="9" x2="9" y2="15" />
                            <line x1="9" y1="9" x2="15" y2="15" />
                        </svg>
                    }
                />
                <StatCard
                    label="Pending Approvals"
                    value={data.approval.pending}
                    color={data.approval.pending > 0 ? 'var(--warning)' : 'var(--text-muted)'}
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M9 11l3 3L22 4" />
                            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                        </svg>
                    }
                />
            </div>

            {/* Quick links for manager */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
                <QuickActionCard label="Team Traces" href="/traces" icon="📊" color="var(--accent)" />
                <QuickActionCard label="Approvals" href="/approvals" icon="✅" color="var(--warning)" />
                <QuickActionCard label="Dept Agents" href="/agents" icon="🤖" color="var(--info)" />
                <QuickActionCard label="Tasks" href="/tasks" icon="📋" color="var(--success)" />
            </div>

            {/* Errors */}
            {data.top_errors.length > 0 && (
                <div className="card" style={{ padding: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>
                        Department Errors (24h)
                    </h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {data.top_errors.map((e) => (
                            <div
                                key={e.error_code}
                                style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    padding: '8px 12px',
                                    background: 'var(--bg-surface)',
                                    borderRadius: 8,
                                }}
                            >
                                <code style={{ fontSize: 12, color: 'var(--danger)' }}>{e.error_code}</code>
                                <span className="badge badge-danger">{e.count}×</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}

/* ── Contributor Overview: My Work ────────── */

function ContributorOverview({ data, userName }: { data: DashboardData; userName: string }) {
    const totalTraces = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
    const running = data.status_counts['running'] || 0;
    const completed = data.status_counts['completed'] || 0;

    return (
        <>
            <div style={{ marginBottom: 24 }}>
                <h1 style={{ fontSize: 24, fontWeight: 700 }}>
                    Welcome back, <span style={{ color: 'var(--accent)' }}>{userName}</span>
                </h1>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                    Your workspace overview
                </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
                <StatCard
                    label="Active Traces"
                    value={running}
                    sub={`${completed} completed`}
                    color="var(--accent)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                    }
                />
                <StatCard
                    label="Total Activity"
                    value={totalTraces}
                    color="var(--info)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" />
                            <polyline points="12 6 12 12 16 14" />
                        </svg>
                    }
                />
                <StatCard
                    label="Cost Usage"
                    value={`$${data.cost.today_usd.toFixed(2)}`}
                    sub="today"
                    color="var(--success)"
                    icon={
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="12" y1="1" x2="12" y2="23" />
                            <path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
                        </svg>
                    }
                />
            </div>

            {/* Quick Actions */}
            <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: 'var(--text-primary)' }}>Quick Actions</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
                <QuickActionCard label="Chat with Agent" href="/playground" icon="💬" color="var(--accent)" />
                <QuickActionCard label="My Tasks" href="/tasks" icon="📋" color="var(--success)" />
                <QuickActionCard label="My SOUL" href="/souls" icon="💜" color="#8b5cf6" />
                <QuickActionCard label="Knowledge Base" href="/knowledge" icon="📚" color="var(--info)" />
                <QuickActionCard label="My Traces" href="/traces" icon="📊" color="var(--warning)" />
            </div>
        </>
    );
}

/* ── Main Page Controller ────────────────── */

export default function DashboardPage() {
    const { user } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        api
            .getDashboard(24)
            .then(setData)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    const role = user?.role || 'contributor';
    const roleLevel = ROLE_LEVEL[role] || 1;

    if (loading) {
        return (
            <div>
                <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Dashboard Overview</h1>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
                    {[...Array(6)].map((_, i) => (
                        <div key={i} className="card shimmer" style={{ height: 100, borderRadius: 12 }} />
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div>
                <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 16 }}>Dashboard Overview</h1>
                <div className="card" style={{ padding: 32, textAlign: 'center' }}>
                    <div style={{ fontSize: 48, marginBottom: 12 }}>⚠️</div>
                    <div style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 4 }}>
                        Failed to Load Dashboard
                    </div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{error}</div>
                    <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>
                        Make sure the backend is running at{' '}
                        <code style={{ color: 'var(--accent)' }}>localhost:8000</code>
                    </div>
                </div>
            </div>
        );
    }

    if (!data) return null;

    return (
        <div className="animate-fade-in">
            {/* Role badge */}
            <div style={{ position: 'absolute', top: 16, right: 24 }}>
                <span
                    className={`badge ${roleLevel >= 4 ? 'badge-danger' : roleLevel >= 3 ? 'badge-warning' : roleLevel >= 2 ? 'badge-info' : 'badge-success'}`}
                    style={{ fontSize: 11 }}
                >
                    {role.toUpperCase()}
                </span>
            </div>

            {/* Conditional rendering per role */}
            {roleLevel >= 4 ? (
                <AdminOverview data={data} />
            ) : roleLevel >= 3 ? (
                <ManagerOverview data={data} department={user?.department || 'unknown'} />
            ) : (
                <ContributorOverview data={data} userName={user?.name || 'User'} />
            )}
        </div>
    );
}
