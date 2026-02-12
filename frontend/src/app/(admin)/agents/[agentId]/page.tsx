'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, AgentPromptData } from '@/lib/api';

export default function AgentPromptEditorPage() {
    const params = useParams();
    const agentId = params.agentId as string;

    const [data, setData] = useState<AgentPromptData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [saving, setSaving] = useState(false);

    // Editor state
    const [promptText, setPromptText] = useState('');
    const [changeReason, setChangeReason] = useState('');
    const [showHistory, setShowHistory] = useState(false);
    const [successMsg, setSuccessMsg] = useState('');

    const load = useCallback(() => {
        setLoading(true);
        api
            .getAgentPrompt(agentId)
            .then((d) => {
                setData(d);
                setPromptText(d.current_prompt || d.default_prompt || '');
            })
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [agentId]);

    useEffect(() => { load(); }, [load]);

    const handleSave = async () => {
        if (!promptText.trim()) return;
        setSaving(true);
        setSuccessMsg('');
        try {
            const res = await api.updateAgentPrompt(agentId, {
                prompt_text: promptText,
                change_reason: changeReason || undefined,
            });
            setSuccessMsg(res.message);
            setChangeReason('');
            load(); // Refresh data
        } catch (e: unknown) {
            setError((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const handleRollback = async (version: number) => {
        if (!confirm(`Rollback to version ${version}?`)) return;
        setSaving(true);
        try {
            const res = await api.rollbackAgentPrompt(agentId, { target_version: version });
            setSuccessMsg(res.message);
            load();
        } catch (e: unknown) {
            setError((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    const handleResetDefault = async () => {
        if (!confirm('Reset to default hardcoded prompt? This will clear the DB override.')) return;
        setSaving(true);
        try {
            const res = await api.rollbackAgentPrompt(agentId, { target_version: 0 });
            setSuccessMsg(res.message);
            load();
        } catch (e: unknown) {
            setError((e as Error).message);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="card shimmer" style={{ height: 400, borderRadius: 12 }} />;
    if (error && !data) return <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>{error}</div>;
    if (!data) return null;

    const isModified = promptText !== (data.current_prompt || data.default_prompt || '');

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div style={{ marginBottom: 20 }}>
                <a href="/agents" style={{ fontSize: 12, color: 'var(--text-secondary)', textDecoration: 'none' }}>
                    ← Back to Agents
                </a>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
                    <div>
                        <h1 style={{ fontSize: 24, fontWeight: 700 }}>{data.agent_name}</h1>
                        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                            {data.department} department · Version {data.prompt_version}
                            {data.has_override && (
                                <span className="badge badge-accent" style={{ marginLeft: 8 }}>Custom Override</span>
                            )}
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button
                            className="btn btn-ghost"
                            onClick={() => setShowHistory(!showHistory)}
                        >
                            {showHistory ? 'Hide History' : 'Version History'}
                        </button>
                        {data.has_override && (
                            <button className="btn btn-danger" onClick={handleResetDefault} disabled={saving}>
                                Reset to Default
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Success / Error */}
            {successMsg && (
                <div
                    style={{
                        padding: '10px 16px',
                        marginBottom: 16,
                        borderRadius: 8,
                        background: 'var(--success-soft)',
                        color: 'var(--success)',
                        fontSize: 13,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                    }}
                >
                    ✓ {successMsg}
                    <button
                        onClick={() => setSuccessMsg('')}
                        style={{ background: 'none', border: 'none', color: 'var(--success)', cursor: 'pointer', fontSize: 16 }}
                    >
                        ×
                    </button>
                </div>
            )}
            {error && (
                <div
                    style={{
                        padding: '10px 16px',
                        marginBottom: 16,
                        borderRadius: 8,
                        background: 'var(--danger-soft)',
                        color: 'var(--danger)',
                        fontSize: 13,
                    }}
                >
                    ⚠ {error}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: showHistory ? '1fr 360px' : '1fr', gap: 16 }}>
                {/* Prompt Editor */}
                <div className="card" style={{ padding: 20 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600 }}>System Prompt</h3>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            {promptText.length} characters
                        </div>
                    </div>
                    <textarea
                        value={promptText}
                        onChange={(e) => setPromptText(e.target.value)}
                        style={{
                            width: '100%',
                            minHeight: 350,
                            padding: 16,
                            borderRadius: 8,
                            background: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-primary)',
                            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                            fontSize: 13,
                            lineHeight: 1.6,
                            resize: 'vertical',
                            outline: 'none',
                            transition: 'border-color 0.2s',
                        }}
                        onFocus={(e) => (e.target.style.borderColor = 'var(--accent)')}
                        onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
                    />

                    {/* Change reason + save */}
                    <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'flex-end' }}>
                        <div style={{ flex: 1 }}>
                            <label style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
                                Change reason (optional)
                            </label>
                            <input
                                className="input-field"
                                value={changeReason}
                                onChange={(e) => setChangeReason(e.target.value)}
                                placeholder="e.g. 'Added compliance guardrails'"
                            />
                        </div>
                        <button
                            className="btn btn-primary"
                            onClick={handleSave}
                            disabled={saving || !isModified}
                            style={{ opacity: saving || !isModified ? 0.5 : 1, minWidth: 100 }}
                        >
                            {saving ? 'Saving…' : 'Save Prompt'}
                        </button>
                    </div>

                    {isModified && (
                        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--warning)' }}>
                            ⚠ Unsaved changes
                        </div>
                    )}
                </div>

                {/* Version History Panel */}
                {showHistory && (
                    <div className="card" style={{ padding: 16, maxHeight: 540, overflowY: 'auto' }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Version History</h3>
                        {data.history.length === 0 ? (
                            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 20 }}>
                                No history yet
                            </div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {data.history.map((h) => (
                                    <div
                                        key={h.version}
                                        style={{
                                            padding: 12,
                                            borderRadius: 8,
                                            background: 'var(--bg-surface)',
                                            border: '1px solid var(--border)',
                                        }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600, fontSize: 13 }}>v{h.version}</span>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ padding: '2px 8px', fontSize: 11 }}
                                                onClick={() => handleRollback(h.version)}
                                                disabled={saving}
                                            >
                                                Rollback
                                            </button>
                                        </div>
                                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                                            by {h.changed_by} · {h.changed_at ? new Date(h.changed_at).toLocaleDateString() : ''}
                                        </div>
                                        {h.change_reason && (
                                            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4, fontStyle: 'italic' }}>
                                                &quot;{h.change_reason}&quot;
                                            </div>
                                        )}
                                        <div
                                            style={{
                                                marginTop: 8,
                                                padding: 8,
                                                borderRadius: 6,
                                                background: 'var(--bg-card)',
                                                fontSize: 11,
                                                fontFamily: 'monospace',
                                                color: 'var(--text-secondary)',
                                                maxHeight: 80,
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'pre-wrap',
                                            }}
                                        >
                                            {h.prompt_text.substring(0, 200)}
                                            {h.prompt_text.length > 200 && '…'}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
