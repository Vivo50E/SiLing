# Mobile replies — US2-A2/A3 increment

2026-10-06. Continues the approved UI/UX spec after the local archive increment.
Targets FR-008/009, supporting FR-004/024/025/026; physical SC-004 acceptance
remains separate. No framework, desktop composer or process-lifecycle redesign.

## Gap and contract

The mobile reader currently provides snapshots and an explicit terminal but no
multiline composer or isolated drafts. Existing desktop send helpers swallow
errors and the generic API may repeat a request after authentication. The tmux
helper also retries transient failures, including unknown timeouts. Reusing
those defaults would not provide a safe unknown-result workflow.

- Reply is an explicit mode beside read-only output; Enter inserts a newline,
  only Send submits. Esc/Tab/Ctrl+C are explicit buttons; Ctrl+C confirms target.
- Draft and delivery state are keyed by execution ID in tab sessionStorage,
  independent of desktop drafts. Pending at reload becomes uncertain. Storage
  failure retains an in-memory copy with a visible warning. Never store private
  input through this ordinary composer; no cross-device draft synchronization.
- One page-wide request at a time, fixed original target, bounded 8,000-character
  text and 12-second client wait. No auth replay, automatic resend, retries on
  visibility/reconnect/navigation, or sending while execution is known ended.
- A successful response means terminal input accepted, not agent execution.
  Unknown delivery keeps the draft and blocks further sends/keys until the user
  checks output and explicitly acknowledges the duplication risk. Offline before
  a request is labelled not sent. New drafts are not silently cleared.
- Add authenticated `/api/sessions/{id}/input` with strict text/key validation,
  bounded body, existing target lookup and tmux transport with retries disabled.
  Keep legacy `/send` behavior unchanged. Old remote nodes reject the new route;
  never fall back to legacy send. No new permission or control authority.
- Compact reply layout uses visual-viewport height and safe-area padding while
  preserving reading, Files/back, at most one terminal, and desktop preferences.

## Tasks and verification

1. Read spec/baseline, reader/send implementations, existing tests and security.
2. Add failing API and browser regressions before implementation.
3. Implement the bounded endpoint and independent mobile composer module.
4. Verify draft isolation/reload, multiline/IME, cancellation, double clicks,
   offline/auth/error/timeout/late results, archive/back/Files, special keys,
   ended/offline targets, locale/theme, 360/390/430 and landscape/keyboard-sized
   viewports. Verify normal navigation produces no input/control calls.
5. Run full `make verify`, full browser suite and isolated real tmux input smoke;
   keep physical phone and native agent acceptance explicitly pending.
6. Update bilingual README/baseline and evidence; push only tested own main under
   standing authorization. Runtime update remains separately approved.

## Compatibility and rollback

No server state migration. New tab-local drafts use their own versioned key;
older code ignores them. The extra endpoint and optional tmux retry argument are
additive. Rollback must not delete draft storage. No guarantee of exactly-once
execution after a lost response: uncertainty is surfaced, never papered over.
