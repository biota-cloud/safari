/**
 * Auto-scroll functionality for log areas.
 * Uses MutationObserver to detect content changes and scroll to bottom.
 */

(function () {
    // IDs of scroll areas that should auto-scroll
    const SCROLL_AREA_IDS = [
        'live-logs-scroll',           // Training dashboard live logs
        'run-detail-logs-scroll',     // Training run detail logs
        'video-autolabel-logs-scroll', // Video editor autolabel modal logs
        'image-autolabel-logs-scroll'  // Image editor autolabel modal logs
    ];

    // Map to track observers and prevent duplicates
    const observerMap = new Map();

    /**
     * Scroll a Radix scroll area to the bottom
     */
    function scrollToBottom(scrollArea) {
        if (!scrollArea) return;
        const viewport = scrollArea.querySelector('[data-radix-scroll-area-viewport]');
        if (viewport) {
            viewport.scrollTop = viewport.scrollHeight;
        }
    }

    /**
     * Set up MutationObserver for a scroll area
     */
    function setupObserver(id) {
        const scrollArea = document.getElementById(id);
        if (!scrollArea) return;

        // Already observing this element
        if (observerMap.has(id)) return;

        // Create observer that watches for content changes
        const observer = new MutationObserver((mutations) => {
            // Scroll to bottom on any change
            scrollToBottom(scrollArea);
        });

        // Observe the scroll area and all descendants for any changes
        observer.observe(scrollArea, {
            childList: true,
            subtree: true,
            characterData: true
        });

        observerMap.set(id, observer);

        // Initial scroll to bottom
        scrollToBottom(scrollArea);
    }

    /**
     * Check for scroll areas and set up observers
     */
    function checkAndSetupObservers() {
        SCROLL_AREA_IDS.forEach(id => {
            setupObserver(id);
        });
    }

    // Initial check
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkAndSetupObservers);
    } else {
        checkAndSetupObservers();
    }

    // Also check periodically for dynamically added elements (modals, etc.)
    setInterval(checkAndSetupObservers, 1000);

    // Cleanup observers when elements are removed
    const bodyObserver = new MutationObserver((mutations) => {
        observerMap.forEach((observer, id) => {
            const element = document.getElementById(id);
            if (!element) {
                observer.disconnect();
                observerMap.delete(id);
            }
        });
    });

    bodyObserver.observe(document.body, {
        childList: true,
        subtree: true
    });
})();
