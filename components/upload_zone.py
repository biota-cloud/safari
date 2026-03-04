"""
Upload Zone Component — Drag-and-drop file upload with preview.

Usage:
    from components.upload_zone import upload_zone
    
    upload_zone(
        on_upload=MyState.handle_upload,
        is_uploading=MyState.is_uploading,
    )
"""

import reflex as rx
import styles


def upload_zone(
    upload_id: str = "image_upload",
    is_uploading: rx.Var[bool] = False,
) -> rx.Component:
    """
    Drag-and-drop upload zone for images.
    
    Args:
        upload_id: Unique ID for the upload component (for rx.upload_files)
        is_uploading: Whether upload is in progress (disables interaction)
    """
    
    # JavaScript to handle thumbnail generation reliably
    # Captures files from drop/input events and uses polling to render
    preview_script = rx.script(
        f"""
        (function() {{
            const uploadId = '{upload_id}';
            const previewContainerId = uploadId + '_previews';
            
            if (!window._filePreviews) window._filePreviews = {{}};
            if (!window._previewIntervals) window._previewIntervals = {{}};
            if (!window._previewRendered) window._previewRendered = {{}};
            if (!window._previewListenersAttached) window._previewListenersAttached = {{}};
            if (!window._previewDataUrls) window._previewDataUrls = {{}};
            
            function renderPreviews() {{
                const container = document.getElementById(previewContainerId);
                const files = window._filePreviews[uploadId];
                
                if (!container) return false;
                if (!files || files.length === 0) return false;
                
                const fileKey = Array.from(files).map(f => f.name + f.size).join('|');
                
                // If container was emptied by re-render but we have cached data URLs, re-render from cache
                const hasChildren = container.children.length > 0;
                if (window._previewRendered[uploadId] === fileKey && hasChildren) return true;
                
                // Check if we have cached data URLs for this file set
                const cached = window._previewDataUrls[uploadId];
                if (cached && cached.key === fileKey) {{
                    console.log('[Preview] Re-rendering from cache for', uploadId);
                    container.innerHTML = '';
                    cached.urls.forEach(item => {{
                        const wrapper = document.createElement('div');
                        wrapper.style.cssText = 'width:80px;height:80px;border-radius:6px;overflow:hidden;border:1px solid #27272A;background:#18181B;display:flex;align-items:center;justify-content:center;margin-bottom:8px;';
                        const img = document.createElement('img');
                        img.src = item;
                        img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
                        wrapper.appendChild(img);
                        container.appendChild(wrapper);
                    }});
                    window._previewRendered[uploadId] = fileKey;
                    return true;
                }}
                
                console.log('[Preview] Rendering', files.length, 'image previews for', uploadId);
                window._previewRendered[uploadId] = fileKey;
                window._previewDataUrls[uploadId] = {{ key: fileKey, urls: [] }};
                container.innerHTML = '';
                
                Array.from(files).slice(0, 12).forEach(file => {{
                    if (!file.type.startsWith('image/')) return;
                    
                    const wrapper = document.createElement('div');
                    wrapper.style.cssText = 'width:80px;height:80px;border-radius:6px;overflow:hidden;border:1px solid #27272A;background:#18181B;display:flex;align-items:center;justify-content:center;margin-bottom:8px;';
                    wrapper.innerHTML = '<span style="color:#71717A;font-size:10px;">Loading</span>';
                    container.appendChild(wrapper);
                    
                    const reader = new FileReader();
                    reader.onload = e => {{
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
                        wrapper.innerHTML = '';
                        wrapper.appendChild(img);
                        // Cache the data URL for re-renders
                        if (window._previewDataUrls[uploadId] && window._previewDataUrls[uploadId].key === fileKey) {{
                            window._previewDataUrls[uploadId].urls.push(e.target.result);
                        }}
                    }};
                    reader.readAsDataURL(file);
                }});
                
                return true;
            }}
            
            function handleDrop(e) {{
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
                    console.log('[Preview] Drop captured:', e.dataTransfer.files.length, 'files for', uploadId);
                    window._filePreviews[uploadId] = e.dataTransfer.files;
                    window._previewRendered[uploadId] = null;
                    // Render immediately, don't wait for poll
                    setTimeout(renderPreviews, 50);
                }}
            }}
            
            function handleInputChange(e) {{
                if (e.target.files && e.target.files.length > 0) {{
                    console.log('[Preview] Input change:', e.target.files.length, 'files for', uploadId);
                    window._filePreviews[uploadId] = e.target.files;
                    window._previewRendered[uploadId] = null;
                    setTimeout(renderPreviews, 50);
                }}
            }}
            
            function attachListeners() {{
                const uploadWrapper = document.getElementById(uploadId);
                if (!uploadWrapper) return false;
                
                // Re-attach on every script run since Reflex may re-render the DOM
                const handlerKey = '_previewDropHandler_' + uploadId;
                if (window[handlerKey]) {{
                    uploadWrapper.removeEventListener('drop', window[handlerKey], true);
                }}
                window[handlerKey] = handleDrop;
                uploadWrapper.addEventListener('drop', handleDrop, true);
                
                const input = uploadWrapper.querySelector('input[type="file"]');
                if (input && !input._previewListenerAttached) {{
                    input.addEventListener('change', handleInputChange);
                    input._previewListenerAttached = true;
                }}
                
                return true;
            }}
            
            function poll() {{
                attachListeners();
                renderPreviews();
            }}
            
            if (window._previewIntervals[uploadId]) {{
                clearInterval(window._previewIntervals[uploadId]);
            }}
            
            window._previewIntervals[uploadId] = setInterval(poll, 500);
            setTimeout(poll, 100);
            
            console.log('[Preview] Image preview system started for', uploadId);
        }})();
        """
    )
    
    return rx.fragment(
        rx.upload(
            rx.vstack(
                # Icon changes based on upload state
                rx.cond(
                    is_uploading,
                    rx.spinner(size="3"),
                    rx.icon(
                        "upload",
                        size=48,
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                    ),
                ),
                rx.text(
                    rx.cond(
                        is_uploading,
                        "Uploading...",
                        "Drag & drop images here"
                    ),
                    size="3",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.text(
                    "or click to browse",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.text(
                    "Supports: JPG, PNG, WebP",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                ),
                spacing="2",
                align="center",
                justify="center",
                style={"padding": styles.SPACING_8},
            ),
            id=upload_id,
            accept={
                "image/*": [".jpg", ".jpeg", ".png", ".webp"]
            },
            multiple=True,
            disabled=is_uploading,
            border=f"2px dashed {styles.BORDER}",
            border_radius=styles.RADIUS_LG,
            background=styles.BG_SECONDARY,
            width="100%",
            min_height="200px",
            display="flex",
            align_items="center",
            justify_content="center",
            cursor=rx.cond(is_uploading, "not-allowed", "pointer"),
            _hover={
                "border_color": styles.ACCENT,
                "background": styles.BG_TERTIARY,
            },
            transition=styles.TRANSITION_FAST,
        ),
        preview_script
    )


def video_upload_zone(
    upload_id: str = "video_upload",
    is_uploading: rx.Var[bool] = False,
) -> rx.Component:
    """
    Drag-and-drop upload zone for videos.
    
    Args:
        upload_id: Unique ID for the upload component (for rx.upload_files)
        is_uploading: Whether upload is in progress (disables interaction)
    """
    
    # JavaScript to handle video thumbnail generation
    # Captures files from drop/input events and uses polling to render
    preview_script = rx.script(
        f"""
        (function() {{
            const uploadId = '{upload_id}';
            const previewContainerId = uploadId + '_previews';
            
            if (!window._filePreviews) window._filePreviews = {{}};
            if (!window._previewIntervals) window._previewIntervals = {{}};
            if (!window._previewRendered) window._previewRendered = {{}};
            if (!window._previewListenersAttached) window._previewListenersAttached = {{}};
            
            function generateVideoThumbnail(file, wrapper) {{
                const video = document.createElement('video');
                video.preload = 'metadata';
                video.muted = true;
                video.playsInline = true;
                
                video.onloadedmetadata = function() {{
                    video.currentTime = Math.min(1, video.duration * 0.1);
                }};
                
                video.onseeked = function() {{
                    try {{
                        const canvas = document.createElement('canvas');
                        canvas.width = 160;
                        canvas.height = 90;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                        
                        const img = document.createElement('img');
                        img.src = canvas.toDataURL('image/jpeg', 0.7);
                        img.style.cssText = 'width:100%;height:100%;object-fit:cover;';
                        wrapper.innerHTML = '';
                        wrapper.appendChild(img);
                        
                        const playIcon = document.createElement('div');
                        playIcon.innerHTML = '▶';
                        playIcon.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:white;font-size:20px;text-shadow:0 2px 4px rgba(0,0,0,0.5);pointer-events:none;';
                        wrapper.appendChild(playIcon);
                    }} catch (err) {{
                        console.error('[Preview] Video thumbnail error:', err);
                        wrapper.innerHTML = '<span style="color:#71717A;font-size:10px;">Error</span>';
                    }}
                    URL.revokeObjectURL(video.src);
                }};
                
                video.onerror = function() {{
                    console.error('[Preview] Video load error');
                    wrapper.innerHTML = '<span style="color:#71717A;font-size:10px;">Error</span>';
                    URL.revokeObjectURL(video.src);
                }};
                
                video.src = URL.createObjectURL(file);
                video.load();
            }}
            
            function renderPreviews() {{
                const container = document.getElementById(previewContainerId);
                const files = window._filePreviews[uploadId];
                
                if (!container) return false;
                if (!files || files.length === 0) return false;
                
                const fileKey = Array.from(files).map(f => f.name + f.size).join('|');
                if (window._previewRendered[uploadId] === fileKey) return true;
                
                console.log('[Preview] Rendering', files.length, 'video previews for', uploadId);
                window._previewRendered[uploadId] = fileKey;
                container.innerHTML = '';
                
                Array.from(files).slice(0, 8).forEach(file => {{
                    if (!file.type.startsWith('video/')) return;
                    
                    const wrapper = document.createElement('div');
                    wrapper.style.cssText = 'position:relative;width:120px;height:68px;border-radius:6px;overflow:hidden;border:1px solid #27272A;background:#18181B;display:flex;align-items:center;justify-content:center;';
                    wrapper.innerHTML = '<span style="color:#71717A;font-size:10px;">Loading...</span>';
                    container.appendChild(wrapper);
                    
                    generateVideoThumbnail(file, wrapper);
                }});
                
                return true;
            }}
            
            function handleDrop(e) {{
                // Capture files from drop event before react-dropzone processes them
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
                    console.log('[Preview] Drop captured:', e.dataTransfer.files.length, 'files for', uploadId);
                    window._filePreviews[uploadId] = e.dataTransfer.files;
                    window._previewRendered[uploadId] = null;
                }}
            }}
            
            function handleInputChange(e) {{
                // Capture files from file input
                if (e.target.files && e.target.files.length > 0) {{
                    console.log('[Preview] Input change:', e.target.files.length, 'files for', uploadId);
                    window._filePreviews[uploadId] = e.target.files;
                    window._previewRendered[uploadId] = null;
                }}
            }}
            
            function attachListeners() {{
                const uploadWrapper = document.getElementById(uploadId);
                if (!uploadWrapper) return false;
                
                if (!window._previewListenersAttached[uploadId]) {{
                    // Use capture phase to get files before react-dropzone
                    uploadWrapper.addEventListener('drop', handleDrop, true);
                    
                    // Also listen on the input for file browser selection
                    const input = uploadWrapper.querySelector('input[type="file"]');
                    if (input) {{
                        input.addEventListener('change', handleInputChange);
                    }}
                    
                    window._previewListenersAttached[uploadId] = true;
                    console.log('[Preview] Listeners attached for', uploadId);
                }}
                return true;
            }}
            
            function poll() {{
                // First, ensure listeners are attached
                attachListeners();
                
                // Then try to render previews
                renderPreviews();
            }}
            
            // Clear any existing interval
            if (window._previewIntervals[uploadId]) {{
                clearInterval(window._previewIntervals[uploadId]);
            }}
            
            // Poll to attach listeners and render previews
            window._previewIntervals[uploadId] = setInterval(poll, 300);
            setTimeout(poll, 100);
            
            console.log('[Preview] Video preview system started for', uploadId);
        }})();
        """
    )
    
    return rx.fragment(
        rx.upload(
            rx.vstack(
                # Icon changes based on upload state
                rx.cond(
                    is_uploading,
                    rx.spinner(size="3"),
                    rx.icon(
                        "video",
                        size=48,
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                    ),
                ),
                rx.text(
                    rx.cond(
                        is_uploading,
                        "Uploading...",
                        "Drag & drop videos here"
                    ),
                    size="3",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.text(
                    "or click to browse",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.text(
                    "Supports: MP4, MOV, WebM",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                ),
                spacing="2",
                align="center",
                justify="center",
                style={"padding": styles.SPACING_8},
            ),
            id=upload_id,
            accept={
                "video/*": [".mp4", ".mov", ".webm"]
            },
            multiple=True,
            disabled=is_uploading,
            border=f"2px dashed {styles.BORDER}",
            border_radius=styles.RADIUS_LG,
            background=styles.BG_SECONDARY,
            width="100%",
            min_height="200px",
            display="flex",
            align_items="center",
            justify_content="center",
            cursor=rx.cond(is_uploading, "not-allowed", "pointer"),
            _hover={
                "border_color": styles.ACCENT,
                "background": styles.BG_TERTIARY,
            },
            transition=styles.TRANSITION_FAST,
        ),
        preview_script,
    )


def upload_preview_grid(upload_id: str = "image_upload") -> rx.Component:
    """
    Display preview of selected files before upload.
    Shows file count and names. Thumbnails use client-side JavaScript.
    
    Args:
        upload_id: Must match the upload zone's ID
    """
    return rx.cond(
        rx.selected_files(upload_id).length() > 0,
        rx.box(
            rx.hstack(
                rx.icon("image", size=16, style={"color": styles.ACCENT}),
                rx.text(
                    rx.selected_files(upload_id).length().to_string() + " file(s) ready to upload",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                spacing="2",
                align="center",
            ),
            # Container for JS-generated previews
            rx.el.div(
                id=f"{upload_id}_previews",
                style={
                    "display": "flex",
                    "flex_wrap": "wrap",
                    "gap": "12px",
                    "margin_top": "12px",
                    "min_height": "80px",
                }
            ),
            # File list with names
            rx.hstack(
                rx.foreach(
                    rx.selected_files(upload_id),
                    lambda file: rx.box(
                        rx.text(
                            file,
                            size="1",
                            style={
                                "color": styles.TEXT_SECONDARY,
                                "padding": "4px 8px",
                                "background": styles.BG_SECONDARY,
                                "border_radius": styles.RADIUS_SM,
                                "max_width": "150px",
                                "overflow": "hidden",
                                "text_overflow": "ellipsis",
                                "white_space": "nowrap",
                            }
                        ),
                    )
                ),
                spacing="2",
                wrap="wrap",
                style={"margin_top": styles.SPACING_3},
            ),
            style={
                "padding": styles.SPACING_4,
                "background": styles.BG_TERTIARY,
                "border_radius": styles.RADIUS_LG,
                "margin_top": styles.SPACING_4,
            }
        ),
        rx.fragment(),
    )


def video_upload_preview_grid(upload_id: str = "video_upload") -> rx.Component:
    """
    Display preview of selected video files before upload.
    Shows file count, names, and video thumbnails using client-side JavaScript.
    
    Args:
        upload_id: Must match the video upload zone's ID
    """
    return rx.cond(
        rx.selected_files(upload_id).length() > 0,
        rx.box(
            rx.hstack(
                rx.icon("video", size=16, style={"color": styles.WARNING}),
                rx.text(
                    rx.selected_files(upload_id).length().to_string() + " video(s) ready to upload",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                spacing="2",
                align="center",
            ),
            # Container for JS-generated video previews
            rx.el.div(
                id=f"{upload_id}_previews",
                style={
                    "display": "flex",
                    "flex_wrap": "wrap",
                    "gap": "12px",
                    "margin_top": "12px",
                    "min_height": "68px",
                }
            ),
            # File list with names
            rx.hstack(
                rx.foreach(
                    rx.selected_files(upload_id),
                    lambda file: rx.box(
                        rx.text(
                            file,
                            size="1",
                            style={
                                "color": styles.TEXT_SECONDARY,
                                "padding": "4px 8px",
                                "background": styles.BG_SECONDARY,
                                "border_radius": styles.RADIUS_SM,
                                "max_width": "150px",
                                "overflow": "hidden",
                                "text_overflow": "ellipsis",
                                "white_space": "nowrap",
                            }
                        ),
                    )
                ),
                spacing="2",
                wrap="wrap",
                style={"margin_top": styles.SPACING_3},
            ),
            style={
                "padding": styles.SPACING_4,
                "background": styles.BG_TERTIARY,
                "border_radius": styles.RADIUS_LG,
                "margin_top": styles.SPACING_4,
            }
        ),
        rx.fragment(),
    )


def upload_button(
    upload_id: str = "image_upload",
    on_upload: rx.EventHandler = None,
    is_uploading: rx.Var[bool] = False,
) -> rx.Component:
    """
    Upload button to trigger the file upload.
    
    Args:
        upload_id: Must match the upload zone's ID
        on_upload: Event handler to call when upload button is clicked
        is_uploading: Whether upload is in progress
    """
    return rx.button(
        rx.cond(
            is_uploading,
            rx.hstack(
                rx.spinner(size="1"),
                rx.text("Uploading..."),
                spacing="2",
            ),
            rx.hstack(
                rx.icon("upload", size=16),
                rx.text("Upload Images"),
                spacing="2",
            ),
        ),
        on_click=on_upload,
        disabled=is_uploading,
        style={
            "background": styles.ACCENT,
            "color": "white",
            "padding_left": styles.SPACING_4,
            "padding_right": styles.SPACING_4,
            "&:hover": {
                "background": styles.ACCENT_HOVER,
            },
            "&:disabled": {
                "opacity": "0.5",
                "cursor": "not-allowed",
            },
        }
    )
