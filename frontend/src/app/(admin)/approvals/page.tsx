'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApprovalRow } from '@/lib/api';

function formatWait(seconds: number) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export default function ApprovalsPage() {
    const [approvals, setApprovals] = useState<ApprovalRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        setLoading(true);
        api
            .getApprovals()
            .then((d) => setApprovals(d.approvals))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Approval Queue</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Traces waiting for human approval
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-ghost" onClick={load}>Refresh</button>
                </div>
            </div>

            {loading ? (
                <div className="card shimmer" style={{ height: 300, borderRadius: 12 }} />
            ) : error ? (
                <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>
            ) : approvals.length === 0 ? (
                <div className="card" style={{ padding: 48, textAlign: 'center' }}>
                    <div style={{ fontSize: 48, marginBottom: 12 }}>✅</div>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>All Clear</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No pending approvals</div>
                </div>
            ) : (
                <div className="table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Trace ID</th>
                                <th>Department</th>
                                <th>Risk</th>
                                <th>Waiting</th>
                                <th>Current Step</th>
                                <th>Summary</th>
                            </tr>
                        </thead>
                        <tbody>
                            {approvals.map((a) => (
                                <tr key={a.trace_id}>
                                    <td>
                                        <a
                                            href={`/traces/${a.trace_id}`}
                                            style={{ color: 'var(--accent)', textDecoration: 'none', fontFamily: 'monospace', fontSize: 12 }}
                                        >
                                            {a.trace_id.substring(0, 8)}…
                                        </a>
                                    </td>
                                    <td style={{ textTransform: 'capitalize' }}>{a.department}</td>
                                    <td>
                                        <span className={`badge badge-${a.risk_level === 'high' || a.risk_level === 'critical' ? 'danger' : a.risk_level === 'medium' ? 'warning' : 'success'}`}>
                                            {a.risk_level || '—'}
                                        </span>
                                    </td>
                                    <td>
                                        <span style={{
                                            color: a.waiting_seconds > 3600 ? 'var(--danger)' : a.waiting_seconds > 600 ? 'var(--warning)' : 'var(--text-secondary)',
                                            fontWeight: a.waiting_seconds > 600 ? 600 : 400,
                                            fontSize: 13,
                                        }}>
                                            {formatWait(a.waiting_seconds)}
                                        </span>
                                    </td>
                                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{a.current_step || '—'}</td>
                                    <td style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {a.summary || '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
