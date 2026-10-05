# Mobile reader contract

GET /api/sessions/{encoded-run-id}/read?lines=200&position=tail&max_chars=32000

- Existing Dashboard auth and remote routing remain unchanged.
- max_chars is optional, 1–200000 Unicode code points; absent preserves existing text semantics.
- Bounded mode probes one extra line; retains requested head/tail, then caps characters in the same direction. Exact equality does not prove truncation.
- observed_at is snapshot completion time, not last agent output. content_updated_at stays null where unknown. Older remote metadata remains unknown.
- 404 missing session; 422 invalid bounds; auth/remote errors unchanged. No attach/input/stop/restart/resume call for reading.

List has search and all/attention filters. Row opening does not modify desktop slots or manual priority. Back restores list scroll/focus. Failed refresh preserves original snapshot time and marks stale. Output uses textContent.

Interactive terminal is explicit and limited to one mobile iframe; back/selection/desktop resize detach without stopping the agent. Files uses the existing viewer.
