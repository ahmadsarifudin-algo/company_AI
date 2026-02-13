'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, TaskRow } from '@/lib/api';

const STATUS_BADGES: Record<string, string> = {
    pending: 'badge-warning',
    running: 'badge-info',
    waiting_approval: 'badge-warning',
    completed: 'badge-success',
    failed: 'badge-danger',
};

export default function TasksPage() {
    const router = useRouter();
    const [tasks, setTasks] = useState<TaskRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({ department: '', task_status: '' });
    const [creating, setCreating] = useState(false);
    const [newTask, setNewTask] = useState({ title: '', department: 'tech', description: '', priority: 'P2' });
    const [executingId, setExecutingId] = useState<string | null>(null);
    const [execResult, setExecResult] = useState<{ taskId: string; message: string; isError: boolean } | null>(null);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        api
            .getTasks({
                department: filters.department || undefined,
                task_status: filters.task_status || undefined,
            })
            .then((d) => setTasks(d))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [filters]);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async () => {
        if (!newTask.title.trim()) return;
        try {
            await api.createTask(newTask);
            setCreating(false);
            setNewTask({ title: '', department: 'tech', description: '', priority: 'P2' });
            load();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to create task');
        }
    };

    const handleStatusUpdate = async (taskId: string, newStatus: string) => {
        try {
            await api.updateTaskStatus(taskId, newStatus);
            load();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to update');
        }
    };

    const handleExecute = async (taskId: string) => {
        setExecutingId(taskId);
        setExecResult(null);
        try {
            const result = await api.executeTask(taskId);
            setExecResult({
                taskId,
                message: `✅ Agent "${result.agent_name}" completed in ${Math.round(result.execution_time_ms)}ms (${result.token_usage} tokens, ${result.tool_calls} tool calls)`,
                isError: false,
            });
            load();
        } catch (e: unknown) {
            setExecResult({
                taskId,
                message: e instanceof Error ? e.message : 'Execution failed',
                isError: true,
            });
            load();
        } finally {
            setExecutingId(null);
        }
    };

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Tasks</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Task submissions, tracking, and agent execution
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => setCreating(!creating)}>
                        {creating ? 'Cancel' : '+ New Task'}
                    </button>
                    <button className="btn btn-ghost" onClick={load}>Refresh</button>
                </div>
            </div>

            {/* Execution Result Banner */}
            {execResult && (
                <div
                    className="card"
                    style={{
                        padding: '12px 16px',
                        marginBottom: 16,
                        background: execResult.isError ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                        border: `1px solid ${execResult.isError ? 'var(--danger)' : 'var(--success)'}`,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                    }}
                >
                    <span style={{ fontSize: 13, color: execResult.isError ? 'var(--danger)' : 'var(--success)' }}>
                        {execResult.message}
                    </span>
                    <button
                        className="btn btn-ghost"
                        style={{ fontSize: 11, padding: '2px 8px' }}
                        onClick={() => setExecResult(null)}
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* Create Task Form */}
            {creating && (
                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Create New Task</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                            <input
                                className="input-field"
                                style={{ flex: 1, minWidth: 250 }}
                                placeholder="Task title..."
                                value={newTask.title}
                                onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
                            />
                            <select
                                className="input-field"
                                style={{ maxWidth: 160 }}
                                value={newTask.department}
                                onChange={(e) => setNewTask({ ...newTask, department: e.target.value })}
                            >
                                <option value="tech">Tech</option>
                                <option value="finance">Finance</option>
                                <option value="hr">HR</option>
                                <option value="sales">Sales</option>
                                <option value="marketing_digital">Marketing Digital</option>
                            </select>
                            <select
                                className="input-field"
                                style={{ maxWidth: 100 }}
                                value={newTask.priority}
                                onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                            >
                                <option value="P0">P0 🔴</option>
                                <option value="P1">P1 🟠</option>
                                <option value="P2">P2 🟡</option>
                                <option value="P3">P3 🟢</option>
                            </select>
                        </div>
                        <div style={{ display: 'flex', gap: 12 }}>
                            <textarea
                                className="input-field"
                                style={{ flex: 1, minHeight: 60, resize: 'vertical', fontFamily: 'inherit' }}
                                placeholder="Task description (detailed instructions for the agent)..."
                                value={newTask.description}
                                onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
                            />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button className="btn btn-primary" onClick={handleCreate}>Submit Task</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Filters */}
            <div className="card" style={{ padding: 16, marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
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
                    style={{ maxWidth: 160 }}
                    value={filters.task_status}
                    onChange={(e) => setFilters({ ...filters, task_status: e.target.value })}
                >
                    <option value="">All Status</option>
                    <option value="pending">Pending</option>
                    <option value="running">Running</option>
                    <option value="waiting_approval">Waiting Approval</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
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
                                <th>ID</th>
                                <th>Title</th>
                                <th>Channel</th>
                                <th>Dept</th>
                                <th>Priority</th>
                                <th>Status</th>
                                <th>Result</th>
                                <th>Created</th>
                                <th style={{ textAlign: 'center' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tasks.length === 0 ? (
                                <tr>
                                    <td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
                                        No tasks found
                                    </td>
                                </tr>
                            ) : (
                                tasks.map((t) => {
                                    const rj = t.result_json as Record<string, string> | null;
                                    const resultOutput = rj?.output || rj?.error || null;
                                    const resultAgent = rj?.agent || null;
                                    const resultIsError = !!rj?.error;
                                    const isExpanded = expandedId === t.id;
                                    return (
                                        <>
                                            <tr key={t.id} style={{ cursor: resultOutput ? 'pointer' : 'default' }} onClick={() => resultOutput && setExpandedId(isExpanded ? null : t.id)}>
                                                <td style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                                                    {t.id.slice(0, 8)}…
                                                </td>
                                                <td style={{ fontSize: 13, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    <div
                                                        style={{ fontWeight: 500, color: 'var(--accent)', cursor: 'pointer' }}
                                                        onClick={(e) => { e.stopPropagation(); router.push(`/tasks/${t.id}`); }}
                                                    >
                                                        {t.title || '—'}
                                                    </div>
                                                    {t.description && (
                                                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                                                            {t.description.slice(0, 80)}{t.description.length > 80 ? '…' : ''}
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                                                    {t.channel === 'telegram' ? '📱' : t.channel === 'whatsapp' ? '💬' : '🖥️'}{' '}
                                                    <span style={{ textTransform: 'capitalize' }}>{t.channel || 'dashboard'}</span>
                                                    {t.sender_name && (
                                                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 1 }}>
                                                            {t.sender_name}
                                                        </div>
                                                    )}
                                                </td>
                                                <td style={{ textTransform: 'capitalize', fontSize: 12 }}>{t.department}</td>
                                                <td>
                                                    <span style={{
                                                        fontSize: 11,
                                                        fontWeight: 600,
                                                        color: t.priority === 'P0' ? 'var(--danger)' : t.priority === 'P1' ? '#f97316' : t.priority === 'P2' ? '#eab308' : 'var(--success)',
                                                    }}>
                                                        {t.priority}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={`badge ${STATUS_BADGES[t.status] || 'badge-neutral'}`}>
                                                        {t.status.replace(/_/g, ' ')}
                                                    </span>
                                                </td>
                                                <td style={{ fontSize: 11, maxWidth: 200 }}>
                                                    {resultOutput ? (
                                                        <button
                                                            className="btn btn-ghost"
                                                            onClick={(e) => { e.stopPropagation(); setExpandedId(isExpanded ? null : t.id); }}
                                                            style={{
                                                                fontSize: 11,
                                                                padding: '2px 8px',
                                                                color: resultIsError ? 'var(--danger)' : 'var(--accent)',
                                                                fontWeight: 500,
                                                            }}
                                                        >
                                                            {isExpanded ? '▼ Hide' : '▶ View Result'}
                                                        </button>
                                                    ) : (
                                                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                                                    )}
                                                </td>
                                                <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                                                    {t.created_at ? new Date(t.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                                                </td>
                                                <td style={{ textAlign: 'center', whiteSpace: 'nowrap' }} onClick={(e) => e.stopPropagation()}>
                                                    {(t.status === 'pending' || t.status === 'failed') && (
                                                        <button
                                                            className="btn"
                                                            disabled={executingId === t.id}
                                                            onClick={() => handleExecute(t.id)}
                                                            style={{
                                                                background: 'var(--accent)',
                                                                color: '#fff',
                                                                border: 'none',
                                                                padding: '5px 12px',
                                                                borderRadius: 6,
                                                                fontSize: 11,
                                                                fontWeight: 600,
                                                                cursor: executingId === t.id ? 'wait' : 'pointer',
                                                                opacity: executingId === t.id ? 0.6 : 1,
                                                                marginRight: 4,
                                                            }}
                                                        >
                                                            {executingId === t.id ? '⏳ Running…' : '▶ Execute'}
                                                        </button>
                                                    )}
                                                    {t.status === 'running' && (
                                                        <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>
                                                            ⏳ Processing...
                                                        </span>
                                                    )}
                                                    {t.status !== 'completed' && t.status !== 'running' && (
                                                        <select
                                                            className="input-field"
                                                            style={{ fontSize: 11, padding: '2px 6px', maxWidth: 100 }}
                                                            value=""
                                                            onChange={(e) => {
                                                                if (e.target.value) handleStatusUpdate(t.id, e.target.value);
                                                            }}
                                                        >
                                                            <option value="">Status…</option>
                                                            <option value="running">Running</option>
                                                            <option value="completed">Completed</option>
                                                            <option value="failed">Failed</option>
                                                        </select>
                                                    )}
                                                </td>
                                            </tr>
                                            {isExpanded && resultOutput && (
                                                <tr key={`${t.id}-result`}>
                                                    <td colSpan={8} style={{ padding: 0 }}>
                                                        <div style={{
                                                            padding: '16px 20px',
                                                            background: resultIsError ? 'rgba(239,68,68,0.05)' : 'rgba(59,130,246,0.05)',
                                                            borderTop: '1px solid var(--border)',
                                                            borderBottom: '2px solid var(--border)',
                                                        }}>
                                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                                                <span style={{ fontSize: 12, fontWeight: 600, color: resultIsError ? 'var(--danger)' : 'var(--accent)' }}>
                                                                    {resultIsError ? '❌ Error' : '✅ AI Response'}
                                                                    {resultAgent && ` — ${resultAgent}`}
                                                                </span>
                                                                <button
                                                                    className="btn btn-ghost"
                                                                    style={{ fontSize: 10, padding: '2px 6px' }}
                                                                    onClick={() => { navigator.clipboard.writeText(resultOutput); }}
                                                                >
                                                                    📋 Copy
                                                                </button>
                                                            </div>
                                                            <pre style={{
                                                                fontSize: 12,
                                                                lineHeight: 1.6,
                                                                whiteSpace: 'pre-wrap',
                                                                wordBreak: 'break-word',
                                                                color: 'var(--text-primary)',
                                                                margin: 0,
                                                                maxHeight: 400,
                                                                overflowY: 'auto',
                                                                fontFamily: 'inherit',
                                                            }}>
                                                                {resultOutput}
                                                            </pre>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
