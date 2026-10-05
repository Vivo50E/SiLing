# SiLing Constitution

## Core Principles

### I. Protect running sessions

UI changes MUST preserve session identity, resume information, terminal input,
drafts and remote-node compatibility. Closing or reconnecting a display MUST NOT
implicitly terminate or restart its agent. Destructive actions require explicit intent.

### II. Local-first, explicit authority

Preserve loopback defaults and authenticated non-loopback access. Never commit
credentials, transcripts, private prompts, certificates or machine-local settings.
Observations are not authorization: monitoring MUST NOT silently approve agent
permissions, start work, merge code or deploy an update.

### III. Evidence before completion claims

Every behavior change MUST have focused regression coverage and pass the full
repository suite. Record the tested revision, command, failures and skips.
Browser fixtures, real terminal smoke tests and physical-device validation are
different evidence classes; none may be presented as another. A checked spec-quality
item does not certify a shipped capability.

### IV. Bounded changes and compatible boundaries

Follow the component map and existing code style. Keep each increment scoped to
one reviewable outcome; preserve root entrypoints and public CLI/API behavior.
Changes to persisted state require migration and rollback reasoning. Do not
introduce a framework migration or dependency merely to reorganize UI code.

### V. Understandable, accessible behavior

Expose execution state separately from display connectivity and manual labels.
Never rely on color alone or label an unobserved outcome as success. User-facing
controls need accessible names and keyboard paths. Keep English and Chinese
instructions synchronized when behavior or setup changes.

## Repository Constraints

[Contributor rules](../../AGENTS.md), [contribution guide](../../CONTRIBUTING.md),
[security](../../SECURITY.md), [release guide](../../RELEASING.md), and the
[architecture map](../../docs/architecture/README.md) remain authoritative
repository guidance. Spec Kit is optional development tooling, not a runtime
dependency; initialization MUST preserve existing project instructions and settings.

## Development Workflow and Quality Gates

Read existing specs, implementation and tests before proposing a change. Develop
in an isolated worktree, not the active Dashboard checkout. Use `make verify`
with the selected Python interpreter and `git diff --check`. Dashboard or terminal
changes additionally need the relevant isolated browser/terminal smoke tests.

Keep requirements, implementation plans and dated validation evidence distinct.
Review the selected increment before implementing; a Spec Kit stage does not
authorize its next stage. Commit/push and runtime update retain the user's existing
authorization boundaries. Pushing the project's own `main` is not deployment.

## Governance

This constitution records existing constraints; it does not override explicit
user instructions or silently replace repository policy. Amend through a reviewed
documentation change with rationale and affected specs identified. Use semantic
versions: major for incompatible principles, minor for new principles, patch for
clarifications. Plans and reviews MUST record exceptions with reasons and approval;
never weaken a gate simply because a test fails.

**Version**: 1.0.0 | **Ratified**: 2026-10-05 | **Last Amended**: 2026-10-05
