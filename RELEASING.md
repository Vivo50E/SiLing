# Release process

The public repository is the canonical home for portable product code. A
private deployment may carry machine-local integration work, but reusable
changes should be upstreamed here promptly so the two implementations do not
become independent forks. Secrets, host-specific commands, runtime state, and
private task data belong only in ignored local configuration or external
state—not in a second source variant.

## Before a release

The base product version lives in `agent_orchestrator/version.py` (`VERSION`).
Bump it for a named release; ordinary committed updates automatically receive a
unique `+g<12-character commit>` build suffix. About SiLing reports the identity
captured at Dashboard app startup, not a fetched candidate. Restart the service
through the approved update flow before checking the new running version.
Source archives without `.git` report `+unknown`; retain Git metadata for an
identifiable build. Do not publish `.dirty` or `.unknown` as verified releases.

1. Keep machine-specific settings, credentials, logs, and task data in ignored
   local files or outside the repository.
2. Run the test suite and syntax checks documented in `CONTRIBUTING.md`.
3. Scan the complete tracked tree for credentials, private paths, internal
   hostnames, and unexpectedly large files.
4. Review the diff since the previous public release and any portable changes
   that exist only in a private deployment.

## Publish reviewed source, not private history

Never copy or merge a private commit graph merely to move reusable code. Port
reviewed source changes as ordinary public commits, with private configuration
removed and tests preserved. Historical commits can retain deleted secrets,
paths, transcripts, and infrastructure names even when the current checkout
looks clean.

Before publishing, compare shared modules between public and private trees and
account for every difference. Deployment-only differences should be small,
documented, and configuration-driven. A reusable code fix that remains only in
the private tree is release debt and should be upstreamed before the next
release.

Publishing, rewriting a public branch, and changing repository visibility each
require an explicit maintainer review.
