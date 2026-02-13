'use client';

import { useEffect, useRef, useState } from 'react';
import { api, ChatAgentResponse } from '@/lib/api';

interface AgentOption {
    id: string;
    name: string;
    department: string;
}

interface ChatMessage {
    role: 'user' | 'agent';
    content: string;
    agentName?: string;
    timestamp: Date;
}

export default function ChatPage() {
    const [agents, setAgents] = useState<AgentOption[]>([]);
    const [selectedAgent, setSelectedAgent] = useState('');
    const [threadId, setThreadId] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [sending, setSending] = useState(false);
    const [error, setError] = useState('');
    const messagesEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        api.getAgents().then((resp) => {
            const data = (resp as unknown as { agents: Record<string, string>[]; count: number }).agents || resp;
            const opts: AgentOption[] = (Array.isArray(data) ? data : []).map((a: Record<string, string>) => ({
                id: a.id,
                name: a.name,
                department: a.department,
            }));
            setAgents(opts);
            if (opts.length > 0 && !selectedAgent) setSelectedAgent(opts[0].id);
        }).catch(() => setError('Failed to load agents'));
    }, []);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = async () => {
        if (!input.trim() || !selectedAgent || sending) return;
        const userMsg = input.trim();
        setInput('');
        setError('');

        setMessages(prev => [...prev, {
            role: 'user',
            content: userMsg,
            timestamp: new Date(),
        }]);

        setSending(true);
        try {
            const resp: ChatAgentResponse = await api.chatWithAgent(
                selectedAgent,
                userMsg,
                threadId || undefined,
            );
            setThreadId(resp.thread_id);
            setMessages(prev => [...prev, {
                role: 'agent',
                content: resp.response,
                agentName: resp.agent_name,
                timestamp: new Date(),
            }]);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to send message');
        } finally {
            setSending(false);
        }
    };

    const handleNewChat = () => {
        setThreadId(null);
        setMessages([]);
        setError('');
    };

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 64px)',
            maxWidth: 900,
            margin: '0 auto',
            padding: '0 16px',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '16px 0',
                borderBottom: '1px solid var(--border)',
            }}>
                <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, flex: 1 }}>
                    💬 Chat with Agent
                </h1>
                <select
                    value={selectedAgent}
                    onChange={(e) => { setSelectedAgent(e.target.value); handleNewChat(); }}
                    style={{
                        padding: '6px 12px',
                        borderRadius: 8,
                        border: '1px solid var(--border)',
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                        fontSize: 13,
                        minWidth: 200,
                    }}
                >
                    <option value="">Select agent...</option>
                    {agents.map(a => (
                        <option key={a.id} value={a.id}>
                            {a.name} ({a.department})
                        </option>
                    ))}
                </select>
                <button
                    className="btn btn-ghost"
                    style={{ fontSize: 12, padding: '6px 12px' }}
                    onClick={handleNewChat}
                >
                    🔄 New Chat
                </button>
            </div>

            {/* Messages area */}
            <div style={{
                flex: 1,
                overflowY: 'auto',
                padding: '16px 0',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
            }}>
                {messages.length === 0 && (
                    <div style={{
                        textAlign: 'center',
                        color: 'var(--text-muted)',
                        marginTop: 80,
                        fontSize: 14,
                    }}>
                        <div style={{ fontSize: 48, marginBottom: 12 }}>🤖</div>
                        <div>Select an agent and start chatting!</div>
                        <div style={{ fontSize: 12, marginTop: 4 }}>
                            Your conversation will be maintained within this session.
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
                        <div style={{
                            maxWidth: '75%',
                            padding: '10px 14px',
                            borderRadius: msg.role === 'user'
                                ? '16px 16px 4px 16px'
                                : '16px 16px 16px 4px',
                            background: msg.role === 'user'
                                ? 'var(--accent)'
                                : 'var(--bg-secondary)',
                            color: msg.role === 'user'
                                ? '#fff'
                                : 'var(--text-primary)',
                            border: msg.role === 'agent'
                                ? '1px solid var(--border)'
                                : 'none',
                        }}>
                            {msg.role === 'agent' && msg.agentName && (
                                <div style={{
                                    fontSize: 10,
                                    fontWeight: 600,
                                    color: 'var(--accent)',
                                    marginBottom: 4,
                                }}>
                                    🤖 {msg.agentName}
                                </div>
                            )}
                            <div style={{
                                fontSize: 13,
                                lineHeight: 1.6,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                            }}>
                                {msg.content}
                            </div>
                            <div style={{
                                fontSize: 9,
                                opacity: 0.6,
                                marginTop: 4,
                                textAlign: msg.role === 'user' ? 'right' : 'left',
                            }}>
                                {msg.timestamp.toLocaleTimeString()}
                            </div>
                        </div>
                    </div>
                ))}

                {sending && (
                    <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                        <div style={{
                            padding: '10px 14px',
                            borderRadius: '16px 16px 16px 4px',
                            background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)',
                            fontSize: 13,
                            color: 'var(--text-muted)',
                        }}>
                            ⏳ Thinking...
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Error */}
            {error && (
                <div style={{
                    padding: '8px 12px',
                    background: 'rgba(239,68,68,0.1)',
                    color: 'var(--danger)',
                    borderRadius: 8,
                    fontSize: 12,
                    marginBottom: 8,
                }}>
                    {error}
                </div>
            )}

            {/* Input */}
            <div style={{
                display: 'flex',
                gap: 8,
                padding: '12px 0',
                borderTop: '1px solid var(--border)',
            }}>
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                    placeholder={selectedAgent ? 'Type your message...' : 'Select an agent first'}
                    disabled={!selectedAgent || sending}
                    style={{
                        flex: 1,
                        padding: '10px 14px',
                        borderRadius: 12,
                        border: '1px solid var(--border)',
                        background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)',
                        fontSize: 13,
                        outline: 'none',
                    }}
                />
                <button
                    className="btn btn-primary"
                    style={{
                        padding: '10px 20px',
                        borderRadius: 12,
                        fontSize: 14,
                        fontWeight: 600,
                        cursor: (!selectedAgent || !input.trim() || sending) ? 'not-allowed' : 'pointer',
                        opacity: (!selectedAgent || !input.trim() || sending) ? 0.5 : 1,
                    }}
                    onClick={handleSend}
                    disabled={!selectedAgent || !input.trim() || sending}
                >
                    Send ↗
                </button>
            </div>
        </div>
    );
}
