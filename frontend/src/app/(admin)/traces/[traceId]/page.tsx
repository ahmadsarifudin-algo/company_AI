'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, TraceDetail } from '@/lib/api';

function EventDot({ eventType }: { eventType: string }) {
    const colors: Record<string, string> = {
        llm_call_completed: 'var(--accent)',
        tool_call_completed: 'var(--info)',
        tool_call_denied: 'var(--danger)',
        policy_evaluated: 'var(--warning)',
        approval_requested: 'var(--warning)',
        approval_granted: 'var(--success)',
        approval_denied: 'var(--danger)',
        task_started: 'var(--info)',
        task_completed: 'var(--success)',
        task_failed: 'var(--danger)',
    };
    return (
        <div
            style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: colors[eventType] || 'var(--text-muted)',
                flexShrink: 0,
                marginTop: 5,
            }}
        />
    );
}

export default function TraceDetailPage() {
    const params = useParams();
    const traceId = params.traceId as string;
    const [data, setData] = useState<TraceDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        api
            .getTraceDetail(traceId)
            .then(setData)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [traceId]);

    if (loading) return <div className="card shimmer" style={{ height: 400, borderRadius: 12 }} />;
    if (error) return <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>;
    if (!data) return null;

    const h = data.header;

    return (
        <div className="animate-fade-in">
            {/* Back + Title */}
            <div style={{ marginBottom: 20 }}>
                <a href="/traces" style={{ fontSize: 12, color: 'var(--text-secondary)', textDecoration: 'none' }}>
                    ← Back to Traces
                </a>
                <h1 style={{ fontSize: 24, fontWeight: 700, marginTop: 8 }}>
                    Trace{' '}
                    <code style={{ color: 'var(--accent)', fontSize: 18 }}>{traceId.substring(0, 12)}…</code>
                </h1>
            </div>

            {/* Header Stats */}
            {h && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Department</div>
                        <div style={{ fontSize: 16, fontWeight: 600, textTransform: 'capitalize', marginTop: 4 }}>{h.department}</div>
                    </div>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Status</div>
                        <div style={{ marginTop: 4 }}>
                            <span className={`badge badge-${h.status === 'completed' ? 'success' : h.status === 'failed' ? 'danger' : 'info'}`}>
                                {h.status}
                            </span>
                        </div>
                    </div>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Cost</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--success)', marginTop: 4 }}>
                            ${h.total_cost_usd.toFixed(4)}
                        </div>
                    </div>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Risk Level</div>
                        <div style={{ marginTop: 4 }}>
                            <span className={`badge badge-${h.risk_level === 'high' || h.risk_level === 'critical' ? 'danger' : h.risk_level === 'medium' ? 'warning' : 'success'}`}>
                                {h.risk_level || '—'}
                            </span>
                        </div>
                    </div>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Tokens In/Out</div>
                        <div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>
                            {h.total_tokens_in ?? 0} / {h.total_tokens_out ?? 0}
                        </div>
                    </div>
                    <div className="stat-card">
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Events</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--accent)', marginTop: 4 }}>{data.event_count}</div>
                    </div>
                </div>
            )}

            {/* Timeline */}
            <div className="card" style={{ padding: 20 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Event Timeline</h3>
                {data.events.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>No events</div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                        {data.events.map((ev, i) => (
                            <div key={i} style={{ display: 'flex', gap: 12, position: 'relative' }}>
                                {/* Vertical line */}
                                {i < data.events.length - 1 && (
                                    <div
                                        style={{
                                            position: 'absolute',
                                            left: 4,
                                            top: 16,
                                            bottom: -4,
                                            width: 2,
                                            background: 'var(--border)',
                                        }}
                                    />
                                )}
                                <EventDot eventType={ev.event_type} />
                                <div style={{ flex: 1, paddingBottom: 16 }}>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                                            {ev.event_type.replace(/_/g, ' ')}
                                        </span>
                                        {ev.decision && (
                                            <span className={`badge badge-${ev.decision === 'allow' ? 'success' : 'danger'}`}>
                                                {ev.decision}
                                            </span>
                                        )}
                                        {ev.agent_id && (
                                            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>by {ev.agent_id}</span>
                                        )}
                                    </div>
                                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                                        {ev.created_at ? new Date(ev.created_at).toLocaleTimeString() : ''}
                                        {ev.tool_name && ` · tool: ${ev.tool_name}`}
                                        {ev.model && ` · model: ${ev.model}`}
                                        {ev.cost_usd != null && ` · $${ev.cost_usd.toFixed(4)}`}
                                        {ev.latency_ms != null && ` · ${ev.latency_ms}ms`}
                                    </div>
                                    {ev.reason && (
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{ev.reason}</div>
                                    )}
                                    {ev.error_code && (
                                        <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 4 }}>
                                            ⚠ {ev.error_code}: {ev.error_message_short}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
