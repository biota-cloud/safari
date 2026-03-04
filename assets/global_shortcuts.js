/**
 * Global Shortcuts
 * 
 * Keyboard shortcuts that work across all authenticated pages.
 * Loaded via head_components in the main app.
 */

(function () {
    // Only run once
    if (window.__globalShortcutsInitialized) return;
    window.__globalShortcutsInitialized = true;

    document.addEventListener('keydown', function (e) {
        // Don't trigger if typing in an input field
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // Don't trigger on login page
        if (window.location.pathname === '/login' || window.location.pathname === '/') return;

        // H - Go to Dashboard/Hub
        if (e.key.toLowerCase() === 'h' && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            window.location.href = '/dashboard';
        }
    });

    console.log('[GlobalShortcuts] Initialized');
})();
