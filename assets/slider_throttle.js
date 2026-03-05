/**
 * Global slider performance optimizations for Reflex apps.
 *
 * 1. WS Throttle: Limits slider on_change WS messages to max 1 per 300ms
 *    (for sliders that still use controlled value + on_change).
 *
 * 2. Value Display Observer: Updates displayed value text during drag
 *    for uncontrolled sliders (default_value + on_value_commit only).
 *    Zero WS traffic — reads aria-valuenow from the slider thumb.
 *
 * Loaded as the first head_component to patch WebSocket.prototype.send
 * before any Reflex WS connections are established.
 */

// ============================================================
// 1. WebSocket Throttle for controlled sliders
// ============================================================
(function () {
    if (window._sliderThrottleInstalled) return;
    window._sliderThrottleInstalled = true;

    var origSend = WebSocket.prototype.send;

    // Throttle config: event handler name -> settings
    var throttled = {
        set_patience: { lastSent: 0, pending: null, timer: null, limit: 300 },
        set_lr0: { lastSent: 0, pending: null, timer: null, limit: 300 },
        set_lrf: { lastSent: 0, pending: null, timer: null, limit: 300 },
        set_train_split: { lastSent: 0, pending: null, timer: null, limit: 300 },
        set_sam3_max_epochs: { lastSent: 0, pending: null, timer: null, limit: 300 },
        set_sam3_early_stop_patience: {
            lastSent: 0,
            pending: null,
            timer: null,
            limit: 300,
        },
        set_convnext_lr0_slider: {
            lastSent: 0,
            pending: null,
            timer: null,
            limit: 300,
        },
        set_convnext_weight_decay_slider: {
            lastSent: 0,
            pending: null,
            timer: null,
            limit: 300,
        },
    };

    WebSocket.prototype.send = function (data) {
        if (typeof data === "string") {
            var ws = this;
            var keys = Object.keys(throttled);
            for (var i = 0; i < keys.length; i++) {
                var key = keys[i];
                if (data.indexOf(key) !== -1) {
                    var cfg = throttled[key];
                    var now = Date.now();
                    var elapsed = now - cfg.lastSent;

                    if (elapsed < cfg.limit) {
                        cfg.pending = data;
                        if (!cfg.timer) {
                            cfg.timer = setTimeout(function () {
                                cfg.timer = null;
                                if (cfg.pending) {
                                    cfg.lastSent = Date.now();
                                    origSend.call(ws, cfg.pending);
                                    cfg.pending = null;
                                }
                            }, cfg.limit - elapsed);
                        }
                        return;
                    }

                    cfg.lastSent = now;
                    cfg.pending = null;
                    return origSend.call(ws, data);
                }
            }
        }
        return origSend.call(this, data);
    };
})();

// ============================================================
// 2. MutationObserver for uncontrolled slider value display
// ============================================================
(function () {
    // Map: slider container ID -> display element ID
    var sliderDisplayMap = {
        "epochs-slider": "epochs-value-display",
    };

    function installObservers() {
        var keys = Object.keys(sliderDisplayMap);
        for (var i = 0; i < keys.length; i++) {
            var sliderId = keys[i];
            var displayId = sliderDisplayMap[sliderId];
            var container = document.getElementById(sliderId);
            var display = document.getElementById(displayId);

            if (!container || !display || container.dataset.observed) continue;

            var thumb = container.querySelector('[role="slider"]');
            if (!thumb) continue;

            container.dataset.observed = "true";

            // Create observer closure
            (function (t, d) {
                new MutationObserver(function (mutations) {
                    for (var j = 0; j < mutations.length; j++) {
                        if (mutations[j].attributeName === "aria-valuenow") {
                            d.textContent = t.getAttribute("aria-valuenow");
                        }
                    }
                }).observe(t, { attributes: true, attributeFilter: ["aria-valuenow"] });
            })(thumb, display);
        }
    }

    // Poll for slider elements (they may render after page load)
    var attempts = 0;
    var iv = setInterval(function () {
        installObservers();
        attempts++;
        if (attempts > 60) clearInterval(iv); // Stop after 30s
    }, 500);
})();
