'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, ApprovalRow } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const ROLE_LEVEL: Record<string, number> = { admin: 4, manager: 3, lead: 2, contributor: 1 };

function formatWait(seconds: number) {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

export default function ApprovalsPage() {
    const { user } = useAuth();
    const [approvals, setApprovals] = useState<ApprovalRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [deciding, setDeciding] = useState<string | null>(null); // trace_id being decided
    const [rejectId, setRejectId] = useState<string | null>(null); // trace_id for reject modal
    const [rejectReason, setRejectReason] = useState('');

    const canDecide = (ROLE_LEVEL[user?.role || ''] || 0) >= 2; // lead+

    const load = useCallback(() => {
        setLoading(true);
        api
            .getApprovals()
            .then((d) => setApprovals(d.approvals))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleDecide = async (traceId: string, decision: 'approved' | 'rejected', reason?: string) => {
        setDeciding(traceId);
        try {
            await api.decideApproval(traceId, { decision, reason });
            setApprovals((prev) => prev.filter((a) => a.trace_id !== traceId));
            setRejectId(null);
            setRejectReason('');
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to process decision');
        } finally {
            setDeciding(null);
        }
    };

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
                                {canDecide && <th style={{ textAlign: 'center' }}>Actions</th>}
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
                                    {canDecide && (
                                        <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }}>
                                            <button
                                                className="btn"
                                                disabled={deciding === a.trace_id}
                                                onClick={() => handleDecide(a.trace_id, 'approved')}
                                                style={{
                                                    background: 'var(--success)',
                                                    color: '#fff',
                                                    border: 'none',
                                                    padding: '6px 14px',
                                                    borderRadius: 6,
                                                    fontSize: 12,
                                                    fontWeight: 600,
                                                    cursor: 'pointer',
                                                    marginRight: 6,
                                                    opacity: deciding === a.trace_id ? 0.5 : 1,
                                                }}
                                            >
                                                {deciding === a.trace_id ? '…' : '✓ Approve'}
                                            </button>
                                            <button
                                                className="btn"
                                                disabled={deciding === a.trace_id}
                                                onClick={() => setRejectId(a.trace_id)}
                                                style={{
                                                    background: 'var(--danger)',
                                                    color: '#fff',
                                                    border: 'none',
                                                    padding: '6px 14px',
                                                    borderRadius: 6,
                                                    fontSize: 12,
                                                    fontWeight: 600,
                                                    cursor: 'pointer',
                                                    opacity: deciding === a.trace_id ? 0.5 : 1,
                                                }}
                                            >
                                                ✕ Reject
                                            </button>
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Reject reason modal */}
            {rejectId && (
                <div style={{
                    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
                }}>
                    <div className="card" style={{ padding: 24, minWidth: 400, maxWidth: 500 }}>
                        <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Reject Trace</h3>
                        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
                            Trace: <code>{rejectId.substring(0, 12)}…</code>
                        </p>
                        <textarea
                            placeholder="Reason for rejection (optional)"
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            rows={3}
                            style={{
                                width: '100%', padding: 10, borderRadius: 8,
                                background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                border: '1px solid var(--border)', fontSize: 13,
                                fontFamily: 'inherit', resize: 'vertical', marginBottom: 12,
                            }}
                        />
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                            <button
                                className="btn btn-ghost"
                                onClick={() => { setRejectId(null); setRejectReason(''); }}
                            >
                                Cancel
                            </button>
                            <button
                                className="btn"
                                disabled={deciding === rejectId}
                                onClick={() => handleDecide(rejectId, 'rejected', rejectReason || undefined)}
                                style={{
                                    background: 'var(--danger)', color: '#fff', border: 'none',
                                    padding: '8px 20px', borderRadius: 8, fontWeight: 600, cursor: 'pointer',
                                }}
                            >
                                {deciding === rejectId ? 'Processing…' : 'Reject'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
