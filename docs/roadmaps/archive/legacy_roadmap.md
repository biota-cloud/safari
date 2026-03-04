# 🚀 One-Man-SaaS: YOLO Object Detection Platform

> **Stack**: Reflex (UI), Modal (GPU Compute), Cloudflare R2 (Storage), Supabase (Auth/DB)  
> **Philosophy**: Decoupled Monolith — each module (Labeling, Training, Inference) works independently.

---

> [!IMPORTANT]
> ## 📍 Current Focus
> **Phase**: 3.4 — Inference Results & Model Comparison System
> **Active Steps**: Phase 3.4.6 — Inference Results Gallery (Optional)
> **Last Completed**: Phase 3.4.5 — Video Playback with Dynamic Label Rendering ✅
> **Blocked On**: None
> **Technical Debt**: See `.agent/tech_debt.md`

> 
> **Context for Agent**: Phase 3.4.5 complete! Video inference results now display with smooth 60fps canvas rendering, proper letterboxing for any aspect ratio, and requestAnimationFrame-based playback. Labels stored as normalized coordinates and transformed at render time. Core inference pipeline (upload → inference → playback) is fully functional. Next: optional gallery view or proceed to Phase 4 (Training enhancements).


---

## 🎨 Design System & Look and Feel

**Objective**: A modern, data-dense yet clean interface. Think **Linear**, **Vercel**, or **Raycast** aesthetics.

### Color Palette (Dark Mode Default)

| Token | Value | Usage |
|-------|-------|-------|
| `BG_PRIMARY` | `#0A0A0B` | Main background (near-black) |
| `BG_SECONDARY` | `#141415` | Cards, modals, sidebars |
| `BG_TERTIARY` | `#1C1C1E` | Hover states, subtle elevation |
| `ACCENT` | `#3B82F6` | Primary actions (Blue-500) |
| `ACCENT_HOVER` | `#2563EB` | Button hover states (Blue-600) |
| `SUCCESS` | `#22C55E` | Completed states, positive feedback |
| `WARNING` | `#F59E0B` | Alerts, training in progress |
| `ERROR` | `#EF4444` | Destructive actions, errors |
| `TEXT_PRIMARY` | `#FAFAFA` | Headings, important text |
| `TEXT_SECONDARY` | `#A1A1AA` | Body text, descriptions |
| `BORDER` | `#27272A` | Subtle borders, dividers |

> [!TIP]
> Store all colors in `styles.py`. Import from there only — never hardcode hex values in components.

### Typography

| Element | Font | Weight | Size |
|---------|------|--------|------|
| Headings | `Inter` or System | 600 (Semibold) | 24-32px |
| Body | `Inter` or System | 400 (Regular) | 14-16px |
| Labels | `Inter` or System | 500 (Medium) | 12-13px |
| Code/Data | `JetBrains Mono` | 400 | 13px |

### Layout Guidelines

- **Sidebar**: Fixed width (240px), collapsible on mobile.
- **Max Content Width**: 1280px centered for dashboard views.
- **Spacing**: Use 4px grid (4, 8, 12, 16, 24, 32, 48px).
- **Border Radius**: 8px for cards, 6px for buttons, 4px for inputs.

### Interactive States

| State | Visual Treatment |
|-------|------------------|
| Hover | Background lightens (`BG_TERTIARY`), subtle scale (1.01) |
| Active | Scale down (0.98), darker background |
| Focus | 2px ring in `ACCENT` with 2px offset |
| Disabled | 50% opacity, `cursor: not-allowed` |
| Loading | Pulse animation or spinner, never freeze the UI |

### Animation Guidelines

- **Duration**: 150ms for micro-interactions, 300ms for modals/transitions.
- **Easing**: `cubic-bezier(0.4, 0, 0.2, 1)` for smooth natural motion.
- **Toasts**: Slide in from bottom-right, auto-dismiss in 4 seconds.

> [!IMPORTANT]
> Every async action MUST show immediate feedback. Use optimistic UI — update state first, then confirm with backend.

---

## 📂 Architecture & File Structure

```plaintext
/SAFARI
├── assets/                  # Public images, icons
├── .env                     # Environment secrets (never commit!)
├── rxconfig.py              # Reflex configuration
├── styles.py                # ⭐ THEME SOURCE OF TRUTH
├── app_state.py             # Global state (user session, context)
│
├── backend/                 # Pure logic (NO UI imports)
│   ├── supabase_client.py   # Database connection helper
│   ├── r2_storage.py        # Boto3 wrapper for R2
│   └── modal_jobs/          # Standalone GPU scripts
│       ├── train_job.py     # Training logic
│       └── infer_job.py     # Inference logic
│
├── components/              # Reusable UI components
│   ├── sidebar.py           # Navigation sidebar
│   ├── card.py              # Project card component
│   ├── button.py            # Styled button variants
│   └── toast.py             # Notification system
│
├── modules/                 # Feature modules (independent)
│   ├── auth/                # Phase 0
│   │   ├── login.py
│   │   └── signup.py
│   ├── labeling/            # Phase 1
│   │   ├── state.py         # Drawing logic (pure Python)
│   │   ├── editor.py        # Image canvas UI
│   │   └── tools.py         # Class selector, toolbar
│   ├── training/            # Phase 2
│   │   ├── state.py         # Modal trigger logic
│   │   └── dashboard.py     # Progress UI
│   └── inference/           # Phase 3
│       ├── state.py         # API logic
│       └── playground.py    # Drag-drop testing
│
└── yolo_app/                # Main Reflex app entry
    └── yolo_app.py
```

> [!TIP]
> **Context Overflow Prevention**: Keep Modal imports in `backend/` only. Never import `modal` inside Reflex pages — use `modal.Function.from_name()` at runtime.

---

## 🔐 Phase 0: Foundation & Authentication

**Goal**: Secure the app and establish the storage "handshake" before building features.

### 0.1 Project Initialization

- [x] **0.1.1** Run `reflex init` to scaffold the project
- [x] **0.1.2** Create the folder structure above (manually create `backend/`, `modules/`, `components/`)
- [x] **0.1.3** Verify with `reflex run` — should show default Reflex welcome page
- [x] **0.1.4** Create `.env` file with all required variables (see Environment Reference below)
- [x] **0.1.5** Create `styles.py` with the color tokens from the Design System section

> [!TIP]
> **Test checkpoint**: After 0.1.5, run the app and ensure `import styles` works in any file without errors.

### 0.2 Storage Layer (R2)

- [x] **0.2.1** Create Cloudflare R2 bucket in dashboard, note the endpoint URL
- [x] **0.2.2** Generate R2 API token with read/write permissions
- [x] **0.2.3** Add R2 credentials to `.env` (see reference below)
- [x] **0.2.4** Create `backend/r2_storage.py` with a basic `R2Client` class
- [x] **0.2.5** Implement `upload_file(file_bytes: bytes, path: str) -> str` method
- [x] **0.2.6** Implement `download_file(path: str) -> bytes` method
- [x] **0.2.7** Implement `list_files(prefix: str) -> list[str]` method
- [x] **0.2.8** Implement `generate_presigned_url(path: str) -> str` method (expires in 1hr)
- [x] **0.2.9** Create `test_r2.py` script — upload a test image, download it, list files, generate URL
- [x] **0.2.10** Verify: Open the presigned URL in browser — image should display

```python
# backend/r2_storage.py - Minimal structure
import boto3
from botocore.config import Config
import os

class R2Client:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=os.getenv('R2_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
            config=Config(signature_version='s3v4'),
        )
        self.bucket = os.getenv('R2_BUCKET_NAME')
    
    def upload_file(self, file_bytes: bytes, path: str) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=path, Body=file_bytes)
        return path
    
    def generate_presigned_url(self, path: str, expires_in: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': path},
            ExpiresIn=expires_in
        )
```

### 0.3 Database Layer (Supabase)

- [x] **0.3.1** Create Supabase project, note the URL and anon key
- [x] **0.3.2** Add Supabase credentials to `.env`
- [x] **0.3.3** Create `profiles` table in Supabase SQL editor:

```sql
CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Policy: users can only read their own profile
CREATE POLICY "Users can read own profile" ON profiles
    FOR SELECT USING (auth.uid() = id);

-- Policy: users can insert their own profile (for signup)
CREATE POLICY "Users can insert own profile" ON profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

-- Policy: users can update their own profile
CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);
```

- [x] **0.3.4** Create `projects` table:

```sql
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    classes TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own projects" ON projects
    FOR ALL USING (auth.uid() = user_id);
```

- [x] **0.3.5** Create `backend/supabase_client.py` with connection helper
- [x] **0.3.6** Test: Query `profiles` table from Python REPL

```python
# backend/supabase_client.py
from supabase import create_client
import os

def get_supabase():
    return create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_KEY')
    )
```

### 0.4 Authentication UI

- [x] **0.4.1** Create `app_state.py` with `BaseState` class containing:
  - `user: Optional[dict] = None`
  - `is_loading: bool = False`
  - `error_message: str = ""`
- [x] **0.4.2** Implement `login(self, email: str, password: str)` method
- [x] **0.4.3** Implement `logout(self)` method
- [x] **0.4.4** Implement `check_auth(self)` to verify session on page load
- [x] **0.4.5** Create `modules/auth/login.py` with login form UI
- [x] **0.4.6** Style login page: centered card, dark theme, subtle border
- [x] **0.4.7** Add loading state to login button (spinner + disabled)
- [x] **0.4.8** Add error toast for failed login attempts
- [x] **0.4.9** Implement route protection: redirect to `/login` if not authenticated
- [x] **0.4.10** Create basic `/dashboard` page (empty for now, just confirms auth works)

> [!IMPORTANT]
> **Test checkpoint**: Complete login flow. Sign up in Supabase dashboard → Login via UI → See dashboard → Refresh page (should remain logged in).

---

## 🏗️ Phase 1: The Labeling Studio

**Goal**: A visual bounding box editor using a **custom, Reflex-native solution** built on HTML5 Canvas.

> [!IMPORTANT]
> **Architecture Choice**: We use a custom Python-driven solution instead of external libraries.
> - **Zero npm dependencies** — no complex JS interop
> - **Pure Reflex state binding** — all annotation data in Python
> - **Full control** — easy to debug, customize, and maintain
> - **HTML5 Canvas** — performant rendering with pan/zoom support

### 1.1 Project Management

- [x] **1.1.1** Create `components/card.py` — reusable project card component
- [x] **1.1.2** Create `/projects` page with grid layout (3 columns on desktop, 1 on mobile)
- [x] **1.1.3** Fetch projects from Supabase and display in cards
- [x] **1.1.4** Add "New Project" button in top-right
- [x] **1.1.5** Create "New Project" modal with form:
  - Project name (required)
  - Initial class names (comma-separated, optional)
- [x] **1.1.6** Implement `create_project` handler in state
- [x] **1.1.7** After creation: redirect to `/projects/{id}`
- [x] **1.1.8** Add loading skeleton while projects fetch

> [!TIP]
> **Test checkpoint**: Create a project → See it in grid → Refresh → Still there (persistence works).

### 1.2 Image Upload System

- [x] **1.2.1** Create `components/upload_zone.py` — drag-drop component
- [x] **1.2.2** Style: dashed border, hover highlight, accept image files only
- [x] **1.2.3** On drop: show preview thumbnails of selected files
- [x] **1.2.4** Implement `upload_images` handler:
  - Generate UUID for each file
  - Upload to R2: `projects/{project_id}/images/{uuid}.jpg`
  - Save metadata to Supabase `images` table
- [x] **1.2.5** Create `images` table in Supabase:

```sql
CREATE TABLE images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    r2_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    labeled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE images ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own project images" ON images
    FOR ALL USING (
        project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
    );
```

- [x] **1.2.6** Show upload progress bar per file
- [x] **1.2.7** On complete: show toast "X images uploaded"
- [x] **1.2.8** Display uploaded images in thumbnail grid below upload zone

> [!TIP]
> **Test checkpoint**: Upload 3 images → Check R2 bucket → Check Supabase table → Thumbnails visible in UI.

### 1.3 Labeling State & Foundation

> [!TIP]
> **Stage 1**: Get a static image displaying correctly before adding interactivity.

- [x] **1.3.1** Create `modules/labeling/state.py` with `LabelingState` class containing:
  - `current_image_url: str = ""`
  - `image_width: int = 0`
  - `image_height: int = 0`
  - `annotations: list[dict] = []`
  - `selected_annotation_id: Optional[str] = None`
- [x] **1.3.2** Create `modules/labeling/editor.py` page layout:
  - Left sidebar (20%): Image thumbnail list placeholder
  - Center (60%): Canvas container with `rx.el.canvas(id="labeling-canvas")`
  - Right sidebar (20%): Class selector placeholder (no save button - autosave behavior)
- [x] **1.3.3** Add inline JavaScript to load image into canvas when `current_image_url` changes
- [x] **1.3.4** Handle image aspect ratio — fit within container, center if needed
- [x] **1.3.5** Verify: Set a test image URL → Image displays correctly in canvas
- [x] **1.3.6** Cache presigned URLs: Generate `full_url` during image load, reuse on navigation

> [!IMPORTANT]
> **Checkpoint 1.3**: Load a test image URL → Image displays correctly, not stretched.

### 1.4 Pan & Zoom

> [!TIP]
> **Stage 2**: Enable navigation around large images before drawing.

- [x] **1.4.1** Add to state: `zoom_level: float = 1.0`, `pan_x: float = 0.0`, `pan_y: float = 0.0`
- [ ] **1.4.2** ~~Mouse wheel zoom~~ → *Deferred to 1.5 (requires canvas/JS interop)*
- [ ] **1.4.3** ~~Shift+drag panning~~ → *Deferred to 1.5 (requires canvas/JS interop)*
- [x] **1.4.4** Clamp zoom to reasonable bounds (1.0 to 10 — no zoom out below 100%)
- [x] **1.4.5** Add on-screen zoom controls (+/- buttons, "Reset View" button)
- [/] **1.4.6** Verify: Load image → Zoom in → Reset → Works smoothly (pan deferred)

> [!IMPORTANT]
> **Checkpoint 1.4**: Zoom in 5x → Pan to corner → Reset → Smooth transitions, no glitches.

### 1.5 Drawing Rectangles

> [!TIP]
> **Stage 3**: Core annotation functionality — creating bounding boxes.
> **Note**: Phase 1.5 will migrate from `rx.image` + CSS transforms (used in 1.4) to HTML5 Canvas for drawing support.

- [x] **1.5.0** Migrate to HTML5 Canvas with JS interop:
  - [x] Add wheel zoom handler (deferred from 1.4.2)
  - [x] Add Shift+drag panning (deferred from 1.4.3)
  - [x] Set up canvas rendering pipeline for annotations
  - [x] **1.5.0.1** Performance: Implement sliding-window pre-fetching (cache next 3 images)
- [x] **1.5.1** Add to state: `current_tool: str = "select"`, `is_drawing: bool = False`
- [x] **1.5.2** Add "Draw Box" toolbar button that sets `current_tool = "draw"`
- [x] **1.5.3** Track mouse-down position when in draw mode
- [x] **1.5.4** Draw preview rectangle (dashed) from mouse-down to current mouse position
- [x] **1.5.5** On mouse-up, create annotation dict with UUID, add to `annotations` list, and **trigger autosave**:
```python
{
    "id": str(uuid.uuid4()),
    "x": float,      # Left edge, normalized 0-1
    "y": float,      # Top edge, normalized 0-1  
    "width": float,  # Box width, normalized 0-1
    "height": float, # Box height, normalized 0-1
    "class_id": int,
    "class_name": str
}
```
- [x] **1.5.6** Render all annotations on canvas (iterate list, draw solid rectangles)
- [x] **1.5.7** Verify: Select Draw tool → Draw 3 boxes → All boxes visible and persist (trigger autosave)

> [!IMPORTANT]
> **Checkpoint 1.5**: Draw 5 boxes → Zoom out → All boxes visible at correct positions.

### 1.6 Box Selection & Deletion

> [!TIP]
> **Stage 4**: Allow editing of existing annotations.

- [x] **1.6.1** Add "Select" toolbar button that sets `current_tool = "select"`
- [x] **1.6.2** On click in select mode, detect if click is inside any annotation (hit testing)
- [x] **1.6.3** Highlight selected annotation (thicker border, accent color)
- [x] **1.6.4** Set `selected_annotation_id` in state when box clicked
- [x] **1.6.5** Add Delete key listener — delete selected annotation (triggers autosave)
- [x] **1.6.6** Add "Delete" button in sidebar as alternative
- [x] **1.6.7** Assign `current_class` to new annotations
- [x] **1.6.8** Verify: Draw boxes → Click to select → Delete key removes → Correct box gone

> [!IMPORTANT]
> **Checkpoint 1.6**: Draw 3 boxes → Select middle one → Delete → Only that box removed.

### 1.7 Box Resizing & Moving

> [!TIP]
> **Stage 5**: Fine-tune annotation positions after initial draw.

- [x] **1.7.1** Render 4 corner handles (small squares) on selected annotation
- [x] **1.7.2** Detect when mouse-down is on a handle vs. box interior
- [x] **1.7.3** When dragging a handle, resize annotation accordingly
- [x] **1.7.4** When dragging box interior, move the entire box
- [x] **1.7.5** Clamp box bounds to image dimensions (can't drag outside image)
- [x] **1.7.6** Update state with new bounds after drag ends (triggers autosave)
- [x] **1.7.7** Verify: Select box → Drag corner → Resize works → Drag interior → Move works

> [!IMPORTANT]
> **Checkpoint 1.7**: Resize box to half size → Move to corner → Release → Bounds correct.

### 1.8 Class Management

> [!TIP]
> **Stage 6**: Assign classes to annotations with visual distinction.

- [x] **1.8.1** Add to state: `classes: list[str] = []`, `current_class_id: int = 0`
- [x] **1.8.2** Load classes from project config (Supabase `projects.classes` field)
- [x] **1.8.3** Add class selector in right sidebar (radio buttons with color dots)
- [x] **1.8.4** When drawing new box, use `current_class_id` from selector
- [x] **1.8.5** Display class label text above each box on canvas
- [x] **1.8.6** Assign unique color per class (generate from index using HSL rotation)
- [x] **1.8.7** Allow changing class of selected box via dropdown (re-class existing annotation)
- [x] **1.8.8** Show annotation list in sidebar (class name + mini-preview)
- [x] **1.8.9** Add class on-the-fly via input in sidebar
- [x] **1.8.10** Rename class (editable text, updates all annotations by class_id) — *implemented via form wrapper for Enter key*
- [x] **1.8.11** Delete class with confirmation modal (deletes all annotations using that class)
- [x] **1.8.12** Verify: Create 3 classes → Draw boxes with each → Correct colors/labels

> [!IMPORTANT]
> **Checkpoint 1.8**: 3 classes with distinct colors → Each box shows correct label and color.

### 1.9 Autosave & Persistence (Local-First)

> [!TIP]
> **Stage 7**: Local-first architecture — edits saved in state, synced to R2 on image change.
> **Why**: Instant feedback, no network latency on every edit, feels snappy like PyCharm/Figma.

- [x] **1.9.1** Remove any "Save" buttons — persistence is automatic
- [x] **1.9.2** Add `is_current_image_dirty: bool = False` flag to track unsaved changes
- [x] **1.9.3** Implement `to_yolo_format()` method in state:
```python
def to_yolo_format(self) -> str:
    """Convert all annotations to YOLO format string."""
    lines = []
    for ann in self.annotations:
        x_center = ann["x"] + ann["width"] / 2
        y_center = ann["y"] + ann["height"] / 2
        lines.append(f"{ann['class_id']} {x_center:.6f} {y_center:.6f} {ann['width']:.6f} {ann['height']:.6f}")
    return "\n".join(lines)
```
- [x] **1.9.4** Implement `save_annotations_to_r2()` method:
  - Upload `.txt` file to R2 `projects/{id}/labels/{image_id}.txt`
  - Update `images.labeled = true` in Supabase (if first annotation)
  - Reset `is_current_image_dirty = False` after successful upload
- [x] **1.9.5** **Saving Triggers**:
  - On image navigation (prev/next/thumbnail click): save current if dirty → then load new
  - On `beforeunload` event: use `navigator.sendBeacon()` to flush pending changes
  - On explicit page leave (back button, close tab): same as above
- [x] **1.9.6** UI Feedback: Show subtle "Saving..." → "Saved ✓" indicator in top corner (no toasts)
- [x] **1.9.7** Implement `from_yolo_format(txt_content: str)` to parse labels:
```python
def from_yolo_format(self, txt_content: str):
    """Parse YOLO format and restore annotations."""
    self.annotations = []
    for line in txt_content.strip().split("\n"):
        if not line: continue
        parts = line.split()
        class_id, x_center, y_center, w, h = int(parts[0]), *map(float, parts[1:])
        self.annotations.append({
            "id": str(uuid.uuid4()),
            "x": x_center - w / 2,
            "y": y_center - h / 2,
            "width": w,
            "height": h,
            "class_id": class_id,
            "class_name": self.classes[class_id] if class_id < len(self.classes) else "unknown"
        })
```
- [x] **1.9.8** **Label Pre-fetching** (same logic as image pre-fetching in 1.5.0.1):
  - On image load, pre-fetch `.txt` files for next 3 images in background
  - Cache parsed annotations in `label_cache: dict[str, list[dict]]`
  - On navigation, check cache first before R2 fetch
- [x] **1.9.9** **First Image Auto-Load**:
  - On page load, automatically load both image AND labels for first image (index 0)
  - Already implemented for images, add label loading to the same flow
- [x] **1.9.10** Verify: Draw boxes → Navigate to next image → Come back → Boxes restored
- [x] **1.9.11** Verify: Draw boxes → Refresh page immediately → Boxes restored correctly

> [!IMPORTANT]
> **Checkpoint 1.9**: Draw boxes → Navigate away → Come back → Boxes persist. Refresh page → Still there.

### 1.10 Image Navigation

> [!TIP]
> **Stage 8**: Move between images in the dataset.

- [x] **1.10.1** Populate left sidebar with image thumbnails from project
  - Enhanced layout: 50x50 thumbnail + filename + annotation count (230px sidebar)
  - Progress bar at top: "X of Y labeled" with percentage
  - Filename truncation: `direction: rtl` shows end (counters like `_001.jpg`), tooltip for full name
  - `annotation_count` field in `ImageModel`, synced on save
- [x] **1.10.2** Clicking thumbnail loads that image into canvas
- [x] **1.10.3** Add Previous/Next buttons below canvas
- [x] **1.10.4** Show current position "3 of 25 images"
- [x] **1.10.5** Mark labeled images with green checkmark in thumbnail list
- [x] **1.10.6** Ensure any pending autosaves complete before navigating
- [x] **1.10.7** Remove any validation roadblocks — navigation is fluid
- [x] **1.10.8** Verify: Upload 5 images → Label 3 → Navigate between → All saved correctly

> [!IMPORTANT]
> **Checkpoint 1.10**: Label 3/5 images → Navigate freely → All labels persist → Checkmarks show.

### 1.11 Keyboard Shortcuts

> [!TIP]
> **Stage 9**: Power-user efficiency.

- [ ] **1.11.1** ~~`S` = Save current labels~~ (Autosave enabled)
- [x] **1.11.2** `R` = Switch to draw mode
- [x] **1.11.3** `V` = Switch to select mode
- [x] **1.11.4** `Delete` / `Backspace` = Delete selected box
- [x] **1.11.5** `1-9` = Select class by index
- [x] **1.11.6** `A` / `D` = Previous/Next image
- [x] **1.11.7** `Escape` = Deselect current box / Cancel drawing
- [x] **1.11.8** `?` = Show shortcuts help overlay
- [X] **1.11.9** Verify: Complete full labeling workflow using only keyboard

> [!IMPORTANT]
> **Checkpoint 1.11**: Draw, label, save, navigate — all via keyboard shortcuts.

---

### 1.12 Dataset Hierarchy Refactor

> [!TIP]
> **Stage 10**: Restructure data model from flat "projects" to **Project → Dataset** hierarchy.
> This enables multiple datasets (image sets, video sets) per project and prepares for video labeling.

#### 1.12.1 Database Migration (Supabase — User Action Required)

> [!WARNING]
> **User must run these SQL scripts in Supabase Dashboard → SQL Editor**.

**Step 1**: Create new `projects` table (container level):

```sql
-- NEW: Projects table (container for datasets)
CREATE TABLE projects_new (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE projects_new ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own projects" ON projects_new
    FOR ALL USING (auth.uid() = user_id);
```

- [ ] **1.12.1.1** Run Step 1 SQL in Supabase

**Step 2**: Rename `projects` → `datasets` and add new columns:

```sql
-- Rename existing projects table to datasets
ALTER TABLE projects RENAME TO datasets;

-- Add new columns for hierarchy and type
ALTER TABLE datasets ADD COLUMN project_id UUID;
ALTER TABLE datasets ADD COLUMN type TEXT DEFAULT 'image' CHECK (type IN ('image', 'video'));
ALTER TABLE datasets ADD COLUMN description TEXT;

-- Rename projects_new to projects
ALTER TABLE projects_new RENAME TO projects;

-- Add FK constraint
ALTER TABLE datasets ADD CONSTRAINT datasets_project_id_fkey 
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- Update images table FK column name for clarity
ALTER TABLE images RENAME COLUMN project_id TO dataset_id;
```

- [ ] **1.12.1.2** Run Step 2 SQL in Supabase

**Step 3**: Migrate existing data (create parent project for orphan datasets):

```sql
-- For each user with datasets, create a "Migrated" parent project
INSERT INTO projects (user_id, name, description)
SELECT DISTINCT user_id, 'Migrated Projects', 'Auto-created during migration'
FROM datasets
WHERE project_id IS NULL;

-- Link orphan datasets to their user's migrated project
UPDATE datasets d
SET project_id = (
    SELECT p.id FROM projects p 
    WHERE p.user_id = d.user_id 
    AND p.name = 'Migrated Projects'
    LIMIT 1
)
WHERE d.project_id IS NULL;

-- Now make project_id required
ALTER TABLE datasets ALTER COLUMN project_id SET NOT NULL;
```

- [ ] **1.12.1.3** Run Step 3 SQL in Supabase

**Step 4**: Update RLS policies:

```sql
-- Drop old policy
DROP POLICY IF EXISTS "Users can CRUD own projects" ON datasets;

-- Create new policy referencing parent projects table
CREATE POLICY "Users can CRUD own datasets" ON datasets
    FOR ALL USING (
        project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
    );
```

- [x] **1.12.1.4** Run Step 4 SQL in Supabase
- [x] **1.12.1.5** Verify in Supabase: Both `projects` and `datasets` tables exist with correct columns

#### 1.12.2 Backend Updates

- [x] **1.12.2.1** Update `backend/supabase_client.py`:
  - [x] Add project CRUD: `get_user_projects()`, `create_project()`, `get_project()`, `update_project()`, `delete_project()`
  - [x] Rename existing funcs: `get_user_projects()` → `get_user_datasets()`, etc.
  - [x] Add `get_project_datasets(project_id)` to list datasets in a project
  - [x] Update `create_dataset()` to require `project_id` and `type` params
  - [x] Update all image functions: `project_id` param → `dataset_id`

- [x] **1.12.2.2** Added `delete_project()` and `delete_dataset()` functions

#### 1.12.3 State Refactor

- [x] **1.12.3.1** Create `modules/projects/models.py` with:
  - `ProjectModel`: id, name, description, dataset_count, created_at
  - `DatasetModel`: id, project_id, name, type, classes, created_at
- [x] **1.12.3.2** Rename `modules/projects/state.py`:
  - `ProjectsState` → manages list of projects (containers)
  - Create new `create_project()` method with description instead of classes
- [x] **1.12.3.3** Create `modules/datasets/state.py`:
  - `DatasetsState`: manages datasets within a project
  - Methods: `load_datasets()`, `create_dataset()`, etc.
- [x] **1.12.3.4** Update `modules/projects/project_detail_state.py`:
  - Created `dataset_detail_state.py` with `DatasetDetailState`
  - Update all `project_id` refs → `dataset_id`
- [x] **1.12.3.5** Update `LabelingState` in `modules/labeling/state.py`:
  - `current_project_id` → `current_dataset_id`
  - Update R2 paths: `projects/{project_id}/...` → `datasets/{dataset_id}/...`

#### 1.12.4 Route Updates

- [x] **1.12.4.1** Update `modules/projects/projects.py`:
  - `/projects` now shows project containers (not datasets)
  - Each card links to `/projects/{project_id}`
- [x] **1.12.4.2** Create new `modules/projects/project_detail.py`:
  - Shows datasets within a project
  - "New Dataset" modal with type selector (Image / Video)
  - Dataset cards link to `/projects/{project_id}/datasets/{dataset_id}`
- [x] **1.12.4.3** Rename current `project_detail.py` → `modules/datasets/dataset_detail.py`:
  - Route: `/projects/{project_id}/datasets/{dataset_id}`
  - Image upload and thumbnail grid (for image datasets)
- [x] **1.12.4.4** Update labeling route:
  - `/projects/{id}/label` → `/projects/{project_id}/datasets/{dataset_id}/label`
- [x] **1.12.4.5** Update `SAFARI/SAFARI.py` with new page imports

#### 1.12.5 UI Updates

- [x] **1.12.5.1** Update project cards to show dataset count
- [x] **1.12.5.2** Create dataset card component with type icon (📷 image / 🎬 video)
- [x] **1.12.5.3** Update sidebar navigation if needed
- [x] **1.12.5.4** Add breadcrumb navigation: Project > Dataset > Label

#### 1.12.6 Delete Feature (Added)

- [x] **1.12.6.1** Add delete button to project cards (hover-reveal with stop propagation)
- [x] **1.12.6.2** Add delete confirmation modal with type-to-confirm security
- [x] **1.12.6.3** Add delete button to dataset cards
- [x] **1.12.6.4** Add dataset delete confirmation modal

> [!IMPORTANT]
> **Checkpoint 1.12**: Create project → Create dataset → Upload images → Label → All persists correctly. ✅ VERIFIED

---

### 1.13 Video Labeling Support

> [!TIP]
> **Stage 11**: Enable labeling of video files with on-demand frame extraction and keyframe marking.
> Same annotation experience as images, but with video timeline navigation.

#### 1.13.1 Video Upload

- [x] **1.13.1.1** Extend upload zone to accept video files (`.mp4`, `.mov`, `.webm`)
- [x] **1.13.1.2** Generate thumbnail from first frame on upload (via ffmpeg)
- [x] **1.13.1.3** Store videos in R2: `datasets/{dataset_id}/videos/{uuid}.mp4`
- [x] **1.13.1.4** Create `videos` table in Supabase:

```sql
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    r2_path TEXT NOT NULL,
    duration_seconds FLOAT,
    frame_count INTEGER,
    fps FLOAT,
    width INTEGER,
    height INTEGER,
    thumbnail_path TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE videos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own dataset videos" ON videos
    FOR ALL USING (
        dataset_id IN (
            SELECT d.id FROM datasets d
            JOIN projects p ON d.project_id = p.id
            WHERE p.user_id = auth.uid()
        )
    );
```

- [x] **1.13.1.5** Add video CRUD to `supabase_client.py`

#### 1.13.2 Video Labeling Editor ✅

- [x] **1.13.2.1** Create `modules/labeling/video_editor.py`:
  - Route: `/projects/{project_id}/datasets/{dataset_id}/video-label`
  - Layout: Same as image editor (left sidebar, center canvas, right tools)
- [x] **1.13.2.2** Create `VideoLabelingState` in `modules/labeling/video_state.py`:
  - `current_video_id`, `current_video_url`
  - `current_frame: int = 0`
  - `total_frames: int = 0`
  - `fps: float = 30.0`
  - `is_playing: bool = False`
  - `keyframes: list[KeyframeModel] = []`
- [x] **1.13.2.3** Create `KeyframeModel`:
  - `frame_number: int`
  - `timestamp: float`
  - `is_empty: bool = False` (for negative samples)
  - `annotations: list[dict] = []`
  - `thumbnail_url: str = ""`

#### 1.13.3 Video Player Component ✅

- [x] **1.13.3.1** Add hidden `<video>` element for frame source
- [x] **1.13.3.2** Implement slider that controls video currentTime
- [x] **1.13.3.3** Add Play/Pause button with Space keyboard shortcut
- [x] **1.13.3.4** Add frame step buttons: `←/→` (±1 frame), `Shift+←/→` (±10 frames)
- [x] **1.13.3.5** Display current frame number and timestamp: `f:024 / 00:00.8s`
- [x] **1.13.3.6** Sync slider position with video playback

#### 1.13.4 Keyframe Marking ✅

- [x] **1.13.4.1** Implement "Mark Frame (K)" button:
  - Capture current frame via `canvas.drawImage(video, ...)`
  - Save frame image to R2: `datasets/{id}/keyframes/{video_id}_f{frame}.jpg`
  - Add to `keyframes` list
- [x] **1.13.4.2** Implement "Mark Empty (E)" button:
  - Same as Mark Frame but sets `is_empty = True`
  - Exports as empty `.txt` file (negative sample)
- [x] **1.13.4.3** Update left sidebar to show keyframes only:
  - Thumbnail + frame number + annotation count (or "empty")
  - Click to jump slider to that frame
- [x] **1.13.4.4** Auto-scroll sidebar when slider passes a keyframe
- [x] **1.13.4.5** Add visual markers on slider showing keyframe positions

### 1.14 YOLO Dataset ZIP Upload
- [x] **1.14.1** Implement `zip_processor.py` for extraction and parsing
- [x] **1.14.2** Add bulk image creation to `supabase_client.py`
- [x] **1.14.3** Implement project-level ZIP upload handler in `DatasetsState`
- [/] **1.14.4** Debug label parsing issue (wishlist #17)
- [ ] **1.14.5** Implement concurrent R2 uploads for faster import (wishlist #16)

#### 1.13.5 Annotation on Keyframes ✅

- [x] **1.13.5.1** Reuse existing canvas annotation logic (draw, select, resize, delete)
- [x] **1.13.5.2** Store annotations per keyframe (not per video)
- [x] **1.13.5.3** Implement autosave: annotations saved to R2 on keyframe change
- [x] **1.13.5.4** Load annotations when returning to a keyframe
- [x] **1.13.5.5** Sync annotation count in sidebar keyframe list

#### 1.13.6 Video Keyboard Shortcuts

- [/] **1.13.6.1** Update `/assets/labeling_shortcuts.js` for video mode (implemented but not triggering — see tech_debt.md):

| Key | Action |
|-----|--------|
| `Space` | Play/Pause video |
| `Z` | Previous frame (-1) |
| `C` | Next frame (+1) |
| `Shift+Z` | Jump back 10 frames |
| `Shift+C` | Jump forward 10 frames |
| `K` | Mark current frame for labeling |
| `E` | Mark current frame as empty |
| `V` | Select tool (existing) |
| `R` | Draw tool (existing) |
| `Delete` | Delete selected annotation (existing) |
| `?` | Show help overlay (existing) |

- [x] **1.13.6.2** Update help overlay to show video-specific shortcuts

> [!IMPORTANT]
> **Checkpoint 1.13**: Upload video → Mark keyframes → Draw boxes → Annotations persist per keyframe.

---

## 🧠 Phase 2: Training Pipeline

**Goal**: Enable GPU training on Modal (cloud) and bare metal (local RTX 3090), with a training dashboard for configuration, progress monitoring, and result analysis.

> [!NOTE]
> **Architecture**: Data assembly happens on Modal side (no download→zip→upload). Pass R2 presigned URLs directly to training function. Use YOLO11 for stability.

### 2.1 Database Schema Enhancement

**Goal**: Add tables and columns to support training runs, model versioning, and multi-target training.

#### 2.1.1 Training Runs Table

```sql
CREATE TABLE training_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,  -- Project-level training
    dataset_ids UUID[] DEFAULT '{}',  -- Selected datasets for this run
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,  -- Legacy/optional
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')),
    target TEXT DEFAULT 'cloud' CHECK (target IN ('cloud', 'local')),
    claimed_by TEXT,                -- machine_id for local training
    config JSONB NOT NULL,          -- {epochs, model_size, batch_size, augmentations}
    metrics JSONB,                  -- {mAP50, mAP50-95, precision, recall, train_time_s}
    artifacts_r2_prefix TEXT,       -- e.g., projects/{id}/runs/{run_id}/
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE training_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can CRUD own training runs" ON training_runs
    FOR ALL USING (
        project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
    );
```

- [x] **2.1.1.1** Run SQL in Supabase Dashboard
- [x] **2.1.1.2** Verify: Insert test row via SQL → Query from Python → Delete test row

#### 2.1.2 Models Table

```sql
CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    training_run_id UUID REFERENCES training_runs(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    weights_path TEXT NOT NULL,     -- R2 path to best.pt
    metrics JSONB,                  -- Copy of final metrics for quick access
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE models ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can CRUD own models" ON models
    FOR ALL USING (user_id = auth.uid());

-- Only one active model per dataset
CREATE UNIQUE INDEX models_one_active_per_dataset 
    ON models (dataset_id) WHERE is_active = TRUE;
```

- [x] **2.1.2.1** Run SQL in Supabase Dashboard
- [x] **2.1.2.2** Verify: Test unique constraint by trying to set two active models

#### 2.1.3 Profile & Dataset Enhancements

```sql
-- Profiles: Add usage tracking
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'free';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS api_key TEXT UNIQUE;

-- Datasets: Add training metadata
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS last_trained_at TIMESTAMPTZ;
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS active_model_id UUID REFERENCES models(id) ON DELETE SET NULL;
```

- [x] **2.1.3.1** Run SQL in Supabase Dashboard

> [!IMPORTANT]
> **Checkpoint 2.1**: All tables created. Test: Query `training_runs` and `models` from Python REPL.

---

### 2.2 Backend CRUD Operations

**Goal**: Add Supabase client functions for training runs and models.

#### 2.2.1 Training Runs CRUD

Add to `backend/supabase_client.py`:
- `create_training_run(dataset_id, user_id, config, target='cloud')` → returns run_id
- `get_training_run(run_id)` → returns run dict
- `get_dataset_training_runs(dataset_id)` → returns list of runs
- `update_training_run(run_id, **fields)` → update status, metrics, etc.
- `get_pending_local_runs(user_id)` → for bare metal polling
- `claim_training_run(run_id, machine_id)` → atomically claim

- [x] **2.2.1.1** Implement training run CRUD functions
- [x] **2.2.1.2** Test: Create run → Query → Update status → Verify

#### 2.2.2 Models CRUD

Add functions:
- `create_model(training_run_id, dataset_id, user_id, name, weights_path, metrics)`
- `get_dataset_models(dataset_id)` → list all models
- `set_active_model(model_id)` → deactivate others, activate this one
- `get_active_model(dataset_id)` → returns active model or None

- [x] **2.2.2.1** Implement model CRUD functions
- [x] **2.2.2.2** Test: Create model → Set active → Create another → Set active → Verify only one active

> [!IMPORTANT]
> **Checkpoint 2.2**: All CRUD operations work. Test via Python REPL.

---

### 2.3 Training Dashboard UI — Configuration

**Goal**: Create the training dashboard at **project level** with dataset selection and training configuration.

> [!NOTE]
> **Architecture Change**: Training is triggered at project level, not dataset level. Users select which datasets to include, enabling multi-dataset training.

#### 2.3.1 Training State

Create `modules/training/state.py`:

```python
class DatasetOption(BaseModel):
    id: str
    name: str
    type: str  # "image" or "video"
    labeled_count: int
    total_count: int
    is_selected: bool

class TrainingState(rx.State):
    current_project_id: str = ""
    project_name: str = ""
    
    # Datasets for selection
    datasets: list[DatasetOption] = []
    selected_dataset_ids: list[str] = []
    
    # Aggregated stats from selected datasets
    total_labeled_count: int = 0
    total_images_count: int = 0
    combined_classes: list[str] = []
    
    # Configuration
    epochs: int = 50
    model_size: str = "n"  # n/s/m/l
    batch_size: int = 16
    target: str = "cloud"  # cloud/local
    
    # Training runs history
    training_runs: list[TrainingRunModel] = []
    is_loading: bool = False
```

- [x] **2.3.1.1** Create `modules/training/state.py` with state class
- [x] **2.3.1.2** Implement `load_dashboard()` method with dataset loading

#### 2.3.2 Training Dashboard Page

Create `modules/training/dashboard.py`:
Route: `/projects/{project_id}/train` (project level)

Layout:
- **Header**: Breadcrumb (Projects > Project Name > Training)
- **Dataset Selection Card**: Checkboxes for each dataset, auto-selects those with labeled data
- **Aggregated Stats**: Total labeled/images across selected datasets
- **Configuration Card**:
  - Epochs slider (10-500, default 50)
  - Model size dropdown (nano/small/medium/large)
  - Batch size dropdown (8/16/32)
  - Target toggle: ☁️ Cloud (Modal) / 🖥️ Local (bare metal)
- **Start Training Button** (disabled if <1 labeled image selected)
- **Training History** section (per-project)

- [x] **2.3.2.1** Create dashboard page with layout
- [x] **2.3.2.2** Add route to `SAFARI.py`
- [x] **2.3.2.3** Add "Train" button to **project detail page** linking to dashboard
- [x] **2.3.2.4** Verify: Navigate to training dashboard → Select datasets → Adjust config

> [!IMPORTANT]
> **Checkpoint 2.3**: Training dashboard loads at project level, shows dataset selection, config controls work.

---

### 2.4 Modal Training Job (Cloud)

**Goal**: Implement the Modal GPU training function that fetches data from R2 and trains YOLO11.

#### 2.4.1 Modal Setup

- [x] **2.4.1.1** Verify Modal CLI installed: `modal --version`
- [x] **2.4.1.2** Authenticate if needed: `modal setup`

#### 2.4.2 Training Job Implementation

Create `backend/modal_jobs/train_job.py`:

```python
import modal

app = modal.App("yolo-training")

image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "ultralytics>=8.3.0",  # YOLO11
    "boto3",
    "supabase",
)

@app.function(
    image=image,
    gpu="T4",
    timeout=7200,  # 2 hours max
    secrets=[modal.Secret.from_name("r2-credentials"), modal.Secret.from_name("supabase-credentials")],
)
def train_yolo(
    run_id: str,
    project_id: str,           # Project-level training
    dataset_ids: list[str],    # Selected datasets
    image_urls: list[str],     # Presigned R2 URLs for images (aggregated from all datasets)
    label_urls: list[str],     # Presigned R2 URLs for labels
    classes: list[str],        # Combined class list
    config: dict,              # {epochs, model_size, batch_size}
):
    """
    1. Download images and labels from R2 URLs to /tmp/dataset/
    2. Generate data.yaml with 80/20 train/val split
    3. Run YOLO11 training
    4. Upload best.pt, last.pt, results.csv, results.png to R2 at projects/{id}/runs/{run_id}/
    5. Update training_run status in Supabase
    """
    pass
```

- [x] **2.4.2.1** Create `backend/modal_jobs/train_job.py` scaffold
- [x] **2.4.2.2** Implement data download from presigned URLs (parallel with ThreadPoolExecutor)
- [x] **2.4.2.3** Implement `data.yaml` generation with train/val split
- [x] **2.4.2.4** Implement YOLO11 training call
- [x] **2.4.2.5** Implement artifact upload to R2 (best.pt, last.pt, results.csv, results.png, confusion_matrix.png)
- [x] **2.4.2.6** Implement Supabase status updates

#### 2.4.3 Modal Secrets Setup

- [x] **2.4.3.1** Create `r2-credentials` secret in Modal Dashboard
- [x] **2.4.3.2** Create `supabase-credentials` secret in Modal Dashboard

#### 2.4.4 Deploy and Test

- [x] **2.4.4.1** Deploy Modal app: `modal deploy backend/modal_jobs/train_job.py`
- [x] **2.4.4.2** Test with minimal dataset (5 images, 2 classes, 5 epochs)
- [x] **2.4.4.3** Verify: Check R2 for uploaded `best.pt` and `results.csv`

> [!IMPORTANT]
> **Checkpoint 2.4**: Modal job runs end-to-end. Manually trigger → Training completes → Weights in R2.

---

### 2.5 Trigger Training from Dashboard

**Goal**: Connect the "Start Training" button to the Modal job.

#### 2.5.1 Start Training Handler

Add to `modules/training/state.py`:
1. Create `training_run` in Supabase with `project_id` and `dataset_ids` (status='pending')
2. Loop over selected datasets, aggregate presigned URLs for all labeled images + labels
3. If target='cloud': spawn Modal function with `f.spawn(...)`
4. If target='local': leave as 'pending' for polling client

- [x] **2.5.1.1** Implement `start_training()` method
- [x] **2.5.1.2** Add presigned URL generation for batch of images/labels across datasets
- [x] **2.5.1.3** Integrate Modal function spawn using `modal.Function.from_name()`
- [x] **2.5.1.4** Stream live logs from Modal to Supabase (`logs` column) & display in dashboard
- [x] **2.5.1.4** Stream live logs from Modal to Supabase (`logs` column) & display in dashboard

#### 2.5.2 Training Progress in UI

- [x] **2.5.2.1** Add training status indicator in dashboard
- [x] **2.5.2.2** Poll Supabase every 10 seconds while status='running'
- [x] **2.5.2.3** Show current epoch (if tracked in metrics JSONB)
- [x] **2.5.2.4** On completion: show success toast + refresh dashboard

> [!IMPORTANT]
> **Checkpoint 2.5**: Click "Start Training" → Modal job spawns → Status updates → Completion shown.

---

### 2.6 Training Results Display

**Goal**: Show training results, metrics charts, and download links.

#### 2.6.1 Results Card

When a training run completes, display:
- **Metrics Grid**: mAP@50, mAP@50-95, Precision, Recall
- **Training Time**: formatted duration
- **Download Links**: best.pt, last.pt (presigned URLs)

- [x] **2.6.1.1** Add results card component
- [x] **2.6.1.2** Generate presigned URLs for weight downloads

#### 2.6.2 Training Charts

Parse `results.csv` and display interactive charts:
- Loss curve (box_loss, cls_loss, dfl_loss)
- mAP curve over epochs
- Precision/Recall over epochs

- [x] **2.6.2.1** Fetch and parse `results.csv` from R2
- [x] **2.6.2.2** Create chart component (JS library or rx.recharts)
- [x] **2.6.2.3** Display charts in expandable section

#### 2.6.3 Training Artifacts Gallery

Display uploaded images:
- `results.png` — YOLO's summary image
- `confusion_matrix.png`
- `F1_curve.png`, `PR_curve.png`
- `labels.jpg` — class distribution

- [x] **2.6.3.1** Upload additional artifacts from Modal job
- [x] **2.6.3.2** Create image gallery component with lightbox

#### 2.6.4 Training History

List all training runs for this **project**:
- Date, status badge, selected datasets, epochs, model size, mAP score
- Click to expand details

- [x] **2.6.4.1** Implement training runs list component
- [x] **2.6.4.2** Add "Create Model" button to promote run to saved model

> [!IMPORTANT]
> **Checkpoint 2.6**: Training completes → Results card shows metrics → Charts render → Can download weights.

---

### 2.7 Bare Metal Training Client

**Goal**: Python script that polls Supabase for local training jobs and executes on RTX 3090.

#### 2.7.1 Client Script

Create `backend/local_trainer.py`:

```python
"""
Bare Metal Training Client
--------------------------
Polls Supabase every 30s for pending local training jobs.
Claims and executes training on local GPU.

Usage:
    python local_trainer.py --user-id <uuid> --machine-id rtx3090-home
"""

import argparse
import time

def poll_for_jobs(user_id: str, machine_id: str):
    while True:
        # 1. Query pending runs where target='local' and user_id matches
        # 2. If found, atomically claim with machine_id
        # 3. Download data from R2
        # 4. Run YOLO11 training
        # 5. Upload results to R2
        # 6. Update Supabase status
        time.sleep(30)
```

- [ ] **2.7.1.1** Create `backend/local_trainer.py` scaffold
- [ ] **2.7.1.2** Implement job polling with atomic claim
- [ ] **2.7.1.3** Implement data download (reuse presigned URLs from run config)
- [ ] **2.7.1.4** Implement training execution
- [ ] **2.7.1.5** Implement result upload and status update

#### 2.7.2 Client Distribution

- [ ] **2.7.2.1** Create `requirements-trainer.txt` with minimal deps
- [ ] **2.7.2.2** Test standalone: `python local_trainer.py --help`

> [!IMPORTANT]
> **Checkpoint 2.7**: Run client on RTX 3090 → Queue job in dashboard → Client picks up → Training completes → Weights uploaded.

---

### 2.8 Dashboard Hub

**Goal**: Create a command center landing page with project management and module navigation.

#### 2.8.1 Hub Page Design

Hub sections:
- **Project Manager**: List/Create/Edit/Delete projects, select active project
- **Labeling Studio** (context: active project): List datasets with direct annotation links
- **Training Pipeline** (context: active project): Go to training + recent runs preview
- **Inference API** (no project context): All models across projects (placeholder)

Navigation:
- **Nav Header**: Logo links back to `/dashboard`, breadcrumb slot, user menu
- **Active Project**: Persisted in localStorage (Supabase sync later)

- [x] **2.8.1.1** Implement hub page layout with stats and module cards (V1)
- [x] **2.8.1.2** Add stats queries (projects, datasets, images count)
- [x] **2.8.1.3** Add project manager section with active project selector
- [x] **2.8.1.4** Context-aware Labeling panel (datasets list for active project)
- [x] **2.8.1.5** Context-aware Training panel (recent runs for active project)
- [x] **2.8.1.6** Create `nav_header.py` component with dashboard link
- [x] **2.8.1.7** Integrate nav_header into all authenticated pages

> [!NOTE]
> **Future Enhancement**: Sync active project to Supabase profiles table for cross-device persistence.

> [!NOTE]
> **Future Enhancement (Phase 3)**: Add Model counts to Quick Stats row after model versioning is implemented.

> [!IMPORTANT]
> **Checkpoint 2.8**: Select project → Labeling shows datasets → Training shows runs → Click logo from any page returns to hub.

---

## ⚡ Phase 3: Inference & API

**Goal**: Use trained models for predictions with minimal latency.

### 3.1 Inference Modal Function

- [x] **3.1.1** Create `backend/modal_jobs/infer_job.py`:

```python
import modal

app = modal.App("yolo-inference")

image = modal.Image.debian_slim().pip_install("ultralytics", "boto3")

@app.cls(
    image=image,
    gpu="T4",
    keep_warm=1  # Keep one GPU instance ready
)
class YOLOInference:
    def __init__(self, model_path: str, r2_config: dict):
        self.model_path = model_path
        self.r2_config = r2_config
    
    @modal.enter()
    def load_model(self):
        # Download model from R2 and load into YOLO
        from ultralytics import YOLO
        # ... download best.pt ...
        self.model = YOLO("/tmp/best.pt")
    
    @modal.method()
    def predict(self, image_bytes: bytes) -> list[dict]:
        results = self.model.predict(image_bytes)
        return [
            {"class": r.cls, "box": r.xyxy, "confidence": r.conf}
            for r in results[0].boxes
        ]
```

- [x] **3.1.2** Deploy: `modal deploy backend/modal_jobs/infer_job.py`
- [x] **3.1.3** Verify: Call deployed function with test image → Returns predictions

> [!IMPORTANT]
> **Checkpoint 3.1**: Deploy inference function → Send test image via Python → Receive bounding box predictions.

### 3.2 Playground UI

- [x] **3.2.1** Create `modules/inference/playground.py` page
- [x] **3.2.2** Layout: Left half = upload zone, Right half = result canvas
- [x] **3.2.3** Reuse canvas component from Phase 1 (read-only mode)
- [x] **3.2.4** On image upload:
  - Show uploaded image in left panel
  - Send to Modal function
  - Display loading spinner
- [x] **3.2.5** On result received:
  - Draw boxes on right panel canvas
  - Show confidence scores
  - List detections below canvas
- [x] **3.2.6** Add "Download Results" button (JSON format)
- [x] **3.2.7** Verify: Full playground flow works

> [!IMPORTANT]
> **Checkpoint 3.2**: Upload image in playground → Boxes appear on canvas → Download JSON → Data matches predictions.

### 3.3 API Access

- [ ] **3.3.1** Create `api_keys` table in Supabase:

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id),
    key_hash TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE
);
```

- [ ] **3.3.2** Create Settings page with "Generate API Key" button
- [ ] **3.3.3** Show key only once on generation (security)
- [ ] **3.3.4** Display usage documentation:

```bash
curl -X POST "https://your-modal-endpoint/predict" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "image=@photo.jpg"
```

- [ ] **3.3.5** Implement key validation in Modal inference function
- [ ] **3.3.6** Verify: API access works with generated key

> [!IMPORTANT]
> **Checkpoint 3.3**: Generate API key → Make curl request → Receive predictions → Key shows in usage list.

### 3.4 Inference Results & Model Comparison System

**Goal**: Transform playground into a comprehensive model testing and comparison tool with persistent results.

**Architecture**: 
- Save **labels only** (not rendered videos) for cost efficiency and flexibility
- Render labels dynamically during playback with full style control
- Enable future multi-model comparison on same video
- Support both images and videos with smart format detection

---

#### 3.4.1 Database Schema for Inference Results

**Goal**: Track all inference runs with metadata for comparison and replay.

**Create `inference_results` table**:

```sql
CREATE TABLE inference_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,  -- NULL if built-in model
    model_name TEXT NOT NULL,  -- e.g., "yolo11s.pt" or custom model name
    
    -- Input metadata
    input_type TEXT NOT NULL CHECK (input_type IN ('image', 'video')),
    input_filename TEXT NOT NULL,
    input_r2_path TEXT NOT NULL,
    
    -- Video-specific fields
    video_start_time FLOAT,  -- NULL for images, seconds for video clips
    video_end_time FLOAT,    -- NULL for images, seconds for video clips
    video_fps FLOAT,         -- NULL for images
    video_total_frames INTEGER,  -- NULL for images
    
    -- Inference configuration
    confidence_threshold FLOAT NOT NULL DEFAULT 0.25,
    
    -- Results storage
    predictions_json JSONB NOT NULL,  -- Array of frame predictions for videos, single array for images
    labels_r2_path TEXT,  -- Path to YOLO format labels (for images) or per-frame labels (for videos)
    
    -- Metadata
    inference_duration_ms INTEGER,  -- How long inference took
    detection_count INTEGER,  -- Total detections across all frames
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_inference_results_user_id ON inference_results(user_id);
CREATE INDEX idx_inference_results_model_id ON inference_results(model_id);
CREATE INDEX idx_inference_results_created_at ON inference_results(created_at DESC);
CREATE INDEX idx_inference_results_input_type ON inference_results(input_type);

ALTER TABLE inference_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own inference results" ON inference_results
    FOR ALL USING (auth.uid() = user_id);
```

**Create `models` table** (if not exists from Phase 2):

```sql
CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    training_run_id UUID REFERENCES training_runs(id) ON DELETE SET NULL,
    
    name TEXT NOT NULL,
    description TEXT,
    model_size TEXT,  -- 'n', 's', 'm', 'l', 'x'
    
    -- Storage
    weights_r2_path TEXT NOT NULL,  -- Path to .pt file
    
    -- Metadata
    is_active BOOLEAN DEFAULT FALSE,  -- Active model for project
    classes TEXT[] NOT NULL,
    metrics JSONB,  -- {mAP50: 0.85, mAP50_95: 0.72, ...}
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_models_user_id ON models(user_id);
CREATE INDEX idx_models_project_id ON models(project_id);

ALTER TABLE models ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own models" ON models
    FOR ALL USING (auth.uid() = user_id);
```

- [ ] **3.4.1.1** Run SQL to create `inference_results` table in Supabase
- [ ] **3.4.1.2** Run SQL to create `models` table (if not exists)
- [ ] **3.4.1.3** Verify tables and indexes in Supabase dashboard

> [!IMPORTANT]
> **Checkpoint 3.4.1**: Tables created, RLS policies active, indexes exist.

---

#### 3.4.2 Backend Functions for Inference Results

**Goal**: CRUD operations for inference results and model management.

**Add to `backend/supabase_client.py`**:

```python
# ============================================================================
# Inference Results
# ============================================================================

def create_inference_result(
    user_id: str,
    model_id: str | None,
    model_name: str,
    input_type: str,
    input_filename: str,
    input_r2_path: str,
    predictions_json: dict,
    confidence_threshold: float,
    labels_r2_path: str | None = None,
    video_start_time: float | None = None,
    video_end_time: float | None = None,
    video_fps: float | None = None,
    video_total_frames: int | None = None,
    inference_duration_ms: int | None = None,
    detection_count: int | None = None,
) -> dict:
    """Create new inference result record."""
    pass

def get_user_inference_results(user_id: str, limit: int = 50) -> list[dict]:
    """Get user's inference results, most recent first."""
    pass

def get_inference_result(result_id: str) -> dict:
    """Get single inference result by ID."""
    pass

def delete_inference_result(result_id: str) -> None:
    """Delete inference result (also clean up R2 files)."""
    pass

def get_inference_results_by_model(model_id: str) -> list[dict]:
    """Get all inference results for a specific model."""
    pass

# ============================================================================
# Models
# ============================================================================

def create_model_from_training_run(
    user_id: str,
    project_id: str,
    training_run_id: str,
    name: str,
    description: str | None = None,
) -> dict:
    """Promote training run to saved model."""
    pass

def get_user_models(user_id: str) -> list[dict]:
    """Get all saved models for user."""
    pass

def get_project_models(project_id: str) -> list[dict]:
    """Get all models for a project."""
    pass

def set_active_model(model_id: str, project_id: str) -> dict:
    """Set a model as active (unsets others in same project)."""
    pass

def delete_model(model_id: str) -> None:
    """Delete model (keeps training run)."""
    pass
```

- [ ] **3.4.2.1** Implement inference result CRUD functions
- [ ] **3.4.2.2** Implement model management functions
- [ ] **3.4.2.3** Test in Python REPL: create inference result → fetch → verify fields
- [ ] **3.4.2.4** Test model functions: create from training run → set active → verify

> [!IMPORTANT]
> **Checkpoint 3.4.2**: All backend functions working in REPL, data persists correctly.

---

#### 3.4.3 Modal Function Updates - Built-in Models & Video Support

**Goal**: Support YOLO11 built-in models and video inference with label output.

**Update `backend/modal_jobs/infer_job.py`**:

Key changes:
1. Accept `model_type` param: `"builtin"` or `"custom"`
2. For built-in: use `YOLO("yolo11s.pt")` directly (downloads from Ultralytics)
3. For custom: download from R2 as before
4. Add video inference support
5. Return labels in YOLO format instead of annotated images/videos

```python
import modal
from pathlib import Path
import json

app = modal.App("yolo-inference")

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg")  # For video trimming, metadata extraction, thumbnails
    .pip_install("ultralytics", "boto3")
)

@app.cls(
    image=image,
    gpu="T4",
    timeout=600,  # 10 minutes for video processing
)
class YOLOInference:
    def __init__(self, model_config: dict, r2_config: dict):
        """
        model_config: {
            "type": "builtin" | "custom",
            "name": "yolo11s.pt" | custom model name,
            "r2_path": str (only for custom),
        }
        """
        import boto3
        from ultralytics import YOLO
        
        self.r2_config = r2_config
        self.s3_client = boto3.client(
            's3',
            endpoint_url=r2_config['endpoint_url'],
            aws_access_key_id=r2_config['access_key_id'],
            aws_secret_access_key=r2_config['secret_access_key'],
        )
        self.bucket = r2_config['bucket_name']
        
        # Load model
        if model_config["type"] == "builtin":
            # Use Ultralytics hub models (auto-downloads)
            self.model = YOLO(model_config["name"])
        else:
            # Download custom model from R2
            model_path = Path(f"/tmp/{model_config['name']}")
            self.s3_client.download_file(
                self.bucket,
                model_config["r2_path"],
                str(model_path)
            )
            self.model = YOLO(str(model_path))
    
    @modal.method()
    def predict_image(
        self,
        image_url: str,
        confidence: float = 0.25,
        save_labels: bool = True,
    ) -> dict:
        """
        Run inference on single image.
        
        Returns:
            {
                "predictions": [...],  # List of detections
                "labels_txt": "0 0.5 0.5 0.2 0.3\\n1 0.7 0.3 0.1 0.15",  # YOLO format
                "detection_count": 2,
            }
        """
        pass
    
    @modal.method()
    def predict_video(
        self,
        video_url: str,
        confidence: float = 0.25,
        start_frame: int = 0,
        end_frame: int | None = None,
        frame_skip: int = 1,  # Process every Nth frame
    ) -> dict:
        """
        Run inference on video frames.
        
        Returns:
            {
                "predictions_by_frame": {
                    "0": [...],
                    "5": [...],
                    ...
                },
                "labels_by_frame": {
                    "0": "0 0.5 0.5 0.2 0.3",
                    "5": "",
                    ...
                },
                "total_frames_processed": 120,
                "total_detections": 45,
                "fps": 30.0,
            }
        """
        pass
```

**Implementation steps**:

- [ ] **3.4.3.1** Update Modal image with ffmpeg (via apt_install) for video trimming and metadata extraction
- [ ] **3.4.3.2** Implement built-in model support in `__init__`
- [ ] **3.4.3.3** Implement `predict_image()` method with YOLO format label output
- [ ] **3.4.3.4** Test image inference: `modal run infer_job.py --model yolo11s.pt --image test.jpg`
- [ ] **3.4.3.5** Verify label format matches YOLO spec (class_id x_center y_center width height)
- [ ] **3.4.3.6** Implement `predict_video()` method with frame extraction and batch processing
- [ ] **3.4.3.7** Add frame skip logic to reduce processing cost
- [ ] **3.4.3.8** Test video inference with sample video (10 seconds, 30fps)
- [ ] **3.4.3.9** Deploy Modal app: `modal deploy backend/modal_jobs/infer_job.py`

> [!TIP]
> YOLO format: `class_id x_center y_center width height` (all normalized 0-1)

> [!IMPORTANT]
> **Checkpoint 3.4.3**: Image inference works with YOLO11s → Video inference processes frames → Labels in correct format.

---

#### 3.4.4 Playground Multi-Format Upload & Format Detection

**Goal**: Accept images AND videos in playground, detect format, route to correct inference method.

**Update `modules/inference/state.py`**:

```python
class InferenceState(rx.State):
    # Existing fields...
    uploaded_file_type: str = ""  # "image" | "video"
    uploaded_video_duration: float = 0.0
    uploaded_video_fps: float = 0.0
    
    # Video time range selection
    video_start_time: float = 0.0
    video_end_time: float = 0.0
    enable_frame_skip: bool = True
    frame_skip_interval: int = 5  # Process every 5th frame
    
    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle image or video upload with format detection."""
        if not files:
            return
        
        file = files[0]
        filename = file.filename.lower()
        
        # Detect file type
        if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            self.uploaded_file_type = "image"
            await self._handle_image_upload(file)
        elif filename.endswith(('.mp4', '.mov', '.avi', '.webm')):
            self.uploaded_file_type = "video"
            await self._handle_video_upload(file)
        else:
            self.prediction_error = "Unsupported file format"
            return
    
    async def _handle_image_upload(self, file: rx.UploadFile):
        """Process image upload."""
        # Existing image upload logic...
        pass
    
    async def _handle_video_upload(self, file: rx.UploadFile):
        """Process video upload and extract metadata."""
        # 1. Upload to R2
        # 2. Extract duration, fps using ffprobe (if available) or OpenCV
        # 3. Set video_end_time = duration (default to full video)
        # 4. Generate thumbnail from first frame
        pass
    
    async def run_inference(self):
        """Route to image or video inference based on file type."""
        if self.uploaded_file_type == "image":
            await self._run_image_inference()
        elif self.uploaded_file_type == "video":
            await self._run_video_inference()
    
    async def _run_image_inference(self):
        """Run inference on image, save results to DB."""
        # 1. Call Modal predict_image
        # 2. Save labels to R2
        # 3. Create inference_result record
        # 4. Store result_id for playback
        pass
    
    async def _run_video_inference(self):
        """Run inference on video frames, save labels per frame."""
        # 1. Calculate start/end frames from time range
        # 2. Call Modal predict_video with frame range and skip
        # 3. Save labels_by_frame as JSON to R2
        # 4. Create inference_result record
        # 5. Store result_id for playback
        pass
```

- [x] **3.4.4.1** Add file type detection logic to upload handler
- [x] **3.4.4.2** Implement video metadata extraction (duration, fps)
- [x] **3.4.4.3** Add time range selection UI components (start/end sliders)
- [x] **3.4.4.4** Add frame skip toggle and interval selector
- [x] **3.4.4.5** Update upload zone to accept both images and videos
- [x] **3.4.4.6** Implement `_run_image_inference()` with result persistence
- [x] **3.4.4.7** Implement `_run_video_inference()` with frame range calculation
- [x] **3.4.4.8** Test: Upload image → Run inference → Check DB for result record
- [x] **3.4.4.9** Test: Upload video → Select 5-10s range → Run inference → Verify frame range

> [!TIP]
> Use ffprobe for video metadata: `ffprobe -v quiet -print_format json -show_format video.mp4`

> [!IMPORTANT]
> **Checkpoint 3.4.4**: Both image and video uploads work → Format detection correct → Results saved to DB.

---

#### 3.4.5 Video Playback with Dynamic Label Rendering

**Goal**: Render YOLO labels on video during playback in playground results panel.

**Architecture Overview**:
- HTML5 `<video>` element for playback
- HTML5 `<canvas>` overlay for drawing bounding boxes
- JavaScript syncs canvas drawing with video `timeupdate` event
- Load labels from R2, parse JSON, cache in state

**Implementation Guidelines**:

1. **Component Structure** (`modules/inference/video_player.py`):
   - Create video player component with canvas overlay
   - Use `rx.el.video()` with ID for JavaScript access
   - Overlay canvas with same dimensions, absolute positioning
   - Add info overlay (model name, confidence, frame number)

2. **State Management** (`modules/inference/state.py`):
   - Add result playback state: `current_result_id`, `current_result_video_url`, `current_result_model_name`
   - Add frame tracking: `current_frame_number`, `labels_by_frame: dict[int, list[dict]]`
   - Implement `load_inference_result(result_id)` to:
     - Fetch result from Supabase
     - Generate presigned URL for video
     - Load labels JSON from R2 and parse
   - Handle `on_video_time_update` event to calculate frame number and trigger redraw

3. **JavaScript Canvas Drawing** (`assets/inference_player.js`):
   - Create `drawLabelsOnCanvas()` function
   - Match canvas size to video dimensions
   - Get current frame labels from window state
   - **CRITICAL**: Box coordinates from Modal are **NORMALIZED** (0-1 range)
   - **Transform before drawing**: Multiply x/y/width/height by canvas dimensions
   - **Be careful with rect scaling**: Account for any canvas CSS scaling or transformations
   - Draw boxes with stroke, add label background and text
   - Attach to video `timeupdate` and `seeked` events

4. **Coordinate Transformation Pattern**:
   ```javascript
   // Labels from Modal inference are normalized [0-1]
   // Must transform to canvas pixel coordinates
   const x = label.x * canvas.width;  // NOT css width!
   const y = label.y * canvas.height; // NOT css height!
   const w = label.width * canvas.width;
   const h = label.height * canvas.height;
   ```

5. **Playback Controls**:
   - Play/Pause button with Space keyboard shortcut
   - Speed control (0.25x, 0.5x, 1x, 2x)
   - Frame step buttons (±1 frame, ±10 frames with Shift)

> [!WARNING]
> **Coordinate Normalization**: Box coordinates from Modal are normalized (0-1). Transform to pixel coordinates by multiplying by canvas dimensions. Do NOT use CSS dimensions if canvas is scaled.

> [!TIP]
> Use `requestAnimationFrame()` for smooth canvas updates during playback. Cache labels by frame to avoid repeated parsing.

**Task Checklist**:

- [x] **3.4.5.1** Create video player component with canvas overlay
- [x] **3.4.5.2** Implement `load_inference_result()` to fetch and parse labels
- [x] **3.4.5.3** Create JavaScript canvas drawing logic with proper coordinate transformation
- [x] **3.4.5.4** Sync video time with frame number calculation
- [x] **3.4.5.5** Test: Load video result → Play → Boxes render at correct positions
- [x] **3.4.5.6** Test: Seek to different timestamp → Boxes update correctly
- [x] **3.4.5.7** Add playback controls (play/pause, speed, frame step)
- [x] **3.4.5.8** Add info overlay with model name and confidence

> [!IMPORTANT]
> **Checkpoint 3.4.5**: Video plays with synchronized bounding boxes → Seeking works → Labels show correct info.

---

#### 3.4.6 Inference Results Gallery

**Goal**: Browse historical inference results, filter by type/model, replay any result.

**Implementation Guidelines**:

1. **Gallery UI** (`modules/inference/results_gallery.py`):
   - Create header with "Inference History" heading
   - Add two filter dropdowns: type (All/Images/Videos) and model
   - Display results in responsive grid (3 columns desktop, 1 mobile)
   - Use `rx.foreach()` to render result cards

2. **Result Card Component**:
   - Show thumbnail (video first frame or image with boxes preview)
   - Display metadata: model name, detection count, timestamp
   - Add "View" button → loads result in video player (3.4.5)
   - Add "Delete" button → confirmation modal → cleanup
   - Card styling: BG_SECONDARY, hover elevation, border radius

3. **State Management** (`modules/inference/state.py`):
   - Add `inference_results: list[dict]` and `filtered_results: list[dict]`
   - Implement `load_results_gallery()` to fetch from Supabase:
     - Query `inference_results` table ordered by created_at DESC
     - Generate presigned URLs for thumbnails
     - Cache in state
   - Implement filter methods:
     - `filter_results_by_type(file_type: str)` → filter by media type
     - `filter_results_by_model(model_name: str)` → filter by model
   - Implement `delete_result(result_id: str)`:
     - Delete row from Supabase
     - Delete input file from R2 (`inference_inputs/{result_id}.*`)
     - Delete labels JSON from R2 (`inference_results/{result_id}.json`)
     - Refresh gallery state

4. **Pagination**:
   - Show 20 results per page
   - Add Previous/Next buttons at bottom
   - Display page indicator (Page X of Y)

5. **Empty State**:
   - If no results: show illustration + "No inference results yet"
   - CTA button → "Run Inference" (redirect to playground)

> [!TIP]
> Reuse the result card component from the playground results panel for consistency.

**Task Checklist**:

- [ ] **3.4.6.1** Create results gallery UI layout
- [ ] **3.4.6.2** Implement result card component with thumbnail and metadata
- [ ] **3.4.6.3** Implement `load_results_gallery()` method
- [ ] **3.4.6.4** Add filter logic (by type and model)
- [ ] **3.4.6.5** Implement delete functionality with R2 cleanup
- [ ] **3.4.6.6** Add pagination (show 20 results per page)
- [ ] **3.4.6.7** Test: Create 3 inference results → Gallery shows all → Filters work
- [ ] **3.4.6.8** Test: Click "View" → Loads result in player correctly
- [ ] **3.4.6.9** Test: Delete result → Removed from gallery and DB

> [!IMPORTANT]
> **Checkpoint 3.4.6**: Gallery displays all results → Filters work → View/Delete actions functional.

---

#### 3.4.7 YOLO11-Small Built-in Model Testing

**Goal**: Verify entire flow with YOLO11s built-in model before custom models.

**Test Checklist**:

- [ ] **3.4.7.1** Update playground model selector to include built-in models:
  - `yolo11n.pt` (Nano - fastest)
  - `yolo11s.pt` (Small - balanced)
  - `yolo11m.pt` (Medium - accurate)
- [ ] **3.4.7.2** Test image inference with YOLO11s:
  - Upload test image with common objects (person, car, dog)
  - Run inference
  - Verify detections are accurate
  - Check labels saved to R2
  - Verify DB record created
- [ ] **3.4.7.3** Test video inference with YOLO11s:
  - Upload 10-second test video
  - Select 5-second range (2s-7s)
  - Enable frame skip (every 5th frame)
  - Run inference
  - Verify processing time is reasonable
  - Check labels_by_frame saved correctly
- [ ] **3.4.7.4** Test video playback:
  - Load video result from gallery
  - Play video
  - Verify bounding boxes appear and track objects
  - Test seeking to different timestamps
- [ ] **3.4.7.5** Test model comparison foundation:
  - Run same video with YOLO11n (fast, less accurate)
  - Run same video with YOLO11m (slow, more accurate)
  - Compare detection counts in gallery
  - Verify each result stored separately with correct model name
- [ ] **3.4.7.6** Performance validation:
  - Measure Modal cold start time
  - Measure inference time for 10s video
  - Estimate cost per inference
  - Document in tech_debt.md if optimizations needed

> [!TIP]
> Use COCO dataset sample images/videos for testing (freely available, well-labeled).

> [!IMPORTANT]
> **Checkpoint 3.4.7**: Full flow works end-to-end with YOLO11s → Image + video inference → Playback with labels → Multiple results stored.

---

### Phase 3.4 Completion Criteria

✅ **Database**: Tables created, RLS policies working  
✅ **Backend**: All CRUD functions implemented and tested  
✅ **Modal**: Image + video inference with label output  
✅ **Playground**: Multi-format upload with format detection  
✅ **Playback**: Video rendering with synchronized labels  
✅ **Gallery**: Browse, filter, view, delete results  
✅ **Testing**: YOLO11s working for both images and videos  

**Next Steps** (Future Phases):
- Custom model integration (use trained models from Phase 2)
- Multi-model comparison view (render labels from 2+ models on same video)
- Export annotations (convert inference results to training datasets)
- Performance optimizations (batch processing, caching)

> [!NOTE]
> **Tech Debt**: Storage limits and cost management - see `.agent/tech_debt.md`

---

## 📋 Environment Variables Reference

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Cloudflare R2
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
R2_BUCKET_NAME=your-bucket-name

# Modal (configured via 'modal setup', no env var needed)
```

---

## 🔧 Troubleshooting Guide

| Issue | Cause | Solution |
|-------|-------|----------|
| `modal` import errors in Reflex | Direct import of Modal-decorated functions | Use `modal.Function.lookup()` instead |
| Supabase 401/403 errors | RLS policies blocking queries | Check policies, or use service key for backend |
| R2 403 errors | CORS or credential issues | Verify CORS policy in R2 dashboard, check keys |
| Canvas not rendering | Missing `rx.el.canvas` or JS not loaded | Ensure canvas element has `id` and JS script runs after DOM ready |
| Training OOM on Modal | Dataset too large for GPU | Use `a10g` or `a100`, or reduce batch size |
| Slow inference | Cold start (no warm instances) | Use `keep_warm=1` in Modal decorator |
| Boxes not scaling on resize | Using pixel coordinates | Always use percentage-based positioning |

---

## 📦 Dependencies

### Python (`requirements.txt`)

```
reflex>=0.6.0
supabase
boto3
python-dotenv
ultralytics  # For local testing; Modal handles this in cloud
```

### JavaScript (`package.json` additions)

```json
{
  // No external dependencies required for labeling
  // Custom canvas solution is fully Python-driven
}
```

---

## 💡 Best Practices Summary

1. **Never import Modal in Reflex files** — use `modal.Function.from_name()` at runtime
2. **Always use presigned URLs** for R2 images — never serve through Reflex backend
3. **Store all styles in `styles.py`** — single source of truth prevents inconsistency
4. **Optimistic UI updates** — show loading states immediately, confirm with backend
5. **Test each checkpoint** before moving to the next phase
6. **Use UUIDs for all file uploads** — prevents naming conflicts and security issues
7. **Keep Modal functions stateless** — pass all config (R2 keys, project ID) as arguments
