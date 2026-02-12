'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, SoulTemplate, UserSoul } from '@/lib/api';

export default function SoulsPage() {
    const [templates, setTemplates] = useState<SoulTemplate[]>([]);
    const [souls, setSouls] = useState<UserSoul[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [tab, setTab] = useState<'my' | 'templates'>('my');
    const [creating, setCreating] = useState(false);
    const [newSoul, setNewSoul] = useState({ name: '', personality: '', tone: 'friendly', language_style: 'auto' });

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [t, s] = await Promise.all([api.getSoulTemplates(), api.getMySouls()]);
            setTemplates(t);
            setSouls(s);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Load failed');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async () => {
        if (!newSoul.name.trim() || !newSoul.personality.trim()) return;
        try {
            await api.createSoul(newSoul);
            setCreating(false);
            setNewSoul({ name: '', personality: '', tone: 'friendly', language_style: 'auto' });
            load();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Create failed');
        }
    };

    const handleClone = async (tpl: SoulTemplate) => {
        try {
            await api.createSoul({ name: `${tpl.name} (Copy)`, personality: tpl.personality, tone: tpl.tone, language_style: tpl.language_style, template_id: tpl.id });
            setTab('my');
            load();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Clone failed');
        }
    };

    const handleActivate = async (id: string) => {
        try { await api.activateSoul(id); load(); } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Activate failed'); }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Delete this soul?')) return;
        try { await api.deleteSoul(id); load(); } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Delete failed'); }
    };

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>SOUL Manager</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Personality profiles for agent communication style
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-primary" onClick={() => setCreating(!creating)}>
                        {creating ? 'Cancel' : '+ New Soul'}
                    </button>
                    <button className="btn btn-ghost" onClick={load}>Refresh</button>
                </div>
            </div>

            {error && <div className="card" style={{ padding: 12, marginBottom: 12, color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

            {/* Create Form */}
            {creating && (
                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Create New Soul</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                            <input className="input-field" style={{ flex: 1, minWidth: 200 }} placeholder="Soul name" value={newSoul.name} onChange={(e) => setNewSoul({ ...newSoul, name: e.target.value })} />
                            <select className="input-field" style={{ maxWidth: 140 }} value={newSoul.tone} onChange={(e) => setNewSoul({ ...newSoul, tone: e.target.value })}>
                                <option value="friendly">Friendly</option>
                                <option value="professional">Professional</option>
                                <option value="casual">Casual</option>
                                <option value="formal">Formal</option>
                            </select>
                            <select className="input-field" style={{ maxWidth: 140 }} value={newSoul.language_style} onChange={(e) => setNewSoul({ ...newSoul, language_style: e.target.value })}>
                                <option value="auto">Auto</option>
                                <option value="id">Bahasa Indonesia</option>
                                <option value="en">English</option>
                            </select>
                        </div>
                        <textarea className="input-field" style={{ minHeight: 80 }} placeholder="Personality description (min 10 chars)..." value={newSoul.personality} onChange={(e) => setNewSoul({ ...newSoul, personality: e.target.value })} />
                        <button className="btn btn-primary" style={{ alignSelf: 'flex-end' }} onClick={handleCreate}>Create</button>
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
                <button className={`btn ${tab === 'my' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('my')}>
                    My Souls ({souls.length})
                </button>
                <button className={`btn ${tab === 'templates' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('templates')}>
                    Templates ({templates.length})
                </button>
            </div>

            {loading ? (
                <div className="card shimmer" style={{ height: 300, borderRadius: 12 }} />
            ) : tab === 'my' ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
                    {souls.length === 0 ? (
                        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1/-1' }}>
                            No souls configured. Create one or clone from a template.
                        </div>
                    ) : souls.map((s) => (
                        <div key={s.id} className="card" style={{ padding: 20, position: 'relative', borderLeft: s.is_active ? '3px solid var(--success)' : 'none' }}>
                            {s.is_active && <span className="badge badge-success" style={{ position: 'absolute', top: 12, right: 12, fontSize: 10 }}>ACTIVE</span>}
                            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>{s.name}</h3>
                            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                                <span className="badge badge-neutral" style={{ fontSize: 10 }}>{s.tone}</span>
                                <span className="badge badge-neutral" style={{ fontSize: 10 }}>{s.language_style}</span>
                            </div>
                            <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 12, maxHeight: 60, overflow: 'hidden' }}>
                                {s.personality}
                            </p>
                            <div style={{ display: 'flex', gap: 6 }}>
                                {!s.is_active && <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => handleActivate(s.id)}>Activate</button>}
                                <button className="btn btn-ghost" style={{ fontSize: 11, color: 'var(--danger)' }} onClick={() => handleDelete(s.id)}>Delete</button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16 }}>
                    {templates.length === 0 ? (
                        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', gridColumn: '1/-1' }}>
                            No templates available.
                        </div>
                    ) : templates.map((tpl) => (
                        <div key={tpl.id} className="card" style={{ padding: 20 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                {tpl.icon && <span style={{ fontSize: 20 }}>{tpl.icon}</span>}
                                <h3 style={{ fontSize: 16, fontWeight: 600 }}>{tpl.name}</h3>
                            </div>
                            <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>{tpl.description}</p>
                            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                                <span className="badge badge-neutral" style={{ fontSize: 10 }}>{tpl.tone}</span>
                                <span className="badge badge-neutral" style={{ fontSize: 10 }}>{tpl.language_style}</span>
                            </div>
                            <button className="btn btn-primary" style={{ fontSize: 12 }} onClick={() => handleClone(tpl)}>Clone to My Souls</button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
