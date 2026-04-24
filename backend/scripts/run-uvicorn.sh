#!/bin/sh
# Wrapper that runs uvicorn with kernel OOM protection.
#
# On Linux hosts running large local models (60GB+), system-wide memory
# pressure can trigger the OOM killer. This wrapper lowers the OOM score
# so the kernel prefers killing the model server over the benchmarking
# orchestrator (which would lose in-progress run state).
#
# Requires: sudo access to write /proc/self/oom_score_adj (optional —
# the script continues without OOM protection if sudo is unavailable).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_UVICORN="$SCRIPT_DIR/../.venv/bin/uvicorn"

if [ ! -f "$VENV_UVICORN" ]; then
    VENV_UVICORN="$(command -v uvicorn)"
fi

if sudo -n /usr/bin/sh -c "echo -1000 > /proc/$$/oom_score_adj" 2>/dev/null; then
    : # OOM protection active
fi

exec "$VENV_UVICORN" app.main:app --host 0.0.0.0 --port 8000
