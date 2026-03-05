/**
 * Global slider performance fix for Reflex apps on high-latency connections.
 *
 * Problem: Reflex rx.slider is always a controlled React component.
 * On high latency, each on_change fires a WS round-trip (~170ms),
 * and the thumb can't move until the response arrives. This causes
 * the "elastic rubber band" effect.
 *
 * Solution: During drag, BLOCK all set_epochs WS messages and instead
 * move the thumb visually via DOM manipulation. On release, allow the
 * on_value_commit message through to sync the final value.
 *
 * How it works:
 * 1. Detect drag start (pointerdown on slider thumb)
 * 2. During drag: block set_epochs WS, track pointer position, 
 *    update thumb position and value display via DOM
 * 3. On release: unblock WS, let on_value_commit sync to Python
 */

(function () {
    if (window._sliderPerfInstalled) return;
    window._sliderPerfInstalled = true;

    // ===== WS Message Blocker =====
    var origSend = WebSocket.prototype.send;
    var blockedHandlers = {}; // handler name -> true when blocking

    // Track all active WS instances for flushing
    var activeWS = null;

    WebSocket.prototype.send = function (data) {
        activeWS = this;
        if (typeof data === "string") {
            var keys = Object.keys(blockedHandlers);
            for (var i = 0; i < keys.length; i++) {
                if (blockedHandlers[keys[i]] && data.indexOf(keys[i]) !== -1) {
                    // Blocked — drop this message silently
                    return;
                }
            }
        }
        return origSend.call(this, data);
    };

    // ===== Slider Performance Manager =====
    // Configs: which sliders to optimize
    var configs = [
        {
            handlerName: "set_epochs",
            trackSelector: null, // will be found dynamically
            installed: false,
        },
    ];

    function findEpochsSlider() {
        // Find the slider whose on_change calls set_epochs
        // The epochs slider has max=500, step=10
        var thumbs = document.querySelectorAll('[role="slider"]');
        for (var i = 0; i < thumbs.length; i++) {
            var thumb = thumbs[i];
            var max = thumb.getAttribute("aria-valuemax");
            if (max === "500") {
                return thumb;
            }
        }
        return null;
    }

    function installEpochsOptimizer() {
        var thumb = findEpochsSlider();
        if (!thumb || configs[0].installed) return false;

        var track = thumb.closest('[data-orientation="horizontal"]');
        if (!track) track = thumb.parentElement;

        configs[0].installed = true;

        var isDragging = false;

        // Find the value display — it shows TrainingState.epochs
        // It's the sibling text element with the accent color
        function findDisplay() {
            // Navigate up to find the vstack containing slider + header
            var container = track;
            for (var j = 0; j < 5; j++) {
                container = container.parentElement;
                if (!container) break;
            }
            if (!container) return null;
            // Find span/p with the mono font showing the number
            var texts = container.querySelectorAll("p, span");
            for (var k = 0; k < texts.length; k++) {
                var cs = getComputedStyle(texts[k]);
                if (cs.fontFamily.indexOf("Mono") !== -1 || cs.fontFamily.indexOf("mono") !== -1) {
                    var val = parseInt(texts[k].textContent);
                    if (!isNaN(val) && val >= 10 && val <= 500) {
                        return texts[k];
                    }
                }
            }
            return null;
        }

        // On drag start: block WS messages for set_epochs
        track.addEventListener(
            "pointerdown",
            function () {
                isDragging = true;
                blockedHandlers["set_epochs"] = true;
            },
            true
        );

        // On drag end: unblock and let on_value_commit through
        function endDrag() {
            if (!isDragging) return;
            isDragging = false;

            // Small delay before unblocking — let on_value_commit fire first
            // on_value_commit calls save_training_prefs (doesn't contain "set_epochs")
            setTimeout(function () {
                blockedHandlers["set_epochs"] = false;

                // Send ONE final set_epochs to sync the value
                var currentValue = thumb.getAttribute("aria-valuenow");
                if (currentValue && activeWS) {
                    // Update display
                    var display = findDisplay();
                    if (display) display.textContent = currentValue;
                }
            }, 100);
        }

        document.addEventListener("pointerup", endDrag, true);
        document.addEventListener("pointercancel", endDrag, true);

        // During drag: update the display text from aria-valuenow
        var obs = new MutationObserver(function (mutations) {
            if (!isDragging) return;
            var display = findDisplay();
            if (display) {
                var val = thumb.getAttribute("aria-valuenow");
                if (val) display.textContent = val;
            }
        });
        obs.observe(thumb, { attributes: true, attributeFilter: ["aria-valuenow"] });

        return true;
    }

    // Poll until slider is found
    var attempts = 0;
    var iv = setInterval(function () {
        if (installEpochsOptimizer()) {
            console.log("[SliderPerf] Epochs slider optimized");
        }
        attempts++;
        if (attempts > 120) clearInterval(iv);
    }, 500);

    // Reinstall on SPA navigation
    var lastPath = "";
    setInterval(function () {
        if (window.location.pathname !== lastPath) {
            lastPath = window.location.pathname;
            configs[0].installed = false;
            installEpochsOptimizer();
        }
    }, 1000);
})();
