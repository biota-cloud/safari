/**
 * Global slider performance optimizations for Reflex apps.
 *
 * 1. WS Throttle: Limits slider on_change WS messages for controlled sliders.
 * 2. Pure HTML Slider Management: Initializes, updates display, and syncs
 *    pure HTML range inputs that bypass Reflex's auto-generated controlled bindings.
 *
 * Loaded as the first head_component to patch WebSocket.prototype.send
 * before any Reflex WS connections are established.
 */

// ============================================================
// 1. WebSocket Throttle for controlled sliders (non-epoch)
// ============================================================
(function () {
    if (window._sliderThrottleInstalled) return;
    window._sliderThrottleInstalled = true;

    var origSend = WebSocket.prototype.send;

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
// 2. Pure HTML slider management (epochs)
// ============================================================
(function () {
    /**
     * For each slider config:
     * - rangeId: the <input type="range"> element
     * - displayId: the <span> showing the current value
     * - bridgeId: hidden <input> that triggers Reflex on_change on release
     */
    var sliders = [
        {
            rangeId: "epochs-range",
            displayId: "epochs-value-display",
            bridgeId: "epochs-bridge",
        },
    ];

    function setupSlider(cfg) {
        var range = document.getElementById(cfg.rangeId);
        var display = document.getElementById(cfg.displayId);
        var bridge = document.getElementById(cfg.bridgeId);

        if (!range || !bridge || range.dataset.managed) return false;
        range.dataset.managed = "true";

        // Set initial value from data-initial attribute (rendered by Reflex from state)
        var initial = range.getAttribute("data-initial");
        if (initial && initial !== "None" && initial !== "undefined") {
            range.value = initial;
        }

        // Update display immediately with initial value
        if (display) {
            display.textContent = range.value;
        }

        // Live display update during drag — zero WS, purely client-side
        range.addEventListener("input", function () {
            if (display) {
                display.textContent = range.value;
            }
        });

        // On release: sync to Python via hidden input bridge
        range.addEventListener("change", function () {
            if (bridge) {
                // Set value and dispatch change event to trigger Reflex on_change
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype,
                    "value"
                ).set;
                nativeInputValueSetter.call(bridge, range.value);
                bridge.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });

        return true;
    }

    function installAll() {
        var allDone = true;
        for (var i = 0; i < sliders.length; i++) {
            if (!document.getElementById(sliders[i].rangeId)) {
                allDone = false;
                continue;
            }
            if (
                document.getElementById(sliders[i].rangeId) &&
                !document.getElementById(sliders[i].rangeId).dataset.managed
            ) {
                if (!setupSlider(sliders[i])) allDone = false;
            }
        }
        return allDone;
    }

    // Poll for elements (page may not be rendered yet)
    var attempts = 0;
    var iv = setInterval(function () {
        installAll();
        attempts++;
        if (attempts > 120) clearInterval(iv); // Stop after 60s
    }, 500);

    // Also re-install on page navigation (Reflex SPA transitions)
    var lastPath = "";
    setInterval(function () {
        if (window.location.pathname !== lastPath) {
            lastPath = window.location.pathname;
            // Reset managed flags on path change
            for (var i = 0; i < sliders.length; i++) {
                var el = document.getElementById(sliders[i].rangeId);
                if (el) delete el.dataset.managed;
            }
            installAll();
        }
    }, 500);
})();
