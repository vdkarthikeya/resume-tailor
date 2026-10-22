#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x .venv/bin/uvicorn ]; then
  rm -rf .venv
  python3 -m venv .venv || exit 1
  .venv/bin/pip install --upgrade pip || exit 1
  .venv/bin/pip install -r requirements.txt || { echo "Install failed, see the error above"; rm -rf .venv; exit 1; }
fi
echo "Open http://127.0.0.1:8000"
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
