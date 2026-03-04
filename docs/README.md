# SAFARI Documentation

> Central index for all project documentation.

---

## Quick Links

| Document | Purpose |
|----------|---------|
| [Architecture Reference](architecture/architecture_reference.md) | Core system design, inference flows, Supabase schema |
| [API Internals](reference/api_internals.md) | API routing, SAM3 processing, endpoint details |
| [Cross-Repo Changes](cross_repo/cross_repo_changes.md) | SAFARIDesktop sync log |

---

## By Category

### Architecture
System design, diagrams, and compute flows.

- [architecture_reference.md](architecture/architecture_reference.md) — Master architecture document
- [architecture_diagrams.md](architecture/architecture_diagrams.md) — Mermaid flow diagrams
- [api_architecture_diagram.md](architecture/api_architecture_diagram.md) — API-specific diagrams

### Reference
Technical details for integrations and subsystems.

- [api_internals.md](reference/api_internals.md) — API routing and SAM3 processing
- [sam3.md](reference/sam3.md) — SAM3 model integration notes
- [modal.md](reference/modal.md) — Modal GPU job patterns
- [tyto_desktop_mask_rendering.md](reference/tyto_desktop_mask_rendering.md) — Desktop mask rendering (pending rename to safari_*)

### Patterns
Reusable implementation patterns.

- [antigravity_skill_guide.md](patterns/antigravity_skill_guide.md) — Agent skill development
- [video_annotation_rendering.md](patterns/video_annotation_rendering.md) — Video annotation patterns

### Deployment
Production setup and operations.

- [production_deployment.md](deployment/production_deployment.md) — VPS setup, systemd, Caddy, operations

### Roadmaps
Feature planning and progress tracking.

- [api_roadmap.md](roadmaps/api_roadmap.md) — API feature roadmap
- [tauri_desktop_roadmap.md](roadmaps/tauri_desktop_roadmap.md) — SAFARIDesktop roadmap
- [classification_roadmap.md](roadmaps/classification_roadmap.md) — Classification training roadmap
- [architecture_roadmap_v2.md](roadmaps/architecture_roadmap_v2.md) — Shared core refactoring (complete)
- [archive/](roadmaps/archive/) — Completed/superseded roadmaps

### Cross-Repo
Coordination between SAFARI and SAFARIDesktop.

- [cross_repo_changes.md](cross_repo/cross_repo_changes.md) — API change log for client updates

### Archive
Historical investigations and completed work.

- [video_switching_investigation.md](archive/video_switching_investigation.md)

---

## Naming Convention

All documentation files use `lowercase_snake_case.md` for consistency.
