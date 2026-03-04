/**
 * Session Manager — Token Refresh & WebSocket Reconnection
 * 
 * Fixes:
 * 1. Proactively refreshes Supabase tokens before they expire
 * 2. Detects tab visibility changes and forces state sync
 * 3. Monitors for session problems and recovers gracefully
 */

(function () {
    'use strict';

    // Read Supabase config from server-injected globals (set by safari.py)
    const config = window.__SAFARI_CONFIG || {};
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
        console.error('[SAFARI Session] Missing window.__SAFARI_CONFIG — Supabase credentials not injected by server.');
    }
    const SUPABASE_URL = config.supabaseUrl;
    const SUPABASE_ANON_KEY = config.supabaseAnonKey;

    const REFRESH_THRESHOLD_MS = 5 * 60 * 1000;  // Refresh 5 mins before expiry
    const CHECK_INTERVAL_MS = 60 * 1000;         // Check every minute

    let lastVisibilityChange = Date.now();
    let isRefreshing = false;

    /**
     * Decode JWT to get expiration time
     */
    function getTokenExpiry(token) {
        if (!token) return null;
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            return payload.exp * 1000;  // Convert to milliseconds
        } catch (e) {
            console.error('[SAFARI Session] Failed to decode token:', e);
            return null;
        }
    }

    /**
     * Refresh the access token using the refresh token
     */
    async function refreshToken() {
        if (isRefreshing) return false;
        isRefreshing = true;

        try {
            const refreshToken = localStorage.getItem('safari_refresh_token') ||
                sessionStorage.getItem('safari_refresh_token');

            if (!refreshToken) {
                console.log('[SAFARI Session] No refresh token available');
                isRefreshing = false;
                return false;
            }

            console.log('[SAFARI Session] Refreshing token...');

            const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'apikey': SUPABASE_ANON_KEY
                },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (!response.ok) {
                console.error('[SAFARI Session] Token refresh failed:', response.status);
                // If refresh fails, session is invalid — redirect to login
                if (response.status === 400 || response.status === 401) {
                    console.log('[SAFARI Session] Session expired, redirecting to login');
                    clearStoredTokens();
                    window.location.href = '/login';
                }
                isRefreshing = false;
                return false;
            }

            const data = await response.json();

            // Update tokens in storage
            const storage = localStorage.getItem('safari_access_token') ? localStorage : sessionStorage;
            storage.setItem('safari_access_token', data.access_token);
            storage.setItem('safari_refresh_token', data.refresh_token);

            console.log('[SAFARI Session] Token refreshed successfully');
            isRefreshing = false;
            return true;
        } catch (e) {
            console.error('[SAFARI Session] Token refresh error:', e);
            isRefreshing = false;
            return false;
        }
    }

    /**
     * Clear all stored tokens
     */
    function clearStoredTokens() {
        localStorage.removeItem('safari_access_token');
        localStorage.removeItem('safari_refresh_token');
        localStorage.removeItem('safari_user_id');
        localStorage.removeItem('safari_user_email');
        sessionStorage.removeItem('safari_access_token');
        sessionStorage.removeItem('safari_refresh_token');
        sessionStorage.removeItem('safari_user_id');
        sessionStorage.removeItem('safari_user_email');
    }

    /**
     * Check if token needs refresh
     */
    async function checkAndRefreshToken() {
        const accessToken = localStorage.getItem('safari_access_token') ||
            sessionStorage.getItem('safari_access_token');

        if (!accessToken) return;

        const expiry = getTokenExpiry(accessToken);
        if (!expiry) return;

        const timeUntilExpiry = expiry - Date.now();

        if (timeUntilExpiry < REFRESH_THRESHOLD_MS) {
            console.log(`[SAFARI Session] Token expires in ${Math.round(timeUntilExpiry / 1000)}s, refreshing...`);
            await refreshToken();
        }
    }

    /**
     * Handle visibility change (tab focus/blur)
     */
    async function handleVisibilityChange() {
        if (document.visibilityState === 'visible') {
            const hiddenDuration = Date.now() - lastVisibilityChange;
            console.log(`[SAFARI Session] Tab became visible after ${Math.round(hiddenDuration / 1000)}s`);

            // If hidden for more than 30 minutes, force token refresh + page reload
            // This ensures both client tokens AND backend state are fully synchronized
            if (hiddenDuration > 30 * 60 * 1000) {
                console.log('[SAFARI Session] Extended inactivity detected (>30 min), forcing full resync...');
                await refreshToken();  // Ensure fresh tokens in storage first
                window.location.reload();  // Clean reload syncs backend state
                return;  // Don't continue, page is reloading
            }

            // If hidden for more than 5 minutes, just check and refresh token (no reload)
            if (hiddenDuration > 5 * 60 * 1000) {
                checkAndRefreshToken();
            }
        }
        lastVisibilityChange = Date.now();
    }

    /**
     * Initialize session manager
     */
    function init() {
        // Only run on authenticated pages (not login page)
        if (window.location.pathname === '/login') return;

        console.log('[SAFARI Session] Session manager initialized');

        // Check token periodically
        setInterval(checkAndRefreshToken, CHECK_INTERVAL_MS);

        // Initial check
        setTimeout(checkAndRefreshToken, 5000);  // Wait 5s for page to settle

        // Listen for visibility changes
        document.addEventListener('visibilitychange', handleVisibilityChange);

        // Listen for online/offline events
        window.addEventListener('online', () => {
            console.log('[SAFARI Session] Network restored, checking token...');
            checkAndRefreshToken();
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
