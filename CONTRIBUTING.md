# Contributing

Thanks for helping improve SiLing.

## Development setup

1. Use Python 3.10 or newer.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Install at least one supported agent CLI and `tmux` for manual integration
   testing.
4. Install `make`, Bash and Node.js for repository checks. Browser checks also
   need a Chromium-based executable via `UI_BROWSER`; they are opt-in and use
   isolated test sessions, not your existing sessions.

Start with the [architecture map](docs/architecture/README.md) and
[documentation index](docs/README.md). `workspace.json` is the machine-readable
component catalog; `make map` validates and prints it. Runtime scripts stay in
`scripts/`; developer-only tools belong in `tools/`.

Copy `examples/dashboard.local.json` to `dashboard.local.json` when you want
machine-specific Dashboard shortcuts. Keep private task recipes in
`tasks/private/` and runtime data in `outputs/`. These paths are ignored by
Git. Never include tokens, transcripts, local paths, or private prompts in an
issue or pull request.

## Checks

Run the same entrypoint used in continuous integration:

```bash
make verify PYTHON=.venv/bin/python
```

Use an absolute interpreter path for a development worktree without its own
`.venv`. Do not resolve a virtualenv interpreter symlink to system Python.

| Command | Purpose |
| --- | --- |
| `make map` | Validate and print the component catalog as JSON |
| `make check` | Validate layout/import boundaries and Python, each shell script, JS, inline Dashboard JS and JSON syntax |
| `make test` | Run all `unittest` tests with warnings treated as errors |
| `make verify` | Run both checks and the full test suite; no deployment |
| `make dev` | Explicitly start the local Dashboard |
| `make test-ui` | Isolated browser regression checks; requires `UI_BROWSER` |
| `make test-terminal` | Real isolated tmux/ttyd regression; requires `UI_BROWSER`, `tmux`, `ttyd` |

Set `PYTHON` on any target that invokes Python. Without make, use
`python -W error tools/check.py` and
`python -W error -m unittest discover -s tests -v`.
Review both staged and unstaged changes with `git diff --check` and
`git diff --cached --check` before committing.

The existing self-update verifier continues to run full `unittest` discovery
and reject zero tests. Repository layout and Python import boundaries are part
of that suite. Do not replace full verification with component-only tests or
change update approval behavior as part of a source-layout change.

Application modules live in `agent_orchestrator/`. The root-level
`orchestrator.py` and `dashboard.py` files are compatibility entrypoints; add
new Python implementation code to the package instead of the repository root.

For dashboard changes, also start a local instance, create a background
session, attach a terminal pane, send input, and stop the session cleanly.
Remote Nodes changes should additionally start a temporary node-only instance
and verify session discovery plus HTTP/WebSocket terminal proxying.

## Pull requests

For desktop changes, also run `npm ci --prefix apps/desktop` and
`npm run test:integration --prefix apps/desktop`. This launches an isolated
Electron window with fixture servers and a temporary profile; it never uses the
running Dashboard. Dependency-free desktop policy tests are included in
`make verify`. Keep Electron pinned and refresh its lockfile when updating it.

- Keep each change focused and explain its user-visible behavior.
- Add or update tests for logic changes.
- Keep the English homepage (`README.md`) and Chinese page (`README_CN.md`) in
  sync, with a language switch at the top of each. `README_EN.md` is only a
  compatibility link; do not duplicate the English content there or combine
  both languages into the homepage.
- Preserve the safe defaults: localhost binding without a token, mandatory
  authentication for non-loopback binds, and ignored runtime data.

Maintainers preparing a public snapshot should also follow `RELEASING.md`.
