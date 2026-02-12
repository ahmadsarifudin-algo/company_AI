'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

interface Credential {
    key: string;
    service: string;
    value: string;
    is_secret: boolean;
    is_set: boolean;
}

interface ServiceGroup {
    id: string;
    label: string;
    description: string;
    icon: string;
    color: string;
    fields: { key: string; label: string; placeholder: string; is_secret: boolean }[];
}

const SERVICE_GROUPS: ServiceGroup[] = [
    {
        id: 'twilio',
        label: 'WhatsApp (Twilio)',
        description: 'Send & receive WhatsApp messages via Twilio Business API',
        icon: '💬',
        color: '#25D366',
        fields: [
            { key: 'twilio_account_sid', label: 'Account SID', placeholder: 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', is_secret: true },
            { key: 'twilio_auth_token', label: 'Auth Token', placeholder: 'Your Twilio auth token', is_secret: true },
            { key: 'twilio_whatsapp_from', label: 'WhatsApp Number', placeholder: 'whatsapp:+14155238886', is_secret: false },
        ],
    },
    {
        id: 'telegram',
        label: 'Telegram Bot',
        description: 'Send & receive Telegram messages via Bot API',
        icon: '✈️',
        color: '#0088cc',
        fields: [
            { key: 'telegram_bot_token', label: 'Bot Token', placeholder: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11', is_secret: true },
            { key: 'telegram_webhook_secret', label: 'Webhook Secret', placeholder: 'Optional secret for webhook verification', is_secret: true },
        ],
    },
    {
        id: 'smtp',
        label: 'Email (SMTP)',
        description: 'Send emails via SMTP — supports Gmail, Outlook, custom servers',
        icon: '📧',
        color: '#EA4335',
        fields: [
            { key: 'smtp_host', label: 'SMTP Host', placeholder: 'smtp.gmail.com', is_secret: false },
            { key: 'smtp_port', label: 'SMTP Port', placeholder: '587', is_secret: false },
            { key: 'smtp_user', label: 'SMTP User', placeholder: 'your-email@gmail.com', is_secret: false },
            { key: 'smtp_password', label: 'SMTP Password', placeholder: 'App password or SMTP password', is_secret: true },
            { key: 'smtp_from', label: 'From Address', placeholder: 'noreply@company.ai', is_secret: false },
        ],
    },
    {
        id: 'google',
        label: 'Google Workspace',
        description: 'Calendar, Drive, Gmail — uses Service Account',
        icon: '🔷',
        color: '#4285F4',
        fields: [
            { key: 'google_service_account_json', label: 'Service Account JSON', placeholder: '{"type":"service_account",...}', is_secret: true },
            { key: 'google_delegated_email', label: 'Delegated Email', placeholder: 'admin@company.ai', is_secret: false },
            { key: 'google_calendar_id', label: 'Calendar ID', placeholder: 'primary or calendar-id@group.calendar.google.com', is_secret: false },
            { key: 'google_drive_folder_id', label: 'Drive Folder ID', placeholder: '1ABCDefGHiJKLMnopQRSTUvwXYZ', is_secret: false },
        ],
    },
    {
        id: 'channels',
        label: 'Notification Channels',
        description: 'Configure default notification routing and allowed domains',
        icon: '🔔',
        color: '#8B5CF6',
        fields: [
            { key: 'notification_channels', label: 'Default Channels', placeholder: 'email,whatsapp', is_secret: false },
            { key: 'allowed_email_domains', label: 'Allowed Email Domains', placeholder: 'company.ai,partner.com', is_secret: false },
        ],
    },
];

function StatusDot({ configured }: { configured: boolean }) {
    return (
        <div
            style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: configured ? '#22c55e' : '#64748b',
                boxShadow: configured ? '0 0 6px rgba(34, 197, 94, 0.5)' : 'none',
                flexShrink: 0,
            }}
        />
    );
}

export default function ConfigurationsPage() {
    const [credentials, setCredentials] = useState<Credential[]>([]);
    const [integrationStatus, setIntegrationStatus] = useState<Record<string, { configured: boolean }>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [saving, setSaving] = useState<string | null>(null);
    const [testing, setTesting] = useState<string | null>(null);
    const [testResult, setTestResult] = useState<{ service: string; status: string; message: string } | null>(null);
    const [success, setSuccess] = useState('');
    const [editValues, setEditValues] = useState<Record<string, string>>({});
    const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError('');
            const [statusData, credData] = await Promise.all([
                api.getIntegrationStatus(),
                api.getCredentials(),
            ]);
            setIntegrationStatus(statusData.integrations);
            setCredentials(credData.credentials);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load configuration');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    function getCredValue(key: string): Credential | undefined {
        return credentials.find((c) => c.key === key);
    }

    async function handleSave(field: { key: string; is_secret: boolean }, service: string) {
        const value = editValues[field.key];
        if (!value?.trim()) return;

        try {
            setSaving(field.key);
            setError('');
            setSuccess('');
            await api.setCredential({
                key: field.key,
                value: value.trim(),
                service,
                is_secret: field.is_secret,
            });
            setSuccess(`${field.key} saved successfully`);
            setEditValues((prev) => ({ ...prev, [field.key]: '' }));
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save');
        } finally {
            setSaving(null);
        }
    }

    async function handleDelete(key: string) {
        try {
            setSaving(key);
            setError('');
            await api.deleteCredential(key);
            setSuccess(`${key} removed`);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete');
        } finally {
            setSaving(null);
        }
    }

    async function handleTest(service: string) {
        try {
            setTesting(service);
            setTestResult(null);
            const result = await api.testConnection(service);
            setTestResult(result);
        } catch (err) {
            setTestResult({
                service,
                status: 'error',
                message: err instanceof Error ? err.message : 'Connection test failed',
            });
        } finally {
            setTesting(null);
        }
    }

    // Auto-clear messages
    useEffect(() => {
        if (success) {
            const t = setTimeout(() => setSuccess(''), 4000);
            return () => clearTimeout(t);
        }
    }, [success]);

    if (loading) {
        return (
            <div>
                <h1 className="page-title">Configurations</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4, marginBottom: 24 }}>
                    Manage integrations and service credentials
                </p>
                <div style={{ display: 'grid', gap: 16 }}>
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="card shimmer" style={{ height: 80, borderRadius: 12 }} />
                    ))}
                </div>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            <div style={{ marginBottom: 24 }}>
                <h1 className="page-title">Configurations</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
                    Manage integrations, API keys, and service credentials
                </p>
            </div>

            {/* Global Messages */}
            {error && (
                <div
                    style={{
                        padding: '10px 14px',
                        borderRadius: 8,
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        color: '#ef4444',
                        fontSize: 13,
                        marginBottom: 16,
                    }}
                >
                    ⚠ {error}
                </div>
            )}
            {success && (
                <div
                    style={{
                        padding: '10px 14px',
                        borderRadius: 8,
                        background: 'rgba(34, 197, 94, 0.1)',
                        border: '1px solid rgba(34, 197, 94, 0.3)',
                        color: '#22c55e',
                        fontSize: 13,
                        marginBottom: 16,
                        transition: 'opacity 0.3s',
                    }}
                >
                    ✓ {success}
                </div>
            )}

            {/* Status Overview */}
            <div
                className="card"
                style={{
                    padding: 20,
                    marginBottom: 24,
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                    gap: 16,
                }}
            >
                {SERVICE_GROUPS.map((group) => {
                    const isConfigured = integrationStatus[group.id]?.configured ?? false;
                    return (
                        <div
                            key={group.id}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 10,
                                padding: '10px 14px',
                                borderRadius: 8,
                                background: 'var(--bg-primary)',
                                border: `1px solid ${isConfigured ? 'rgba(34, 197, 94, 0.2)' : 'var(--border)'}`,
                            }}
                        >
                            <span style={{ fontSize: 20 }}>{group.icon}</span>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {group.label.split(' (')[0]}
                                </div>
                                <div style={{ fontSize: 11, color: isConfigured ? '#22c55e' : 'var(--text-muted)' }}>
                                    {isConfigured ? 'Connected' : 'Not configured'}
                                </div>
                            </div>
                            <StatusDot configured={isConfigured} />
                        </div>
                    );
                })}
            </div>

            {/* Service Groups */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {SERVICE_GROUPS.map((group) => {
                    const isExpanded = expandedGroup === group.id;
                    const isConfigured = integrationStatus[group.id]?.configured ?? false;

                    return (
                        <div key={group.id} className="card" style={{ overflow: 'hidden' }}>
                            {/* Header */}
                            <button
                                onClick={() => setExpandedGroup(isExpanded ? null : group.id)}
                                style={{
                                    width: '100%',
                                    padding: '18px 20px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 14,
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                }}
                            >
                                <div
                                    style={{
                                        width: 42,
                                        height: 42,
                                        borderRadius: 10,
                                        background: `${group.color}15`,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: 22,
                                        flexShrink: 0,
                                    }}
                                >
                                    {group.icon}
                                </div>
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                                        {group.label}
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                                        {group.description}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <StatusDot configured={isConfigured} />
                                    <svg
                                        width="16"
                                        height="16"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="var(--text-muted)"
                                        strokeWidth="2"
                                        style={{
                                            transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                                            transition: 'transform 0.2s',
                                        }}
                                    >
                                        <polyline points="6 9 12 15 18 9" />
                                    </svg>
                                </div>
                            </button>

                            {/* Expanded Fields */}
                            {isExpanded && (
                                <div
                                    style={{
                                        padding: '0 20px 20px',
                                        borderTop: '1px solid var(--border)',
                                    }}
                                >
                                    {/* Test Connection Button */}
                                    {group.id !== 'channels' && (
                                        <div style={{ padding: '12px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
                                            <button
                                                onClick={() => handleTest(group.id)}
                                                disabled={testing === group.id || !isConfigured}
                                                style={{
                                                    padding: '6px 14px',
                                                    borderRadius: 6,
                                                    border: '1px solid var(--border)',
                                                    background: 'var(--bg-primary)',
                                                    color: isConfigured ? 'var(--text-primary)' : 'var(--text-muted)',
                                                    fontSize: 12,
                                                    fontWeight: 600,
                                                    cursor: isConfigured ? 'pointer' : 'not-allowed',
                                                    opacity: isConfigured ? 1 : 0.5,
                                                }}
                                            >
                                                {testing === group.id ? '⟳ Testing...' : '🔌 Test Connection'}
                                            </button>
                                            {testResult && testResult.service === group.id && (
                                                <span
                                                    style={{
                                                        fontSize: 12,
                                                        color: testResult.status === 'connected' || testResult.status === 'valid'
                                                            ? '#22c55e'
                                                            : testResult.status === 'not_configured'
                                                                ? 'var(--text-muted)'
                                                                : '#ef4444',
                                                    }}
                                                >
                                                    {testResult.status === 'connected' || testResult.status === 'valid'
                                                        ? '✓ '
                                                        : '✗ '}
                                                    {testResult.message}
                                                </span>
                                            )}
                                        </div>
                                    )}

                                    {/* Credential Fields */}
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                        {group.fields.map((field) => {
                                            const cred = getCredValue(field.key);
                                            const isEditing = editValues[field.key] !== undefined && editValues[field.key] !== '';
                                            const isShowingSecret = showSecrets[field.key];

                                            return (
                                                <div key={field.key}>
                                                    <label
                                                        style={{
                                                            display: 'block',
                                                            fontSize: 12,
                                                            fontWeight: 600,
                                                            color: 'var(--text-secondary)',
                                                            marginBottom: 6,
                                                        }}
                                                    >
                                                        {field.label}
                                                        {cred?.is_set && (
                                                            <span
                                                                style={{
                                                                    marginLeft: 8,
                                                                    fontSize: 10,
                                                                    padding: '2px 6px',
                                                                    borderRadius: 4,
                                                                    background: 'rgba(34, 197, 94, 0.1)',
                                                                    color: '#22c55e',
                                                                }}
                                                            >
                                                                SET
                                                            </span>
                                                        )}
                                                    </label>
                                                    <div style={{ display: 'flex', gap: 8 }}>
                                                        <div style={{ flex: 1, position: 'relative' }}>
                                                            <input
                                                                type={field.is_secret && !isShowingSecret ? 'password' : 'text'}
                                                                value={editValues[field.key] ?? ''}
                                                                onChange={(e) =>
                                                                    setEditValues((prev) => ({
                                                                        ...prev,
                                                                        [field.key]: e.target.value,
                                                                    }))
                                                                }
                                                                placeholder={
                                                                    cred?.is_set
                                                                        ? `Current: ${cred.value} (enter new value to change)`
                                                                        : field.placeholder
                                                                }
                                                                style={{
                                                                    width: '100%',
                                                                    padding: '8px 12px',
                                                                    paddingRight: field.is_secret ? 36 : 12,
                                                                    borderRadius: 6,
                                                                    border: '1px solid var(--border)',
                                                                    background: 'var(--bg-primary)',
                                                                    color: 'var(--text-primary)',
                                                                    fontSize: 13,
                                                                    fontFamily: field.is_secret ? 'monospace' : 'inherit',
                                                                    outline: 'none',
                                                                    boxSizing: 'border-box',
                                                                }}
                                                            />
                                                            {field.is_secret && (
                                                                <button
                                                                    onClick={() =>
                                                                        setShowSecrets((prev) => ({
                                                                            ...prev,
                                                                            [field.key]: !prev[field.key],
                                                                        }))
                                                                    }
                                                                    style={{
                                                                        position: 'absolute',
                                                                        right: 6,
                                                                        top: '50%',
                                                                        transform: 'translateY(-50%)',
                                                                        background: 'none',
                                                                        border: 'none',
                                                                        color: 'var(--text-muted)',
                                                                        cursor: 'pointer',
                                                                        fontSize: 14,
                                                                        padding: 2,
                                                                    }}
                                                                >
                                                                    {isShowingSecret ? '🙈' : '👁'}
                                                                </button>
                                                            )}
                                                        </div>
                                                        <button
                                                            onClick={() => handleSave(field, group.id)}
                                                            disabled={!isEditing || saving === field.key}
                                                            style={{
                                                                padding: '8px 14px',
                                                                borderRadius: 6,
                                                                border: 'none',
                                                                background:
                                                                    isEditing
                                                                        ? 'linear-gradient(135deg, var(--accent), #8b5cf6)'
                                                                        : 'var(--bg-surface)',
                                                                color: isEditing ? 'white' : 'var(--text-muted)',
                                                                fontSize: 12,
                                                                fontWeight: 600,
                                                                cursor: isEditing ? 'pointer' : 'default',
                                                                whiteSpace: 'nowrap',
                                                                opacity: isEditing ? 1 : 0.5,
                                                            }}
                                                        >
                                                            {saving === field.key ? '⟳' : 'Save'}
                                                        </button>
                                                        {cred?.is_set && (
                                                            <button
                                                                onClick={() => handleDelete(field.key)}
                                                                disabled={saving === field.key}
                                                                style={{
                                                                    padding: '8px 10px',
                                                                    borderRadius: 6,
                                                                    border: '1px solid rgba(239, 68, 68, 0.3)',
                                                                    background: 'rgba(239, 68, 68, 0.05)',
                                                                    color: '#ef4444',
                                                                    fontSize: 12,
                                                                    cursor: 'pointer',
                                                                    whiteSpace: 'nowrap',
                                                                }}
                                                                title="Remove this credential"
                                                            >
                                                                ✕
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Help Section */}
            <div
                className="card"
                style={{
                    padding: 20,
                    marginTop: 24,
                    fontSize: 13,
                    color: 'var(--text-muted)',
                    lineHeight: 1.7,
                }}
            >
                <h4 style={{ color: 'var(--text-secondary)', marginBottom: 10, fontSize: 14 }}>
                    💡 Quick Setup Guide
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                    <div>
                        <strong style={{ color: 'var(--text-primary)' }}>WhatsApp (Twilio)</strong>
                        <ol style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                            <li>Create account at{' '}
                                <a href="https://www.twilio.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
                                    twilio.com
                                </a>
                            </li>
                            <li>Enable WhatsApp Sandbox or Business API</li>
                            <li>Copy Account SID, Auth Token, and WhatsApp number</li>
                            <li>Set webhook URL to <code style={{ fontSize: 11 }}>/api/v1/gateway/whatsapp</code></li>
                        </ol>
                    </div>
                    <div>
                        <strong style={{ color: 'var(--text-primary)' }}>Telegram Bot</strong>
                        <ol style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                            <li>Open{' '}
                                <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
                                    @BotFather
                                </a>{' '}on Telegram
                            </li>
                            <li>Send <code style={{ fontSize: 11 }}>/newbot</code> and follow prompts</li>
                            <li>Copy the Bot Token and paste it above</li>
                            <li>Set webhook URL to <code style={{ fontSize: 11 }}>/api/v1/gateway/telegram</code></li>
                        </ol>
                    </div>
                    <div>
                        <strong style={{ color: 'var(--text-primary)' }}>Google Workspace</strong>
                        <ol style={{ paddingLeft: 18, margin: '4px 0 0' }}>
                            <li>Create Service Account in{' '}
                                <a href="https://console.cloud.google.com" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)' }}>
                                    Google Cloud Console
                                </a>
                            </li>
                            <li>Enable Calendar, Drive, Gmail APIs</li>
                            <li>Download JSON key and paste it above</li>
                            <li>Set up Domain-Wide Delegation if needed</li>
                        </ol>
                    </div>
                </div>
            </div>
        </div>
    );
}
