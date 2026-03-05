/**
 * Global WebSocket throttle for Reflex slider events.
 *
 * Problem: Radix slider on_change fires per pixel (~100+ events per drag).
 * On high-latency connections, each event = 1 WS round-trip (~170ms),
 * causing massive pileup and slider lag.
 *
 * Solution: Intercept WebSocket.send and throttle slider events to
 * max 1 per 300ms, keeping only the latest pending value.
 * Guaranteed to fire on release via the pending flush.
 *
 * This runs as a global asset, before any Reflex WS connections are made.
 */
(function () {
    if (window._sliderThrottleInstalled) return;
    window._sliderThrottleInstalled = true;

    var origSend = WebSocket.prototype.send;

    // Throttle config: event name substring -> { lastSent, pending, timer, limit }
    var throttled = {
        set_epochs: { lastSent: 0, pending: null, timer: null, limit: 300 },
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
                        // Too soon — store as pending, schedule flush
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
                        return; // Drop this message
                    }

                    // Enough time passed — send immediately
                    cfg.lastSent = now;
                    cfg.pending = null;
                    return origSend.call(ws, data);
                }
            }
        }
        // Not a throttled event — pass through
        return origSend.call(this, data);
    };
})();
