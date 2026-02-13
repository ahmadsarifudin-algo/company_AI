'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, PolicyEvent } from '@/lib/api';
import { useAuth } from '@/lib/auth';

const ROLE_LEVEL: Record<string, number> = { admin: 4, manager: 3, lead: 2, contributor: 1 };

export default function PoliciesPage() {
    const { user } = useAuth();
    const roleLevel = ROLE_LEVEL[user?.role || ''] || 0;

    const [events, setEvents] = useState<PolicyEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({ decision: '', department: '', days: '7' });

    const load = useCallback(() => {
        setLoading(true);
        api
            .getPolicies({
                decision: filters.decision || undefined,
                department: filters.department || undefined,
                days: parseInt(filters.days) || 7,
            })
            .then((d) => setEvents(d.events))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [filters]);

    useEffect(() => { load(); }, [load]);

    // Role gate — only lead+ can view policies
    if (roleLevel < 2) {
        return (
            <div className="animate-fade-in" style={{ textAlign: 'center', paddingTop: 80 }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
                <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Access Restricted</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                    Policy monitoring requires Lead or higher access.
                </p>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Policy Monitor</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Policy violations, tool denies, and security events
                    </p>
                </div>
                <button className="btn btn-primary" onClick={load}>Refresh</button>
            </div>

            {/* Filters */}
            <div className="card" style={{ padding: 16, marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <select
                    className="input-field"
                    style={{ maxWidth: 140 }}
                    value={filters.decision}
                    onChange={(e) => setFilters({ ...filters, decision: e.target.value })}
                >
                    <option value="">All Decisions</option>
                    <option value="deny">Deny</option>
                    <option value="allow">Allow</option>
                    <option value="escalate">Escalate</option>
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
                    style={{ maxWidth: 130 }}
                    value={filters.days}
                    onChange={(e) => setFilters({ ...filters, days: e.target.value })}
                >
                    <option value="1">Last 24h</option>
                    <option value="7">Last 7d</option>
                    <option value="30">Last 30d</option>
                    <option value="90">Last 90d</option>
                </select>
                <button className="btn btn-ghost" onClick={load}>Apply</button>
            </div>

            {loading ? (
                <div className="card shimmer" style={{ height: 400, borderRadius: 12 }} />
            ) : error ? (
                <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>
            ) : (
                <div className="table-container">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Event Type</th>
                                <th>Decision</th>
                                <th>Department</th>
                                <th>Agent</th>
                                <th>Tool / Resource</th>
                                <th>Risk</th>
                                <th>Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            {events.length === 0 ? (
                                <tr>
                                    <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
                                        No policy events found
                                    </td>
                                </tr>
                            ) : (
                                events.map((ev, i) => (
                                    <tr key={i}>
                                        <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                                            {ev.created_at ? new Date(ev.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                                        </td>
                                        <td>
                                            <span className="badge badge-neutral" style={{ fontSize: 11 }}>
                                                {ev.event_type.replace(/_/g, ' ')}
                                            </span>
                                        </td>
                                        <td>
                                            {ev.decision ? (
                                                <span className={`badge badge-${ev.decision === 'allow' ? 'success' : ev.decision === 'deny' ? 'danger' : 'warning'}`}>
                                                    {ev.decision}
                                                </span>
                                            ) : (
                                                <span style={{ color: 'var(--text-muted)' }}>—</span>
                                            )}
                                        </td>
                                        <td style={{ textTransform: 'capitalize', fontSize: 12 }}>{ev.department}</td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{ev.agent_id}</td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                            {ev.tool_name || ev.resource || '—'}
                                        </td>
                                        <td>
                                            {ev.risk_level ? (
                                                <span className={`badge badge-${ev.risk_level === 'high' || ev.risk_level === 'critical' ? 'danger' : ev.risk_level === 'medium' ? 'warning' : 'success'}`}>
                                                    {ev.risk_level}
                                                </span>
                                            ) : '—'}
                                        </td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {ev.reason || '—'}
                                        </td>
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
