# Cross-Repository Change Log

Track API changes that require SAFARIDesktop client updates.

## Format

```markdown
## YYYY-MM-DD: [Change Title]
- **API Change**: What changed in API
- **Endpoint(s)**: Affected routes
- **Client Impact**: What SAFARIDesktop needs to update
- **Status**: Pending / Communicated / Implemented
```

---

## Changes

### 2026-01-15: API Internals Documentation for SAFARIDesktop

- **API Change**: Added comprehensive internal documentation
- **Files Added/Updated**:
  - `docs/API_INTERNALS.md` — Technical reference for routing logic, SAM3 processing
  - `docs/openapi.json` — Enhanced with batch endpoint, video schemas, model_type details
- **Client Impact**: SAFARIDesktop agent can now understand:
  - Model type routing (`detection` vs `classification`)
  - SAM3 video processing (all frames processed for tracking, `frame_skip` filters output only)
  - Batch endpoint for high-throughput frame sequences
  - Video result schema with `track_id` for temporal consistency
- **Status**: Pending

---

*(Add new entries above this line)*

---

## How to Use

1. **When making API changes** that affect the client:
   - Add an entry above with the change details
   - Set status to "Pending"

2. **When communicating to SAFARIDesktop**:
   - Update status to "Communicated"
   - SAFARIDesktop team will update their `docs/api-contracts/CHANGELOG.md`

3. **When client implements**:
   - Update status to "Implemented"
