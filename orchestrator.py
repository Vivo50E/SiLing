#!/usr/bin/env python3
"""Backward-compatible entrypoint for the SiLing CLI.

New commands should use the repository's ``siling`` launcher.
"""

from agent_orchestrator.cli import main


if __name__ == "__main__":
    main()
