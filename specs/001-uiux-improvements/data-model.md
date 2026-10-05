# Data Model: Mobile reader

Browser state: responsive mode, selected run ID, all/attention filter, search, list scroll, request generation, AbortController, poll timer, last successful snapshot, optional single terminal iframe. Selection/back/resize invalidate requests and dispose the iframe. Hidden pages stop polling. No server persistence or agent lifecycle transition.

Snapshot preserves existing ok/text/source/alive/position/line fields. Bounded requests add observed_at (epoch seconds), content_updated_at (null when unknown), truncated and truncation_reasons (lines/chars). Empty successful text differs from unavailable output. Failed refresh retains original text/time with a stale notice.

Desktop controllers retain card/input DOM while their transports are suspended. Slots/layout/TTY preferences never become mobile navigation state.
