'use client';

import { useEffect, useState } from 'react';
import { api, DashboardData } from '@/lib/api';

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

export default function DashboardPage() {
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

    const totalTraces = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
    const failed = data.status_counts['failed'] || 0;
    const maxDeptCost = Math.max(...data.cost_by_department.map((d) => d.cost_usd), 0.01);

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Dashboard Overview</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Real-time agent governance metrics (last 24h)
                    </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div className="pulse-dot" style={{ background: 'var(--success)' }} />
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Live</span>
                </div>
            </div>

            {/* Stat Cards */}
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

            {/* Two columns: Cost by Department + Top Errors */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                {/* Cost by Department */}
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

                {/* Top Errors */}
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
        </div>
    );
}
