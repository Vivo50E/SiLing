# Implementation Plan: Mobile session reader (US2-A1)

**Branch**: `agent/self-improve-mobile-reader-20261005` | **Date**: 2026-10-05
**Spec**: [spec.md](spec.md)

## Summary

Implement an independent US2 slice: phone list → bounded read-only snapshot → return; explicit single interactive terminal. Reuse Files/authentication and preserve desktop preferences. This does not complete the entire specification or US2 keyboard/draft acceptance.

## Technical Context

- Python 3.10+, FastAPI; vanilla JavaScript/CSS; no new dependency.
- Existing authenticated /read endpoint, tmux snapshots and logs; /tty only on explicit interaction.
- Storage: mobile navigation in memory, no server schema changes.
- Testing: unittest, Node syntax checks, isolated Chromium fixtures and real tmux/ttyd smoke.
- Platform: Dashboard web UI, narrow viewports below 820px; physical phone acceptance remains manual.
- Performance: one foreground reader request at a time, 5-second polling; 200 lines / 32,000 characters. No automatic mobile terminal attachments.
- Constraints: preserve background sessions, desktop drafts, slots/layout/TTY preferences; ignore stale requests; distinguish snapshot observation from actual output update time.
- Scope: FR-007 and supporting FR-004/005/010/024/025/026 safeguards. US1, US3–US6, comprehensive Files redesign, mobile multiline composer and full SC-004 device acceptance deferred.

## Constitution Check

PASS before and after design: isolated worktree; no runtime update; read-only navigation has no session-control calls; additive authenticated API; explicit terminal; literal output; bilingual labels and 44px controls. Full regression and behavioral checks required. No exceptions.

## Project Structure

Design documents live beside this plan: research.md, data-model.md, contracts/mobile-reader.md, quickstart.md and tasks.md.
Implementation: static/mobile-reader.js and .css; narrow adapters in static/index.html and ui-messages.js; additive endpoint metadata in agent_orchestrator/dashboard.py.
Tests: tests/test_mobile_reader.py and tests/ui_browser.mjs.

**Structure decision**: a focused module rather than another inline subsystem or framework migration.

## Complexity Tracking

No constitution violations. Browser dimension tests are not physical-device validation.
