/**
 * Canvas Labeling Script
 * Handles image display, zoom, pan, and annotations for the labeling editor.
 */
(function () {
    // ==========================================================================
    // CANVAS STATE (JS-owned for 60fps responsiveness)
    // ==========================================================================

    let canvas = null;
    let ctx = null;
    let currentImage = null;
    let sourceWidth = 0;   // Width of current source (image or video)
    let sourceHeight = 0;  // Height of current source (image or video)

    // Transform state
    let scale = 1.0;        // Current zoom level
    let offsetX = 0;        // Pan offset X (in canvas pixels)
    let offsetY = 0;        // Pan offset Y (in canvas pixels)

    // Image cache (URL -> HTMLImageElement)
    const imageCache = new Map();

    // Image fit state (calculated once per image load)
    let baseScale = 1.0;    // Scale to fit image in canvas
    let baseOffsetX = 0;    // Centering offset X
    let baseOffsetY = 0;    // Centering offset Y

    // Zoom constraints
    const MIN_ZOOM = 1.0;
    const MAX_ZOOM = 10.0;
    const ZOOM_STEP = 0.25;
    const WHEEL_ZOOM_FACTOR = 0.001;

    // Panning state
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panOffsetStartX = 0;
    let panOffsetStartY = 0;

    // Tool state
    let currentTool = 'select';  // 'select', 'draw', or 'mask_edit'

    // Pending image URL (in case loadCanvasImage is called before canvas is ready)
    let pendingImageUrl = null;
    let canvasReady = false;

    // ==========================================================================
    // INITIALIZATION
    // ==========================================================================

    // Drawing state
    let isDrawing = false;
    let drawStartX = 0;
    let drawStartY = 0;
    let drawCurrentX = 0;
    let drawCurrentY = 0;

    // Annotations
    let annotations = [];
    let selectedAnnotationId = null;

    // Current class for new annotations (synced from Python)
    let currentClassId = 0;
    let currentClassName = "Unknown";

    // Drag state for resize/move
    let isDraggingHandle = false;
    let isDraggingBox = false;
    let dragHandleIndex = -1; // 0=TL, 1=TR, 2=BL, 3=BR
    let dragAnnotationId = null;
    let dragStartAnnotation = null; // Original bounds before drag
    let dragStartMouseX = 0;
    let dragStartMouseY = 0;

    // Mask-edit state
    let maskEditAnnId = null;         // Annotation currently in mask-edit mode
    let isDraggingVertex = false;     // Is a mask vertex being dragged?
    let dragVertexIdx = -1;           // Index of the vertex being dragged
    let hoveredVertexIdx = -1;        // Index of vertex near cursor (-1 if none)
    let maskMouseX = 0;               // Current mouse X in screen coords (for proximity)
    let maskMouseY = 0;               // Current mouse Y in screen coords (for proximity)
    const VERTEX_HANDLE_RADIUS = 5;   // Visual radius of vertex circles
    const VERTEX_HIT_RADIUS = 10;     // Hit test radius for vertex picking
    const VERTEX_PROXIMITY_PX = 60;   // Only show handles within this px radius of cursor
    const EDGE_HIT_TOLERANCE = 8;     // Px tolerance for clicking on a polygon edge

    // ==========================================================================
    // HELPER FUNCTIONS
    // ==========================================================================

    /**
     * Generate consistent color for a class using HSL rotation (golden angle).
     * SAFARI Naturalist palette: warm, earthy tones (lower saturation).
     * Must stay in sync with Python's LabelingState.get_class_color formula.
     * @param {number} classId - Class index
     * @returns {string} HSL color string
     */
    function getClassColor(classId) {
        const hue = (classId * 137 + 30) % 360;  // +30° offset for warmer starting point
        return `hsl(${hue}, 45%, 42%)`;
    }

    // ==========================================================================
    // INITIALIZATION
    // ==========================================================================

    function initCanvas() {
        canvas = document.getElementById('labeling-canvas');
        if (!canvas) {
            console.log('[Canvas] Waiting for canvas element...');
            setTimeout(initCanvas, 100);
            return;
        }
        ctx = canvas.getContext('2d');
        resizeCanvas();

        // Event listeners
        // Resize handling using ResizeObserver for container size changes
        // This handles both window resize and layout changes (e.g. focus mode sidebar animation)
        const observer = new ResizeObserver(() => {
            // Use requestAnimationFrame to debounce and ensuring smooth animation
            requestAnimationFrame(() => resizeCanvas());
        });
        if (canvas.parentElement) {
            observer.observe(canvas.parentElement);
        } else {
            // Fallback
            window.addEventListener('resize', resizeCanvas);
        }
        canvas.addEventListener('wheel', handleWheel, { passive: false });
        canvas.addEventListener('mousedown', handleMouseDown);
        canvas.addEventListener('mousemove', handleMouseMove);
        canvas.addEventListener('mouseup', handleMouseUp);
        canvas.addEventListener('mouseleave', handleMouseUp);

        // Handle context menu on right-click (for annotation actions)
        canvas.addEventListener('contextmenu', handleContextMenu);

        // Keyboard listeners (on document, not canvas, to catch keys reliably)
        document.addEventListener('keydown', handleKeyDown);

        // Save-before-leave handlers for browser navigation (back button, close tab, etc.)
        // These trigger Python to flush any pending saves
        window.addEventListener('beforeunload', handleBeforeUnload);
        window.addEventListener('pagehide', handlePageHide);
        window.addEventListener('popstate', handlePopState);

        canvasReady = true;
        console.log('[Canvas] Initialized successfully');

        // Load pending image if any
        if (pendingImageUrl) {
            console.log('[Canvas] Loading pending image:', pendingImageUrl);
            loadImageInternal(pendingImageUrl);
            pendingImageUrl = null;
        }
    }

    /**
     * Handle beforeunload event - triggers synchronous save via hidden input
     */
    function handleBeforeUnload(e) {
        // Save silently without confirmation dialog (PyCharm-like behavior)
        triggerSaveBeforeLeave();
    }

    /**
     * Handle pagehide event - iOS Safari and some browsers use this instead of beforeunload
     */
    function handlePageHide(e) {
        triggerSaveBeforeLeave();
    }

    /**
     * Handle popstate event - back/forward button navigation
     */
    function handlePopState(e) {
        triggerSaveBeforeLeave();
    }

    /**
     * Trigger save before leaving the page via hidden input
     */
    function triggerSaveBeforeLeave() {
        const input = document.getElementById('save-before-leave-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered save before leave');
        }
    }

    /**
     * Handle right-click context menu on canvas.
     * If right-clicking on a selected annotation, trigger Python context menu.
     * Otherwise, just prevent default browser context menu.
     */
    function handleContextMenu(e) {
        e.preventDefault();

        // Mask-edit mode: right-click removes a vertex
        if (currentTool === 'mask_edit' && maskEditAnnId) {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            const vertIdx = hitTestMaskVertices(mouseX, mouseY);
            if (vertIdx !== -1) {
                const ann = annotations.find(a => a.id === maskEditAnnId);
                if (ann && ann.mask_polygon && ann.mask_polygon.length > 3) {
                    ann.mask_polygon.splice(vertIdx, 1);
                    console.log('[Canvas] Removed vertex at index:', vertIdx);
                    hoveredVertexIdx = -1;
                    saveUpdatedAnnotationToPython(ann);
                    drawCanvas();
                } else {
                    console.log('[Canvas] Cannot remove vertex: polygon needs at least 3 points');
                }
            }
            return;
        }

        // Only show context menu if we have an image and a selected annotation
        if (!currentImage || !selectedAnnotationId) {
            return;
        }

        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Check if right-click is on the selected annotation
        const hitId = hitTestAnnotations(mouseX, mouseY);
        if (hitId === selectedAnnotationId) {
            // Trigger context menu in Python with viewport coordinates
            triggerContextMenu(e.clientX, e.clientY, selectedAnnotationId);
        }
    }

    /**
     * Trigger context menu in Python via hidden input.
     * @param {number} x - Viewport X coordinate
     * @param {number} y - Viewport Y coordinate
     * @param {string} annotationId - ID of the annotation
     */
    function triggerContextMenu(x, y, annotationId) {
        const input = document.getElementById('context-menu-trigger');
        if (input) {
            const data = JSON.stringify({ x, y, annotation_id: annotationId });
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, data);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered context menu for annotation:', annotationId);
        } else {
            console.warn('[Canvas] context-menu-trigger input not found');
        }
    }

    function ensureLiveCanvas() {
        const liveCanvas = document.getElementById('labeling-canvas');
        if (liveCanvas && liveCanvas !== canvas) {
            console.log('[Canvas] Detected new canvas element, updating reference');
            canvas = liveCanvas;
            ctx = canvas.getContext('2d');

            // Re-attach listeners to new element
            canvas.addEventListener('wheel', handleWheel, { passive: false });
            canvas.addEventListener('mousedown', handleMouseDown);
            canvas.addEventListener('mousemove', handleMouseMove);
            canvas.addEventListener('mouseup', handleMouseUp);
            canvas.addEventListener('mouseleave', handleMouseUp);
            canvas.addEventListener('contextmenu', handleContextMenu);

            return true;
        }
        return !!canvas;
    }

    function resizeCanvas() {
        ensureLiveCanvas();
        if (!canvas) return;

        // Look specifically for our named container first
        let container = document.getElementById('canvas-container');

        // Fallback to parent walking if named container not found or empty
        if (!container || (container.clientWidth === 0 && container.clientHeight === 0)) {
            container = canvas.parentElement;
            while (container && (container.clientWidth === 0 || container.clientHeight === 0)) {
                container = container.parentElement;
            }
        }

        if (!container || container.clientWidth === 0 || container.clientHeight === 0) {
            console.log('[Canvas] No sized container found, retrying...');
            // updateDebugStatus('Waiting for layout...'); // Too noisy
            setTimeout(resizeCanvas, 100);
            return;
        }

        // Only resize if different to avoid flickering/clearing
        if (canvas.width !== container.clientWidth || canvas.height !== container.clientHeight) {
            canvas.width = container.clientWidth;
            canvas.height = container.clientHeight;
            console.log('[Canvas] Resized to:', canvas.width, 'x', canvas.height);
        }

        if (currentImage) {
            // Always update fit parameters on resize to ensure centering math is current
            calculateFit();
            drawCanvas();
        } else {
            drawPlaceholder();
        }
    }

    // ==========================================================================
    // IMAGE LOADING & FIT
    // ==========================================================================

    function drawPlaceholder() {
        if (!ctx || !canvas) return;
        ctx.fillStyle = '#141415';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#A1A1AA';
        ctx.font = '16px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Select an image to start labeling', canvas.width / 2, canvas.height / 2);
    }

    function updateDebugStatus(msg) {
        const el = document.getElementById('js-status');
        if (el) el.textContent = 'JS: ' + msg;
        console.log('[Debug] ' + msg);
    }

    // Public API: Load image into canvas
    window.loadCanvasImage = function (url) {
        updateDebugStatus('Load called...');
        console.log('[Canvas] loadCanvasImage called with:', url ? url.substring(0, 50) + '...' : 'null');

        if (!url) {
            currentImage = null;
            sourceWidth = 0;
            sourceHeight = 0;
            if (canvasReady) drawPlaceholder();
            updateDebugStatus('No URL provided');
            return;
        }

        if (!canvasReady) {
            console.log('[Canvas] Not ready yet, storing pending URL');
            updateDebugStatus('Canvas not ready, pending...');
            pendingImageUrl = url;
            return;
        }

        loadImageInternal(url);
    };

    // Internal: Actually load the image
    function loadImageInternal(url) {
        updateDebugStatus('Loading Internal...');
        if (imageCache.has(url)) {
            const cachedImg = imageCache.get(url);
            if (cachedImg.complete) {
                console.log('[Canvas] Using cached image:', url.substring(0, 50) + '...');
                updateDebugStatus('Using cache');
                handleLoadedImage(cachedImg);
                return;
            }
        }

        console.log('[Canvas] Loading image:', url.substring(0, 50) + '...');
        updateDebugStatus('Fetching image...');
        const img = new Image();
        // img.crossOrigin = 'anonymous'; // Disabled to fix likely CORS issues
        img.onload = function () {
            imageCache.set(url, img);
            handleLoadedImage(img);
        };
        img.onerror = function (e) {
            console.error('[Canvas] Failed to load image:', url, e);
            updateDebugStatus('Error: Failed to load');
            currentImage = null;
            sourceWidth = 0;
            sourceHeight = 0;
            drawPlaceholder();
        };
        img.src = url;
    }

    function handleLoadedImage(img) {
        // Use decode() to ensure image data is ready for canvas
        img.decode().then(() => {
            console.log('[Canvas] Image decoded:', img.width, 'x', img.height);
            updateDebugStatus('Image Ready ' + img.width + 'x' + img.height);
            currentImage = img;
            sourceWidth = img.width;
            sourceHeight = img.height;
            // Reset view when loading new image
            scale = 1.0;
            offsetX = 0;
            offsetY = 0;
            // Ensure canvas is sized correctly before drawing
            resizeCanvas();
            console.log('[Canvas] Canvas size:', canvas.width, 'x', canvas.height);
            syncZoomToReflex();
        }).catch((err) => {
            console.error('[Canvas] Image decode failed:', err);
            updateDebugStatus('Decode Error: ' + err.message);
        });
    }

    /**
     * Public API: Pre-fetch images into cache
     * @param {string[]} urls - List of image URLs to pre-fetch
     */
    window.prefetchImages = function (urls) {
        if (!urls || !Array.isArray(urls)) return;

        console.log('[Canvas] Pre-fetching', urls.length, 'images...');
        urls.forEach(url => {
            if (imageCache.has(url)) return;

            const img = new Image();
            // img.crossOrigin = 'anonymous'; // Disabled to match loadImageInternal
            img.onload = () => {
                console.log('[Canvas] Pre-fetched successfully:', url.substring(0, 50) + '...');
                imageCache.set(url, img);
            };
            img.onerror = (e) => {
                console.warn('[Canvas] Pre-fetch failed for:', url, e);
            };
            img.src = url;
        });
    };

    /**
     * Public API: Render annotations from Python
     * @param {Array} a - List of annotation objects
     */
    window.renderAnnotations = function (a) {
        annotations = a || [];
        drawCanvas();
    };

    function calculateFit() {
        if (!currentImage || !canvas) return;

        const imgWidth = sourceWidth;
        const imgHeight = sourceHeight;
        const canvasWidth = canvas.width;
        const canvasHeight = canvas.height;

        // Calculate scale to fit (don't upscale beyond 1)
        const scaleX = canvasWidth / imgWidth;
        const scaleY = canvasHeight / imgHeight;
        baseScale = Math.min(scaleX, scaleY, 1);

        // Calculate centering offset
        const scaledWidth = imgWidth * baseScale;
        const scaledHeight = imgHeight * baseScale;
        baseOffsetX = (canvasWidth - scaledWidth) / 2;
        baseOffsetY = (canvasHeight - scaledHeight) / 2;

        console.log('[Canvas] calculateFit:', {
            img: [imgWidth, imgHeight],
            canvas: [canvasWidth, canvasHeight],
            baseScale,
            offset: [baseOffsetX, baseOffsetY]
        });
    }

    // ==========================================================================
    // RENDERING
    // ==========================================================================

    function drawCanvas() {
        if (!ctx || !canvas) return;

        // Clear canvas
        ctx.fillStyle = '#0A0A0B';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (!currentImage) {
            drawPlaceholder();
            return;
        }

        // Calculate final transform
        // Total scale = baseScale * zoom
        const totalScale = baseScale * scale;

        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        // Draw image
        const scaledWidth = sourceWidth * totalScale;
        const scaledHeight = sourceHeight * totalScale;

        console.log('[Canvas] drawImage:', {
            imgX, imgY, scaledWidth, scaledHeight, totalScale,
            sourceWidth, sourceHeight
        });

        try {
            ctx.drawImage(currentImage, imgX, imgY, scaledWidth, scaledHeight);
        } catch (e) {
            console.error('[Canvas] drawImage failed:', e);
            updateDebugStatus('Render Error: ' + e.message);
        }

        // Draw annotations: masks first (below boxes), then boxes on top
        annotations.forEach(ann => {
            if (ann.mask_polygon && ann.mask_polygon.length > 2) {
                const isSelected = ann.id === selectedAnnotationId;
                const classColor = getClassColor(ann.class_id || 0);
                drawMask(ann.mask_polygon, classColor, isSelected);
            }
        });
        annotations.forEach(ann => {
            const isSelected = ann.id === selectedAnnotationId;
            // Use class-based color (golden angle HSL rotation, matching Python)
            const classColor = getClassColor(ann.class_id || 0);
            const color = isSelected ? '#5FAD56' : classColor; // SAFARI accent green if selected
            const lineWidth = isSelected ? 3 : 2;
            // In mask-edit mode, dim boxes for non-edited annotations
            if (currentTool === 'mask_edit') {
                const dimColor = classColor.replace('hsl(', 'hsla(').replace(')', ', 0.4)');
                drawBox(ann.x, ann.y, ann.width, ann.height, dimColor, 1, false, ann.class_name, dimColor);
            } else {
                drawBox(ann.x, ann.y, ann.width, ann.height, color, lineWidth, isSelected, ann.class_name, classColor);
            }
        });

        // Draw mask vertex handles when in mask-edit mode
        if (currentTool === 'mask_edit' && maskEditAnnId) {
            const editAnn = annotations.find(a => a.id === maskEditAnnId);
            if (editAnn) {
                drawMaskVertices(editAnn);
            }
        }

        // Draw preview box if drawing
        if (isDrawing) {
            // Convert screen coords to normalized to draw consistently using drawBox
            // But we have screen coords, so maybe just draw rect directly?
            // Let's use screen coords for preview to avoid round-trip errors during draw
            ctx.strokeStyle = '#5FAD56'; // SAFARI accent green
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 3]);
            ctx.strokeRect(
                Math.min(drawStartX, drawCurrentX),
                Math.min(drawStartY, drawCurrentY),
                Math.abs(drawCurrentX - drawStartX),
                Math.abs(drawCurrentY - drawStartY)
            );
            ctx.setLineDash([]);
        }

        // Draw loading overlay if active
        if (videoCache.isLoading) {
            drawLoadingOverlay();
        }

        // SEARCH_TAGS: #DEBUG_TELEMETRY #CANVAS_METRICS #ZOOM_DEBUG
        // To enable debug overlay (scale, offsets, img position), uncomment the line below:
        // drawDebugTelemetry();
    }

    /**
     * Draw debug information on canvas.
     * SEARCH_TAGS: #DEBUG_TELEMETRY #CANVAS_METRICS #ZOOM_DEBUG
     */
    function drawDebugTelemetry() {
        if (!ctx || !canvas || !currentImage) return;

        const padding = 15;
        const lineHeight = 16;
        const x = padding;
        const totalLines = 8;
        // Position at top-left below the header (header is ~50-60px)
        let y = 70;

        ctx.save();
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(x - 5, y - 15, 230, lineHeight * totalLines + 10);

        ctx.fillStyle = '#00FF00'; // Matrix green
        ctx.font = '12px monospace';
        ctx.textAlign = 'left';

        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        ctx.fillText(`Scale: ${scale.toFixed(3)} (total: ${totalScale.toFixed(3)})`, x, y); y += lineHeight;
        ctx.fillText(`Offset: ${offsetX.toFixed(1)}, ${offsetY.toFixed(1)}`, x, y); y += lineHeight;
        ctx.fillText(`ImgPos: ${imgX.toFixed(1)}, ${imgY.toFixed(1)}`, x, y); y += lineHeight;
        ctx.fillText(`BaseOff: ${baseOffsetX.toFixed(1)}, ${baseOffsetY.toFixed(1)}`, x, y); y += lineHeight;
        ctx.fillText(`Canvas: ${canvas.width}x${canvas.height}`, x, y); y += lineHeight;
        ctx.fillText(`BaseScale: ${baseScale.toFixed(4)}`, x, y); y += lineHeight;
        ctx.fillText(`Source: ${sourceWidth}x${sourceHeight}`, x, y); y += lineHeight;
        ctx.fillText(`Tool: ${currentTool}`, x, y);

        ctx.restore();
    }

    // Helper to draw a box from normalized 0-1 coordinates
    function drawBox(nx, ny, nw, nh, color, lineWidth, isSelected, className, classColor) {
        // Convert normalized -> image pixels -> screen pixels
        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        const screenX = imgX + nx * sourceWidth * totalScale;
        const screenY = imgY + ny * sourceHeight * totalScale;
        const screenW = nw * sourceWidth * totalScale;
        const screenH = nh * sourceHeight * totalScale;


        ctx.strokeStyle = color;
        ctx.lineWidth = lineWidth;
        ctx.strokeRect(screenX, screenY, screenW, screenH);

        // Fill with semi-transparent class color (NOT the selection color)
        // Use HSLA since classColor is HSL format
        const fillColor = classColor || color;
        // Parse HSL and add alpha, or handle hex colors
        if (fillColor.startsWith('hsl(')) {
            // Convert hsl(...) to hsla(..., alpha)
            const alpha = isSelected ? 0.25 : 0.12;
            ctx.fillStyle = fillColor.replace('hsl(', 'hsla(').replace(')', `, ${alpha})`);
        } else if (fillColor.startsWith('#')) {
            // Hex color - append alpha
            ctx.fillStyle = fillColor + (isSelected ? '40' : '20');
        } else {
            ctx.fillStyle = fillColor;
        }
        ctx.fillRect(screenX, screenY, screenW, screenH);

        // Draw class label above box (YOLO-style) - always use class color
        if (className) {
            const labelColor = classColor || color;
            const labelText = className;
            ctx.font = 'bold 12px Inter, system-ui, sans-serif';
            const textMetrics = ctx.measureText(labelText);
            const labelPadding = 4;
            const labelHeight = 18;
            const labelWidth = textMetrics.width + labelPadding * 2;

            // Label background (positioned above box)
            const labelX = screenX;
            const labelY = screenY - labelHeight;

            ctx.fillStyle = labelColor;
            ctx.fillRect(labelX, labelY, labelWidth, labelHeight);

            // Label text (white on colored background)
            ctx.fillStyle = '#FFFFFF';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            ctx.fillText(labelText, labelX + labelPadding, labelY + labelHeight / 2);

            // Reset textAlign for other drawing
            ctx.textAlign = 'start';
        }

        // Draw corner handles if selected
        if (isSelected) {
            const handleSize = 8;
            ctx.fillStyle = color;
            // Corner handles: top-left, top-right, bottom-left, bottom-right
            const corners = [
                [screenX, screenY],
                [screenX + screenW, screenY],
                [screenX, screenY + screenH],
                [screenX + screenW, screenY + screenH]
            ];
            corners.forEach(([cx, cy]) => {
                ctx.fillRect(cx - handleSize / 2, cy - handleSize / 2, handleSize, handleSize);
            });
        }
    }

    /**
     * Draw a mask polygon from normalized 0-1 coordinates.
     * Renders as a semi-transparent filled polygon using the class color.
     * @param {Array} polygon - List of [x, y] normalized points
     * @param {string} classColor - HSL color string for the class
     * @param {boolean} isSelected - Whether the annotation is selected
     */
    function drawMask(polygon, classColor, isSelected) {
        if (!currentImage || !polygon || polygon.length < 3) return;

        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        ctx.save();
        ctx.beginPath();

        // First point
        const sx0 = imgX + polygon[0][0] * sourceWidth * totalScale;
        const sy0 = imgY + polygon[0][1] * sourceHeight * totalScale;
        ctx.moveTo(sx0, sy0);

        // Remaining points
        for (let i = 1; i < polygon.length; i++) {
            const sx = imgX + polygon[i][0] * sourceWidth * totalScale;
            const sy = imgY + polygon[i][1] * sourceHeight * totalScale;
            ctx.lineTo(sx, sy);
        }

        ctx.closePath();

        // Fill with semi-transparent class color
        const alpha = isSelected ? 0.40 : 0.30;
        if (classColor.startsWith('hsl(')) {
            ctx.fillStyle = classColor.replace('hsl(', 'hsla(').replace(')', `, ${alpha})`);
        } else {
            ctx.fillStyle = classColor + (isSelected ? '66' : '4D');
        }
        ctx.fill();

        // Draw outline
        ctx.strokeStyle = classColor;
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.stroke();

        ctx.restore();
    }

    // ==========================================================================
    // MASK-EDIT HELPERS
    // ==========================================================================

    /**
     * Convert normalized polygon coordinates to screen coordinates.
     * @param {Array} polygon - List of [x, y] normalized points
     * @returns {Array} List of [screenX, screenY]
     */
    function polygonToScreen(polygon) {
        if (!currentImage || !polygon) return [];
        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        return polygon.map(pt => [
            imgX + pt[0] * sourceWidth * totalScale,
            imgY + pt[1] * sourceHeight * totalScale,
        ]);
    }

    /**
     * Convert screen coordinates to normalized image coordinates.
     */
    function screenToNormalized(sx, sy) {
        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);
        return [
            (sx - imgX) / (sourceWidth * totalScale),
            (sy - imgY) / (sourceHeight * totalScale),
        ];
    }

    /**
     * Point-in-polygon test using ray-casting algorithm.
     * @param {number} px - Point X (screen)
     * @param {number} py - Point Y (screen)
     * @param {Array} screenPoly - List of [screenX, screenY] polygon vertices
     * @returns {boolean}
     */
    function pointInPolygon(px, py, screenPoly) {
        let inside = false;
        for (let i = 0, j = screenPoly.length - 1; i < screenPoly.length; j = i++) {
            const xi = screenPoly[i][0], yi = screenPoly[i][1];
            const xj = screenPoly[j][0], yj = screenPoly[j][1];
            const intersect = ((yi > py) !== (yj > py)) &&
                (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    /**
     * Hit test: find which annotation's mask polygon contains the screen point.
     * Returns annotation ID or null.
     */
    function hitTestMasks(screenX, screenY) {
        if (!currentImage) return null;
        for (let i = annotations.length - 1; i >= 0; i--) {
            const ann = annotations[i];
            if (!ann.mask_polygon || ann.mask_polygon.length < 3) continue;
            const sp = polygonToScreen(ann.mask_polygon);
            if (pointInPolygon(screenX, screenY, sp)) {
                return ann.id;
            }
        }
        return null;
    }

    /**
     * Hit test: find which vertex of the mask-edit annotation is at (sx, sy).
     * Returns vertex index or -1.
     */
    function hitTestMaskVertices(sx, sy) {
        if (!maskEditAnnId) return -1;
        const ann = annotations.find(a => a.id === maskEditAnnId);
        if (!ann || !ann.mask_polygon) return -1;

        const sp = polygonToScreen(ann.mask_polygon);
        for (let i = 0; i < sp.length; i++) {
            const dx = sx - sp[i][0];
            const dy = sy - sp[i][1];
            if (dx * dx + dy * dy <= VERTEX_HIT_RADIUS * VERTEX_HIT_RADIUS) {
                return i;
            }
        }
        return -1;
    }

    /**
     * Hit test: find if click is on an edge of the mask-edit polygon.
     * Returns { index: insertionIndex } or null.
     * insertionIndex is the index where a new vertex should be inserted.
     */
    function hitTestMaskEdge(sx, sy) {
        if (!maskEditAnnId) return null;
        const ann = annotations.find(a => a.id === maskEditAnnId);
        if (!ann || !ann.mask_polygon || ann.mask_polygon.length < 3) return null;

        const sp = polygonToScreen(ann.mask_polygon);
        for (let i = 0; i < sp.length; i++) {
            const j = (i + 1) % sp.length;
            const dist = pointToSegmentDistance(sx, sy, sp[i][0], sp[i][1], sp[j][0], sp[j][1]);
            if (dist <= EDGE_HIT_TOLERANCE) {
                return { index: j }; // Insert after vertex i (= at position j)
            }
        }
        return null;
    }

    /**
     * Distance from point (px, py) to line segment (x1,y1)-(x2,y2).
     */
    function pointToSegmentDistance(px, py, x1, y1, x2, y2) {
        const dx = x2 - x1;
        const dy = y2 - y1;
        const lenSq = dx * dx + dy * dy;
        if (lenSq === 0) return Math.hypot(px - x1, py - y1);
        let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
        t = Math.max(0, Math.min(1, t));
        const projX = x1 + t * dx;
        const projY = y1 + t * dy;
        return Math.hypot(px - projX, py - projY);
    }

    /**
     * Draw vertex handles for the mask-edit annotation.
     * Only shows vertices within VERTEX_PROXIMITY_PX of the current mouse position.
     */
    function drawMaskVertices(ann) {
        if (!ann || !ann.mask_polygon || ann.mask_polygon.length < 3) return;

        const sp = polygonToScreen(ann.mask_polygon);

        ctx.save();
        for (let i = 0; i < sp.length; i++) {
            const vx = sp[i][0];
            const vy = sp[i][1];

            // Only show handles near the cursor
            const dist = Math.hypot(vx - maskMouseX, vy - maskMouseY);
            if (dist > VERTEX_PROXIMITY_PX) continue;

            // Fade based on distance (closer = more opaque)
            const alpha = Math.max(0.3, 1 - (dist / VERTEX_PROXIMITY_PX));

            ctx.beginPath();
            ctx.arc(vx, vy, VERTEX_HANDLE_RADIUS, 0, Math.PI * 2);

            if (i === hoveredVertexIdx) {
                // Highlighted hovered vertex
                ctx.fillStyle = `rgba(245, 158, 11, ${alpha})`; // Amber
                ctx.strokeStyle = '#FFFFFF';
                ctx.lineWidth = 2;
            } else {
                // Normal vertex
                ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.9})`;
                ctx.strokeStyle = `rgba(0, 0, 0, ${alpha * 0.6})`;
                ctx.lineWidth = 1.5;
            }
            ctx.fill();
            ctx.stroke();
        }
        ctx.restore();
    }

    /**
     * Exit mask-edit mode. Resets all mask-edit state.
     */
    function exitMaskEditMode() {
        if (maskEditAnnId) {
            console.log('[Canvas] Exiting mask-edit mode for:', maskEditAnnId);
        }
        maskEditAnnId = null;
        isDraggingVertex = false;
        dragVertexIdx = -1;
        hoveredVertexIdx = -1;
        drawCanvas();
    }

    // ==========================================================================
    // ZOOM HANDLING
    // ==========================================================================

    function handleWheel(e) {
        e.preventDefault();
        if (!currentImage) return;

        // Calculate zoom change (scroll up = zoom in)
        const delta = -e.deltaY * WHEEL_ZOOM_FACTOR;
        const oldScale = scale;
        const newScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, scale + delta * scale));

        if (newScale === oldScale) return;

        // Get mouse position relative to canvas
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Calculate zoom toward cursor
        const scaleRatio = newScale / oldScale;

        // Adjust offsets to compensate for the "Zoom from center" bias in drawCanvas
        // imgX = CW/2 + scale * (baseOffsetX - CW/2) + offsetX
        // The effective point being scaled is shifted by CW/2
        const biasX = canvas.width / 2;
        const biasY = canvas.height / 2;

        offsetX = (mouseX - biasX) - scaleRatio * (mouseX - biasX - offsetX);
        offsetY = (mouseY - biasY) - scaleRatio * (mouseY - biasY - offsetY);

        scale = newScale;
        drawCanvas();
        syncZoomToReflex();
    }

    // Exposed for Python zoom buttons
    window.adjustZoom = function (delta) {
        if (!currentImage) return;

        const oldScale = scale;
        const newScale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, scale + delta));

        if (newScale === oldScale) return;

        // Zoom toward center of canvas
        const scaleRatio = newScale / oldScale;

        // Just scale the current offset to maintain the same relative focus point
        // when using the center-balanced drawCanvas formula.
        offsetX *= scaleRatio;
        offsetY *= scaleRatio;

        scale = newScale;
        drawCanvas();
        syncZoomToReflex();
    };

    /**
     * Animate scale and offset changes smoothly (used for Focus Mode and Reset)
     * @param {number} targetScale - Target scale value
     * @param {number} targetX - Target offsetX
     * @param {number} targetY - Target offsetY
     * @param {number} duration - Animation duration in ms
     */
    let animationId = null;
    window.animateTransform = function (targetScale, targetX = 0, targetY = 0, duration = 300) {
        if (!currentImage) {
            scale = targetScale;
            offsetX = targetX;
            offsetY = targetY;
            return;
        }

        if (animationId) cancelAnimationFrame(animationId);

        const startScale = scale;
        const startX = offsetX;
        const startY = offsetY;
        const startTime = performance.now();

        function animate(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // easeInOutQuad
            const eased = progress < 0.5
                ? 2 * progress * progress
                : 1 - Math.pow(-2 * progress + 2, 2) / 2;

            scale = startScale + (targetScale - startScale) * eased;
            offsetX = startX + (targetX - startX) * eased;
            offsetY = startY + (targetY - startY) * eased;

            drawCanvas();
            syncZoomToReflex();

            if (progress < 1) {
                animationId = requestAnimationFrame(animate);
            } else {
                animationId = null;
            }
        }
        animationId = requestAnimationFrame(animate);
    };

    window.resetView = function (targetScale = 1.0) {
        window.animateTransform(targetScale, 0, 0, 300);
    };

    function syncZoomToReflex() {
        // Update the zoom percentage display directly in DOM for instant feedback
        const zoomPercent = Math.round(scale * 100);
        const el = document.getElementById('zoom-percentage');
        if (el) {
            el.textContent = zoomPercent + '%';
        }
    }

    // ==========================================================================
    // PANNING & DRAWING (Shift+Drag)
    // ==========================================================================

    function handleMouseDown(e) {
        if (!currentImage) return;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Shift+drag or middle mouse button for panning
        if (e.shiftKey || e.button === 1) {
            isPanning = true;
            panStartX = e.clientX;
            panStartY = e.clientY;
            panOffsetStartX = offsetX;
            panOffsetStartY = offsetY;
            canvas.style.cursor = 'grabbing';
            e.preventDefault();
            return;
        }

        // Select tool: check handles first, then box interior, then pan
        if (currentTool === 'select') {
            // 1. Check if clicking on a handle of the selected annotation
            const handleIdx = hitTestHandles(mouseX, mouseY);
            if (handleIdx !== -1) {
                // Start resize operation
                const ann = annotations.find(a => a.id === selectedAnnotationId);
                if (ann) {
                    isDraggingHandle = true;
                    dragHandleIndex = handleIdx;
                    dragAnnotationId = selectedAnnotationId;
                    dragStartAnnotation = { ...ann };
                    dragStartMouseX = mouseX;
                    dragStartMouseY = mouseY;
                    canvas.style.cursor = getResizeCursor(handleIdx);
                    e.preventDefault();
                    return;
                }
            }

            // 2. Check if clicking inside any annotation
            const hitId = hitTestAnnotations(mouseX, mouseY);
            if (hitId) {
                if (hitId === selectedAnnotationId) {
                    // Already selected - start move operation
                    const ann = annotations.find(a => a.id === hitId);
                    if (ann) {
                        isDraggingBox = true;
                        dragAnnotationId = hitId;
                        dragStartAnnotation = { ...ann };
                        dragStartMouseX = mouseX;
                        dragStartMouseY = mouseY;
                        canvas.style.cursor = 'move';
                        e.preventDefault();
                        return;
                    }
                } else {
                    // Select the annotation
                    selectAnnotation(hitId);
                    e.preventDefault();
                    return;
                }
            }

            // 3. No annotation hit - deselect current and start panning
            if (selectedAnnotationId) {
                deselectAnnotation();
            }
            isPanning = true;
            panStartX = e.clientX;
            panStartY = e.clientY;
            panOffsetStartX = offsetX;
            panOffsetStartY = offsetY;
            canvas.style.cursor = 'grabbing';
            e.preventDefault();
            return;
        }

        if (currentTool === 'draw') {
            // Note: We allow drawing anytime now - Python handles auto-keyframe creation
            isDrawing = true;
            drawStartX = mouseX;
            drawStartY = mouseY;
            drawCurrentX = mouseX;
            drawCurrentY = mouseY;
            e.preventDefault();
        }

        // Mask-edit tool: vertex drag, add vertex on edge, select mask
        if (currentTool === 'mask_edit') {
            // Right-click: remove vertex
            if (e.button === 2) {
                // Handled in contextmenu handler for mask-edit mode
                return;
            }

            // 1. If in mask-edit mode, check vertex hit first
            if (maskEditAnnId) {
                const vertIdx = hitTestMaskVertices(mouseX, mouseY);
                if (vertIdx !== -1) {
                    // Start dragging this vertex
                    isDraggingVertex = true;
                    dragVertexIdx = vertIdx;
                    dragStartMouseX = mouseX;
                    dragStartMouseY = mouseY;
                    canvas.style.cursor = 'grabbing';
                    e.preventDefault();
                    return;
                }

                // 2. Check if clicking on an edge → insert vertex
                const edgeHit = hitTestMaskEdge(mouseX, mouseY);
                if (edgeHit) {
                    const ann = annotations.find(a => a.id === maskEditAnnId);
                    if (ann && ann.mask_polygon) {
                        const newPt = screenToNormalized(mouseX, mouseY);
                        // Clamp to image bounds
                        newPt[0] = Math.max(0, Math.min(1, newPt[0]));
                        newPt[1] = Math.max(0, Math.min(1, newPt[1]));
                        ann.mask_polygon.splice(edgeHit.index, 0, newPt);
                        console.log('[Canvas] Inserted vertex at index:', edgeHit.index);
                        // Start dragging the new vertex immediately
                        isDraggingVertex = true;
                        dragVertexIdx = edgeHit.index;
                        dragStartMouseX = mouseX;
                        dragStartMouseY = mouseY;
                        canvas.style.cursor = 'grabbing';
                        drawCanvas();
                        e.preventDefault();
                        return;
                    }
                }
            }

            // 3. Check if clicking on a mask polygon → select it for editing
            const maskHitId = hitTestMasks(mouseX, mouseY);
            if (maskHitId) {
                if (maskHitId !== maskEditAnnId) {
                    maskEditAnnId = maskHitId;
                    selectedAnnotationId = maskHitId;
                    console.log('[Canvas] Mask-edit selected:', maskHitId);
                    syncSelectionToPython(maskHitId);
                }
                drawCanvas();
                e.preventDefault();
                return;
            }

            // 4. Clicking outside any mask → exit mask-edit mode, start panning
            exitMaskEditMode();
            isPanning = true;
            panStartX = e.clientX;
            panStartY = e.clientY;
            panOffsetStartX = offsetX;
            panOffsetStartY = offsetY;
            canvas.style.cursor = 'grabbing';
            e.preventDefault();
            return;
        }
    }

    function getResizeCursor(handleIndex) {
        // 0=TL, 1=TR, 2=BL, 3=BR
        switch (handleIndex) {
            case 0: return 'nwse-resize'; // TL
            case 1: return 'nesw-resize'; // TR
            case 2: return 'nesw-resize'; // BL
            case 3: return 'nwse-resize'; // BR
            default: return 'default';
        }
    }

    function handleMouseMove(e) {
        if (!currentImage) return;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        if (isPanning) {
            const dx = e.clientX - panStartX;
            const dy = e.clientY - panStartY;
            offsetX = panOffsetStartX + dx;
            offsetY = panOffsetStartY + dy;
            drawCanvas();
            return;
        }

        if (isDrawing) {
            drawCurrentX = mouseX;
            drawCurrentY = mouseY;
            drawCanvas(); // Redraw for preview
            return;
        }

        // Handle resize drag
        if (isDraggingHandle && dragStartAnnotation) {
            const ann = annotations.find(a => a.id === dragAnnotationId);
            if (ann) {
                const delta = screenDeltaToNormalized(
                    mouseX - dragStartMouseX,
                    mouseY - dragStartMouseY
                );

                // Calculate new bounds based on which handle is being dragged
                let newX = dragStartAnnotation.x;
                let newY = dragStartAnnotation.y;
                let newW = dragStartAnnotation.width;
                let newH = dragStartAnnotation.height;

                switch (dragHandleIndex) {
                    case 0: // Top-left: move origin, adjust size inversely
                        newX = dragStartAnnotation.x + delta.dx;
                        newY = dragStartAnnotation.y + delta.dy;
                        newW = dragStartAnnotation.width - delta.dx;
                        newH = dragStartAnnotation.height - delta.dy;
                        break;
                    case 1: // Top-right: Y moves, width grows
                        newY = dragStartAnnotation.y + delta.dy;
                        newW = dragStartAnnotation.width + delta.dx;
                        newH = dragStartAnnotation.height - delta.dy;
                        break;
                    case 2: // Bottom-left: X moves, height grows
                        newX = dragStartAnnotation.x + delta.dx;
                        newW = dragStartAnnotation.width - delta.dx;
                        newH = dragStartAnnotation.height + delta.dy;
                        break;
                    case 3: // Bottom-right: just grow both dimensions
                        newW = dragStartAnnotation.width + delta.dx;
                        newH = dragStartAnnotation.height + delta.dy;
                        break;
                }

                // Ensure minimum size
                const minSize = 0.01; // 1% of image
                if (newW < minSize) {
                    if (dragHandleIndex === 0 || dragHandleIndex === 2) {
                        newX = dragStartAnnotation.x + dragStartAnnotation.width - minSize;
                    }
                    newW = minSize;
                }
                if (newH < minSize) {
                    if (dragHandleIndex === 0 || dragHandleIndex === 1) {
                        newY = dragStartAnnotation.y + dragStartAnnotation.height - minSize;
                    }
                    newH = minSize;
                }

                // Clamp to image bounds
                const clamped = clampAnnotation(newX, newY, newW, newH);
                ann.x = clamped.x;
                ann.y = clamped.y;
                ann.width = clamped.width;
                ann.height = clamped.height;

                drawCanvas();
            }
            return;
        }

        // Handle move drag
        if (isDraggingBox && dragStartAnnotation) {
            const ann = annotations.find(a => a.id === dragAnnotationId);
            if (ann) {
                const delta = screenDeltaToNormalized(
                    mouseX - dragStartMouseX,
                    mouseY - dragStartMouseY
                );

                let newX = dragStartAnnotation.x + delta.dx;
                let newY = dragStartAnnotation.y + delta.dy;

                // Clamp to keep box fully within image
                const clamped = clampAnnotation(newX, newY, ann.width, ann.height);
                ann.x = clamped.x;
                ann.y = clamped.y;

                drawCanvas();
            }
            return;
        }

        // Handle mask vertex drag
        if (isDraggingVertex && maskEditAnnId) {
            const ann = annotations.find(a => a.id === maskEditAnnId);
            if (ann && ann.mask_polygon && dragVertexIdx >= 0 && dragVertexIdx < ann.mask_polygon.length) {
                const pt = screenToNormalized(mouseX, mouseY);
                // Clamp to image bounds [0, 1]
                ann.mask_polygon[dragVertexIdx] = [
                    Math.max(0, Math.min(1, pt[0])),
                    Math.max(0, Math.min(1, pt[1])),
                ];
                drawCanvas();
            }
            return;
        }

        // Mask-edit mode: track mouse for proximity handles and hover
        if (currentTool === 'mask_edit') {
            maskMouseX = mouseX;
            maskMouseY = mouseY;
            const prevHovered = hoveredVertexIdx;
            hoveredVertexIdx = hitTestMaskVertices(mouseX, mouseY);
            if (hoveredVertexIdx !== -1) {
                canvas.style.cursor = 'grab';
            } else if (maskEditAnnId && hitTestMaskEdge(mouseX, mouseY)) {
                canvas.style.cursor = 'cell'; // Indicates add-point
            } else if (hitTestMasks(mouseX, mouseY)) {
                canvas.style.cursor = 'pointer';
            } else {
                canvas.style.cursor = 'default';
            }
            // Redraw to update proximity-based vertex visibility
            if (prevHovered !== hoveredVertexIdx || maskEditAnnId) {
                drawCanvas();
            }
            return;
        }

        // Update cursor based on tool, shift key, and handle hover
        if (e.shiftKey) {
            canvas.style.cursor = 'grab';
        } else if (currentTool === 'draw') {
            canvas.style.cursor = 'crosshair';
        } else if (currentTool === 'select') {
            // Check if hovering over a handle
            const handleIdx = hitTestHandles(mouseX, mouseY);
            if (handleIdx !== -1) {
                canvas.style.cursor = getResizeCursor(handleIdx);
            } else if (selectedAnnotationId && hitTestAnnotations(mouseX, mouseY) === selectedAnnotationId) {
                canvas.style.cursor = 'move';
            } else {
                canvas.style.cursor = 'default';
            }
        } else {
            canvas.style.cursor = 'default';
        }
    }

    /**
     * Convert screen pixel delta to normalized image delta.
     */
    function screenDeltaToNormalized(dx, dy) {
        const totalScale = baseScale * scale;
        return {
            dx: dx / (sourceWidth * totalScale),
            dy: dy / (sourceHeight * totalScale)
        };
    }

    /**
     * Clamp annotation bounds to [0, 1] range.
     */
    function clampAnnotation(x, y, w, h) {
        // Clamp position
        let newX = Math.max(0, Math.min(1 - w, x));
        let newY = Math.max(0, Math.min(1 - h, y));

        // Clamp size (in case width/height extend beyond)
        let newW = Math.min(w, 1 - newX);
        let newH = Math.min(h, 1 - newY);

        return { x: newX, y: newY, width: newW, height: newH };
    }

    function handleMouseUp(e) {
        if (isPanning) {
            isPanning = false;
            canvas.style.cursor = e.shiftKey ? 'grab' : 'default';
            return;
        }

        // Finalize resize drag
        if (isDraggingHandle) {
            isDraggingHandle = false;
            dragHandleIndex = -1;
            canvas.style.cursor = 'default';

            // Sync final state to Python
            const ann = annotations.find(a => a.id === dragAnnotationId);
            if (ann) {
                saveUpdatedAnnotationToPython(ann);
            }

            dragAnnotationId = null;
            dragStartAnnotation = null;
            return;
        }

        // Finalize move drag
        if (isDraggingBox) {
            isDraggingBox = false;
            canvas.style.cursor = 'default';

            // Sync final state to Python
            const ann = annotations.find(a => a.id === dragAnnotationId);
            if (ann) {
                saveUpdatedAnnotationToPython(ann);
            }

            dragAnnotationId = null;
            dragStartAnnotation = null;
            return;
        }

        // Finalize mask vertex drag
        if (isDraggingVertex) {
            isDraggingVertex = false;
            dragVertexIdx = -1;
            canvas.style.cursor = 'default';

            // Sync updated mask polygon to Python
            const ann = annotations.find(a => a.id === maskEditAnnId);
            if (ann) {
                saveUpdatedAnnotationToPython(ann);
                console.log('[Canvas] Mask vertex drag finalized for:', maskEditAnnId);
            }
            return;
        }

        if (isDrawing) {
            isDrawing = false;
            drawCurrentX = e.clientX - canvas.getBoundingClientRect().left;
            drawCurrentY = e.clientY - canvas.getBoundingClientRect().top;

            // Finalize box
            // Convert screen bounds to normalized image coords
            const totalScale = baseScale * scale;
            const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
            const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

            const xMin = Math.min(drawStartX, drawCurrentX);
            const yMin = Math.min(drawStartY, drawCurrentY);
            const width = Math.abs(drawCurrentX - drawStartX);
            const height = Math.abs(drawCurrentY - drawStartY);

            // Check for minimum size (ignore tiny clicks)
            if (width < 5 || height < 5) {
                drawCanvas();
                return;
            }

            const normalizedX = (xMin - imgX) / (sourceWidth * totalScale);
            const normalizedY = (yMin - imgY) / (sourceHeight * totalScale);
            const normalizedW = width / (sourceWidth * totalScale);
            const normalizedH = height / (sourceHeight * totalScale);

            const newAnnotation = {
                x: normalizedX,
                y: normalizedY,
                width: normalizedW,
                height: normalizedH
            };

            saveAnnotationToPython(newAnnotation);

            // Optimistically add to local list for instant feedback
            // Include class info so the label tag renders immediately
            const optimisticAnnotation = {
                id: 'temp_' + Date.now(),  // Temporary ID, will be replaced by Python
                x: normalizedX,
                y: normalizedY,
                width: normalizedW,
                height: normalizedH,
                class_id: currentClassId,
                class_name: currentClassName
            };
            annotations.push(optimisticAnnotation);

            drawCanvas();
        }
    }

    function saveAnnotationToPython(data) {
        const input = document.getElementById('new-annotation-data');
        if (input) {
            // React overrides the value setter, so we need to call the native one
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, JSON.stringify(data));

            // Dispatch event to trigger Reflex on_change
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Sent new annotation to Python');
        } else {
            console.error('[Canvas] Could not find hidden input to save annotation');
        }
    }

    function saveUpdatedAnnotationToPython(annotation) {
        const input = document.getElementById('updated-annotation-data');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, JSON.stringify(annotation));

            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Sent updated annotation to Python:', annotation.id);
        } else {
            console.error('[Canvas] Could not find hidden input to update annotation');
        }
    }

    // ==========================================================================
    // TOOL MANAGEMENT
    // ==========================================================================

    window.setTool = function (tool) {
        // Exit mask-edit mode when switching away from it
        if (currentTool === 'mask_edit' && tool !== 'mask_edit') {
            exitMaskEditMode();
        }
        currentTool = tool;
        if (canvas) {
            if (tool === 'draw') {
                canvas.style.cursor = 'crosshair';
            } else if (tool === 'mask_edit') {
                canvas.style.cursor = 'default';
            } else {
                canvas.style.cursor = 'default';
            }
        }
    };

    // Sync current class from Python for optimistic annotation rendering
    window.setCurrentClass = function (classId, className) {
        currentClassId = classId;
        currentClassName = className || "Unknown";
        console.log('[Canvas] Current class set to:', currentClassId, currentClassName);
    };

    // ==========================================================================
    // SELECTION & DELETION
    // ==========================================================================

    /**
     * Hit test: check if point (screen coords) is inside any annotation.
     * Returns the annotation ID if hit, null otherwise.
     * Tests in reverse order so topmost (last drawn) is selected first.
     */
    function hitTestAnnotations(screenX, screenY) {
        if (!currentImage) return null;

        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        // Iterate in reverse to select topmost first
        for (let i = annotations.length - 1; i >= 0; i--) {
            const ann = annotations[i];
            const boxX = imgX + ann.x * sourceWidth * totalScale;
            const boxY = imgY + ann.y * sourceHeight * totalScale;
            const boxW = ann.width * sourceWidth * totalScale;
            const boxH = ann.height * sourceHeight * totalScale;

            if (screenX >= boxX && screenX <= boxX + boxW &&
                screenY >= boxY && screenY <= boxY + boxH) {
                return ann.id;
            }
        }
        return null;
    }

    /**
     * Hit test: check if point is on a corner handle of the selected annotation.
     * Returns handle index (0-3) or -1 if not on a handle.
     * Handles: 0=TL, 1=TR, 2=BL, 3=BR
     */
    function hitTestHandles(screenX, screenY) {
        if (!currentImage || !selectedAnnotationId) return -1;

        const ann = annotations.find(a => a.id === selectedAnnotationId);
        if (!ann) return -1;

        const totalScale = baseScale * scale;
        const imgX = baseOffsetX * scale + offsetX + (canvas.width * (1 - scale) / 2);
        const imgY = baseOffsetY * scale + offsetY + (canvas.height * (1 - scale) / 2);

        const boxX = imgX + ann.x * sourceWidth * totalScale;
        const boxY = imgY + ann.y * sourceHeight * totalScale;
        const boxW = ann.width * sourceWidth * totalScale;
        const boxH = ann.height * sourceHeight * totalScale;

        const handleSize = 12; // Slightly larger hit area than visual size
        const corners = [
            [boxX, boxY],                     // 0: top-left
            [boxX + boxW, boxY],              // 1: top-right
            [boxX, boxY + boxH],              // 2: bottom-left
            [boxX + boxW, boxY + boxH]        // 3: bottom-right
        ];

        for (let i = 0; i < corners.length; i++) {
            const [cx, cy] = corners[i];
            if (screenX >= cx - handleSize / 2 && screenX <= cx + handleSize / 2 &&
                screenY >= cy - handleSize / 2 && screenY <= cy + handleSize / 2) {
                return i;
            }
        }
        return -1;
    }

    function selectAnnotation(id) {
        selectedAnnotationId = id;
        console.log('[Canvas] Selected annotation:', id);
        drawCanvas();
        // Notify Python of selection
        syncSelectionToPython(id);
    }

    function deselectAnnotation() {
        selectedAnnotationId = null;
        console.log('[Canvas] Deselected annotation');
        drawCanvas();
        syncSelectionToPython(null);
    }

    function syncSelectionToPython(id) {
        const input = document.getElementById('selected-annotation-id');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, id || '');
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function deleteSelectedAnnotation() {
        if (!selectedAnnotationId) return;

        console.log('[Canvas] Deleting annotation:', selectedAnnotationId);
        const idToDelete = selectedAnnotationId;

        // Remove from local array
        annotations = annotations.filter(a => a.id !== idToDelete);
        selectedAnnotationId = null;
        drawCanvas();

        // Notify Python
        const input = document.getElementById('deleted-annotation-id');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, idToDelete);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    // Public API: Select annotation by ID (for sidebar list click)
    window.selectAnnotationById = function (id) {
        if (!id) {
            deselectAnnotation();
            return;
        }
        const ann = annotations.find(a => a.id === id);
        if (ann) {
            selectAnnotation(id);
        } else {
            console.warn('[Canvas] Annotation not found:', id);
        }
    };

    // Public API: Delete selected annotation (for sidebar button)
    window.deleteSelectedAnnotation = function () {
        deleteSelectedAnnotation();
    };

    // Keyboard handler using centralized shortcuts
    function handleKeyDown(e) {
        // Only handle if canvas is focused area (not typing in an input)
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const key = e.key.toLowerCase();
        const shortcuts = window.LABELING_SHORTCUTS || {};

        // Delete annotation
        if (shortcuts.DELETE_ANNOTATION && shortcuts.DELETE_ANNOTATION.includes(e.key)) {
            if (selectedAnnotationId) {
                e.preventDefault();
                deleteSelectedAnnotation();
            }
            return;
        }

        // Deselect / exit mask-edit mode
        if (e.key === shortcuts.DESELECT) {
            if (currentTool === 'mask_edit' && maskEditAnnId) {
                exitMaskEditMode();
                return;
            }
            deselectAnnotation();
            return;
        }

        // Navigation: Next image (D)
        if (key === shortcuts.NEXT_IMAGE) {
            e.preventDefault();
            triggerNavigateNext();
            return;
        }

        // Navigation: Previous image (A)
        if (key === shortcuts.PREV_IMAGE) {
            e.preventDefault();
            triggerNavigatePrev();
            return;
        }

        // =====================================================================
        // VIDEO MODE SHORTCUTS (only when isVideoMode is true)
        // =====================================================================

        if (isVideoMode) {
            // Space: Play/Pause - click the button
            if (e.key === shortcuts.VIDEO_PLAY_PAUSE || e.key === ' ') {
                e.preventDefault();
                document.getElementById('btn-play-pause')?.click();
                return;
            }

            // Z: Previous frame (Shift for 10 frames) - click the button
            if (key === shortcuts.VIDEO_PREV_FRAME || key === 'z') {
                e.preventDefault();
                if (e.shiftKey) {
                    document.getElementById('btn-step-back-10')?.click();
                } else {
                    document.getElementById('btn-step-back-1')?.click();
                }
                return;
            }

            // C: Next frame (Shift for 10 frames) - click the button
            if (key === shortcuts.VIDEO_NEXT_FRAME || key === 'c') {
                e.preventDefault();
                if (e.shiftKey) {
                    document.getElementById('btn-step-fwd-10')?.click();
                } else {
                    document.getElementById('btn-step-fwd-1')?.click();
                }
                return;
            }

            // K: Mark keyframe
            if (key === shortcuts.VIDEO_MARK_KEYFRAME || key === 'k') {
                e.preventDefault();
                triggerMarkKeyframe();
                return;
            }

            // I: Set interval start
            if (key === 'i') {
                e.preventDefault();
                triggerIntervalStart();
                return;
            }

            // O: Set interval end
            if (key === 'o') {
                e.preventDefault();
                triggerIntervalEnd();
                return;
            }

            // P: Create interval keyframes
            if (key === 'p') {
                e.preventDefault();
                triggerIntervalCreate();
                return;
            }

            // Q: Previous keyframe
            if (key === 'q') {
                e.preventDefault();
                triggerPrevKeyframe();
                return;
            }

            // E: Next keyframe (conflicts with existing E shortcut, but video mode takes priority)
            if (key === 'e') {
                e.preventDefault();
                triggerNextKeyframe();
                return;
            }
        }

        // Tool shortcuts
        if (key === shortcuts.TOOL_SELECT) {
            e.preventDefault();
            window.setTool && window.setTool('select');
            syncToolToPython('select');
            return;
        }

        if (key === shortcuts.TOOL_DRAW) {
            e.preventDefault();
            window.setTool && window.setTool('draw');
            syncToolToPython('draw');
            return;
        }

        // Mask-edit tool: C key (only in image mode, not video mode where C = next frame)
        if (key === shortcuts.TOOL_MASK_EDIT && !isVideoMode) {
            e.preventDefault();
            window.setTool && window.setTool('mask_edit');
            syncToolToPython('mask_edit');
            return;
        }

        // Class selection (1-9)
        if (shortcuts.CLASS_SELECT && shortcuts.CLASS_SELECT.includes(e.key)) {
            e.preventDefault();
            const classIndex = parseInt(e.key) - 1; // 1 -> 0, 9 -> 8
            triggerClassSelect(classIndex);
            return;
        }

        // Help overlay (?)
        if (e.key === shortcuts.HELP || (e.shiftKey && e.key === '/')) {
            e.preventDefault();
            triggerHelpToggle();
            return;
        }

        // Dashboard shortcut (H for Hub/Home)
        if (key === 'h') {
            e.preventDefault();
            window.location.href = '/dashboard';
            return;
        }

        // Focus Mode toggle (M key)
        if (key === 'm') {
            e.preventDefault();
            triggerFocusMode();
            return;
        }

        // Fullscreen toggle (F key)
        if (key === 'f') {
            e.preventDefault();
            triggerFullscreen();
            return;
        }
    }

    // Focus mode trigger function
    function triggerFocusMode() {
        const input = document.getElementById('focus-mode-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered focus mode toggle');
        }
    }

    // Fullscreen trigger function
    function triggerFullscreen() {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(err => {
                console.error(`[Fullscreen] Error: ${err.message}`);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }

        // Manual sync just in case, though fullscreenchange event should handle it
        setTimeout(syncFullscreenState, 100);
    }

    // Expose for UI buttons to trigger directly (crucial for Chrome user activation)
    window.toggleFullscreen = triggerFullscreen;

    // Fullscreen state sync - notify Python when fullscreen changes (e.g., Escape key exits)
    function syncFullscreenState() {
        const input = document.getElementById('fullscreen-state-sync');
        if (input) {
            const isFullscreen = !!document.fullscreenElement;
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, isFullscreen ? 'true' : 'false');
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Synced fullscreen state:', isFullscreen);
        }
    }

    // Listen for fullscreen changes (covers Escape key exit)
    document.addEventListener('fullscreenchange', syncFullscreenState);

    function triggerNavigateNext() {
        const input = document.getElementById('navigate-next-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString()); // Unique value to trigger change
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered next image navigation');
        }
    }

    function triggerNavigatePrev() {
        const input = document.getElementById('navigate-prev-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered prev image navigation');
        }
    }

    function syncToolToPython(tool) {
        const input = document.getElementById('tool-change-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, tool);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function triggerClassSelect(index) {
        const input = document.getElementById('class-select-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, index.toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered class select:', index);
        }
    }

    function triggerHelpToggle() {
        const input = document.getElementById('help-toggle-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Canvas] Triggered help toggle');
        }
    }

    // Video trigger functions (for keyboard shortcuts)
    function triggerVideoPlayPause() {
        // Toggle local playback state and notify Python
        if (sourceVideo) {
            const shouldPlay = sourceVideo.paused;
            window.toggleVideoPlayback(shouldPlay);
        }
        console.log('[Video] Triggered play/pause via keyboard');
    }

    function triggerVideoFrameStep(delta) {
        // Step video by delta frames - Python will handle the state update
        if (sourceVideo && videoFps) {
            const currentFrame = Math.floor(sourceVideo.currentTime * videoFps);
            const newFrame = Math.max(0, currentFrame + delta);
            window.seekToFrame(newFrame, videoFps);
            console.log('[Video] Stepped', delta, 'frames to', newFrame);
        }
    }

    function triggerMarkKeyframe() {
        // Trigger Python to mark the current frame as a keyframe
        // This will be handled by the Python state, which calls back to JS captureKeyframe
        const input = document.getElementById('keyframe-mark-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, JSON.stringify({
                timestamp: Date.now()
            }));
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered keyframe mark');
        } else {
            console.warn('[Video] No keyframe-mark-trigger input found');
        }
    }

    function triggerIntervalStart() {
        // Trigger Python to set interval start frame
        const input = document.getElementById('interval-start-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered interval start');
        } else {
            console.warn('[Video] No interval-start-trigger input found');
        }
    }

    function triggerIntervalEnd() {
        // Trigger Python to set interval end frame
        const input = document.getElementById('interval-end-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered interval end');
        } else {
            console.warn('[Video] No interval-end-trigger input found');
        }
    }

    function triggerIntervalCreate() {
        // Trigger Python to create interval keyframes
        const input = document.getElementById('interval-create-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered interval create');
        } else {
            console.warn('[Video] No interval-create-trigger input found');
        }
    }

    function triggerPrevKeyframe() {
        // Trigger Python to navigate to previous keyframe
        const input = document.getElementById('prev-keyframe-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered previous keyframe');
        } else {
            console.warn('[Video] No prev-keyframe-trigger input found');
        }
    }

    function triggerNextKeyframe() {
        // Trigger Python to navigate to next keyframe
        const input = document.getElementById('next-keyframe-trigger');
        if (input) {
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, Date.now().toString());
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered next keyframe');
        } else {
            console.warn('[Video] No next-keyframe-trigger input found');
        }
    }

    // Public API for Python
    window.deleteSelectedAnnotation = deleteSelectedAnnotation;
    window.selectAnnotation = selectAnnotation;
    window.deselectAnnotation = deselectAnnotation;

    // ==========================================================================
    // VIDEO MODE FUNCTIONS
    // ==========================================================================

    let sourceVideo = null;
    let videoFps = 30;
    let isVideoMode = false;
    let videoAnimationFrame = null;
    let hasSelectedKeyframe = false; // Track if keyframe is selected for drawing block
    let videoFrameBuffer = null;     // Persistent offscreen canvas for frame persistence during seeks

    // ── JS-SIDE ANNOTATION CACHE (Phase 1 perf optimization) ──
    // Keyed by frame_number (int) → annotation array.
    // Pushed from Python on video switch / annotation save.
    // Eliminates ~56/60 WS messages/sec during playback.
    let videoAnnotationCache = {};   // frame_number -> annotations[]
    let _lastPythonSyncTime = 0;     // Timestamp of last frame sync to Python
    const PYTHON_SYNC_INTERVAL = 250; // ms — sync frame counter to Python at ~4fps

    /**
     * Set the JS-side annotation cache for the current video.
     * Called from Python after loading keyframes & annotations.
     * @param {Object} cacheData - {frame_number: [annotations...], ...}
     */
    window.setVideoAnnotationCache = function (cacheData) {
        videoAnnotationCache = cacheData || {};
        const count = Object.keys(videoAnnotationCache).length;
        console.log('[PerfOpt] JS annotation cache set:', count, 'keyframes');
    };

    /**
     * Update a single frame's annotations in the JS cache.
     * Called from Python after an annotation is added/modified/deleted.
     * @param {number} frameNumber - The keyframe's frame number
     * @param {Array} anns - The updated annotations array
     */
    window.updateVideoAnnotationCacheFrame = function (frameNumber, anns) {
        videoAnnotationCache[frameNumber] = anns || [];
        console.log('[PerfOpt] JS cache updated for frame', frameNumber, ':', (anns || []).length, 'annotations');
    };

    /**
     * Clear the JS-side annotation cache.
     */
    window.clearVideoAnnotationCache = function () {
        videoAnnotationCache = {};
        console.log('[PerfOpt] JS annotation cache cleared');
    };

    // Video cache for preloading adjacent videos
    const videoCache = {
        elements: new Map(),  // video_id -> {video: VideoElement, url: string, ready: bool}
        maxSize: 6,           // Default, adjusted dynamically based on resolution
        currentVideoId: null,
        thumbnailImage: null, // Current thumbnail being displayed
        isLoading: false,

        preload(videoId, url) {
            if (this.elements.has(videoId)) {
                console.log('[VideoCache] Already cached:', videoId);
                return Promise.resolve();
            }

            console.log('[VideoCache] Preloading:', videoId);

            return new Promise((resolve) => {
                const video = document.createElement('video');
                video.preload = 'auto';
                video.crossOrigin = 'anonymous';
                video.muted = true;
                video.playsinline = true;

                const cacheEntry = { video, url, ready: false };
                this.elements.set(videoId, cacheEntry);

                video.oncanplay = () => {
                    cacheEntry.ready = true;
                    console.log('[VideoCache] Ready:', videoId);
                    resolve();
                };

                video.onerror = (e) => {
                    console.error('[VideoCache] Error loading:', videoId, e);
                    this.elements.delete(videoId);
                    resolve();
                };

                video.src = url;
                video.load();

                this.evictOldest();
            });
        },

        get(videoId) {
            const entry = this.elements.get(videoId);
            if (entry && entry.ready) {
                return entry.video;
            }
            return null;
        },

        has(videoId) {
            return this.elements.has(videoId);
        },

        evictOldest() {
            while (this.elements.size > this.maxSize) {
                const oldestKey = this.elements.keys().next().value;
                if (oldestKey !== this.currentVideoId) {
                    const entry = this.elements.get(oldestKey);
                    if (entry && entry.video) {
                        entry.video.src = '';
                        entry.video.load();
                    }
                    this.elements.delete(oldestKey);
                    console.log('[VideoCache] Evicted:', oldestKey);
                } else {
                    break; // Don't evict current video
                }
            }
        },

        setMaxSize(size) {
            this.maxSize = Math.max(2, Math.min(10, size));
            console.log('[VideoCache] Max size set to:', this.maxSize);
            this.evictOldest();
        },

        clear() {
            for (const [id, entry] of this.elements) {
                if (entry.video) {
                    entry.video.src = '';
                    entry.video.load();
                }
            }
            this.elements.clear();
            console.log('[VideoCache] Cleared');
        }
    };

    // Draw thumbnail placeholder while video loads
    function drawThumbnailPlaceholder(thumbnailUrl) {
        if (!thumbnailUrl || !canvas || !ctx) return;

        videoCache.thumbnailImage = new Image();
        videoCache.thumbnailImage.crossOrigin = 'anonymous';

        videoCache.thumbnailImage.onload = function () {
            console.log('[Video] Thumbnail loaded, drawing placeholder');
            // Use existing drawing pipeline for consistency
            currentImage = videoCache.thumbnailImage;
            sourceWidth = videoCache.thumbnailImage.width;
            sourceHeight = videoCache.thumbnailImage.height;
            calculateFit();
            drawCanvas();
            drawLoadingOverlay();
        };

        videoCache.thumbnailImage.onerror = function () {
            console.warn('[Video] Thumbnail failed to load');
            drawLoadingOverlay();  // Just show loading on blank canvas
        };

        videoCache.thumbnailImage.src = thumbnailUrl;
    }

    // Draw loading overlay on canvas
    function drawLoadingOverlay() {
        if (!canvas || !ctx) {
            console.warn('[Video] Canvas/Ctx not ready for overlay');
            return;
        }

        console.log('[Video] Drawing loading overlay on canvas:', canvas.width, 'x', canvas.height);

        // Semi-transparent overlay
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Loading text
        ctx.fillStyle = 'white';
        ctx.font = '24px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Loading video...', canvas.width / 2, canvas.height / 2);

        ctx.font = '14px sans-serif';
        ctx.fillText('Please wait a moment', canvas.width / 2, canvas.height / 2 + 35);

        videoCache.isLoading = true;
    }

    // Clear loading state
    function clearLoadingOverlay() {
        if (!videoCache.isLoading) return;
        console.log('[Video] Clearing loading overlay');
        videoCache.isLoading = false;
        videoCache.thumbnailImage = null;
        // Re-draw canvas to show video frame clearly
        drawCanvas();
    }

    /**
     * Load a video into the hidden video element and set up video mode.
     * Uses direct URL streaming. For high-bitrate sources (1080p@60fps),
     * a server-side proxy transcode is recommended.
     * @param {string} url - Presigned URL for the video
     * @param {string} videoId - Optional video ID for caching
     * @param {boolean} preserveOverlay - If true, don't clear loading overlay immediately
     */
    window.loadVideo = function (url, videoId = null, preserveOverlay = false) {
        console.log('[Video] loadVideo called');

        if (!sourceVideo) {
            sourceVideo = document.getElementById('source-video');
        }

        if (!sourceVideo) {
            console.error('[Video] No source-video element found!');
            return;
        }

        // OPTIMIZATION: If already loading/loaded the SAME url, just draw and return
        if (sourceVideo.src === url && sourceVideo.readyState >= 2) {
            console.log('[Video] Already loaded this URL, skipping reload');
            isVideoMode = true;
            clearLoadingOverlay();
            triggerVideoLoading('complete');
            drawVideoFrameToCanvas();
            return;
        }

        isVideoMode = true;
        if (!preserveOverlay) {
            clearLoadingOverlay();
        }

        // Check if video is already cached
        if (videoId) {
            videoCache.currentVideoId = videoId;
            const cachedVideo = videoCache.get(videoId);
            if (cachedVideo) {
                console.log('[Video] Using cached video:', videoId);
                videoCache.thumbnailImage = null;

                clearLoadingOverlay();
                triggerVideoLoading('complete');
                drawVideoFrameToCanvas(cachedVideo);

                // Sync source element for playback
                sourceVideo.crossOrigin = 'anonymous';
                sourceVideo.preload = 'auto';
                sourceVideo.src = url;
                sourceVideo.load();
                return;
            }
        }

        // CRITICAL: Set crossOrigin and preload BEFORE setting src
        sourceVideo.crossOrigin = 'anonymous';
        sourceVideo.preload = 'auto';
        sourceVideo.src = url;

        // Trigger loading start
        triggerVideoLoading('start');

        sourceVideo.load();
        console.log('[Video] Video loading started');

        sourceVideo.oncanplay = function () {
            console.log('[Video] oncanplay - video ready');
            clearLoadingOverlay();
            triggerVideoLoading('complete');
            drawVideoFrameToCanvas();
        };

        sourceVideo.onerror = function (e) {
            console.error('[Video] ERROR loading video:', e);
            console.error('[Video] Error details:', sourceVideo.error);
            clearLoadingOverlay();
            triggerVideoLoading('complete');
        };
    };

    /**
     * Load a video with thumbnail placeholder shown while loading
     * @param {string} videoUrl - Presigned URL for the video
     * @param {string} thumbnailUrl - Presigned URL for the thumbnail
     * @param {string} videoId - Video ID for caching
     */
    window.loadVideoWithThumbnail = function (videoUrl, thumbnailUrl, videoId) {
        console.log('[Video] loadVideoWithThumbnail called');
        console.log('[Video] Thumbnail URL:', thumbnailUrl ? thumbnailUrl.substring(0, 60) + '...' : 'null');

        // Check cache first - if cached, skip thumbnail
        if (videoId && videoCache.get(videoId)) {
            console.log('[Video] Video already cached, loading directly');
            window.loadVideo(videoUrl, videoId);
            return;
        }

        // Show thumbnail as placeholder while video loads
        if (thumbnailUrl) {
            drawThumbnailPlaceholder(thumbnailUrl);
        } else {
            drawLoadingOverlay();
        }

        // Load video in background, preserve overlay while loading
        window.loadVideo(videoUrl, videoId, !!thumbnailUrl);
    };

    /**
     * Preload multiple videos for faster switching
     * @param {Array} videos - Array of {id, url} objects
     */
    window.preloadVideos = function (videos) {
        console.log('[VideoCache] Preloading', videos.length, 'videos');

        videos.forEach(v => {
            if (v.id && v.url) {
                videoCache.preload(v.id, v.url);
            }
        });
    };

    /**
     * Set cache size based on estimated video memory usage
     * @param {number} size - Number of videos to cache
     */
    window.setVideoCacheSize = function (size) {
        videoCache.setMaxSize(size);
    };

    /**
     * Clear the video cache
     */
    window.clearVideoCache = function () {
        videoCache.clear();
    };

    let _videoLoadingCounter = 0;
    function triggerVideoLoading(status) {
        const input = document.getElementById('video-loading-trigger');
        if (input) {
            // Append counter to ensure Reflex always sees a unique value change
            _videoLoadingCounter++;
            const uniqueStatus = status + ':' + _videoLoadingCounter;
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, uniqueStatus);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Triggered loading status:', uniqueStatus);
        }
    }



    /**
     * Toggle video playback
     * @param {boolean} shouldPlay - True to play, false to pause
     */
    window.toggleVideoPlayback = function (shouldPlay) {
        if (!sourceVideo) return;

        if (shouldPlay) {
            // Cancel any pending debounced seek
            if (_seekDebounceTimer) {
                clearTimeout(_seekDebounceTimer);
                _seekDebounceTimer = null;
            }

            // If video is seeking, wait for it to finish before playing
            if (sourceVideo.seeking) {
                sourceVideo.addEventListener('seeked', function onReady() {
                    sourceVideo.removeEventListener('seeked', onReady);
                    _isSeeking = false;
                    sourceVideo.play().then(() => {
                        startVideoFrameLoop();
                    }).catch(e => {
                        console.error('[Video] Play error after seek:', e);
                    });
                }, { once: true });
            } else {
                sourceVideo.play().then(() => {
                    startVideoFrameLoop();
                }).catch(e => {
                    console.error('[Video] Play error:', e);
                });
            }
        } else {
            sourceVideo.pause();
            if (videoAnimationFrame) {
                cancelAnimationFrame(videoAnimationFrame);
                videoAnimationFrame = null;
            }
        }
    };

    /**
     * Seek to a specific frame number.
     * Debounced to handle rapid slider drags — only the last seek in a burst fires.
     * @param {number} frame - Frame number to seek to
     * @param {number} fps - Frames per second of the video
     */
    let _seekDebounceTimer = null;
    let _isSeeking = false;
    let _pendingSeekFrame = null;

    window.seekToFrame = function (frame, fps) {
        if (!sourceVideo) return;

        videoFps = fps || 30;

        // Debounce rapid slider drags: only process the last seek within 50ms
        _pendingSeekFrame = frame;

        if (_seekDebounceTimer) {
            clearTimeout(_seekDebounceTimer);
        }

        _seekDebounceTimer = setTimeout(function () {
            _seekDebounceTimer = null;
            _executeSeek(_pendingSeekFrame);
        }, 50);
    };

    function _executeSeek(frame) {
        if (!sourceVideo) return;

        const time = frame / videoFps;
        _isSeeking = true;

        sourceVideo.currentTime = time;

        // Use a one-shot event listener to avoid clobbering
        sourceVideo.addEventListener('seeked', function onSeeked() {
            sourceVideo.removeEventListener('seeked', onSeeked);
            _isSeeking = false;
            drawVideoFrameToCanvas();

            // Render annotations from JS cache (Phase 1 - zero WS traffic)
            const cachedAnns = videoAnnotationCache[frame];
            annotations = cachedAnns || [];
            if (annotations.length > 0) {
                drawCanvas();
            }

            // If another seek was queued while we were seeking, execute it
            if (_pendingSeekFrame !== null && _pendingSeekFrame !== frame) {
                const nextFrame = _pendingSeekFrame;
                _pendingSeekFrame = null;
                _executeSeek(nextFrame);
            } else {
                _pendingSeekFrame = null;
            }
        }, { once: true });
    }


    /**
     * Draw current video frame to canvas.
     * Uses a persistent offscreen canvas (videoFrameBuffer) to capture each decoded frame
     * via a single GPU-accelerated drawImage() call. This gives frame persistence during
     * seeks/buffering (the user always sees the last good frame) without the CPU cost of
     * JPEG encoding via toDataURL.
     * @param {HTMLVideoElement} sourceOverride - Optional custom source (e.g. from cache)
     */
    function drawVideoFrameToCanvas(sourceOverride = null) {
        const source = sourceOverride || sourceVideo;

        if (!source) {
            console.error('[Video] ERROR: No sourceVideo!');
            return;
        }
        if (!ctx || !canvas) {
            console.error('[Video] ERROR: Canvas not initialized!');
            return;
        }
        if (source.readyState < 2) {
            // Video not ready — keep showing the last good frame (videoFrameBuffer)
            if (videoFrameBuffer && currentImage === videoFrameBuffer) {
                drawCanvas();
            }
            return;
        }

        // Ensure the offscreen buffer matches the video dimensions
        if (!videoFrameBuffer ||
            videoFrameBuffer.width !== source.videoWidth ||
            videoFrameBuffer.height !== source.videoHeight) {
            videoFrameBuffer = document.createElement('canvas');
            videoFrameBuffer.width = source.videoWidth;
            videoFrameBuffer.height = source.videoHeight;
        }

        // Copy the decoded video frame to the persistent offscreen buffer (GPU-accelerated)
        const bufCtx = videoFrameBuffer.getContext('2d');
        bufCtx.drawImage(source, 0, 0);

        // Set the offscreen canvas as the drawing source
        // (canvas elements are valid CanvasImageSource and have .width/.height)
        currentImage = videoFrameBuffer;
        sourceWidth = videoFrameBuffer.width;
        sourceHeight = videoFrameBuffer.height;

        if (scale === 1.0 && offsetX === 0 && offsetY === 0) {
            calculateFit();
        }
        drawCanvas();
    }

    /**
     * Start animation loop for video playback.
     * Throttled to ~30fps for canvas draws.
     * 
     * PERF OPTIMIZATION (Phase 1):
     * - Annotations are rendered locally from videoAnnotationCache (zero WS traffic)
     * - Python frame sync is throttled to ~4fps (PYTHON_SYNC_INTERVAL) for UI counter only
     */
    function startVideoFrameLoop() {
        if (videoAnimationFrame) {
            cancelAnimationFrame(videoAnimationFrame);
        }

        let lastFrameTime = 0;
        const minFrameInterval = 1000 / 30; // Cap rendering at 30fps

        function loop(now) {
            if (sourceVideo && !sourceVideo.paused && !sourceVideo.ended) {
                if (now - lastFrameTime >= minFrameInterval) {
                    lastFrameTime = now;
                    drawVideoFrameToCanvas();

                    // Render annotations from JS-side cache (zero latency)
                    const currentFrame = Math.floor(sourceVideo.currentTime * videoFps);
                    const cachedAnns = videoAnnotationCache[currentFrame];
                    annotations = cachedAnns || [];
                    // drawCanvas is already called by drawVideoFrameToCanvas,
                    // but annotations are set after — trigger one more draw
                    // only if we actually have annotations to show
                    if (cachedAnns && cachedAnns.length > 0) {
                        drawCanvas();
                    }

                    // Throttled sync to Python for UI counter updates only (~4fps)
                    if (now - _lastPythonSyncTime >= PYTHON_SYNC_INTERVAL) {
                        _lastPythonSyncTime = now;
                        syncFrameToPython();
                    }
                }
                videoAnimationFrame = requestAnimationFrame(loop);
            }
        }
        videoAnimationFrame = requestAnimationFrame(loop);
    }


    /**
     * Sync current frame position to Python (throttled, UI counter only).
     * No longer triggers renderAnnotations callback — annotations are handled JS-side.
     */
    function syncFrameToPython() {
        if (!sourceVideo) return;

        const currentFrame = Math.floor(sourceVideo.currentTime * videoFps);
        const timestamp = sourceVideo.currentTime;

        const input = document.getElementById('frame-update-data');
        if (input) {
            const data = JSON.stringify({
                frame: currentFrame,
                timestamp: timestamp
            });
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, data);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    /**
     * Capture current video frame as keyframe
     * @param {number} frameNumber - Frame number being captured
     * @param {string} keyframeId - Unique ID for the keyframe
     */
    window.notifyKeyframeCreated = function (frameNumber, keyframeId) {
        console.log('[Video] ========= notifyKeyframeCreated called =========');
        console.log('[Video] Frame:', frameNumber, 'ID:', keyframeId);

        if (!sourceVideo) {
            console.error('[Video] No video loaded for keyframe creation');
            notifyKeyframeCaptured(keyframeId, frameNumber, false);
            return;
        }

        // Just notify Python - no thumbnail capture needed
        const timestamp = sourceVideo.currentTime;
        notifyKeyframeCaptured(keyframeId, frameNumber, true, timestamp);
        console.log('[Video] Keyframe creation notified for frame', frameNumber);
    };

    // Legacy support - redirect to new simplified function
    window.captureKeyframe = function (frameNumber, keyframeId, thumbnailPath) {
        console.log('[Video] captureKeyframe (legacy) redirecting to notifyKeyframeCreated');
        window.notifyKeyframeCreated(frameNumber, keyframeId);
    };

    function notifyKeyframeCaptured(keyframeId, frameNumber, success, timestamp) {
        console.log('[Video] ========= notifyKeyframeCaptured =========');
        console.log('[Video] success:', success);

        const input = document.getElementById('keyframe-captured-data');
        if (input) {
            const data = JSON.stringify({
                keyframe_id: keyframeId,
                frame_number: frameNumber,
                success: success,
                timestamp: timestamp || 0
            });
            console.log('[Video] Sending to Python, data length:', data.length);
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
            nativeInputValueSetter.call(input, data);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            console.log('[Video] Events dispatched');
        } else {
            console.error('[Video] ERROR: keyframe-captured-data input not found!');
        }
    }

    /**
     * Set whether a keyframe is currently selected (called from Python)
     * @param {boolean} isSelected - Whether a keyframe is selected
     */
    window.setKeyframeSelected = function (isSelected) {
        hasSelectedKeyframe = isSelected;
        console.log('[Video] hasSelectedKeyframe set to:', isSelected);
    };


    // ==========================================================================
    // INIT
    // ==========================================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCanvas);
    } else {
        initCanvas();
    }
})();

