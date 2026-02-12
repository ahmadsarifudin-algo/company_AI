'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, TraceRow } from '@/lib/api';

function StatusBadge({ status }: { status: string }) {
    const map: Record<string, string> = {
        completed: 'badge-success',
        running: 'badge-info',
        failed: 'badge-danger',
        pending: 'badge-warning',
        paused: 'badge-neutral',
    };
    return <span className={`badge ${map[status] || 'badge-neutral'}`}>{status}</span>;
}

function RiskBadge({ level }: { level: string | null }) {
    if (!level) return <span className="badge badge-neutral">—</span>;
    const map: Record<string, string> = {
        high: 'badge-danger',
        critical: 'badge-danger',
        medium: 'badge-warning',
        low: 'badge-success',
    };
    return <span className={`badge ${map[level] || 'badge-neutral'}`}>{level}</span>;
}

function formatTime(isoStr: string | null) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function TracesPage() {
    const [traces, setTraces] = useState<TraceRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({
        status: '',
        department: '',
        risk_level: '',
        q: '',
    });

    const load = useCallback(() => {
        setLoading(true);
        const params: Record<string, string> = {};
        if (filters.status) params.status = filters.status;
        if (filters.department) params.department = filters.department;
        if (filters.risk_level) params.risk_level = filters.risk_level;
        if (filters.q) params.q = filters.q;

        api
            .getTraces(params)
            .then((d) => setTraces(d.traces))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [filters]);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Traces</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        All agent execution traces
                    </p>
                </div>
                <button className="btn btn-primary" onClick={load}>
                    Refresh
                </button>
            </div>

            {/* Filters */}
            <div className="card" style={{ padding: 16, marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <input
                    className="input-field"
                    placeholder="Search traces..."
                    style={{ maxWidth: 250 }}
                    value={filters.q}
                    onChange={(e) => setFilters({ ...filters, q: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && load()}
                />
                <select
                    className="input-field"
                    style={{ maxWidth: 140 }}
                    value={filters.status}
                    onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                >
                    <option value="">All Status</option>
                    <option value="completed">Completed</option>
                    <option value="running">Running</option>
                    <option value="failed">Failed</option>
                    <option value="pending">Pending</option>
                </select>
                <select
                    className="input-field"
                    style={{ maxWidth: 140 }}
                    value={filters.department}
                    onChange={(e) => setFilters({ ...filters, department: e.target.value })}
                >
                    <option value="">All Depts</option>
                    <option value="tech">Tech</option>
                    <option value="finance">Finance</option>
                    <option value="hr">HR</option>
                    <option value="sales">Sales</option>
                </select>
                <select
                    className="input-field"
                    style={{ maxWidth: 140 }}
                    value={filters.risk_level}
                    onChange={(e) => setFilters({ ...filters, risk_level: e.target.value })}
                >
                    <option value="">All Risk</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                </select>
                <button className="btn btn-ghost" onClick={load}>
                    Apply
                </button>
            </div>

            {/* Table */}
            {loading ? (
                <div className="card shimmer" style={{ height: 400, borderRadius: 12 }} />
            ) : error ? (
                <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>
            ) : (
                <div className="table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Trace ID</th>
                                <th>Department</th>
                                <th>Status</th>
                                <th>Risk</th>
                                <th>Cost</th>
                                <th>Agent</th>
                                <th>Last Event</th>
                            </tr>
                        </thead>
                        <tbody>
                            {traces.length === 0 ? (
                                <tr>
                                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
                                        No traces found
                                    </td>
                                </tr>
                            ) : (
                                traces.map((t) => (
                                    <tr key={t.trace_id} style={{ cursor: 'pointer' }}>
                                        <td>
                                            <Link
                                                href={`/traces/${t.trace_id}`}
                                                style={{ color: 'var(--accent)', textDecoration: 'none', fontFamily: 'monospace', fontSize: 12 }}
                                            >
                                                {t.trace_id.substring(0, 8)}…
                                            </Link>
                                        </td>
                                        <td style={{ textTransform: 'capitalize' }}>{t.department}</td>
                                        <td><StatusBadge status={t.status} /></td>
                                        <td><RiskBadge level={t.risk_level} /></td>
                                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>${t.total_cost_usd.toFixed(4)}</td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t.current_agent_id || '—'}</td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{formatTime(t.last_event_at)}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
