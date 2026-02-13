'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, UserRow } from '@/lib/api';

const ROLES = ['admin', 'manager', 'lead', 'contributor'] as const;
const DEPARTMENTS = ['finance', 'hr', 'tech', 'sales', 'marketing', 'legal', 'bizdev', 'enterprise'] as const;

const ROLE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
    admin: { bg: 'rgba(239, 68, 68, 0.12)', text: '#ef4444', border: 'rgba(239, 68, 68, 0.3)' },
    manager: { bg: 'rgba(59, 130, 246, 0.12)', text: '#3b82f6', border: 'rgba(59, 130, 246, 0.3)' },
    lead: { bg: 'rgba(234, 179, 8, 0.12)', text: '#eab308', border: 'rgba(234, 179, 8, 0.3)' },
    contributor: { bg: 'rgba(34, 197, 94, 0.12)', text: '#22c55e', border: 'rgba(34, 197, 94, 0.3)' },
};

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
    active: { bg: 'rgba(34, 197, 94, 0.1)', text: '#22c55e', dot: '#22c55e' },
    pending_invite: { bg: 'rgba(234, 179, 8, 0.1)', text: '#eab308', dot: '#eab308' },
    invite_expired: { bg: 'rgba(239, 68, 68, 0.1)', text: '#ef4444', dot: '#ef4444' },
    inactive: { bg: 'rgba(107, 114, 128, 0.1)', text: '#6b7280', dot: '#6b7280' },
};

export default function UsersPage() {
    const [users, setUsers] = useState<UserRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filterRole, setFilterRole] = useState('');
    const [filterDept, setFilterDept] = useState('');

    // Add User modal
    const [showModal, setShowModal] = useState(false);
    const [newUser, setNewUser] = useState({ email: '', name: '', department: 'finance', role: 'contributor', phone_whatsapp: '', telegram_chat_id: '' });
    const [creating, setCreating] = useState(false);

    // Invite link result
    const [inviteResult, setInviteResult] = useState<{ link: string; email: string; expires: string } | null>(null);
    const [copied, setCopied] = useState(false);

    const loadUsers = useCallback(async () => {
        try {
            setLoading(true);
            const params: { department?: string; role?: string } = {};
            if (filterRole) params.role = filterRole;
            if (filterDept) params.department = filterDept;
            const data = await api.getUsers(params);
            setUsers(data.users);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load users');
        } finally {
            setLoading(false);
        }
    }, [filterRole, filterDept]);

    useEffect(() => { loadUsers(); }, [loadUsers]);

    const handleCreate = async () => {
        try {
            setCreating(true);
            setError('');
            const result = await api.createUser(newUser);
            const origin = typeof window !== 'undefined' ? window.location.origin : '';
            setInviteResult({
                link: `${origin}${result.invite_link}`,
                email: result.user.email,
                expires: new Date(result.expires_at).toLocaleDateString(),
            });
            setNewUser({ email: '', name: '', department: 'finance', role: 'contributor', phone_whatsapp: '', telegram_chat_id: '' });
            loadUsers();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create user');
        } finally {
            setCreating(false);
        }
    };

    const handleDelete = async (userId: string, email: string) => {
        if (!confirm(`Deactivate user ${email}?`)) return;
        try {
            await api.deleteUser(userId);
            loadUsers();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to deactivate user');
        }
    };

    const copyLink = () => {
        if (inviteResult) {
            navigator.clipboard.writeText(inviteResult.link);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    // Group users by role
    const groupedUsers = ROLES.reduce((acc, role) => {
        acc[role] = users.filter(u => u.role === role);
        return acc;
    }, {} as Record<string, UserRow[]>);

    return (
        <div>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                        Users
                    </h1>
                    <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
                        Manage user accounts and role assignments
                    </p>
                </div>
                <button
                    onClick={() => { setShowModal(true); setInviteResult(null); }}
                    style={{
                        padding: '10px 20px',
                        borderRadius: 8,
                        border: 'none',
                        background: 'var(--accent)',
                        color: '#fff',
                        fontWeight: 600,
                        fontSize: 13,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                    }}
                >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Add User
                </button>
            </div>

            {/* Filters */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
                <select
                    value={filterRole}
                    onChange={e => setFilterRole(e.target.value)}
                    style={{
                        padding: '8px 12px', borderRadius: 8, fontSize: 13,
                        border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                    }}
                >
                    <option value="">All Roles</option>
                    {ROLES.map(r => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                </select>
                <select
                    value={filterDept}
                    onChange={e => setFilterDept(e.target.value)}
                    style={{
                        padding: '8px 12px', borderRadius: 8, fontSize: 13,
                        border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                    }}
                >
                    <option value="">All Departments</option>
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>)}
                </select>
                <div style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--text-muted)', alignSelf: 'center' }}>
                    {users.length} user{users.length !== 1 && 's'}
                </div>
            </div>

            {error && (
                <div style={{
                    padding: '10px 14px', borderRadius: 8, marginBottom: 16,
                    background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#ef4444', fontSize: 13,
                }}>
                    {error}
                </div>
            )}

            {loading ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Loading users...</div>
            ) : (
                /* Role-grouped sections */
                ROLES.map(role => {
                    const roleUsers = groupedUsers[role];
                    if (roleUsers.length === 0 && filterRole) return null;

                    return (
                        <div key={role} style={{ marginBottom: 24 }}>
                            {/* Role header */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                                <span
                                    style={{
                                        padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                                        textTransform: 'uppercase', letterSpacing: '0.05em',
                                        background: ROLE_COLORS[role]?.bg,
                                        color: ROLE_COLORS[role]?.text,
                                        border: `1px solid ${ROLE_COLORS[role]?.border}`,
                                    }}
                                >
                                    {role}
                                </span>
                                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                    {roleUsers.length} user{roleUsers.length !== 1 && 's'}
                                </span>
                            </div>

                            {roleUsers.length === 0 ? (
                                <div style={{
                                    padding: '16px 20px', borderRadius: 8, fontSize: 13,
                                    background: 'var(--bg-secondary)', color: 'var(--text-muted)',
                                    border: '1px solid var(--border)',
                                }}>
                                    No {role}s
                                </div>
                            ) : (
                                <div className="card" style={{ overflow: 'hidden' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                                        <thead>
                                            <tr style={{ borderBottom: '1px solid var(--border)' }}>
                                                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Name</th>
                                                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Email</th>
                                                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Department</th>
                                                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Contact</th>
                                                <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Status</th>
                                                <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase' }}>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {roleUsers.map(u => {
                                                const sc = STATUS_COLORS[u.status_label] || STATUS_COLORS.inactive;
                                                return (
                                                    <tr key={u.id} style={{ borderBottom: '1px solid var(--border)' }}>
                                                        <td style={{ padding: '12px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>
                                                            {u.name}
                                                        </td>
                                                        <td style={{ padding: '12px 16px', color: 'var(--text-secondary)' }}>
                                                            {u.email}
                                                        </td>
                                                        <td style={{ padding: '12px 16px' }}>
                                                            <span style={{
                                                                padding: '3px 8px', borderRadius: 4, fontSize: 11,
                                                                background: 'var(--bg-secondary)',
                                                                color: 'var(--text-secondary)',
                                                                border: '1px solid var(--border)',
                                                            }}>
                                                                {u.department}
                                                            </span>
                                                        </td>
                                                        <td style={{ padding: '12px 16px' }}>
                                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 11, color: 'var(--text-muted)' }}>
                                                                {u.phone_whatsapp && (
                                                                    <span title="WhatsApp">💬 {u.phone_whatsapp}</span>
                                                                )}
                                                                {u.telegram_chat_id && (
                                                                    <span title="Telegram">✈️ {u.telegram_chat_id}</span>
                                                                )}
                                                                {!u.phone_whatsapp && !u.telegram_chat_id && (
                                                                    <span style={{ color: 'var(--text-muted)', opacity: 0.5 }}>—</span>
                                                                )}
                                                            </div>
                                                        </td>
                                                        <td style={{ padding: '12px 16px' }}>
                                                            <span style={{
                                                                display: 'inline-flex', alignItems: 'center', gap: 6,
                                                                padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 500,
                                                                background: sc.bg, color: sc.text,
                                                            }}>
                                                                <span style={{
                                                                    width: 6, height: 6, borderRadius: '50%', background: sc.dot,
                                                                }} />
                                                                {u.status_label.replace('_', ' ')}
                                                            </span>
                                                        </td>
                                                        <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                                                            {u.is_active && (
                                                                <button
                                                                    onClick={() => handleDelete(u.id, u.email)}
                                                                    style={{
                                                                        padding: '4px 10px', borderRadius: 6, fontSize: 11,
                                                                        border: '1px solid rgba(239, 68, 68, 0.3)',
                                                                        background: 'transparent', color: '#ef4444',
                                                                        cursor: 'pointer',
                                                                    }}
                                                                >
                                                                    Deactivate
                                                                </button>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    );
                })
            )}

            {/* ── Add User Modal ────────────────────── */}
            {showModal && (
                <div
                    style={{
                        position: 'fixed', inset: 0, zIndex: 1000,
                        background: 'rgba(0,0,0,0.5)', display: 'flex',
                        alignItems: 'center', justifyContent: 'center',
                    }}
                    onClick={() => !inviteResult && setShowModal(false)}
                >
                    <div
                        className="card"
                        style={{ width: 440, padding: 28, maxHeight: '80vh', overflow: 'auto' }}
                        onClick={e => e.stopPropagation()}
                    >
                        {!inviteResult ? (
                            <>
                                <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 20 }}>
                                    Add New User
                                </h2>

                                {/* Name */}
                                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                    Full Name
                                </label>
                                <input
                                    type="text"
                                    value={newUser.name}
                                    onChange={e => setNewUser({ ...newUser, name: e.target.value })}
                                    placeholder="John Doe"
                                    style={{
                                        width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                        border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                        marginBottom: 16, boxSizing: 'border-box',
                                    }}
                                />

                                {/* Email */}
                                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                    Email
                                </label>
                                <input
                                    type="email"
                                    value={newUser.email}
                                    onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                                    placeholder="john@company.ai"
                                    style={{
                                        width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                        border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                        marginBottom: 16, boxSizing: 'border-box',
                                    }}
                                />

                                {/* Department + Role */}
                                <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
                                    <div style={{ flex: 1 }}>
                                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                            Department
                                        </label>
                                        <select
                                            value={newUser.department}
                                            onChange={e => setNewUser({ ...newUser, department: e.target.value })}
                                            style={{
                                                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                                border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                            }}
                                        >
                                            {DEPARTMENTS.map(d => (
                                                <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                            Role
                                        </label>
                                        <select
                                            value={newUser.role}
                                            onChange={e => setNewUser({ ...newUser, role: e.target.value })}
                                            style={{
                                                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                                border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                            }}
                                        >
                                            {ROLES.map(r => (
                                                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {/* WhatsApp + Telegram */}
                                <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
                                    <div style={{ flex: 1 }}>
                                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                            💬 WhatsApp Number
                                        </label>
                                        <input
                                            type="text"
                                            value={newUser.phone_whatsapp}
                                            onChange={e => setNewUser({ ...newUser, phone_whatsapp: e.target.value })}
                                            placeholder="+6281234567890"
                                            style={{
                                                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                                border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                                boxSizing: 'border-box',
                                            }}
                                        />
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
                                            ✈️ Telegram
                                        </label>
                                        <input
                                            type="text"
                                            value={newUser.telegram_chat_id}
                                            onChange={e => setNewUser({ ...newUser, telegram_chat_id: e.target.value })}
                                            placeholder="@username or chat ID"
                                            style={{
                                                width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
                                                border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)',
                                                boxSizing: 'border-box',
                                            }}
                                        />
                                    </div>
                                </div>

                                {/* Buttons */}
                                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                                    <button
                                        onClick={() => setShowModal(false)}
                                        style={{
                                            padding: '10px 20px', borderRadius: 8, fontSize: 13,
                                            border: '1px solid var(--border)', background: 'transparent',
                                            color: 'var(--text-secondary)', cursor: 'pointer',
                                        }}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        onClick={handleCreate}
                                        disabled={creating || !newUser.email || !newUser.name}
                                        style={{
                                            padding: '10px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                                            border: 'none', background: 'var(--accent)', color: '#fff',
                                            cursor: creating ? 'not-allowed' : 'pointer',
                                            opacity: (creating || !newUser.email || !newUser.name) ? 0.6 : 1,
                                        }}
                                    >
                                        {creating ? 'Creating...' : 'Create & Generate Link'}
                                    </button>
                                </div>
                            </>
                        ) : (
                            /* ── Invite Link Result ── */
                            <>
                                <div style={{ textAlign: 'center', marginBottom: 20 }}>
                                    <div style={{
                                        width: 48, height: 48, borderRadius: '50%', margin: '0 auto 12px',
                                        background: 'rgba(34, 197, 94, 0.1)', display: 'flex',
                                        alignItems: 'center', justifyContent: 'center',
                                    }}>
                                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                                            <path d="M9 11l3 3L22 4" />
                                            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                                        </svg>
                                    </div>
                                    <h3 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                                        User Created!
                                    </h3>
                                    <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
                                        Send this invite link to <strong>{inviteResult.email}</strong>
                                    </p>
                                </div>

                                {/* Link box */}
                                <div style={{
                                    padding: '12px 14px', borderRadius: 8, fontSize: 12, wordBreak: 'break-all',
                                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                                    color: 'var(--text-secondary)', marginBottom: 12, fontFamily: 'monospace',
                                }}>
                                    {inviteResult.link}
                                </div>

                                <button
                                    onClick={copyLink}
                                    style={{
                                        width: '100%', padding: '10px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                                        border: '1px solid var(--border)',
                                        background: copied ? 'rgba(34, 197, 94, 0.1)' : 'var(--bg-secondary)',
                                        color: copied ? '#22c55e' : 'var(--text-primary)',
                                        cursor: 'pointer', marginBottom: 8,
                                    }}
                                >
                                    {copied ? '✓ Copied!' : 'Copy Invite Link'}
                                </button>

                                <p style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginBottom: 16 }}>
                                    Expires: {inviteResult.expires}
                                </p>

                                <button
                                    onClick={() => { setShowModal(false); setInviteResult(null); }}
                                    style={{
                                        width: '100%', padding: '10px', borderRadius: 8, fontSize: 13,
                                        border: '1px solid var(--border)', background: 'transparent',
                                        color: 'var(--text-secondary)', cursor: 'pointer',
                                    }}
                                >
                                    Done
                                </button>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
