# Repository Guidelines

## Project Structure & Module Organization

Core Python code lives in `agent_orchestrator/`. Add implementation there; the root `orchestrator.py` and `dashboard.py` files are compatibility entrypoints. The `siling` script is the primary CLI launcher. Browser assets are in `static/`, operational shell helpers in `scripts/`, macOS service tooling in `launchd/`, and user documentation in `docs/`. Tests are standard-library `unittest` modules under `tests/`, generally named `test_<feature>.py`. Example configuration belongs in `examples/`; machine-local configuration and runtime data belong in ignored paths such as `dashboard.local.json`, `outputs/`, and `tasks/private/`.

## Build, Test, and Development Commands

Use Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
./siling dashboard
python -W error -m unittest discover -s tests -v
python -m py_compile *.py agent_orchestrator/*.py scripts/*.py launchd/*.py
bash -n scripts/*.sh launchd/*.sh
python -m json.tool examples/dashboard.local.json >/dev/null
```

The first command installs dependencies; the second starts the local Dashboard. The remaining commands mirror CI: tests with warnings treated as errors, Python compilation, shell syntax validation, and JSON validation. For Dashboard changes, also parse the final inline `<script>` in `static/index.html` with Node.js, as shown in `.github/workflows/ci.yml`.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, type hints for public boundaries, `snake_case` functions and variables, and `PascalCase` classes. Keep helpers small and preserve the package’s local-first defaults. JavaScript in `static/index.html` uses two-space indentation and `camelCase`; CSS classes use kebab-case. No automatic formatter is enforced, so match surrounding code and run `git diff --check`.

## Testing Guidelines

Add focused regression tests for every behavior change. Prefer descriptive names such as `test_remote_api_path_quotes_original_id`. Run the full suite before handoff. Dashboard work also needs a manual smoke test: create a background session, attach a pane, send input, and stop it cleanly. Remote-node changes should verify discovery plus HTTP/WebSocket proxying.

## Commit & Pull Request Guidelines

Use short, imperative subjects following repository history: `feat: ...`, `fix: ...`, or `ux: ...`. Keep commits narrowly scoped. Pull requests should explain user-visible behavior, list test evidence, and include screenshots for UI changes. Update both `README.md` and `README_CN.md` when instructions change.

## Security & Configuration

Never commit tokens, transcripts, private prompts, certificates, or local paths. Preserve localhost-only defaults and require authentication for non-loopback binds. Review `SECURITY.md` and `RELEASING.md` before security-sensitive or release work.
