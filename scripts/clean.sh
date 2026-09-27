#!/usr/bin/env bash
# Stop SiLing tmux sessions without touching unrelated sessions.
# Usage: siling clean [-f]

set -euo pipefail

FORCE=false
for arg in "$@"; do
    case "$arg" in
        -f|--force) FORCE=true ;;
        -h|--help)
            echo "usage: siling clean [-f|--force]"
            exit 0
            ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

SESSIONS=()
while IFS= read -r session; do
    [[ "$session" == orch-* ]] && SESSIONS+=("$session")
done < <(tmux list-sessions -F '#{session_name}' 2>/dev/null || true)

if [[ ${#SESSIONS[@]} -eq 0 ]]; then
    echo "No SiLing tmux sessions found."
    exit 0
fi

echo "Stopping SiLing tmux sessions:"
printf '  %s\n' "${SESSIONS[@]}"
if $FORCE; then
    echo "Note: --force is retained for compatibility; tmux sessions are stopped individually."
fi

FAILED=()
for session in "${SESSIONS[@]}"; do
    if ! tmux kill-session -t "$session" 2>/dev/null; then
        FAILED+=("$session")
    fi
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo "Unable to stop these sessions:" >&2
    printf '  %s\n' "${FAILED[@]}" >&2
    exit 1
fi

echo "Stopped ${#SESSIONS[@]} SiLing session(s)."
