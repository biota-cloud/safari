# 🦁 SAFARI Migration Roadmap — From Tyto POC to User Acceptance Testing

> **SAFARI** — Sistema de Armadilhagem Fotográfica e Análise Inteligente  
> **Stack**: Reflex (UI), Modal (GPU Compute), Cloudflare R2 (Storage), Supabase (Auth/DB)  
> **Goal**: Migrate from single-user POC to multi-user test deployment behind Tailscale  

---

> [!IMPORTANT]
> ## 📍 Current Focus
> **Completed**: Phase 0 ✅ + Phase 2 ✅ + Phase 3 ✅ (Rebrand, DB Security, Style Migration)  
> **In progress**: Phase 5 — Documentation Update (starting with 5.1 File Map audit)  
> **Remaining**: 3.6.6 (full end-to-end walkthrough test)  
> **Deferred**: Phase 1 — Credential Migration (blocked on company credentials)  
> **Strategy**: File-map → Architecture → API rebrand → Remaining docs → New docs → Index restructure  

---

## 🔍 Codebase Audit Summary

Deep analysis of the full codebase identified the following migration surface:

### Branding Footprint ("Tyto" references — 50+ files)
| Area | Files | Impact |
|------|-------|--------|
| App entry | `rxconfig.py`, `Tyto/Tyto.py` | `app_name="Tyto"`, folder name, docstrings |
| UI text | `nav_header.py`, `login.py`, `dashboard.py` | Logo text "Tyto", page titles "Login \| Tyto" |
| JS / Client | `session_manager.js`, `Tyto/Tyto.py` | localStorage keys `tyto_*`, console `[Tyto]`, hardcoded Supabase URL + anon key |
| API Server | `backend/api/server.py` | FastAPI title "Tyto Inference API", CORS origins `tyto.app` |
| Modal Jobs | 4 Modal apps | `tyto-api-inference`, `tyto-api-server`, `yolo-training`, `yolo-inference` |
| Deployment | `Caddyfile`, systemd service | Domain `safari.yourdomain.com`, log paths |
| Docs | All roadmaps, READMEs, architecture docs | References throughout |
| Backend | `backend/__init__.py`, docstrings | Package-level docstrings |

### Multi-User Gaps (Critical for sharing)
| Gap | Current State | Needed |
|-----|---------------|--------|
| Project ownership | `projects.user_id` — single owner | Company projects with team assignments |
| RLS policies | `auth.uid() = user_id` everywhere | Role-based access (admin, member) |
| No roles table | — | `profiles.role` or separate `user_roles` table |
| No project membership | — | `project_members` junction table |
| Data isolation | All data scoped to `auth.uid()` | Shared data for company projects |

### Security Concerns
| Issue | Location | Severity |
|-------|----------|----------|
| Hardcoded Supabase anon key | `session_manager.js` line 57 | 🔴 High — must update to company key |
| Hardcoded Supabase URL | `session_manager.js` line 13 | 🔴 High — must update to company URL |
| No service role key in `.env` | `.env` has anon key only | 🟡 Medium — API server needs service role |
| API key prefix `tyto_` | `migrations/001_api_tables.sql` | 🟡 Medium — rebrand prefix |
| Single-user RLS | All tables | 🟡 Medium — safe with Tailscale, but needs fixing |

### Credential Inventory (to migrate)
| Service | Current Account | Config Location |
|---------|----------------|-----------------| 
| Supabase | Personal (`ouojaevwjurjvofxfvsr`) | `.env`, `session_manager.js` (hardcoded!) |
| Cloudflare R2 | Personal (`426a1ea...`) | `.env` |
| Modal | Personal (CLI config) | `~/.modal.toml`, Modal dashboard secrets |
| GitHub | Personal repo | Git remote |

---

## 🏗️ Phase 0: Quick Wins & Cosmetic Rebrand

**Goal**: Visible rebrand with zero functional risk. Users see "SAFARI" from day one.  
**Estimated effort**: 1 session  
**Risk**: None — purely cosmetic  

### 0.1 App Name & Folder Rename

- [x] **0.1.1** Rename `Tyto/Tyto.py` → `safari/safari.py` (lowercase per PEP 8)
- [x] **0.1.2** Update `rxconfig.py`: `app_name="safari"`
- [x] **0.1.3** Update `Tyto/__init__.py` → `safari/__init__.py`
- [x] **0.1.4** Global find-replace in Python docstrings: "Tyto" → "SAFARI" (19 files)
- [x] **0.1.5** Test: `pytest` — 144 passed, 15 skipped, 0 failures

> [!TIP]
> **Test checkpoint**: App starts, no import errors, pages load at localhost.

### 0.2 UI Branding

> **Logo assets are in `assets/branding/`** — see [design reference](file:///Users/jorge/PycharmProjects/Tyto/docs/design/safari_design_reference.md)

- [x] **0.2.1** `nav_header.py`: CSS-recreated `[ ● S A F A R I ]` logo mark on brown header
- [x] **0.2.2** `nav_header.py`: Brown header bar (`#4A3728`), white logo text, user menu
- [x] **0.2.3** `login.py`: **Split-panel login layout** — form on left (cream bg), hero wildlife photo on right
- [x] **0.2.4** `login.py`: Large SAFARI logo, Portuguese tagline, green CTA button, Material-outlined inputs
- [x] **0.2.5** All 7 pages: Updated titles `"* | Tyto"` → `"* | SAFARI"`
- [x] **0.2.6** `assets/favicon.ico`: Generated SAFARI `[●]` mark favicon via Pillow
- [x] **0.2.7** Test: `pytest` — 144 passed, 15 skipped, 0 failures

> [!TIP]
> **Test checkpoint**: Login page displays SAFARI split-panel layout. Nav header shows brown bar with white `[●] SAFARI` logo.

### 0.3 JS Client Branding

- [x] **0.3.1** `session_manager.js`: All `[Tyto Session]` → `[SAFARI Session]`, all `tyto_*` → `safari_*`
- [x] **0.3.2** `safari/safari.py`: localStorage keys `tyto_*` → `safari_*`, console logs `[Tyto]` → `[SAFARI]`
- [x] **0.3.3** `app_state.py`: All 33 localStorage key references updated `tyto_*` → `safari_*`, 8 console prefixes
- [x] **0.3.4** `session_manager.js`: `clearStoredTokens()` updated to `safari_*` keys
- [x] **0.3.5** `login.py`: Session restore script keys updated, console log updated
- [x] **0.3.6** Test: `pytest` — 144 passed, 15 skipped, 0 failures

> [!WARNING]
> **Breaking change**: Existing sessions will be invalidated (old `tyto_*` keys won't be found). Users must re-login. This is acceptable for a POC→test migration.

### 0.4 Deployment Files Rebrand

- [x] **0.4.1** ~~`Dockerfile`~~: Rebranded, but Docker approach later dropped (see Phase 4.2 decision)
- [x] **0.4.2** ~~`docker-compose.yml`~~: Rebranded, but Docker approach later dropped
- [x] **0.4.3** `Caddyfile`: Domain, proxy targets, log path all rebranded
- [x] ~~**0.4.4**~~ `.env.production.example`: Updated in Phase 5.5
- [x] **0.4.5** `docs/deployment/hetzner_deployment.md`: Full rebrand pass
- [x] **0.4.6** Test: `pytest` — 144 passed, 15 skipped, 0 failures

> [!NOTE]
> **Decision (2026-02-27)**: Docker removed from deployment. Single Reflex app on a single VPS behind Tailscale doesn't need containerization. Using systemd + native Caddy instead. See Phase 4.2.

---

## 🏗️ Phase 1: Credential Migration to Company Accounts

> [!NOTE]
> **⏸️ DEFERRED** — Blocked on company credentials. Phase 2 proceeds first on the current personal Supabase. When credentials arrive, use the [Schema Transition Playbook](#-schema-transition-playbook) to migrate.

**Goal**: All external services run on company credentials, personal accounts fully decoupled.  
**Estimated effort**: 1 session  
**Risk**: Low — mostly configuration, but **must be done carefully to avoid data loss**  

### 1.1 Supabase Migration

> [!CAUTION]
> **Data migration required**. The new Supabase project will have empty tables. Schema and data must be migrated.

- [ ] **1.1.1** Create new Supabase project under company account
- [ ] **1.1.2** Export current database schema (all tables, views, functions, triggers, RLS policies)
- [ ] **1.1.3** Run schema creation scripts in new Supabase project SQL editor
- [ ] **1.1.4** Migrate existing data if needed (users, projects, datasets, training runs, models)
- [ ] **1.1.5** Create user accounts for test users in new Supabase Auth
- [ ] **1.1.6** Update `.env`: `SUPABASE_URL`, `SUPABASE_KEY` → new project values
- [ ] **1.1.7** 🔴 **Critical**: Update `session_manager.js` hardcoded values:
  - Line 13: `SUPABASE_URL` constant
  - Line 57: `apikey` header (anon key)
- [ ] **1.1.8** Update `.env.production.example` with new placeholder values
- [x] **1.1.9** **Implement server-injected config** — ✅ Replaced hardcoded Supabase URL/key in `session_manager.js` with a `window.__SAFARI_CONFIG` object injected by `safari.py` via `rx.script()`. JS reads from `os.environ` at runtime — future credential migrations only require updating `.env`.
- [ ] **1.1.10** Test: Login works, projects load, images load from R2

### 1.2 Cloudflare R2 Migration

- [ ] **1.2.1** Create new R2 bucket in company Cloudflare account (e.g., `safari-storage`)
- [ ] **1.2.2** Generate new R2 API tokens with read/write permissions
- [ ] **1.2.3** Update `.env`: `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- [ ] **1.2.4** **Decide on R2 data path convention** — Evaluate whether to keep the current `projects/{project_id}/...` structure or adopt a different pattern. The current convention works well and is recommended to keep.
- [ ] **1.2.5** Migrate existing data from old bucket if needed (use `rclone` or S3 sync)
- [ ] **1.2.6** Test: Upload an image, download it, generate presigned URL → opens in browser

### 1.3 Modal Migration

- [ ] **1.3.1** Create company Modal account / workspace
- [ ] **1.3.2** Run `modal setup` to configure CLI for new account
- [ ] **1.3.3** Create Modal secrets in company workspace:
  - `r2-credentials` (new R2 keys)
  - `supabase-credentials` (new Supabase keys)
- [ ] **1.3.4** Rename Modal app names to SAFARI branding:
  - `yolo-training` → `safari-training`
  - `yolo-inference` → `safari-inference`
  - `tyto-api-inference` → `safari-api-inference`
  - `tyto-api-server` → `safari-api-server`
- [ ] **1.3.5** Update all `modal.Function.from_name()` / `modal.Cls.lookup()` references in:
  - `backend/inference_router.py`
  - `backend/job_router.py`
  - `backend/api/server.py`
- [ ] **1.3.6** Deploy all Modal apps: `modal deploy backend/modal_jobs/*.py` and `modal deploy backend/api/server.py`
- [ ] **1.3.7** Test: Trigger a training run → job runs on new Modal account → results saved to new R2

> [!TIP]
> **Test checkpoint**: Full pipeline test — upload images → label → train → inference → results display.

---

## 🏗️ Phase 2: Database Security & Multi-User Foundation

**Goal**: Prepare the database for multiple users with proper isolation.  
**Estimated effort**: 2-3 sessions  
**Risk**: Medium — RLS changes can break existing queries if not tested carefully  
**Status**: ✅ Complete

> [!IMPORTANT]
> **Development strategy**: All Phase 2 work is done on the **current personal Supabase** instance. Every SQL change must be saved as a numbered migration script in `migrations/` so it can be replayed on the company instance later. This also serves as useful testing — the personal DB already has real data.  

### 2.1 User Roles Schema

- [x] **2.1.1** Add `role` column to `profiles` table
- [x] **2.1.2** Set initial admin user(s) role
- [x] **2.1.3** Create helper function for role checking (`is_admin()`)
- [x] **2.1.4** Test: `is_admin()` returns true for admin, false for regular user

### 2.2 Project Sharing Model

- [x] **2.2.1** Add `is_company` flag to `projects` table
- [x] **2.2.2** Create `project_members` junction table (with `owner`/`member` roles, cascade delete)
- [x] **2.2.3** Create RLS policies for `project_members` (SELECT/INSERT/DELETE for owners, admins)
- [x] **2.2.4** Test: Insert a member record, query as that user, verify visibility

### 2.3 Update Project RLS Policies

> [!WARNING]
> **This is the most critical migration step**. It changes who can see what data. Test thoroughly.

- [x] **2.3.1** Update `projects` RLS to support both personal and company projects (SELECT/INSERT/UPDATE/DELETE)
- [x] **2.3.2** Cascade RLS updates to dependent tables (`datasets`, `images`, `videos`, `keyframes`, `models`, `training_runs`, `inference_results`, `autolabel_jobs`)
- [x] **2.3.3** Test as admin: Can see all company projects and personal projects
- [x] **2.3.4** Test as regular user: Can only see own projects and company projects they're assigned to
- [x] **2.3.5** Test data isolation: User A cannot see User B's personal projects

> [!TIP]
> **Test checkpoint**: Log in as two different users. User A creates a personal project — User B cannot see it. Admin promotes project to company — User B can now see it.

### 2.4 Backend Support for Project Sharing

- [x] **2.4.1** Update `backend/supabase_client.py` — added `promote_to_team_project()`, `demote_from_team_project()`, `add_project_member()`, `remove_project_member()`, `get_project_members()`, `get_all_users()`, `set_user_role()`
- [x] **2.4.2** Updated project list to show team vs. personal projects (via `is_team` flag on `HubProjectModel`)
- [x] **2.4.3** Created admin panel — admin modal (user list + role toggle), Members popover (add/remove members, Team Project switch)
- [x] **2.4.4** Test: Admin assigns User B to a company project → User B refreshes → project appears

### 2.5 Supabase Client Architecture (Added)

> [!NOTE]
> This subsection was added during implementation to fix a critical RLS bug.

- [x] **2.5.1** Split Supabase into dual clients: `get_supabase()` (service role, data ops) + `get_supabase_auth()` (anon key, auth ops)
- [x] **2.5.2** Replaced `lru_cache` with module-level singleton pattern for safe multi-worker usage
- [x] **2.5.3** Updated all auth calls in `app_state.py` and `supabase_auth.py` to use `get_supabase_auth()`
- [x] **2.5.4** Added `SUPABASE_SERVICE_ROLE` env var requirement (SQL changelog entry #8)

### 2.6 Team Project Toggle & Safety Guards (Added)

- [x] **2.6.1** "Team" toggle switch in project header — visible to project owners and admins
- [x] **2.6.2** One-way toggle for non-admins: can promote to Team, only admins can demote
- [x] **2.6.3** Team project deletion blocked for non-admins (toast error + hidden trash icon with alignment placeholder)
- [x] **2.6.4** Tooltip explains restriction: "Only admins can remove team status"
- [x] **2.6.5** Refactored all Python-side `is_company`/`company_project` → `is_team`/`team_project` naming

### 2.7 Profile & Auth Triggers (Added)

- [x] **2.7.1** Auto-create `profiles` row trigger on `auth.users` insert (`handle_new_user()`)
- [x] **2.7.2** Admin-only user email dropdown in nav header (with admin modal access)

---

## 🏗️ Phase 3: Style Migration — "SAFARI Naturalist" Design System ✅

**Goal**: Re-skin the entire UI with the warm organic aesthetic from the SAFARI demos while preserving navigation structure and data density.  
**Completed**: Feb 2026 (across Phase 0.2 + dedicated style session)  
**Risk**: Low — purely visual, all tokens centralized in `styles.py`  
**Design reference**: [safari_design_reference.md](file:///Users/jorge/PycharmProjects/Tyto/docs/design/safari_design_reference.md)  
**Demo screenshots**: `docs/roadmaps/safari demo screenshots/`

> [!NOTE]
> This is NOT a pixel-perfect copy of the demo. We adopted the same **style family** — the warm naturalist palette, Material-outlined inputs, and organic feel — applied to our existing layout and navigation.

### 3.1 Color Token Swap (`styles.py`) ✅

All color tokens centralized in `styles.py` — single source of truth. 19+ hardcoded hex values across modules were consolidated into style tokens.

| Token | Previous (Dark) | Implemented |
|---|---|---|
| `BG_PRIMARY` | `#0A0A0B` | `#F5F0EB` (warm cream) |
| `BG_SECONDARY` | `#141415` | `#FFFFFF` (white cards) |
| `BG_TERTIARY` | `#1C1C1E` | `#F0EBE5` (warm hover) |
| `ACCENT` | `#3B82F6` (blue) | `#5FAD56` (leaf green) |
| `ACCENT_HOVER` | `#2563EB` | `#4E9A47` |
| `TEXT_PRIMARY` | `#FAFAFA` | `#333333` (near-black) |
| `TEXT_SECONDARY` | `#A1A1AA` | `#888888` (warm grey) |
| `BORDER` | `#27272A` | `#D5D0CB` (warm grey) |
| `HEADER_BG` | n/a | `#4A3728` (chocolate brown) — **new** |
| `HEADER_TEXT` | n/a | `#FFFFFF` — **new** |
| `EARTH_TAUPE` | n/a | `#8B7355` — secondary icons — **new** |
| `EARTH_SIENNA` | n/a | `#A0785A` — data categories — **new** |

- [x] **3.1.1** Updated `styles.py` — all color constants swapped to SAFARI Naturalist values
- [x] **3.1.2** Added new tokens: `HEADER_BG`, `HEADER_TEXT`, `ACCENT_MUTE`, `ACCENT_MUTE_GREEN`, `EARTH_TAUPE`, `EARTH_SIENNA`
- [x] **3.1.3** Updated `CARD_BG`, `POPOVER_BG`, `CARD_ITEM_BG`, `POPOVER_ITEM_BG` semantic aliases
- [x] **3.1.4** Updated shadow values for light mode (`SHADOW_SM`, `SHADOW_MD`, `SHADOW_LG`)
- [x] **3.1.5** Consolidated color palette — removed 19+ redundant hex values, all reference `styles.*`
- [x] **3.1.6** Theme: `rx.App(theme=rx.theme(appearance="light", accent_color="green"))`
- [x] **3.1.7** Test: All pages render in warm light palette, 144 tests pass

### 3.2 Typography & Button Style ✅

- [x] **3.2.1** Added `BUTTON_TEXT_TRANSFORM = "uppercase"` and `BUTTON_LETTER_SPACING = "0.08em"` to `styles.py`
- [x] **3.2.2** **Font family**: Replaced Inter with **Poppins** (rounded geometric sans-serif matching demo)
  - Created `assets/safari_fonts.css` — Google Fonts `@import`, global CSS overrides for Radix components
  - `styles.py`: `FONT_FAMILY = "'Poppins', system-ui, -apple-system, sans-serif"`
  - `safari/safari.py`: `stylesheets=["/safari_fonts.css"]`
- [x] **3.2.3** ALL-CAPS applied to primary/secondary buttons across modules
- [x] **3.2.4** Heading weights lightened via CSS: `.rt-Heading` → 500, page titles (size 7+) → 600
- [x] **3.2.5** Test: Poppins renders across all pages, buttons show ALL-CAPS

### 3.3 Form Inputs — Material Outlined Style ✅

- [x] **3.3.1** Created reusable `INPUT_OUTLINED` style dict in `styles.py` (transparent bg, border, green focus)
- [x] **3.3.2** Green focus border animation (`border_color: ACCENT` on focus with `2px` width)
- [x] **3.3.3** Applied to login form, project create modal, dataset forms, API key forms
- [x] **3.3.4** Selection checkboxes on image thumbnails ✅ (already implemented: per-image checkboxes, Select All, Clear, bulk Delete)
- [x] **3.3.5** Test: Inputs have outlined style with green focus, consistent across pages

### 3.4 Card & Layout Refresh ✅

- [x] **3.4.1** Cards: white background, thin warm border, green accent badges with `variant="outline"`
- [x] **3.4.2** Navigation active state: green accent via Radix `accent_color="green"`
- [x] **3.4.3** Status badges: green outline for active/success, kept warning/error colors
- [x] **3.4.4** Modal/dialog: cream backdrop, white card, outlined inputs
- [x] **3.4.5** Thumbnails: enlarged 60px → 80px for readability (dashboard + project detail)
- [x] **3.4.6** Dataset card text: `truncate=True` with `min_width: 0` + `overflow: hidden`
- [x] **3.4.7** Class Distribution card: `overflow: hidden` + `width: 100%` matches Classes card
- [x] **3.4.8** Chart axis labels: truncated to 12 chars with "…" (project + dataset detail)
- [x] **3.4.9** Test: Dashboard, project detail, dataset detail show consistent warm card style

### 3.5 Header Bar & Navigation Chrome ✅

- [x] **3.5.1** `nav_header.py`: Solid brown bar (`#4A3728`), white text, CSS `[● S A F A R I]` logo, user menu
- [x] **3.5.2** Page-level tab bars with green underline for active state
- [x] **3.5.3** Test: Header is chocolate brown across all pages

### 3.6 Page-Specific Polish (Partial)

- [x] **3.6.1** Login page: Split-panel layout, hero wildlife photo, SAFARI logo *(done in Phase 0.2)*
- [x] **3.6.2** Dashboard hub: Warm cards, green accents, enlarged thumbnails
- [x] **3.6.3** Training dashboard: Chart colors and badges look correct — *verified, no changes needed*
- [x] **3.6.4** Image gallery: Selection checkboxes already implemented, tag pills N/A (demo-specific concept)
- [x] **3.6.5** Labeling editor: Dark canvas bg preserved; toolbar uses warm scheme
- [ ] **3.6.6** Full walkthrough test — *not yet done*

### 3.7 Annotation Colors ✅ *(added — not in original plan)*

Annotation colors updated from neon to warm earthy tones across all 3 render paths:

| Parameter | Previous | Implemented |
|---|---|---|
| HSL Saturation | 70% | **45%** |
| HSL Lightness | 50% | **42%** |
| Hue offset | 0° | **+30°** (warmer) |
| Selection highlight | `#F59E0B` (orange) | `#5FAD56` (accent green) |

Files: `state.py` (Python), `canvas.js` (labeling), `inference_player.js` (video playback)

> [!TIP]
> **Only remaining item**: 3.6.6 (full end-to-end walkthrough test) — all code changes complete.

> [!IMPORTANT]
> **Labeling editor exception**: Dark background preserved in the editor canvas for image contrast. Only the toolbar/chrome uses the warm scheme.

---

## 🏗️ Phase 4: Deployment & Hosting

**Goal**: Deploy SAFARI on company infrastructure behind Tailscale.  
**Estimated effort**: 1 session for initial deployment, ongoing for operations  
**Risk**: Medium — first real deployment  

### 4.1 Hosting Decision

- [ ] **4.1.1** Evaluate hosting options:

| Option | Pros | Cons | Monthly Cost |
|--------|------|------|-------------|
| **Hetzner CX22** | Cheap (€4), existing docs | EU-only | ~€4 |
| **Company on-prem** | Free, full control | Maintenance burden | €0 |
| **DigitalOcean** | Simple, good EU regions | Slightly more expensive | ~€12 |
| **AWS EC2 t3.medium** | Company AWS? | Complex, overkill | ~€30 |

> [!TIP]
> **Recommendation**: Hetzner CX22 or company on-prem behind Tailscale. The app itself is lightweight (Reflex frontend + backend); all heavy compute is on Modal. The VPS only needs to serve the UI.

- [ ] **4.1.2** Decide on hosting provider and provision server
- [ ] **4.1.3** Install Tailscale on the server

### 4.2 Tailscale-Only Deployment (No Docker)

> [!IMPORTANT]
> **Security approach**: No public exposure. The app is only accessible within the Tailscale network, eliminating the need for public SSL, DDoS protection, and most attack surface.

> [!NOTE]
> **Architecture decision**: Docker was dropped. A single Reflex app on a single VPS behind Tailscale doesn't benefit from containerization — it's virtualization inside virtualization with no scaling need. Using **systemd + native Caddy + venv** instead.

- [ ] **4.2.1** Set up Python venv and install deps on the server:
  ```bash
  python3.11 -m venv /opt/safari/.venv
  source /opt/safari/.venv/bin/activate
  pip install -r requirements.txt
  ```
- [ ] **4.2.2** Create systemd service (`/etc/systemd/system/safari.service`):
  ```ini
  [Unit]
  Description=SAFARI Wildlife Platform
  After=network.target

  [Service]
  Type=simple
  User=safari
  WorkingDirectory=/opt/safari
  EnvironmentFile=/opt/safari/.env
  ExecStart=/opt/safari/.venv/bin/reflex run --env prod
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
- [ ] **4.2.3** Install Caddy natively (`apt install caddy`) and configure for internal-only:
  ```caddyfile
  :80 {
      reverse_proxy localhost:3000
      @websockets {
          header Connection *Upgrade*
          header Upgrade websocket
      }
      reverse_proxy @websockets localhost:8000
      encode gzip
  }
  ```
- [ ] **4.2.4** Enable and start: `systemctl enable --now safari`
- [ ] **4.2.5** Test: Access app via Tailscale IP or MagicDNS hostname

### 4.3 Operational Tooling

- [ ] **4.3.1** Create `scripts/deploy.sh` — pull, install deps, restart service:
  ```bash
  cd /opt/safari && git pull && source .venv/bin/activate
  pip install -r requirements.txt && sudo systemctl restart safari
  ```
- [ ] **4.3.2** Create `scripts/backup.sh` — pre-migration and recurring safety net:
  - Export Supabase data (`pg_dump` or Supabase API export)
  - List/snapshot R2 bucket contents
  - Run before every credential migration and keep on a schedule
- [ ] **4.3.3** Set up log rotation via journald (systemd handles this natively — verify with `journalctl -u safari`)
- [ ] **4.3.4** **Health monitoring** — Simple health check cron (curl the app every 5 min, alert on failure). Tailscale has built-in node monitoring that covers basic availability — verify it's enabled.

> [!TIP]
> **Test checkpoint**: All team members connected to Tailscale can access the SAFARI app by URL. Users outside Tailscale cannot.

---

## 🏗️ Phase 5: Documentation Update

**Goal**: Clean, onboarding-ready docs for new team members. All docs reflect the current SAFARI codebase.  
**Estimated effort**: 4–5 sessions (each sub-section is one session)  
**Risk**: None — purely documentation  

> [!IMPORTANT]
> **Execution order matters.** File-map and architecture docs require deep codebase audits and are referenced by all other docs. Do these first so downstream docs are accurate from the start.

### 5.1 File Map Update (Deep Codebase Audit) ✅ DONE

> **Why first**: The file-map is the "where to find things" index. If it's wrong, developers lose time. This requires walking the actual codebase to verify every entry.

- [x] **5.1.1** Audit `docs/file-map/README.md`:
  - Update "Quick Jump" table (verify file paths, function names, line counts still match)
  - Update Directory Tree (new files, renamed files, removed files since last update)
  - Fix `Tyto/Tyto.py` → `safari/safari.py` in tree and quick jump
  - Update file size reference table (re-count lines for top files)
  - Rebrand title "Tyto File Map" → "SAFARI File Map"
- [x] **5.1.2** Audit `docs/file-map/backend-services.md`:
  - Verify every function listing still exists and signatures match
  - Add any new functions added since last update
  - Remove any deleted functions
  - Rebrand Tyto → SAFARI references
- [x] **5.1.3** Audit `docs/file-map/frontend-modules.md`:
  - Verify all UI module listings, state classes, and event handlers
  - Add new components/states (e.g., admin panel, team project toggle)
  - Rebrand Tyto → SAFARI references
- [x] **5.1.4** Audit `docs/file-map/modal-and-workers.md`:
  - Verify Modal job listings and dispatch flow
  - Add SAM3 training job if missing
  - Rebrand Tyto → SAFARI references

### 5.2 Architecture Docs Update (Deep Codebase Audit) ✅ DONE

> **Why second**: Architecture docs explain *how* things work. They depend on the file-map being accurate, and all other docs reference architecture concepts.

- [x] **5.2.1** Update `docs/architecture/architecture_reference.md`:
  - Rebrand Tyto → SAFARI throughout
  - Verify Supabase schema section reflects Phase 2 changes (profiles.role, project_members, is_company)
  - Update inference flow descriptions if changed
  - Update any Mermaid diagrams
- [x] **5.2.2** Update `docs/architecture/architecture_diagrams.md`:
  - Rebrand diagram labels
  - Verify flow diagrams match current dispatch logic
- [x] **5.2.3** Update `docs/architecture/api_architecture_diagram.md`:
  - Rebrand Tyto → SAFARI
  - Verify API routing diagrams

### 5.3 API Rebrand (Code + Docs) ✅ DONE

- [x] **5.3.1** Update `backend/api/server.py` FastAPI metadata:
  - Title: `"SAFARI Inference API"`, Modal app: `safari-api-inference`
  - CORS origins: `safari.app`, health check: `safari-api`
- [x] **5.3.2** Update API key prefix `tyto_` → `safari_` in:
  - `backend/api/auth.py` (prefix validation)
  - `backend/supabase_client.py` (key generation)
  - `migrations/001_api_tables.sql` (comment)
  - `modules/api/page.py` (curl example)
- [x] **5.3.3** Update `docs/reference/api_internals.md` — rebranded + fixed Classify Once → Top-K
- [x] **5.3.4** Update `docs/openapi.json` — title, key prefix, TytoDesktop → SAFARIDesktop

### 5.4 Rebrand Remaining Docs + Archive Housekeeping ✅

> Completed 2026-02-26. All documentation files rebranded Tyto → SAFARI.

- [x] **5.4.1** Rebrand `docs/reference/sam3-finetune-reference.md` — 5 refs updated
- [x] **5.4.2** Rebrand `docs/reference/tyto_desktop_mask_rendering.md` — content rebranded, filename pending OS rename
- [x] **5.4.3** Rebrand `docs/patterns/video_annotation_rendering.md`
- [x] **5.4.4** Rebrand `docs/cross_repo/cross_repo_changes.md` — 6 TytoDesktop → SAFARIDesktop
- [x] **5.4.5** Rebrand `docs/design/safari_design_reference.md` — 4 "Current Tyto" → "Current SAFARI"
- [x] **5.4.6** N/A — `docs/deployment/hetzner_deployment.md` does not exist yet (Phase 5.5 scope)
- [x] **5.4.7** Archive moves deferred — files already clearly archived, no urgency
- [x] **5.4.8** Rebrand archived roadmaps (full pass, not just title+header):
  - `archive/legacy_roadmap.md` — file structure, page imports
  - `archive/local_gpu_roadmap.md` — TYTO_HOME→SAFARI_HOME, ~/.tyto→~/.safari, bucket name, SSH key, worker scripts
  - `archive/tauri_roadmap_v1.md` — SafariClient, safari_ prefix, API URL, section headers
- [x] **5.4.9** Rebrand `docs/roadmaps/tauri_desktop_roadmap.md` — title, service name, export, API ref
- [x] **5.4.10** Rebrand `docs/roadmaps/api_roadmap.md` — title, key prefix, Mermaid diagrams, SQL, code, curl
- [x] **Bonus**: Rebrand `docs/README.md` — title, all cross-references
- [x] **Bonus**: Rebrand `docs/file-map/` — backend-services, modal-and-workers, README
- [x] **Bonus**: Complete TYTO_ROOT→SAFARI_ROOT rebrand in `architecture_reference.md` — env var, paths, KI table, changelog

### 5.5 New Documentation (Create) ✅

> Completed 2026-02-26. All new documentation files created.

- [x] **5.5.1** Create root `README.md` — project name, tech stack table, quick start, docs links, project structure
- [x] **5.5.2** Create `docs/ONBOARDING.md` — Tailscale access, login, projects, datasets, labeling, training, inference, analytics
- [x] **5.5.3** Create `docs/DEVELOPMENT.md` — prerequisites, local setup, all env vars documented with examples, Modal deployment, remote GPU, testing
- [x] **5.5.4** Updated `.env.production.example` — fixed stale var names (`R2_ENDPOINT`→`R2_ENDPOINT_URL`, `SUPABASE_SERVICE_KEY`→`SUPABASE_SERVICE_ROLE`), SAFARI branding, added `SAFARI_ROOT`

### 5.6 Documentation Index Restructure

> Final step — only after all other docs are accurate.

- [ ] **5.6.1** Rewrite `docs/README.md`:
  - Title: "SAFARI Documentation"
  - Add links to new docs (ONBOARDING, DEVELOPMENT)
  - Update category listings (add SAFARI migration roadmap, remove stale links)
  - Add file-map quick links
  - Follow best practices: clear hierarchy, quick-start section, contributor guide link

---

## 🏗️ Phase 6: GitHub Migration

**Goal**: Move codebase to company GitHub repository.  
**Estimated effort**: 0.5 session  
**Risk**: Low  

### 6.1 Repository Migration

- [ ] **6.1.1** Create new repository in company GitHub org
- [ ] **6.1.2** Push code with full git history: `git remote add company <url> && git push company main`
- [ ] **6.1.3** Update `.gitignore` — ensure `.env`, `.env.production`, `__pycache__`, `.venv`, `.web` are excluded
- [ ] **6.1.4** Verify no secrets in git history (run `git log --all -p | grep -i "secret\|password\|key"`)
- [ ] **6.1.5** If secrets found in history: use `git-filter-repo` or `BFG` to remove, or start fresh history

> [!CAUTION]
> The current `.env` file **is committed or contains real credentials** in the repo. Before pushing to company GitHub:
> 1. Check if `.env` is in git history: `git log --all -- .env`
> 2. If yes, scrub history or start fresh
> 3. All credentials are being rotated to company accounts anyway

### 6.2 CI/CD (Future — not blocking)

- [ ] **6.2.1** (Optional) Set up GitHub Actions for linting/testing
- [ ] **6.2.2** (Optional) Set up auto-deploy on push to main

---

## 🏗️ Phase 7: Security Hardening (Post-Migration Polish)

**Goal**: Best-practice security for multi-user operation.  
**Estimated effort**: 1-2 sessions  
**Risk**: Low (Tailscale provides network-level security)  

> [!NOTE]
> With Tailscale enforcing network access, the attack surface is already minimal. These steps add defense-in-depth.

### 7.1 Credential Hygiene

- [ ] **7.1.1** Remove all hardcoded credentials from JS files (covered in Phase 1.1.7 but verify)
- [x] **7.1.2** Implement server-injected config pattern for client-side URLs/keys *(done — Phase 1.1.9)*
- [ ] **7.1.3** Add Supabase `service_role` key to production env for backend operations
- [ ] **7.1.4** Verify `.env` is not in git: `git status .env` shows untracked

### 7.2 Database Security Audit

- [ ] **7.2.1** Audit all RLS policies — run comprehensive test matrix:
  | Test | Admin | Member | Non-member | Expected |
  |------|-------|--------|------------|----------|
  | View own project | ✅ | n/a | n/a | See it |
  | View company project (member) | ✅ | ✅ | ❌ | Member sees, non-member doesn't |
  | Edit company project | ✅ | ❓ | ❌ | Define write permissions |
  | Delete personal project | ✅ (own) | n/a | ❌ | Only owner |
  | View other user's personal | ❌ | ❌ | ❌ | Nobody except owner |
- [ ] **7.2.2** Test RLS with Supabase SQL editor using `SET ROLE` to simulate different users
- [ ] **7.2.3** Verify cascading deletes work correctly (project → datasets → images → labels)

### 7.3 Application Security

- [ ] **7.3.1** Session timeout configuration — verify `session_manager.js` token refresh is working
- [ ] **7.3.2** Rate limiting on login attempts (Supabase has built-in, but verify config)
- [ ] **7.3.3** Input validation for project names, class names (prevent injection)

---

## 📋 Suggested Execution Order & Priority

| Priority | Phase | Can users start testing? | Dependencies | Status |
|----------|-------|------------------------|--------------|--------|
| 🔴 P0 | Phase 0 (Rebrand) | No | None | ✅ Done |
| 🔴 P0 | Phase 3 (Styling) | No | Phase 0 | ✅ Done |
| 🔴 P0 | Phase 2 (DB Security & Sharing) | Local testing | Phase 0 | ✅ Done |
| 🔴 P0 | Phase 1 (Credentials) | No | Company creds | ⏸️ Deferred |
| 🔴 P0 | Phase 4 (Deploy) | **Yes** — multi user | Phase 1+2 | Pending |
| 🟡 P1 | **Phase 5 (Docs)** | n/a | Phase 0+2 | 🔜 In Progress |
| 🟢 P2 | Phase 6 (GitHub) | n/a | Phase 1 | Pending |
| 🟢 P2 | Phase 7 (Security) | n/a | Phase 2 | ✅ 7.1.2 Done |

### Updated Execution Strategy

**Phase 2 is complete** on the current personal Supabase — all SQL changes captured as migration scripts.

**Phase 5 proceeds now** in order: 5.1 (file-map audit) → 5.2 (architecture) → 5.3 (API rebrand) → 5.4 (remaining docs) → 5.5 (new docs) → 5.6 (index restructure). Each sub-section is a self-contained session.

**When company credentials arrive**: Run the [Schema Transition Playbook](#-schema-transition-playbook) to set up the new instance (~30 min), then deploy (Phase 4).

**Phases 5, 6, 7** can happen in parallel with user testing.

---

## 💡 Things to Skip for Now

- ❌ Public SSL/domain setup (Tailscale handles this)
- ❌ CI/CD pipeline (manual deploys are fine for UAT)
- ❌ Separate staging environment (Tailscale isolation is enough)
- ❌ Database migrations tooling (manual SQL in Supabase dashboard is fine at this scale)
- ❌ User self-registration (admin creates accounts for now)

---

## 📝 SQL Changelog (Applied Directly to Dev Instance)

> Track all SQL changes applied directly via Supabase SQL Editor during Phase 2.  
> These will be consolidated into migration scripts when migrating to the company instance.

| # | Date | Description | SQL Summary |
|---|------|-------------|-------------|
| 1 | 2026-02-26 | Add `role` column to `profiles` | `ALTER TABLE profiles ADD COLUMN role text DEFAULT 'user'` |
| 2 | 2026-02-26 | Set initial admin | `UPDATE profiles SET role = 'admin' WHERE email = 'jorgemaria4wd@gmail.com'` |
| 3 | 2026-02-26 | Add `is_company` flag to `projects` | `ALTER TABLE projects ADD COLUMN is_company boolean DEFAULT false` |
| 4 | 2026-02-26 | Create `project_members` table | Junction table with `project_id`, `user_id`, `role`, FK + unique constraint |
| 5 | 2026-02-26 | RLS policies for `project_members` | SELECT/INSERT/DELETE policies for project owners and admins |
| 6 | 2026-02-26 | Update project-related RLS | Updated RLS on `projects`, `datasets`, `images`, `videos`, `keyframes`, `models`, `training_runs`, `inference_results`, `autolabel_jobs` for multi-user access |
| 7 | 2026-02-26 | Auto-create profile trigger | `handle_new_user()` function + `on_auth_user_created` trigger on `auth.users` |
| 8 | 2026-02-26 | **ENV**: `SUPABASE_SERVICE_ROLE` required | New `.env` var — backend uses service role for data ops, anon key for auth ops (dual-client split) |

---

## 📦 Schema Transition Playbook

**When to run**: Once company Supabase/R2/Modal credentials are available.  
**Time estimate**: ~30 minutes  
**Prerequisite**: Phase 2 is complete and tested on the personal instance.

### Step 1: Export Tested Schema

```bash
# Full schema export (tables, indexes, constraints, triggers, functions, RLS policies)
pg_dump --schema-only --no-owner --no-privileges \
  -h db.<current-project-id>.supabase.co \
  -U postgres \
  -d postgres > safari_schema_export.sql
```

> [!TIP]
> `pg_dump --schema-only` captures everything structural: tables, columns, constraints, indexes, triggers, functions, **and RLS policies**. No data is exported.

### Step 2: Replay on Company Instance

- Open the new Supabase project → SQL Editor
- Paste and run `safari_schema_export.sql`
- Alternatively, run the numbered migration scripts from `migrations/` in order (more controlled)

### Step 3: Verify RLS Policies

```sql
-- List all policies to confirm they transferred
SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public';
```

### Step 4: Verify Functions

```sql
-- List all custom functions
SELECT routine_name, routine_type 
FROM information_schema.routines 
WHERE routine_schema = 'public';
```

### Step 5: Re-configure Auth (Manual)

- Email templates → copy from old Supabase Dashboard → Authentication → Email Templates
- Auth providers/settings → re-configure in the new project dashboard
- Create initial admin user account

### Step 6: Swap Credentials

| Service | Config locations | Action |
|---------|-----------------|--------|
| **Supabase** | `.env`, `session_manager.js` (hardcoded L13, L57) | Update URL + anon key |
| **Cloudflare R2** | `.env` (4 vars) | New bucket + API tokens |
| **Modal** | `~/.modal.toml`, Modal dashboard secrets | `modal setup` + recreate secrets |

### Step 7: Deploy Modal Apps

```bash
modal deploy backend/modal_jobs/training_job.py
modal deploy backend/modal_jobs/inference_job.py
modal deploy backend/api/server.py
# Update app names in from_name()/lookup() references if renamed
```

### Step 8: Smoke Test

- [ ] Login works on new Supabase
- [ ] R2 upload/download works
- [ ] Modal training job dispatches
- [ ] Modal inference returns results

---

## 🧪 End-to-End Verification Checklist

Run this checklist after completing Phases 0-2 and after deployment:

- [ ] App loads at Tailscale URL
- [ ] Login page shows "SAFARI" branding
- [ ] Admin can log in
- [ ] Admin can create a project
- [ ] Admin can create a dataset and upload images
- [ ] Admin can label images (draw boxes, navigate, autosave works)
- [ ] Admin can upload and label video (keyframe marking)
- [ ] Admin can train a model (Modal job runs on company account)
- [ ] Admin can run inference (playground works)
- [ ] Admin can promote project to company project
- [ ] Regular user can log in
- [ ] Regular user sees only assigned company projects (not admin's personal ones)
- [ ] Regular user can create their own personal project
- [ ] Regular user can label in company project
- [ ] Regular user cannot see other user's personal projects
- [ ] Browser console shows `[SAFARI]` logs, not `[Tyto]`
- [ ] localStorage uses `safari_*` keys
- [ ] Session persists across page refresh
- [ ] Session manager refreshes tokens automatically
