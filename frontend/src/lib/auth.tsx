'use client';

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { useRouter } from 'next/navigation';

export interface AuthUser {
    id: string;
    email: string;
    name: string;
    department: string;
    role: string;
    is_active: boolean;
}

interface AuthContextType {
    user: AuthUser | null;
    token: string | null;
    loading: boolean;
    login: (email: string, password: string) => Promise<void>;
    logout: () => void;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType>({
    user: null,
    token: null,
    loading: true,
    login: async () => { },
    logout: () => { },
    isAuthenticated: false,
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    // Restore from localStorage on mount, then validate against backend
    useEffect(() => {
        const validateSession = async () => {
            try {
                const savedToken = localStorage.getItem(TOKEN_KEY);
                const savedUser = localStorage.getItem(USER_KEY);
                if (!savedToken || !savedUser) {
                    // Skip auto-login if user explicitly logged out
                    if (localStorage.getItem('logged_out') === 'true') {
                        return;
                    }
                    // DEV MODE: Auto-login with default admin credentials
                    try {
                        const autoRes = await fetch(`${API_BASE}/auth/login`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ email: 'admin@company.ai', password: 'admin123' }),
                        });
                        if (autoRes.ok) {
                            const { access_token, user: userData } = await autoRes.json();
                            setToken(access_token);
                            setUser(userData);
                            localStorage.setItem(TOKEN_KEY, access_token);
                            localStorage.setItem(USER_KEY, JSON.stringify(userData));
                            console.log('🔑 Auto-login: admin@company.ai');
                        }
                    } catch { /* backend not reachable, stay logged out */ }
                    return;
                }

                // Validate token against backend
                const res = await fetch(`${API_BASE}/auth/me`, {
                    headers: { Authorization: `Bearer ${savedToken}` },
                });

                if (res.ok) {
                    const freshUser = await res.json();
                    setToken(savedToken);
                    setUser(freshUser);
                    localStorage.setItem(USER_KEY, JSON.stringify(freshUser));
                } else {
                    // Token invalid/expired — clear stale session
                    localStorage.removeItem(TOKEN_KEY);
                    localStorage.removeItem(USER_KEY);
                }
            } catch {
                // Network error — use cached session as fallback
                try {
                    const savedToken = localStorage.getItem(TOKEN_KEY);
                    const savedUser = localStorage.getItem(USER_KEY);
                    if (savedToken && savedUser) {
                        setToken(savedToken);
                        setUser(JSON.parse(savedUser));
                    }
                } catch {
                    localStorage.removeItem(TOKEN_KEY);
                    localStorage.removeItem(USER_KEY);
                }
            } finally {
                setLoading(false);
            }
        };

        validateSession();
    }, []);

    const login = useCallback(async (email: string, password: string) => {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');

        const { access_token, user: userData } = data;
        setToken(access_token);
        setUser(userData);
        localStorage.setItem(TOKEN_KEY, access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(userData));
        localStorage.removeItem('logged_out');
    }, []);

    const logout = useCallback(() => {
        setToken(null);
        setUser(null);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        localStorage.setItem('logged_out', 'true');
        router.push('/login');
    }, [router]);

    return (
        <AuthContext.Provider value={{
            user,
            token,
            loading,
            login,
            logout,
            isAuthenticated: !!token && !!user,
        }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}

/** Get token for API calls (non-hook usage) */
export function getStoredToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(TOKEN_KEY);
}
