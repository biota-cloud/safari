/**
 * Inference Video Player — Canvas-based label rendering for inference playback.
 * 
 * Synchronizes video playback with dynamic bounding box drawing.
 * Labels are stored separately (not burned into video) for cost efficiency.
 * 
 * CRITICAL: Box coordinates from Modal are NORMALIZED (0-1 range).
 * Must transform to pixel coordinates before drawing on canvas.
 */

(function () {
    console.log('[InferencePlayer] Module loaded');

    let video = null;
    let canvas = null;
    let ctx = null;
    let labelsByFrame = {};  // Frame number -> array of boxes
    let masksByFrame = {};   // Frame number -> array of masks
    let currentFps = 30;
    let animationFrameId = null;
    let showMasks = true;    // Toggle mask visibility

    // Cached rendering dimensions (updated on canvas resize)
    let renderWidth = 0;
    let renderHeight = 0;
    let offsetX = 0;
    let offsetY = 0;

    // Track if we've added event listeners to avoid duplicates
    let listenersAttached = false;

    /**
     * Check if an element is still connected to the DOM
     */
    function isElementConnected(el) {
        return el && el.isConnected;
    }

    /**
     * Cleanup previous player state
     */
    function cleanup() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        // Remove old event listeners if video exists
        if (video && listenersAttached) {
            video.removeEventListener('timeupdate', onTimeUpdate);
            video.removeEventListener('seeked', onSeeked);
            video.removeEventListener('play', onPlay);
            video.removeEventListener('pause', onPause);
            video.removeEventListener('loadedmetadata', onLoadedMetadata);
            listenersAttached = false;
        }
        video = null;
        canvas = null;
        ctx = null;
    }

    /**
     * Initialize the player (find DOM elements)
     * @param {boolean} force - Force re-initialization even if elements exist
     */
    function init(force = false) {
        // Check if we need to reinitialize (elements disconnected or forced)
        if (!force && video && isElementConnected(video) && canvas && isElementConnected(canvas)) {
            console.log('[InferencePlayer] Already initialized with connected elements');
            return true;
        }

        // Cleanup previous state
        cleanup();

        video = document.getElementById('inference-video');
        canvas = document.getElementById('inference-canvas');

        if (!video) {
            console.warn('[InferencePlayer] Video element not found');
            return false;
        }

        if (!canvas) {
            console.warn('[InferencePlayer] Canvas element not found');
            return false;
        }

        ctx = canvas.getContext('2d');
        console.log('[InferencePlayer] Initialized (fresh)');

        // Set up video event listeners
        video.addEventListener('timeupdate', onTimeUpdate);
        video.addEventListener('seeked', onSeeked);
        video.addEventListener('play', onPlay);
        video.addEventListener('pause', onPause);
        video.addEventListener('loadedmetadata', onLoadedMetadata);
        listenersAttached = true;

        // Listen for window resize to update canvas size (debounced)
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                if (video && isElementConnected(video) && video.videoWidth > 0) {
                    updateCanvasSize();
                    drawLabels(); // Redraw after resize
                }
            }, 100);
        });

        return true;
    }

    /**
     * Load a video for inference playback
     * @param {string} url - Presigned R2 URL for video
     */
    window.loadInferenceVideo = function (url) {
        console.log('[InferencePlayer] Loading video:', url ? url.substring(0, 80) + '...' : 'null');

        // ALWAYS re-initialize to ensure we have fresh DOM references
        // This is critical when switching between modal preview and full view
        if (!init(true)) {
            console.error('[InferencePlayer] Failed to initialize');
            return;
        }

        // CRITICAL: Set crossOrigin before src to avoid tainted canvas
        video.crossOrigin = 'anonymous';
        video.src = url;
        video.load();
    };

    /**
     * Cleanup function exposed globally for when modal closes
     */
    window.cleanupInferencePlayer = function () {
        console.log('[InferencePlayer] Cleanup called');
        cleanup();
    };

    /**
     * Sync labels data from Python state
     * @param {Object} labelsData - Object with frame numbers as keys, label arrays as values
     */
    window.setInferenceLabels = function (labelsData) {
        labelsByFrame = labelsData || {};
        console.log('[InferencePlayer] Labels loaded:', Object.keys(labelsByFrame).length, 'frames');
    };

    /**
     * Sync masks data from Python state
     * @param {Object} masksData - Object with frame numbers as keys, mask arrays as values
     */
    window.setInferenceMasks = function (masksData) {
        masksByFrame = masksData || {};
        console.log('[InferencePlayer] Masks loaded:', Object.keys(masksByFrame).length, 'frames');
    };

    /**
     * Toggle mask visibility
     * @param {boolean} visible - Whether masks should be visible
     */
    window.setMasksVisible = function (visible) {
        showMasks = visible;
        console.log('[InferencePlayer] Masks visibility:', visible);
        drawLabels(); // Redraw with new visibility
    };

    /**
     * Set the FPS for frame number calculation
     * @param {number} fps - Video frames per second
     */
    window.setInferenceFps = function (fps) {
        currentFps = fps;
        console.log('[InferencePlayer] FPS set to:', fps);
    };

    /**
     * Toggle playback
     * @param {boolean} shouldPlay - True to play, false to pause
     */
    window.toggleInferencePlayback = function (shouldPlay) {
        if (!video) return;

        if (shouldPlay) {
            video.play().catch(e => console.error('[InferencePlayer] Play error:', e));
        } else {
            video.pause();
        }
    };

    /**
     * Step frame by frame
     * @param {number} delta - Number of frames to step (positive or negative)
     */
    window.stepInferenceFrame = function (delta) {
        if (!video) return;

        const currentFrame = Math.floor(video.currentTime * currentFps);
        const newFrame = Math.max(0, currentFrame + delta);
        video.currentTime = newFrame / currentFps;

        console.log('[InferencePlayer] Stepped to frame:', newFrame);
    };

    /**
     * Set playback speed
     * @param {number} speed - Playback rate (0.25, 0.5, 1, 2, etc.)
     */
    window.setInferencePlaybackSpeed = function (speed) {
        if (!video) return;

        video.playbackRate = speed;
        console.log('[InferencePlayer] Playback speed set to:', speed);
    };

    /**
     * Handle video metadata loaded
     */
    function onLoadedMetadata() {
        console.log('[InferencePlayer] Metadata loaded:', {
            duration: video.duration,
            width: video.videoWidth,
            height: video.videoHeight
        });

        // Match canvas to video dimensions
        updateCanvasSize();

        // Draw first frame
        drawLabels();
    }

    /**
     * Update canvas size to match video and calculate letterboxing
     */
    function updateCanvasSize() {
        if (!video || !canvas) return;

        // Get the video's actual displayed size and position
        const videoRect = video.getBoundingClientRect();

        // Set canvas to absolute position to overlay video
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '10';

        // CRITICAL: Set canvas internal resolution to match its DISPLAY size, not video native size
        // This ensures 1:1 pixel mapping between canvas drawing and what's displayed
        canvas.width = Math.floor(videoRect.width);
        canvas.height = Math.floor(videoRect.height);

        // CACHE letterboxing calculations for use in drawLabels
        const videoAspect = video.videoWidth / video.videoHeight;
        const canvasAspect = canvas.width / canvas.height;

        if (videoAspect > canvasAspect) {
            // Video is wider - letterboxed (bars on top/bottom)
            renderWidth = canvas.width;
            renderHeight = canvas.width / videoAspect;
            offsetX = 0;
            offsetY = (canvas.height - renderHeight) / 2;
        } else {
            // Video is taller - pillarboxed (bars on sides)
            renderWidth = canvas.height * videoAspect;
            renderHeight = canvas.height;
            offsetX = (canvas.width - renderWidth) / 2;
            offsetY = 0;
        }

        console.log('[InferencePlayer] Canvas sized:', canvas.width, 'x', canvas.height,
            'offset:', offsetX.toFixed(1), offsetY.toFixed(1));
    }

    /**
     * Handle time update during playback
     */
    function onTimeUpdate() {
        // Only used for non-playing updates (seeking, paused)
        // During playback, we use requestAnimationFrame for smoothness
    }

    /**
     * Handle seek completion
     */
    function onSeeked() {
        drawLabels();
    }

    /**
     * Handle play event - start animation loop
     */
    function onPlay() {
        console.log('[InferencePlayer] Playing');
        startAnimationLoop();
    }

    /**
     * Handle pause event - stop animation loop
     */
    function onPause() {
        console.log('[InferencePlayer] Paused');
        stopAnimationLoop();
    }

    /**
     * Start requestAnimationFrame loop for smooth rendering
     */
    function startAnimationLoop() {
        if (animationFrameId) return; // Already running

        function animate() {
            drawLabels();
            animationFrameId = requestAnimationFrame(animate);
        }

        animationFrameId = requestAnimationFrame(animate);
    }

    /**
     * Stop requestAnimationFrame loop
     */
    function stopAnimationLoop() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        // Draw one last frame to show paused state
        drawLabels();
    }

    /**
     * Draw bounding boxes for current frame
     */
    function drawLabels() {
        if (!video || !canvas || !ctx) return;

        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Calculate current frame number
        const currentFrame = Math.floor(video.currentTime * currentFps);

        // Get labels and masks for this frame
        const labels = labelsByFrame[currentFrame] || [];
        const masks = masksByFrame[currentFrame] || [];

        // Draw masks first (behind boxes) if visible
        if (showMasks && masks.length > 0) {
            masks.forEach((mask) => {
                if (!mask.polygon || mask.polygon.length < 3) return;

                // Generate color based on class_id (SAFARI Naturalist palette)
                const hue = (mask.class_id * 137 + 30) % 360;

                // Draw filled polygon
                ctx.beginPath();
                const firstPoint = mask.polygon[0];
                const startX = offsetX + (firstPoint[0] * renderWidth);
                const startY = offsetY + (firstPoint[1] * renderHeight);
                ctx.moveTo(startX, startY);

                for (let i = 1; i < mask.polygon.length; i++) {
                    const point = mask.polygon[i];
                    const px = offsetX + (point[0] * renderWidth);
                    const py = offsetY + (point[1] * renderHeight);
                    ctx.lineTo(px, py);
                }

                ctx.closePath();
                ctx.fillStyle = `hsla(${hue}, 45%, 42%, 0.35)`;
                ctx.fill();

                // Draw polygon outline
                ctx.strokeStyle = `hsl(${hue}, 45%, 42%)`;
                ctx.lineWidth = 1;
                ctx.stroke();
            });
        }

        if (labels.length === 0) {
            // No labels for this frame (masks may have been drawn)
            return;
        }

        // Use cached rendering dimensions (no recalculation needed!)
        // Draw each bounding box
        labels.forEach((label) => {
            // Extract coordinates from box array
            // Box format is [x1, y1, x2, y2] (corner coordinates)
            const [x1, y1, x2, y2] = label.box;

            // Convert to x, y, width, height
            const normX = x1;
            const normY = y1;
            const normW = x2 - x1;
            const normH = y2 - y1;

            // Transform normalized coordinates (0-1) to pixel coordinates
            // using cached renderWidth, renderHeight, offsetX, offsetY
            const x = offsetX + (normX * renderWidth);
            const y = offsetY + (normY * renderHeight);
            const w = normW * renderWidth;
            const h = normH * renderHeight;

            // Generate color based on class_id (SAFARI Naturalist palette)
            const hue = (label.class_id * 137 + 30) % 360;
            const color = `hsl(${hue}, 45%, 42%)`;

            // Draw box
            ctx.strokeStyle = color;
            ctx.lineWidth = 3;
            ctx.strokeRect(x, y, w, h);

            // Draw label background
            const labelText = `${label.class_name} ${(label.confidence * 100).toFixed(0)}%`;
            ctx.font = '14px Inter, sans-serif';
            const textMetrics = ctx.measureText(labelText);
            const textWidth = textMetrics.width;
            const textHeight = 20;

            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.fillRect(x, y - textHeight - 4, textWidth + 8, textHeight);

            // Draw label text
            ctx.fillStyle = '#FFFFFF';
            ctx.fillText(labelText, x + 4, y - 8);
        });
    }

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    console.log('[InferencePlayer] Module initialized');
})();
