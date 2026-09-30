# Use the selected interpreter for local worktrees and CI alike.
PYTHON ?= python3

.PHONY: help map check test verify dev test-ui test-terminal

help:
	@echo "make map           Show the machine-readable component map"
	@echo "make check         Validate layout and Python/Shell/JS/JSON syntax"
	@echo "make test          Run the full regression suite"
	@echo "make verify        Run check + test (same entrypoint as CI)"
	@echo "make dev           Start a local Dashboard (explicit action)"
	@echo "make test-ui       Run isolated browser checks (requires UI_BROWSER)"
	@echo "make test-terminal Run isolated tmux/ttyd checks (requires UI_BROWSER)"
	@echo "Override the interpreter with PYTHON=/absolute/path/to/venv/bin/python"

map:
	@"$(PYTHON)" tools/check.py --map

check:
	"$(PYTHON)" -W error tools/check.py

test:
	"$(PYTHON)" -W error -m unittest discover -s tests -v

verify: check test

dev:
	"$(PYTHON)" orchestrator.py dashboard

test-ui:
	node tests/ui_browser.mjs

test-terminal:
	PYTHON="$(PYTHON)" node tests/terminal_browser.mjs
