'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, AgentRow } from '@/lib/api';

export default function AgentsPage() {
    const [agents, setAgents] = useState<AgentRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [deptFilter, setDeptFilter] = useState('');

    const load = useCallback(() => {
        setLoading(true);
        api
            .getAgents(deptFilter || undefined)
            .then((d) => setAgents(d.agents))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [deptFilter]);

    useEffect(() => { load(); }, [load]);

    // Group by department
    const grouped = agents.reduce<Record<string, AgentRow[]>>((acc, a) => {
        (acc[a.department] = acc[a.department] || []).push(a);
        return acc;
    }, {});

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Agent Configuration</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Edit system prompts, view version history, and rollback changes
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <select
                        className="input-field"
                        style={{ width: 140 }}
                        value={deptFilter}
                        onChange={(e) => { setDeptFilter(e.target.value); }}
                    >
                        <option value="">All Depts</option>
                        <option value="tech">Tech</option>
                        <option value="finance">Finance</option>
                        <option value="hr">HR</option>
                        <option value="sales">Sales</option>
                    </select>
                    <button className="btn btn-ghost" onClick={load}>Refresh</button>
                </div>
            </div>

            {loading ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                    {[...Array(6)].map((_, i) => (
                        <div key={i} className="card shimmer" style={{ height: 140, borderRadius: 12 }} />
                    ))}
                </div>
            ) : error ? (
                <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>
            ) : (
                Object.entries(grouped).map(([dept, deptAgents]) => (
                    <div key={dept} style={{ marginBottom: 28 }}>
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                            fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em',
                            color: 'var(--text-muted)',
                        }}>
                            <div style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--accent)' }} />
                            {dept} Department
                            <span style={{ fontWeight: 400 }}>({deptAgents.length} agents)</span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
                            {deptAgents.map((agent) => (
                                <Link
                                    key={agent.id}
                                    href={`/agents/${agent.id}`}
                                    style={{ textDecoration: 'none', color: 'inherit' }}
                                >
                                    <div className="card" style={{ padding: 16, cursor: 'pointer' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 600, fontSize: 14 }}>{agent.name}</div>
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                                                    {agent.description || `${agent.tier} tier agent`}
                                                </div>
                                            </div>
                                            <span className={`badge ${agent.status === 'idle' ? 'badge-success' : agent.status === 'busy' ? 'badge-warning' : 'badge-neutral'}`}>
                                                {agent.status}
                                            </span>
                                        </div>
                                        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                                            <span className={`badge ${agent.has_prompt_override ? 'badge-accent' : 'badge-neutral'}`}>
                                                {agent.has_prompt_override ? '✏ Custom Prompt' : 'Default Prompt'}
                                            </span>
                                            {agent.prompt_version > 0 && (
                                                <span className="badge badge-neutral">v{agent.prompt_version}</span>
                                            )}
                                            <span className="badge badge-neutral">{agent.tier}</span>
                                        </div>
                                        {agent.prompt_updated_at && (
                                            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                                                Last edited by {agent.prompt_updated_by} ·{' '}
                                                {new Date(agent.prompt_updated_at).toLocaleDateString()}
                                            </div>
                                        )}
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}
