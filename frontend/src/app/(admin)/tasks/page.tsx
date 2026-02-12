'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, TaskRow } from '@/lib/api';

const STATUS_BADGES: Record<string, string> = {
    pending: 'badge-warning',
    running: 'badge-info',
    waiting_approval: 'badge-warning',
    completed: 'badge-success',
    failed: 'badge-danger',
};

export default function TasksPage() {
    const [tasks, setTasks] = useState<TaskRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({ department: '', task_status: '' });
    const [creating, setCreating] = useState(false);
    const [newTask, setNewTask] = useState({ department: 'tech', description: '' });

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
        if (!newTask.description.trim()) return;
        try {
            await api.createTask(newTask);
            setCreating(false);
            setNewTask({ department: 'tech', description: '' });
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

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Tasks</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Task submissions, tracking, and status management
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => setCreating(!creating)}>
                        {creating ? 'Cancel' : '+ New Task'}
                    </button>
                    <button className="btn btn-ghost" onClick={load}>Refresh</button>
                </div>
            </div>

            {/* Create Task Form */}
            {creating && (
                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Create New Task</h3>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
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
                        <input
                            className="input-field"
                            style={{ flex: 1, minWidth: 250 }}
                            placeholder="Task description..."
                            value={newTask.description}
                            onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
                            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                        />
                        <button className="btn btn-primary" onClick={handleCreate}>Submit</button>
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
                                <th>Description</th>
                                <th>Department</th>
                                <th>Status</th>
                                <th>Submitted By</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {tasks.length === 0 ? (
                                <tr>
                                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
                                        No tasks found
                                    </td>
                                </tr>
                            ) : (
                                tasks.map((t) => (
                                    <tr key={t.id}>
                                        <td style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)' }}>
                                            {t.id.slice(0, 8)}…
                                        </td>
                                        <td style={{ fontSize: 13, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {t.description || '—'}
                                        </td>
                                        <td style={{ textTransform: 'capitalize', fontSize: 12 }}>{t.department}</td>
                                        <td>
                                            <span className={`badge ${STATUS_BADGES[t.status] || 'badge-neutral'}`}>
                                                {t.status.replace(/_/g, ' ')}
                                            </span>
                                        </td>
                                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                            {t.submitted_by || '—'}
                                        </td>
                                        <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                                            {t.created_at ? new Date(t.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                                        </td>
                                        <td>
                                            {t.status !== 'completed' && t.status !== 'failed' && (
                                                <select
                                                    className="input-field"
                                                    style={{ fontSize: 11, padding: '2px 6px', maxWidth: 120 }}
                                                    value=""
                                                    onChange={(e) => {
                                                        if (e.target.value) handleStatusUpdate(t.id, e.target.value);
                                                    }}
                                                >
                                                    <option value="">Change…</option>
                                                    <option value="running">Running</option>
                                                    <option value="completed">Completed</option>
                                                    <option value="failed">Failed</option>
                                                </select>
                                            )}
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
