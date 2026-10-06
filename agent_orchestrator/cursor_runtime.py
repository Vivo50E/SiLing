"""Per-conversation Cursor model state and non-interactive restart preflight."""
import json
import os
from pathlib import Path
import re
import subprocess

MODEL_STATE = '.cursor-model.json'


def saved_model(run_dir: str, conversation_id: str) -> dict | None:
    if not run_dir or not conversation_id:
        return None
    try:
        path = Path(run_dir) / MODEL_STATE
        if path.stat().st_size > 65536:
            return None
        state = json.loads(path.read_text())
        if state.get('version') != 1 or state.get('conversation_id') != conversation_id:
            return None
        fields = state['fields']
        model = fields['model']['modelId']
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,127}', model):
            return None
        # Never carry arbitrary config/authentication fields into another run.
        fields = {key: fields[key] for key in ('model', 'selectedModel', 'modelParameters', 'maxMode', 'maxModeAutoEnabled') if key in fields}
        return {'version': 1, 'conversation_id': conversation_id, 'fields': fields}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def check_auth(cli: str, cwd: str) -> None:
    """Check saved credentials without initiating browser login or logging tokens.

    Cursor status verifies credential availability, not that a future server
    request cannot revoke/expire them. Explicit token authentication is already
    supplied by the caller and isn't represented by Cursor's status command.
    """
    if os.environ.get('CURSOR_API_KEY') or os.environ.get('CURSOR_AUTH_TOKEN'):
        return
    try:
        result = subprocess.run([cli, 'status', '--format', 'json'], cwd=cwd,
                                stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=15)
        status = json.loads(result.stdout)
        if result.returncode == 0 and status.get('isAuthenticated') is True:
            return
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError('Cursor login could not be verified; agent was not stopped. '
                       'Check Cursor login/keychain access in the same desktop session, then retry.')
