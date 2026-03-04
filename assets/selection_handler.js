/**
 * Selection Handler for Image and Video Editor
 * Handles Long Press (Toggle) and Shift+Click (Range)
 */

(function () {
    console.log('[AIO] Selection Helper v2 initialized');

    let pressTimer = null;
    let didLongPress = false;
    const LONG_PRESS_MS = 300;

    // Global state for Reflex callbacks
    window._longpressImageId = '';
    window._rangeSelectImageId = '';
    window._longpressKeyframeId = '';
    window._rangeSelectKeyframeId = '';

    // Handle Mouse Down
    document.addEventListener('mousedown', function (e) {
        // Find if we clicked an image or keyframe thumbnail
        const thumb = e.target.closest('[id^="img-thumb-"], [id^="kf-thumb-"]');
        if (!thumb) return;

        console.log('[AIO] Mousedown on thumbnail:', thumb.id);

        didLongPress = false;
        pressTimer = setTimeout(function () {
            didLongPress = true;

            // Visual feedback
            thumb.style.transform = 'scale(0.97)';
            setTimeout(function () { thumb.style.transform = ''; }, 100);

            if (thumb.id.startsWith('img-thumb-')) {
                const imageId = thumb.id.replace('img-thumb-', '');
                window._longpressImageId = imageId;
                const btn = document.getElementById('longpress-trigger');
                if (btn) {
                    console.log('[AIO] Triggering Image LongPress:', imageId);
                    btn.click();
                } else {
                    console.error('[AIO] Button "longpress-trigger" not found in DOM');
                    // Check if we are in a skeleton state
                }
            } else if (thumb.id.startsWith('kf-thumb-')) {
                const kfId = thumb.id.replace('kf-thumb-', '');
                window._longpressKeyframeId = kfId;
                const btn = document.getElementById('longpress-keyframe-trigger');
                if (btn) {
                    console.log('[AIO] Triggering Keyframe LongPress:', kfId);
                    btn.click();
                } else {
                    console.error('[AIO] Button "longpress-keyframe-trigger" not found in DOM');
                }
            }
        }, LONG_PRESS_MS);
    });

    // Handle Mouse Up
    document.addEventListener('mouseup', function (e) {
        if (pressTimer) {
            clearTimeout(pressTimer);
            pressTimer = null;
        }
    });

    // Handle Clicks (for Range Selection and Blocking LongPress default)
    document.addEventListener('click', function (e) {
        const thumb = e.target.closest('[id^="img-thumb-"], [id^="kf-thumb-"]');
        if (!thumb) return;

        if (didLongPress) {
            console.log('[AIO] Blocking click after long press');
            e.preventDefault();
            e.stopPropagation();
            didLongPress = false;
            return;
        }

        if (e.shiftKey) {
            console.log('[AIO] Shift+Click detected on:', thumb.id);
            e.preventDefault();
            e.stopPropagation();

            if (thumb.id.startsWith('img-thumb-')) {
                const imageId = thumb.id.replace('img-thumb-', '');
                window._rangeSelectImageId = imageId;
                const btn = document.getElementById('range-select-trigger');
                if (btn) {
                    console.log('[AIO] Triggering Image Range Select:', imageId);
                    btn.click();
                } else {
                    console.error('[AIO] Button "range-select-trigger" not found in DOM');
                }
            } else if (thumb.id.startsWith('kf-thumb-')) {
                const kfId = thumb.id.replace('kf-thumb-', '');
                window._rangeSelectKeyframeId = kfId;
                const btn = document.getElementById('range-select-keyframe-trigger');
                if (btn) {
                    console.log('[AIO] Triggering Keyframe Range Select:', kfId);
                    btn.click();
                } else {
                    console.error('[AIO] Button "range-select-keyframe-trigger" not found in DOM');
                }
            }
        }
    }, true);
})();
