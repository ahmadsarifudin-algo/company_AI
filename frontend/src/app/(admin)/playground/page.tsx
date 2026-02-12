'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, AgentRow } from '@/lib/api';

interface ChatMessage {
    role: 'user' | 'agent' | 'system';
    text: string;
    timestamp: Date;
    agentName?: string;
    status?: string;
}

export default function PlaygroundPage() {
    const [agents, setAgents] = useState<AgentRow[]>([]);
    const [selectedAgent, setSelectedAgent] = useState<string>('');
    const [message, setMessage] = useState('');
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [sending, setSending] = useState(false);
    const [threadId, setThreadId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const chatEndRef = useRef<HTMLDivElement>(null);

    const loadAgents = useCallback(() => {
        api.getAgents()
            .then((d) => {
                setAgents(d.agents);
                if (d.agents.length > 0 && !selectedAgent) {
                    setSelectedAgent(d.agents[0].id);
                }
            })
            .finally(() => setLoading(false));
    }, [selectedAgent]);

    useEffect(() => { loadAgents(); }, [loadAgents]);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = async () => {
        if (!message.trim() || !selectedAgent || sending) return;

        const userMsg: ChatMessage = {
            role: 'user',
            text: message,
            timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setMessage('');
        setSending(true);

        try {
            const res = await api.testAgent(selectedAgent, {
                message: userMsg.text,
                thread_id: threadId || undefined,
            });
            if (res.thread_id) setThreadId(res.thread_id);
            setMessages((prev) => [
                ...prev,
                {
                    role: res.status === 'error' ? 'system' : 'agent',
                    text: res.response,
                    timestamp: new Date(),
                    agentName: res.agent_name,
                    status: res.status,
                },
            ]);
        } catch (e: unknown) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'system',
                    text: `Error: ${(e as Error).message}`,
                    timestamp: new Date(),
                    status: 'error',
                },
            ]);
        } finally {
            setSending(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const clearChat = () => {
        setMessages([]);
        setThreadId(null);
    };

    const agentInfo = agents.find((a) => a.id === selectedAgent);

    if (loading) return <div className="card shimmer" style={{ height: 500, borderRadius: 12 }} />;

    return (
        <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 48px)' }}>
            {/* Header */}
            <div style={{ marginBottom: 16 }}>
                <h1 style={{ fontSize: 24, fontWeight: 700 }}>Agent Playground</h1>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                    Test agents by sending prompts and viewing responses in real-time
                </p>
            </div>

            {/* Agent Selector + Controls */}
            <div className="card" style={{ padding: 16, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                    <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                        Select Agent
                    </label>
                    <select
                        value={selectedAgent}
                        onChange={(e) => {
                            setSelectedAgent(e.target.value);
                            clearChat();
                        }}
                        style={{
                            width: '100%',
                            padding: '8px 12px',
                            borderRadius: 8,
                            background: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-primary)',
                            fontSize: 13,
                            outline: 'none',
                            cursor: 'pointer',
                        }}
                    >
                        {agents.map((a) => (
                            <option key={a.id} value={a.id}>
                                {a.name} — {a.department} ({a.tier})
                            </option>
                        ))}
                    </select>
                </div>

                {agentInfo && (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Department</div>
                            <span className="badge badge-accent">{agentInfo.department}</span>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Tier</div>
                            <span className="badge">{agentInfo.tier}</span>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Status</div>
                            <span className={`badge ${agentInfo.status === 'active' ? 'badge-success' : ''}`}>
                                {agentInfo.status}
                            </span>
                        </div>
                        {agentInfo.has_prompt_override && (
                            <span className="badge badge-warning" style={{ alignSelf: 'flex-end' }}>
                                Custom Prompt
                            </span>
                        )}
                    </div>
                )}

                <button className="btn btn-ghost" onClick={clearChat} style={{ marginLeft: 'auto' }}>
                    Clear Chat
                </button>
            </div>

            {/* Chat Area */}
            <div
                className="card"
                style={{
                    flex: 1,
                    padding: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    overflow: 'hidden',
                    minHeight: 300,
                }}
            >
                {/* Messages */}
                <div
                    style={{
                        flex: 1,
                        overflowY: 'auto',
                        padding: 20,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 12,
                    }}
                >
                    {messages.length === 0 && (
                        <div
                            style={{
                                flex: 1,
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: 'var(--text-muted)',
                                gap: 8,
                            }}
                        >
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3 }}>
                                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                            </svg>
                            <div style={{ fontSize: 14, fontWeight: 500 }}>Start a conversation</div>
                            <div style={{ fontSize: 12 }}>
                                Select an agent and type a message below
                            </div>
                        </div>
                    )}

                    {messages.map((msg, i) => (
                        <div
                            key={i}
                            style={{
                                display: 'flex',
                                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                            }}
                        >
                            <div
                                style={{
                                    maxWidth: '75%',
                                    padding: '10px 14px',
                                    borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                                    background:
                                        msg.role === 'user'
                                            ? 'var(--accent)'
                                            : msg.role === 'system'
                                                ? 'var(--danger-soft)'
                                                : 'var(--bg-surface)',
                                    color:
                                        msg.role === 'user'
                                            ? 'white'
                                            : msg.role === 'system'
                                                ? 'var(--danger)'
                                                : 'var(--text-primary)',
                                    border: msg.role === 'agent' ? '1px solid var(--border)' : 'none',
                                }}
                            >
                                {msg.role === 'agent' && msg.agentName && (
                                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', marginBottom: 4 }}>
                                        {msg.agentName}
                                    </div>
                                )}
                                <div style={{
                                    fontSize: 13,
                                    lineHeight: 1.6,
                                    whiteSpace: 'pre-wrap',
                                    fontFamily: msg.role === 'agent' ? "'JetBrains Mono', 'Fira Code', monospace" : 'inherit',
                                }}>
                                    {msg.text}
                                </div>
                                <div style={{ fontSize: 10, color: msg.role === 'user' ? 'rgba(255,255,255,0.7)' : 'var(--text-muted)', marginTop: 4, textAlign: 'right' }}>
                                    {msg.timestamp.toLocaleTimeString()}
                                    {msg.status && msg.status !== 'ok' && (
                                        <span style={{ marginLeft: 6, color: 'var(--warning)' }}>• {msg.status}</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}

                    {sending && (
                        <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                            <div style={{
                                padding: '10px 14px',
                                borderRadius: '12px 12px 12px 4px',
                                background: 'var(--bg-surface)',
                                border: '1px solid var(--border)',
                                display: 'flex',
                                gap: 4,
                                alignItems: 'center',
                            }}>
                                <div className="pulse-dot" style={{ background: 'var(--accent)' }} />
                                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Agent is thinking…</span>
                            </div>
                        </div>
                    )}

                    <div ref={chatEndRef} />
                </div>

                {/* Input */}
                <div
                    style={{
                        padding: '12px 16px',
                        borderTop: '1px solid var(--border)',
                        display: 'flex',
                        gap: 8,
                        alignItems: 'flex-end',
                    }}
                >
                    <textarea
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Type a message to test the agent…"
                        rows={1}
                        style={{
                            flex: 1,
                            padding: '10px 14px',
                            borderRadius: 10,
                            background: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-primary)',
                            fontSize: 13,
                            lineHeight: 1.5,
                            resize: 'none',
                            outline: 'none',
                            transition: 'border-color 0.2s',
                            minHeight: 42,
                            maxHeight: 120,
                        }}
                        onFocus={(e) => (e.target.style.borderColor = 'var(--accent)')}
                        onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
                        onInput={(e) => {
                            const t = e.target as HTMLTextAreaElement;
                            t.style.height = 'auto';
                            t.style.height = Math.min(t.scrollHeight, 120) + 'px';
                        }}
                    />
                    <button
                        className="btn btn-primary"
                        onClick={handleSend}
                        disabled={sending || !message.trim() || !selectedAgent}
                        style={{
                            padding: '10px 20px',
                            opacity: sending || !message.trim() ? 0.5 : 1,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                        }}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="22" y1="2" x2="11" y2="13" />
                            <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                        Send
                    </button>
                </div>

                {/* Thread info */}
                {threadId && (
                    <div style={{ padding: '4px 16px 8px', fontSize: 10, color: 'var(--text-muted)' }}>
                        Thread: {threadId.substring(0, 12)}…
                    </div>
                )}
            </div>
        </div>
    );
}
