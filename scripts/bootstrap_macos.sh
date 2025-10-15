#!/usr/bin/env bash
set -euo pipefail
PY_BIN="${PY_BIN:-python3}"
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "[ERR] python3 not found. Install Python 3.10/3.11 first."
  exit 1
fi
if [ ! -d ".venv" ]; then
  "$PY_BIN" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements-macos.txt
echo "[OK] Environment ready."
