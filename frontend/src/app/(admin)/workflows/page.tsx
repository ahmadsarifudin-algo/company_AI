'use client';

import { useState } from 'react';
import { api, WorkflowInvoiceResult } from '@/lib/api';

export default function WorkflowsPage() {
    const [result, setResult] = useState<WorkflowInvoiceResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [form, setForm] = useState({
        vendor: '',
        amount: '',
        description: '',
        department: 'tech',
        requester: '',
    });

    // Approval action state
    const [approvalAction, setApprovalAction] = useState<'approve' | 'reject' | null>(null);
    const [approvalId, setApprovalId] = useState('');
    const [rejectReason, setRejectReason] = useState('');
    const [actionResult, setActionResult] = useState<{ approval_id: string; status: string } | null>(null);

    const handleSubmit = async () => {
        if (!form.vendor.trim() || !form.amount || !form.description.trim() || !form.requester.trim()) return;
        setLoading(true);
        setError('');
        setResult(null);
        try {
            const res = await api.createInvoice({
                vendor: form.vendor,
                amount: parseFloat(form.amount),
                description: form.description,
                department: form.department,
                requester: form.requester,
            });
            setResult(res);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Workflow failed');
        } finally {
            setLoading(false);
        }
    };

    const handleApprovalAction = async () => {
        if (!approvalId.trim()) return;
        try {
            let res;
            if (approvalAction === 'approve') {
                res = await api.approveInvoice(approvalId);
            } else {
                res = await api.rejectInvoice(approvalId, 'admin', rejectReason);
            }
            setActionResult(res);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Action failed');
        }
    };

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Workflows</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Execute and manage automated business workflows
                    </p>
                </div>
            </div>

            {error && <div className="card" style={{ padding: 12, marginBottom: 12, color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

            {/* Invoice Workflow */}
            <div className="card" style={{ padding: 24, marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <span style={{ fontSize: 22 }}>📋</span>
                    <div>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Finance Invoice Workflow</h2>
                        <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            Input → Draft → Review → Approval → Finalize
                        </p>
                    </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <input className="input-field" style={{ flex: 1, minWidth: 200 }} placeholder="Vendor name" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
                        <input className="input-field" style={{ maxWidth: 160 }} type="number" placeholder="Amount (USD)" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                    </div>
                    <input className="input-field" placeholder="Description of goods/services" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <select className="input-field" style={{ maxWidth: 160 }} value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })}>
                            <option value="tech">Tech</option>
                            <option value="finance">Finance</option>
                            <option value="hr">HR</option>
                            <option value="sales">Sales</option>
                        </select>
                        <input className="input-field" style={{ flex: 1, minWidth: 200 }} placeholder="Requester user ID" value={form.requester} onChange={(e) => setForm({ ...form, requester: e.target.value })} />
                    </div>
                    <button className="btn btn-primary" style={{ alignSelf: 'flex-end' }} onClick={handleSubmit} disabled={loading}>
                        {loading ? 'Processing…' : 'Execute Workflow'}
                    </button>
                </div>
            </div>

            {/* Result */}
            {result && (
                <div className="card" style={{ padding: 20, marginBottom: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Workflow Result</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                        <div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Trace ID</div>
                            <div style={{ fontSize: 12, fontFamily: 'monospace' }}>{result.trace_id.slice(0, 12)}…</div>
                        </div>
                        <div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Status</div>
                            <span className={`badge ${result.status === 'completed' ? 'badge-success' : result.status === 'failed' ? 'badge-danger' : 'badge-warning'}`}>
                                {result.status}
                            </span>
                        </div>
                        {result.invoice_id && (
                            <div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Invoice ID</div>
                                <div style={{ fontSize: 12, fontFamily: 'monospace' }}>{result.invoice_id}</div>
                            </div>
                        )}
                        {result.approval_id && (
                            <div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Approval ID</div>
                                <div style={{ fontSize: 12, fontFamily: 'monospace' }}>{result.approval_id}</div>
                            </div>
                        )}
                        {result.approval_status && (
                            <div>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Approval Status</div>
                                <span className="badge badge-neutral">{result.approval_status}</span>
                            </div>
                        )}
                        {result.error && (
                            <div style={{ gridColumn: '1/-1' }}>
                                <div style={{ fontSize: 11, color: 'var(--danger)', marginBottom: 2 }}>Error</div>
                                <div style={{ fontSize: 12 }}>{result.error}</div>
                            </div>
                        )}
                    </div>
                    {result.audit_trail.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Audit Trail</div>
                            <div style={{ fontSize: 12, fontFamily: 'monospace', background: 'var(--bg-secondary)', padding: 12, borderRadius: 8, lineHeight: 1.8 }}>
                                {result.audit_trail.map((step, i) => (
                                    <div key={i} style={{ color: 'var(--text-secondary)' }}>
                                        <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>{i + 1}.</span> {step}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Approval / Reject Actions */}
            <div className="card" style={{ padding: 24 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Approval Actions</h3>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16 }}>
                    Approve or reject a pending invoice by its approval ID.
                </p>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <div style={{ flex: 1, minWidth: 200 }}>
                        <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Approval ID</label>
                        <input className="input-field" placeholder="Enter approval ID" value={approvalId} onChange={(e) => setApprovalId(e.target.value)} />
                    </div>
                    {approvalAction === 'reject' && (
                        <div style={{ flex: 1, minWidth: 200 }}>
                            <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Reason (optional)</label>
                            <input className="input-field" placeholder="Rejection reason" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                        </div>
                    )}
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-primary" onClick={() => { setApprovalAction('approve'); if (approvalAction === 'approve') handleApprovalAction(); }}>
                            ✅ Approve
                        </button>
                        <button className="btn btn-ghost" style={{ color: 'var(--danger)' }} onClick={() => { setApprovalAction('reject'); if (approvalAction === 'reject') handleApprovalAction(); }}>
                            ❌ Reject
                        </button>
                    </div>
                </div>
                {actionResult && (
                    <div style={{ marginTop: 12, padding: 10, background: 'var(--bg-secondary)', borderRadius: 8, fontSize: 12 }}>
                        Approval <strong>{actionResult.approval_id}</strong> → <span className="badge badge-neutral">{actionResult.status}</span>
                    </div>
                )}
            </div>
        </div>
    );
}
