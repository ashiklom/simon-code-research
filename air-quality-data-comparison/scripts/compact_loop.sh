#!/usr/bin/env bash
# Compact every product repo periodically while long extractions run (they compact only every
# few commits). keep_minutes=10 keeps chunks written by in-flight sessions safe.
cd "$(dirname "$0")/.."
while true; do
  for r in data/store/products-*.icechunk data/store/obs-*.icechunk; do
    n=$(basename "$r" .icechunk)
    ICECHUNK_LOG=error uv run python -c "
import sys; sys.path.insert(0,'src')
from aqc import store
try: print(store.compact('$n', keep_minutes=10))
except Exception as e: print('$n', repr(e))
" 2>&1 | grep -v UV_NATIVE
  done
  sleep 600
done
