#!/bin/bash
# One-off setup for the clip tool: creates a private Python environment, installs
# the transcription package and the renderer, then runs the checks.
# Safe to run again at any time. Needs an internet connection.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

say_step() { printf '\n== %s\n' "$1"; }
missing=0

say_step "Checking what is already on this Mac"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffmpeg is missing. Install it with:  brew install ffmpeg"
  missing=1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js is missing. Install it with:  brew install node"
  missing=1
else
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
  if [ "$NODE_MAJOR" -lt 18 ]; then
    echo "Node.js $(node --version) is too old. Version 18 or newer is needed:  brew install node"
    missing=1
  fi
fi
PY="${CLIP_TOOL_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "Python 3.9 or newer is missing. Install it with:  brew install python"
  missing=1
fi
if [ "$missing" -ne 0 ]; then
  echo
  echo "Install the items above (Homebrew: https://brew.sh), then run this script again."
  exit 1
fi
echo "ffmpeg, Node.js $(node --version) and $("$PY" --version) found."

say_step "Python environment (.venv)"
if [ ! -x ".venv/bin/python" ]; then
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
echo "Transcription package installed."

say_step "Renderer (about 600 MB, a few minutes the first time)"
(cd render && npm install --no-audit --no-fund)

say_step "Settings"
if [ ! -f config.env ]; then
  cp config.example.env config.env
  echo "Created config.env with default settings."
else
  echo "config.env already exists, left untouched."
fi

say_step "Checks"
.venv/bin/python doctor.py
