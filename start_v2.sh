#!/bin/bash
set -e
python -m v2.backend.scanner &
exec python -m uvicorn v2.backend.api:app --host 0.0.0.0 --port "${PORT:-8000}"
