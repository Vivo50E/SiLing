# Tasks: Mobile session reader (US2-A1)

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/mobile-reader.md.
**Scope**: US2-A1/FR-007 only, supporting session-preservation, evidence, bilingual and accessibility safeguards. Other stories and full SC-004 acceptance deferred.

## Phase 1: Setup
- [x] T001 Review spec and isolated-worktree scope in specs/001-uiux-improvements/plan.md.
- [x] T002 Complete research and API/UI contracts in specs/001-uiux-improvements/research.md and contracts/mobile-reader.md.

## Phase 2: Regression foundation
- [x] T003 [P] [US2] Add bounded-read metadata/fallback/validation tests in tests/test_mobile_reader.py; confirm failure before implementation.
- [x] T004 [P] [US2] Add mobile boot/navigation/transport/preference tests in tests/ui_browser.mjs; confirm failure before implementation.

## Phase 3: US2-A1 (P1)
Independent test: fresh phone boot → filtered list → literal bounded snapshot → Files/back, without automatic tty connections or desktop preference writes.
- [x] T005 [US2] Add optional bounded output metadata in agent_orchestrator/dashboard.py (depends T003).
- [x] T006 [US2] Implement mobile state/reader/explicit terminal in static/mobile-reader.js (depends T004).
- [x] T007 [US2] Add themed 44px responsive controls in static/mobile-reader.css and bilingual copy in static/ui-messages.js.
- [x] T008 [US2] Integrate responsive transport/boot gates in static/index.html while preserving desktop cards and drafts.

## Phase 4: Validation and handoff
- [x] T009 [US2] Run full make verify and browser/terminal smoke from specs/001-uiux-improvements/quickstart.md; record evidence in validation.md.
- [x] T010 [US2] Update README.md, README_CN.md and docs/uiux-implementation-status.md with partial-delivery boundaries.

## Dependencies and strategy

Setup → regression foundation → implementation → full validation. T003/T004 are independent research/test work; backend T005 can proceed separately from frontend T006/T007, integrated at T008. Tests precede code. Deliver this MVP only; do not infer completion of other FRs or deploy. Physical-device validation remains an explicitly reported manual follow-up, not a checked automated task.
