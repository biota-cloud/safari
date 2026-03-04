---
description: Commit changes after completing a phase or significant milestone
---

# Commit Workflow

Run this after completing a phase, sub-phase, or significant chunk of work.

## Steps

1. **Check git status**:
   ```bash
   git status
   ```
   - Review what files have changed
   - Ensure no unintended files are staged (e.g., `.env`, `__pycache__`)

2. **Stage all relevant changes**:
   ```bash
   git add .
   ```
   - Or stage specific files if needed: `git add path/to/file`

3. **Create a descriptive commit message**:
   
   Format: `Phase X.Y: Brief description of what was completed`
   
   Examples:
   - `Phase 0.1: Project initialization and folder structure`
   - `Phase 0.2: R2 storage client with upload and presigned URLs`
   - `Phase 1.3: Canvas foundation - image loading and display`
   - `Fix: Resolved R2 CORS issue for presigned URLs`

4. **Commit**:
   ```bash
   git commit -m "Phase X.Y: Description"
   ```

5. **Push to company repo**:
   ```bash
   git push origin main
   ```

## Notes

- `origin` = **company repo** (`biota-cloud/safari`) — all new work goes here
- `personal` = old personal repo (`abetarda/tyto`) — read-only archive
- Always commit after passing a checkpoint
- If a checkpoint fails, don't commit — fix first
- Use `Fix:` prefix for bug fixes, `Phase X.Y:` for planned work
- Keep commits atomic — one logical change per commit