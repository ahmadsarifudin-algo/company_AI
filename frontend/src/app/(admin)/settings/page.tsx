'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface LLMSettings {
    provider: string;
    model: string;
    api_key_set: boolean;
    api_key_masked: string;
    available_providers: {
        id: string;
        name: string;
        models: string[];
    }[];
}

export default function SettingsPage() {
    const [settings, setSettings] = useState<LLMSettings | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    // Form state
    const [selectedProvider, setSelectedProvider] = useState('google');
    const [apiKey, setApiKey] = useState('');
    const [showKey, setShowKey] = useState(false);

    // Sync prompts state
    const [syncing, setSyncing] = useState(false);
    const [syncResult, setSyncResult] = useState<{
        created: string[];
        created_count: number;
        updated: string[];
        updated_count: number;
        total_classes: number;
    } | null>(null);

    useEffect(() => {
        loadSettings();
    }, []);

    async function loadSettings() {
        try {
            setLoading(true);
            setError('');
            const data = await api.getLLMSettings();
            setSettings(data);
            setSelectedProvider(data.provider);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load settings');
        } finally {
            setLoading(false);
        }
    }

    async function handleSave() {
        try {
            setSaving(true);
            setError('');
            setSuccess('');

            const update: { provider?: string; api_key?: string } = {};
            if (selectedProvider !== settings?.provider) {
                update.provider = selectedProvider;
            }
            if (apiKey.trim()) {
                update.api_key = apiKey.trim();
            }

            if (!update.provider && !update.api_key) {
                setError('No changes to save');
                setSaving(false);
                return;
            }

            // If changing provider, always include it
            if (apiKey.trim()) {
                update.provider = selectedProvider;
            }

            await api.updateLLMSettings(update);
            setSuccess('Settings saved successfully!');
            setApiKey('');
            await loadSettings();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save settings');
        } finally {
            setSaving(false);
        }
    }

    const currentProviderInfo = settings?.available_providers.find(
        (p) => p.id === selectedProvider
    );

    return (
        <div>
            <div style={{ marginBottom: 32 }}>
                <h1 className="page-title">Settings</h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
                    Configure LLM provider and API keys for agent interactions
                </p>
            </div>

            {loading ? (
                <div className="card" style={{ padding: 40, textAlign: 'center' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: 12 }}>Loading settings...</p>
                </div>
            ) : (
                <div style={{ maxWidth: 640 }}>
                    {/* Status Card */}
                    <div className="card" style={{ padding: 20, marginBottom: 20 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                            <div
                                style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: 10,
                                    background: settings?.api_key_set
                                        ? 'rgba(34, 197, 94, 0.15)'
                                        : 'rgba(239, 68, 68, 0.15)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 18,
                                }}
                            >
                                {settings?.api_key_set ? '✓' : '✗'}
                            </div>
                            <div>
                                <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                    {settings?.api_key_set ? 'API Key Configured' : 'API Key Missing'}
                                </div>
                                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                                    Provider: {settings?.available_providers.find(p => p.id === settings.provider)?.name || settings?.provider}
                                    {settings?.api_key_masked && ` • Key: ${settings.api_key_masked}`}
                                    {settings?.model && ` • Model: ${settings.model}`}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Provider Selection */}
                    <div className="card" style={{ padding: 24, marginBottom: 20 }}>
                        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--text-primary)' }}>
                            LLM Provider
                        </h3>

                        <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
                            {settings?.available_providers.map((provider) => (
                                <button
                                    key={provider.id}
                                    onClick={() => {
                                        setSelectedProvider(provider.id);
                                        setApiKey('');
                                    }}
                                    style={{
                                        flex: 1,
                                        padding: '14px 16px',
                                        borderRadius: 10,
                                        border: `2px solid ${selectedProvider === provider.id
                                            ? 'var(--accent)'
                                            : 'var(--border)'
                                            }`,
                                        background:
                                            selectedProvider === provider.id
                                                ? 'rgba(99, 102, 241, 0.08)'
                                                : 'var(--bg-secondary)',
                                        cursor: 'pointer',
                                        textAlign: 'left',
                                        transition: 'all 0.2s',
                                    }}
                                >
                                    <div
                                        style={{
                                            fontWeight: 600,
                                            fontSize: 14,
                                            color:
                                                selectedProvider === provider.id
                                                    ? 'var(--accent)'
                                                    : 'var(--text-primary)',
                                            marginBottom: 4,
                                        }}
                                    >
                                        {provider.name}
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                        {provider.models[0]}
                                    </div>
                                </button>
                            ))}
                        </div>

                        {/* Model Info */}
                        {currentProviderInfo && (
                            <div
                                style={{
                                    padding: '12px 16px',
                                    background: 'var(--bg-primary)',
                                    borderRadius: 8,
                                    marginBottom: 20,
                                    fontSize: 13,
                                    color: 'var(--text-secondary)',
                                }}
                            >
                                <strong>Available models:</strong>{' '}
                                {currentProviderInfo.models.join(', ')}
                            </div>
                        )}

                        {/* API Key Input */}
                        <div style={{ marginBottom: 20 }}>
                            <label
                                style={{
                                    display: 'block',
                                    fontSize: 13,
                                    fontWeight: 600,
                                    color: 'var(--text-secondary)',
                                    marginBottom: 6,
                                }}
                            >
                                API Key{' '}
                                <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>
                                    ({selectedProvider === 'google'
                                        ? 'from aistudio.google.com'
                                        : 'from platform.openai.com'})
                                </span>
                            </label>
                            <div style={{ position: 'relative' }}>
                                <input
                                    type={showKey ? 'text' : 'password'}
                                    value={apiKey}
                                    onChange={(e) => setApiKey(e.target.value)}
                                    placeholder={
                                        settings?.api_key_set
                                            ? `Current: ${settings.api_key_masked} (enter new key to change)`
                                            : 'Paste your API key here...'
                                    }
                                    style={{
                                        width: '100%',
                                        padding: '10px 44px 10px 14px',
                                        borderRadius: 8,
                                        border: '1px solid var(--border)',
                                        background: 'var(--bg-primary)',
                                        color: 'var(--text-primary)',
                                        fontSize: 14,
                                        fontFamily: 'monospace',
                                        outline: 'none',
                                        boxSizing: 'border-box',
                                    }}
                                />
                                <button
                                    onClick={() => setShowKey(!showKey)}
                                    style={{
                                        position: 'absolute',
                                        right: 8,
                                        top: '50%',
                                        transform: 'translateY(-50%)',
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--text-muted)',
                                        cursor: 'pointer',
                                        padding: 4,
                                        fontSize: 16,
                                    }}
                                    title={showKey ? 'Hide key' : 'Show key'}
                                >
                                    {showKey ? '🙈' : '👁'}
                                </button>
                            </div>
                        </div>

                        {/* Messages */}
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
                                {error}
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
                                }}
                            >
                                {success}
                            </div>
                        )}

                        {/* Save Button */}
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="btn-primary"
                            style={{
                                width: '100%',
                                padding: '12px 24px',
                                borderRadius: 8,
                                border: 'none',
                                background: saving
                                    ? 'var(--text-muted)'
                                    : 'linear-gradient(135deg, var(--accent), #8b5cf6)',
                                color: 'white',
                                fontWeight: 600,
                                fontSize: 14,
                                cursor: saving ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s',
                            }}
                        >
                            {saving ? 'Saving...' : 'Save Settings'}
                        </button>
                    </div>

                    {/* Agent Prompts Management */}
                    <div className="card" style={{ padding: 24, marginBottom: 20 }}>
                        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
                            Agent Prompts
                        </h3>
                        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
                            Populate all agents with their default system prompts from code.
                            Once synced, you can edit each agent&apos;s prompt from the{' '}
                            <a href="/agents" style={{ color: 'var(--accent)' }}>Agents page</a>.
                        </p>

                        {syncResult && (
                            <div
                                style={{
                                    padding: '10px 14px',
                                    borderRadius: 8,
                                    background: 'rgba(34, 197, 94, 0.1)',
                                    border: '1px solid rgba(34, 197, 94, 0.3)',
                                    color: '#22c55e',
                                    fontSize: 13,
                                    marginBottom: 16,
                                }}
                            >
                                Created {syncResult.created_count}, updated {syncResult.updated_count} of {syncResult.total_classes} agent classes
                                {syncResult.created.length > 0 && (
                                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                                        New: {syncResult.created.join(', ')}
                                    </div>
                                )}
                                {syncResult.updated.length > 0 && (
                                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                                        Updated: {syncResult.updated.join(', ')}
                                    </div>
                                )}
                            </div>
                        )}

                        <button
                            onClick={async () => {
                                try {
                                    setSyncing(true);
                                    setError('');
                                    const result = await api.syncAgentPrompts();
                                    setSyncResult(result);
                                } catch (err) {
                                    setError(err instanceof Error ? err.message : 'Failed to sync prompts');
                                } finally {
                                    setSyncing(false);
                                }
                            }}
                            disabled={syncing}
                            style={{
                                padding: '10px 20px',
                                borderRadius: 8,
                                border: '1px solid var(--border)',
                                background: syncing ? 'var(--bg-secondary)' : 'var(--bg-primary)',
                                color: 'var(--text-primary)',
                                fontWeight: 600,
                                fontSize: 13,
                                cursor: syncing ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s',
                            }}
                        >
                            {syncing ? '⟳ Syncing...' : '🔄 Sync Default Prompts'}
                        </button>
                    </div>

                    {/* Help Section */}
                    <div
                        className="card"
                        style={{
                            padding: 20,
                            fontSize: 13,
                            color: 'var(--text-muted)',
                            lineHeight: 1.6,
                        }}
                    >
                        <h4 style={{ color: 'var(--text-secondary)', marginBottom: 8, fontSize: 14 }}>
                            💡 How to get an API key
                        </h4>
                        <ul style={{ paddingLeft: 18, margin: 0 }}>
                            <li>
                                <strong>Google Gemini:</strong> Go to{' '}
                                <a
                                    href="https://aistudio.google.com/apikey"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: 'var(--accent)' }}
                                >
                                    aistudio.google.com/apikey
                                </a>
                            </li>
                            <li>
                                <strong>OpenAI:</strong> Go to{' '}
                                <a
                                    href="https://platform.openai.com/api-keys"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: 'var(--accent)' }}
                                >
                                    platform.openai.com/api-keys
                                </a>
                            </li>
                        </ul>
                        <p style={{ marginTop: 12, marginBottom: 0 }}>
                            Keys are stored securely in Redis and take effect immediately for the Playground.
                        </p>
                    </div>
                </div>
            )}
        </div>
    );
}
