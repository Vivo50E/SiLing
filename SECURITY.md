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

An explicit same-origin connection action selects an existing trusted JSON MCP
configuration. The Dashboard persists its file/server reference and Jira base URL,
not credentials; expanded environment/header values stay in the client worker's
stdin and memory. Configuration fingerprints require reconnecting after changes.
The SDK 1.x client runs in an isolated subprocess, suppressing provider logs and
returning only bounded ticket keys, titles, statuses and fixed error codes.
Only the fixed `jira_get_issue` tool can be called, with validated evidence keys
and minimal fields. Server tool descriptions cannot select tools or commands;
sampling, elicitation, writes, comments and attachment operations are not enabled.
No transcript or prompt is sent to MCP. Only opted-in groups trigger lookups;
requests and concurrency are bounded. Disconnect discards in-flight results.

MCP configurations and their stdio executables must be trusted: a stdio server
runs with the Dashboard user's OS privileges. Read-only tool selection is not an
OS sandbox and cannot constrain a malicious server. HTTPS (or loopback HTTP) is
required for configured network endpoints; the SDK restricts redirects to the
same origin. Authentication must already be handled by server configuration or a
trusted bridge. Provider-returned content is treated as display text, never as
instructions, HTML or a URL to fetch. Ticket links are constructed from the
explicitly configured Jira site and matching issue key. Existing administrator
and same-account access remains outside this boundary.
