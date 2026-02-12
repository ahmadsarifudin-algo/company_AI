'use client';

import { useCallback, useEffect, useState } from 'react';
import { api, KnowledgeDoc } from '@/lib/api';

export default function KnowledgePage() {
    const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filters, setFilters] = useState({ department: '', doc_type: '' });
    const [tab, setTab] = useState<'docs' | 'ingest' | 'search'>('docs');

    // Ingest form
    const [ingestForm, setIngestForm] = useState({ title: '', content: '', department: 'tech', doc_type: 'manual', source: '' });
    const [ingesting, setIngesting] = useState(false);
    const [ingestResult, setIngestResult] = useState<{ doc_id: string; chunks_created: number } | null>(null);

    // Search
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<{ chunk_text: string; score: number; doc_id: string; title: string }[]>([]);
    const [searching, setSearching] = useState(false);

    const loadDocs = useCallback(() => {
        setLoading(true);
        api
            .getDocuments({
                department: filters.department || undefined,
                doc_type: filters.doc_type || undefined,
            })
            .then((d) => setDocs(d.documents))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [filters]);

    useEffect(() => { loadDocs(); }, [loadDocs]);

    const handleIngest = async () => {
        if (!ingestForm.title.trim() || !ingestForm.content.trim()) return;
        setIngesting(true);
        try {
            const res = await api.ingestDocument(ingestForm);
            setIngestResult(res);
            setIngestForm({ title: '', content: '', department: 'tech', doc_type: 'manual', source: '' });
            loadDocs();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Ingest failed');
        } finally {
            setIngesting(false);
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        setSearching(true);
        try {
            const res = await api.searchKnowledge({ query: searchQuery, top_k: 10 });
            setSearchResults(res.results);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Search failed');
        } finally {
            setSearching(false);
        }
    };

    const handleDelete = async (docId: string) => {
        if (!confirm('Delete this document and all its chunks?')) return;
        try {
            await api.deleteDocument(docId);
            loadDocs();
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Delete failed');
        }
    };

    return (
        <div className="animate-fade-in">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700 }}>Knowledge Base</h1>
                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                        Document ingestion, semantic search, and management
                    </p>
                </div>
                <button className="btn btn-ghost" onClick={loadDocs}>Refresh</button>
            </div>

            {error && <div className="card" style={{ padding: 12, marginBottom: 12, color: 'var(--danger)', fontSize: 13 }}>{error}</div>}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
                <button className={`btn ${tab === 'docs' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('docs')}>
                    📄 Documents ({docs.length})
                </button>
                <button className={`btn ${tab === 'ingest' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('ingest')}>
                    ⬆️ Ingest
                </button>
                <button className={`btn ${tab === 'search' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('search')}>
                    🔍 Search
                </button>
            </div>

            {tab === 'docs' && (
                <>
                    {/* Filters */}
                    <div className="card" style={{ padding: 16, marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        <select className="input-field" style={{ maxWidth: 140 }} value={filters.department} onChange={(e) => setFilters({ ...filters, department: e.target.value })}>
                            <option value="">All Depts</option>
                            <option value="tech">Tech</option>
                            <option value="finance">Finance</option>
                            <option value="hr">HR</option>
                            <option value="sales">Sales</option>
                        </select>
                        <select className="input-field" style={{ maxWidth: 140 }} value={filters.doc_type} onChange={(e) => setFilters({ ...filters, doc_type: e.target.value })}>
                            <option value="">All Types</option>
                            <option value="manual">Manual</option>
                            <option value="sop">SOP</option>
                            <option value="faq">FAQ</option>
                            <option value="policy">Policy</option>
                        </select>
                        <button className="btn btn-ghost" onClick={loadDocs}>Apply</button>
                    </div>

                    {loading ? (
                        <div className="card shimmer" style={{ height: 300, borderRadius: 12 }} />
                    ) : (
                        <div className="table-container">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Title</th>
                                        <th>Department</th>
                                        <th>Type</th>
                                        <th>Chunks</th>
                                        <th>Source</th>
                                        <th>Created</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {docs.length === 0 ? (
                                        <tr>
                                            <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 40 }}>
                                                No documents in knowledge base
                                            </td>
                                        </tr>
                                    ) : docs.map((d) => (
                                        <tr key={d.doc_id}>
                                            <td style={{ fontSize: 13, fontWeight: 500 }}>{d.title}</td>
                                            <td style={{ textTransform: 'capitalize', fontSize: 12 }}>{d.department || '—'}</td>
                                            <td><span className="badge badge-neutral" style={{ fontSize: 10 }}>{d.doc_type || '—'}</span></td>
                                            <td style={{ fontSize: 12, textAlign: 'center' }}>{d.chunk_count}</td>
                                            <td style={{ fontSize: 11, color: 'var(--text-muted)', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.source || '—'}</td>
                                            <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                                                {d.created_at ? new Date(d.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                                            </td>
                                            <td>
                                                <button className="btn btn-ghost" style={{ fontSize: 11, color: 'var(--danger)', padding: '2px 8px' }} onClick={() => handleDelete(d.doc_id)}>Delete</button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}

            {tab === 'ingest' && (
                <div className="card" style={{ padding: 24 }}>
                    <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Ingest Document</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <input className="input-field" placeholder="Document title" value={ingestForm.title} onChange={(e) => setIngestForm({ ...ingestForm, title: e.target.value })} />
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                            <select className="input-field" style={{ maxWidth: 140 }} value={ingestForm.department} onChange={(e) => setIngestForm({ ...ingestForm, department: e.target.value })}>
                                <option value="tech">Tech</option>
                                <option value="finance">Finance</option>
                                <option value="hr">HR</option>
                                <option value="sales">Sales</option>
                            </select>
                            <select className="input-field" style={{ maxWidth: 140 }} value={ingestForm.doc_type} onChange={(e) => setIngestForm({ ...ingestForm, doc_type: e.target.value })}>
                                <option value="manual">Manual</option>
                                <option value="sop">SOP</option>
                                <option value="faq">FAQ</option>
                                <option value="policy">Policy</option>
                            </select>
                            <input className="input-field" style={{ flex: 1, minWidth: 200 }} placeholder="Source (optional)" value={ingestForm.source} onChange={(e) => setIngestForm({ ...ingestForm, source: e.target.value })} />
                        </div>
                        <textarea className="input-field" style={{ minHeight: 200, fontFamily: 'monospace', fontSize: 13 }} placeholder="Paste document content here..." value={ingestForm.content} onChange={(e) => setIngestForm({ ...ingestForm, content: e.target.value })} />
                        <button className="btn btn-primary" style={{ alignSelf: 'flex-end' }} onClick={handleIngest} disabled={ingesting}>
                            {ingesting ? 'Ingesting…' : 'Ingest Document'}
                        </button>
                    </div>
                    {ingestResult && (
                        <div style={{ marginTop: 16, padding: 12, background: 'var(--success-bg)', borderRadius: 8, fontSize: 13 }}>
                            ✅ Document ingested: <strong>{ingestResult.doc_id.slice(0, 8)}…</strong> — {ingestResult.chunks_created} chunks created
                        </div>
                    )}
                </div>
            )}

            {tab === 'search' && (
                <div>
                    <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                        <div style={{ display: 'flex', gap: 12 }}>
                            <input
                                className="input-field"
                                style={{ flex: 1 }}
                                placeholder="Semantic search query..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                            />
                            <button className="btn btn-primary" onClick={handleSearch} disabled={searching}>
                                {searching ? 'Searching…' : 'Search'}
                            </button>
                        </div>
                    </div>
                    {searchResults.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            {searchResults.map((r, i) => (
                                <div key={i} className="card" style={{ padding: 16 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                                        <span style={{ fontSize: 13, fontWeight: 600 }}>{r.title}</span>
                                        <span className="badge badge-neutral" style={{ fontSize: 10 }}>Score: {r.score.toFixed(3)}</span>
                                    </div>
                                    <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                                        {r.chunk_text}
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
