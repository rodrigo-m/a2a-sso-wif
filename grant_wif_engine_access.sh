#!/bin/bash
# ==============================================================================
# Shell wrapper to grant WIF principal IAM permission on Vertex AI Reasoning Engine
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PYTHON_CMD="python3"
if [ -f ".venv/bin/python" ]; then
  PYTHON_CMD=".venv/bin/python"
fi

exec $PYTHON_CMD grant_wif_engine_access.py "$@"
