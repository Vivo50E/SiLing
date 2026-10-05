# Research: US2-A1

## Transport boundary

Decision: independent mobile surface, early gates at grid rendering, boot preference writes, terminal attachment, queued work and late replies. Suspend desktop transports but retain cards/drafts during mobile resize; restore visible panes on desktop return.
Rationale: current responsive mode only changes CSS; refreshList can attach before boot setLayout, and cached iframes retain connections.
Alternatives: whole-card reuse imports lifecycle controls and slot mutation; CSS hiding does not stop connections. Separate read-only frontend/backend research completed; no unresolved technical questions.

## Output evidence

Decision: extend /read with optional max_chars and observation/truncation metadata. Probe one extra line only in bounded mode; preserve legacy defaults and CLI behavior.
Rationale: alive proves neither agent execution nor fresh output. Log mtime is not reliable agent-output time. Older remote nodes missing metadata show unknown.
Alternatives: /pane may read full logs, SSE adds persistent connections without metadata, a new endpoint duplicates auth/proxy logic.
Limit: response cap does not bound total log scanning cost.

## Validation

Reuse isolated CDP fixtures and unittest, plus existing real tmux/ttyd smoke. Test literal output, stale replies, list restoration, drafts/preferences and zero automatic mobile attachments. Physical phone keyboard/TLS evidence remains separate.
