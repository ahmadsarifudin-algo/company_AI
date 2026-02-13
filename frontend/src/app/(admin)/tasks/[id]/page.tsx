'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api, TaskRow, TaskExecutionResult } from '@/lib/api';

export default function TaskDetailPage() {
    const params = useParams();
    const router = useRouter();
    const taskId = params.id as string;

    const [task, setTask] = useState<TaskRow | null>(null);
    const [loading, setLoading] = useState(true);
    const [executing, setExecuting] = useState(false);
    const [execResult, setExecResult] = useState<TaskExecutionResult | null>(null);
    const [error, setError] = useState('');

    const fetchTask = async () => {
        try {
            const data = await api.getTask(taskId);
            setTask(data);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to load task');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchTask(); }, [taskId]);

    const handleExecute = async () => {
        setExecuting(true);
        setExecResult(null);
        try {
            const result = await api.executeTask(taskId);
            setExecResult(result);
            await fetchTask(); // refresh task data
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Execution failed');
        } finally {
            setExecuting(false);
        }
    };

    const statusColor = (s: string) => {
        switch (s) {
            case 'completed': return '#22c55e';
            case 'failed': return '#ef4444';
            case 'running': return '#3b82f6';
            case 'pending': return '#f59e0b';
            default: return '#888';
        }
    };

    if (loading) return (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
            Loading task...
        </div>
    );

    if (error && !task) return (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--danger)' }}>
            {error}
        </div>
    );

    if (!task) return null;

    const rj = task.result_json as Record<string, string> | null;
    const resultOutput = rj?.output || rj?.error || (rj ? JSON.stringify(rj, null, 2) : '');
    const resultAgent = rj?.agent || '';
    const hasResult = !!resultOutput;

    return (
        <div style={{ padding: '24px 32px', maxWidth: 1000, margin: '0 auto' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                <button
                    className="btn btn-ghost"
                    style={{ padding: '4px 8px', fontSize: 14 }}
                    onClick={() => router.push('/tasks')}
                >
                    ← Back
                </button>
                <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, flex: 1 }}>
                    {task.title}
                </h1>
                <span style={{
                    padding: '4px 12px',
                    borderRadius: 12,
                    fontSize: 12,
                    fontWeight: 600,
                    background: statusColor(task.status) + '22',
                    color: statusColor(task.status),
                    textTransform: 'uppercase',
                    letterSpacing: 0.5,
                }}>
                    {task.status}
                </span>
            </div>

            {/* Meta Grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 12,
                marginBottom: 24,
            }}>
                {[
                    { label: 'Department', value: task.department },
                    { label: 'Priority', value: task.priority },
                    { label: 'Agent', value: task.assigned_agent_id || '—' },
                    { label: 'Submitted By', value: task.submitted_by || '—' },
                    { label: 'Created', value: task.created_at ? new Date(task.created_at).toLocaleString() : '—' },
                    { label: 'Updated', value: task.updated_at ? new Date(task.updated_at).toLocaleString() : '—' },
                ].map((item) => (
                    <div key={item.label} style={{
                        background: 'var(--bg-secondary)',
                        borderRadius: 8,
                        padding: '10px 14px',
                        border: '1px solid var(--border)',
                    }}>
                        <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>
                            {item.label}
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                            {item.value}
                        </div>
                    </div>
                ))}
            </div>

            {/* Description */}
            {task.description && (
                <div style={{
                    background: 'var(--bg-secondary)',
                    borderRadius: 8,
                    padding: 16,
                    border: '1px solid var(--border)',
                    marginBottom: 24,
                }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 8 }}>
                        Description
                    </div>
                    <p style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--text-primary)', margin: 0, whiteSpace: 'pre-wrap' }}>
                        {task.description}
                    </p>
                </div>
            )}

            {/* Execute Button */}
            {(task.status === 'pending' || task.status === 'failed') && (
                <div style={{ marginBottom: 24 }}>
                    <button
                        className="btn btn-primary"
                        style={{
                            padding: '10px 24px',
                            fontSize: 14,
                            fontWeight: 600,
                            borderRadius: 8,
                            cursor: executing ? 'not-allowed' : 'pointer',
                            opacity: executing ? 0.6 : 1,
                        }}
                        onClick={handleExecute}
                        disabled={executing}
                    >
                        {executing ? '⏳ Executing...' : '▶ Execute Task'}
                    </button>
                </div>
            )}

            {/* Execution Result (fresh) */}
            {execResult && (
                <div style={{
                    background: execResult.status === 'failed' ? 'rgba(239,68,68,0.05)' : 'rgba(59,130,246,0.05)',
                    borderRadius: 8,
                    padding: 16,
                    border: `1px solid ${execResult.status === 'failed' ? 'var(--danger)' : 'var(--accent)'}`,
                    marginBottom: 24,
                }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', marginBottom: 8 }}>
                        Execution Result
                    </div>
                    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12, marginBottom: 12 }}>
                        <span>Status: <strong>{execResult.status}</strong></span>
                        <span>Agent: <strong>{execResult.agent_name}</strong></span>
                        <span>Tokens: <strong>{execResult.token_usage}</strong></span>
                        <span>Tools: <strong>{execResult.tool_calls}</strong></span>
                        <span>Time: <strong>{execResult.execution_time_ms?.toFixed(0)}ms</strong></span>
                    </div>
                    {execResult.errors?.length > 0 && (
                        <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 8 }}>
                            Errors: {execResult.errors.join(', ')}
                        </div>
                    )}
                </div>
            )}

            {/* Stored Result */}
            {hasResult && (
                <div style={{
                    background: rj?.error ? 'rgba(239,68,68,0.05)' : 'rgba(59,130,246,0.05)',
                    borderRadius: 8,
                    padding: 16,
                    border: `1px solid ${rj?.error ? 'var(--danger)' : 'var(--accent)'}`,
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: rj?.error ? 'var(--danger)' : 'var(--accent)' }}>
                            {rj?.error ? '❌ Error' : '✅ AI Response'}
                            {resultAgent && ` — ${resultAgent}`}
                        </span>
                        <button
                            className="btn btn-ghost"
                            style={{ fontSize: 10, padding: '2px 6px' }}
                            onClick={() => navigator.clipboard.writeText(resultOutput)}
                        >
                            📋 Copy
                        </button>
                    </div>
                    <pre style={{
                        fontSize: 13,
                        lineHeight: 1.7,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        color: 'var(--text-primary)',
                        margin: 0,
                        maxHeight: 600,
                        overflowY: 'auto',
                        fontFamily: 'inherit',
                    }}>
                        {resultOutput}
                    </pre>
                </div>
            )}
        </div>
    );
}
