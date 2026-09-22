#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
if [ -x .venv/bin/python ]; then
  runner=.venv/bin/python
elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
  runner="$CONDA_PREFIX/bin/python"
else
  runner=python3
fi
if ! "$runner" transcribe_betagaki_gui.py; then
  echo "Startup failed. See README.md and install requirements in the selected Python environment."
  read -r -p "Press Enter to close..." unused
  exit 1
fi
