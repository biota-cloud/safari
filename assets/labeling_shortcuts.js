/**
 * Labeling Module Keyboard Shortcuts
 * 
 * Centralized shortcut definitions for the labeling editor.
 * Module-specific: these only apply when in the labeling context.
 */

const LABELING_SHORTCUTS = {
    // Navigation (Image mode)
    NEXT_IMAGE: 'd',
    PREV_IMAGE: 'a',

    // Tools
    TOOL_SELECT: 'v',
    TOOL_DRAW: 'r',
    TOOL_MASK_EDIT: 'c',

    // Actions
    DELETE_ANNOTATION: ['Delete', 'Backspace'],
    DESELECT: 'Escape',

    // Class selection (1-9)
    CLASS_SELECT: ['1', '2', '3', '4', '5', '6', '7', '8', '9'],

    // Help overlay
    HELP: '?',

    // Navigation
    DASHBOARD: 'h', // Go to dashboard hub

    // Video mode shortcuts
    VIDEO_PLAY_PAUSE: ' ', // Space
    VIDEO_PREV_FRAME: 'z',
    VIDEO_NEXT_FRAME: 'c',
    VIDEO_MARK_KEYFRAME: 'k',
    VIDEO_MARK_EMPTY: 'e',
};

// Export for use in canvas.js
window.LABELING_SHORTCUTS = LABELING_SHORTCUTS;

