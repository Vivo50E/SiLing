# Validation: Mobile reader

Use an isolated development worktree, not the running checkout.

```sh
make verify PYTHON=/absolute/path/to/venv/bin/python
UI_BROWSER=/absolute/path/to/chromium make test-ui
UI_BROWSER=/absolute/path/to/chromium make test-terminal PYTHON=/absolute/path/to/venv/bin/python
git diff --check
```

Fixture acceptance: fresh mobile boot with saved desktop slots/TTY → zero terminal requests; list/search/attention → reader → Files/back; explicit terminal → one iframe maximum; late/failed output preserves identity/time; desktop resize preserves drafts/preferences. Check 360/390/430px, landscape, keyboard focus, bilingual copy and overflow.

Real terminal smoke creates disposable sessions, attaches, sends harmless shell input and stops only its own sessions. Never restart a user's agent.
Record automated, browser-emulated, real-terminal and physical-device evidence separately. Physical iOS/Android touch, keyboard and connection acceptance remains pending. No deployment/runtime restart without separate approval.
