# Security Policy

## Supported version

Security fixes target the latest version on the default branch.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub private
vulnerability reporting when it is available, or contact the maintainers
privately. Include reproduction steps and impact, but remove real tokens,
transcripts, local paths, and other personal data.

## Deployment model

SiLing can send input to local tmux sessions and should be treated
as a privileged developer tool.

- The default dashboard bind is localhost-only.
- Non-loopback binds require a token.
- Use HTTPS or a trusted HTTPS tunnel for remote access.
- Remote Nodes extend the local Dashboard's control privileges to each
  configured node. Keep nodes on loopback, use SSH or a trusted tunnel, and
  store per-node tokens in environment variables rather than JSON.
- Native agent hooks are observe-only by default. Permission auto-approval is
  an explicit opt-in and should be enabled only on trusted single-user
  machines after reviewing the affected agent sessions.
- Workspace sync and continuous auto-sync are disabled by default. If enabled,
  begin with a narrow allowlist and review the comparison baseline before any
  transfer.
- Do not publish `outputs/`, `projects/`, `.dashboard-certs/`, local
  configuration files, SSH material, native transcripts, or private task
  recipes.
- Run the dashboard as an unprivileged user and expose it only to trusted
  networks.

## Secret operation boundary

The volatile broker keeps API keys out of agent environment variables, tmux input,
command arguments and response text. Operations bind credentials to fixed HTTPS
requests and expose status only. The fixed Slack `auth.test` POST adapter reads at
most 16,385 response bytes, rejects bodies above 16 KiB, and extracts only a strict
boolean `ok`; HTTP 200 with Slack `ok: false` is a failure. Generic operations never
read response bodies. Raw response bodies/headers, redirects, arbitrary
commands, credential retrieval and request overrides are deliberately excluded.
Names are scoped by session identity, but Dashboard admin authentication can manage
all sessions; it is not an untrusted-agent credential. Same-account processes and
administrators remain outside this API boundary. Separate OS privileges and remove
Dashboard admin-token access before treating an agent as adversarial. Keys are
transient in memory, not encrypted at rest; expiry/revoke erases the retained
bytearray but cannot guarantee removal of Python, HTTP or TLS memory copies.
A request already sent before revocation may finish. Do not paste these keys into
ordinary shell commands or agent messages. Terminal private-input delivery is
retired: even old-page remote requests receive 410 before any forwarding.

## Secret configuration boundary

The explicit configuration writer sends credentials directly to `backend.env`,
never through tmux, agent prompts, command arguments or API response content.
SSH uses a fixed isolated Python helper, stdin payloads, noninteractive auth and
verified host keys; Remote Nodes require HTTPS or loopback tunnels. It validates
single-line dotenv values, rejects symlinks/hardlinks and tracked/unignored Git
targets, stages outside Git on the same filesystem, and atomically replaces an
owner-only file. It does not create backups, reload services or retry writes.
Handled errors clean temporary files; abrupt termination can leave a `0600`
staging file. Existing plaintext, OS memory copies and same-account/admin file
access are outside this boundary. To keep the agent from reading the target,
use separate OS privileges/hosts and withhold that file's access. This writer
is not an encrypted vault or a substitute for the status-only operation broker.

## Review status lookup

On-demand PR/MR status queries use fixed gh/glab read-only commands with numeric
review IDs and explicit repositories. Detail queries accept HTTPS URLs only and
restrict hosts to github.com/gitlab.com, configured CLI host keys, or explicit
GH_HOST/GITLAB_HOST values. CLI configuration is read locally to identify trusted
hosts; credentials and provider error output are never returned or cached by the
Dashboard. A matching response identity is required. Queries run outside the
session index lock with bounded concurrency and duration. Badge-only requests do
not run provider commands. Status failures retain previous observations and are
reported separately; displayed colors are based on the latest known status.

## Jira MCP boundary

An explicit same-origin connection action selects an existing trusted JSON or
Codex TOML MCP configuration. Local discovery reads only user-level server names,
sources and file references; it never starts servers or returns commands,
endpoints, headers or environment values. The Dashboard persists its file/server reference and Jira base URL,
not credentials; expanded environment/header values stay in the client worker's
stdin and memory. Configuration fingerprints require reconnecting after changes.
The SDK 1.x client runs in an isolated subprocess, suppressing provider logs and
returning only bounded ticket keys, titles, statuses and fixed error codes.
Only the fixed `jira_get_issue` and `jira_search` tools can be called, with
validated evidence keys or a generated summary-only JQL query and minimal fields.
Reviewed read adapters accept issue_key/issue_id, string/array minimal fields,
limit/top_k and optional fixed page/disabled expansion flags; at most five sanitized
task-name words and eight results are used. Every search title must match all
words locally before association. Server tool descriptions cannot select tools
or commands;
sampling, elicitation, writes, comments and attachment operations are not enabled.
No full transcript or prompt is sent to MCP; task-name keywords are sent for
ordinary searches. Opt-in AI topic search sends the task name (300 characters)
and saved initial description (2,000 characters) to the local Claude CLI's configured model service, never terminal output or native transcripts. It uses
a temporary non-project working directory, disables tools, MCP, hooks, slash
commands and session persistence, with a $0.10 budget and 25-second timeout.
Metadata with common credential markers is skipped; this heuristic cannot
guarantee arbitrary metadata is secret-free. Model output is untrusted: only
up to three sets of two or three validated keywords are accepted. The model
cannot supply JQL, tools, issue IDs or ticket URLs. SiLing constructs a fixed
summary-only OR query and validates returned titles against a whole keyword set.
Only metadata hashes and topic keywords are cached, not raw input or CLI errors.
Topic plans are reused across restarts; failures cool down for ten minutes.
Opt-in visible active panes refresh at most once per ten minutes in each client;
server search caching and model serialization bound repeated client requests. Generic and credential-like names are skipped. Only opted-in groups
trigger lookups;
requests and concurrency are bounded. Disconnect discards in-flight results.

MCP configurations and their stdio executables must be trusted: a stdio server
runs with the Dashboard user's OS privileges. Read-only tool selection is not an
OS sandbox and cannot constrain a malicious server. HTTPS (or loopback HTTP) is
required for configured network endpoints; the SDK restricts redirects to the
same origin. Header/stdio authentication must already be handled by server configuration or a
trusted bridge. The optional macOS browser flow below manages its own OAuth credentials. Native private OAuth caches and keychains are not read or copied.
Dynamic credential helpers and remote-executor environment are rejected rather
than silently falling back to an unauthenticated or different local identity.
Provider-returned content is treated as display text, never as
instructions, HTML or a URL to fetch. Ticket links are constructed from the
explicitly configured Jira site and matching issue key. Existing administrator
and same-account access remains outside this boundary.

## Update verification evidence

Smart verification reuses only the latest completed successful GitHub CI push
run for the exact upstream main commit and configured GitHub repository. Both
Python full-suite jobs and the desktop job must succeed, with no skipped jobs
or full-suite steps. The run attempt is checked again after fetching its jobs.
Workflow, setup action, requirements and runner changes force full local tests.
Unavailable or malformed evidence also falls back to the full local suite.
Local dependency imports, authenticated startup, exact build identity and a
nonempty passing regression suite remain mandatory when CI is reused.
Neither path changes clean-tree, fast-forward, exact commit binding, approval
token expiry or explicit approval requirements. Provider tokens and raw CLI
errors are not exposed. Full local tests can always be requested explicitly.


## Dashboard Jira OAuth login

Browser login requires an authenticated, same-origin POST with explicit user-click
intent from a direct client on the Dashboard Mac. Native OAuth caches are never
read. One subprocess performs registration, PKCE S256 authorization and token
exchange. The callback binds only to an ephemeral IPv4 loopback port, checks the
exact Host, path and unpredictable state, accepts only one code/error, suppresses
request logs and sends no-store/referrer/CSP headers. It expires after four
minutes; a hard worker deadline, cancellation and shutdown close the listener.
No authorization URL, code or token is returned by the Dashboard API. The system
browser receives the authorization URL through the existing macOS URL opener;
it contains client ID, state and the public PKCE challenge, never the verifier
or a client secret. Only the user's official identity-provider pages handle login.

Discovery begins at the selected trusted MCP's 401 resource-metadata challenge.
Protected-resource metadata must share its origin and identify the exact resource;
the issuer must match authorization metadata. Production issuers/endpoints require
HTTPS, endpoints must share the issuer origin, and HTTP redirects are not followed.
No legacy endpoint guessing, native-client impersonation or secret-copy fallback is
used. Read-named resource scopes are preferred; explicit write/admin scopes are
excluded from the fallback. OAuth consent may still grant gateway-level access;
fixed read-only MCP tool selection remains the application boundary.

A dedicated macOS Keychain service stores client secrets and tokens through
Security.framework memory APIs, never CLI arguments, browser storage or plaintext
files. Records are bound to the exact MCP resource and pinned issuer endpoints.
Only an opaque random account reference is saved in connection configuration.
Per-user private lock files contain no credentials; cross-process locking serializes
refresh-token rotation and deletion. Expiry is absolute across subprocess restarts.
Background refresh cannot register a client or open a browser. Failures report
fixed error codes without provider content. Keychain being locked/denied fails
closed; same-user/admin process access remains outside this boundary.

Explicit login cancellation invalidates pending connection verification and kills
the worker; late responses cannot replace a newer/disconnected configuration.
Failed login entries are deleted. Disconnect disables the saved connection before
deleting its owned Keychain entry and reports deletion failure. It does not revoke
remote grants or remove native credentials. Remote client registrations can remain
after cancellation; revoke unneeded grants with the provider when appropriate.


## Jira MaaS schema compatibility

Tool names remain the fixed `jira_get_issue`/`jira_search` allowlist. Argument
selection depends only on reviewed identifier, field and pagination schema types,
not provider descriptions or model output. Nullable schemas are unwrapped only
when there is a single non-null type. Unknown required arguments and ambiguous
identifiers fail closed. MaaS issue lookup uses `issue_id`, fields are arrays,
and searches use `top_k`; responses explicitly marked unsuccessful are discarded
before nested result unwrapping. Only keys, bounded titles and states are retained.

MaaS text search requires a user-configured project key. Keys are restricted to
ASCII Jira identifier syntax and inserted into generated JQL with the entire
keyword expression parenthesized. Project scope is checked in both worker and
parent before accepting new search associations; explicit evidence-key lookups
and retained historical links are not restricted to the current search project.
Missing scope skips AI planning. A changed project is part of the search-cache
identity. Project-page URLs can be normalized to a site/context root and project
key; explicit conflicts are rejected. No new tool or write operation is enabled.
