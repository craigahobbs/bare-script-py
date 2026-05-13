# runtime_c.c Optimization Log

## Baselines (Phase 0)

Pure-Python runtime (`runtime.py`, `BARESCRIPT_RUNTIME_PY=1`):
- `make test-include`: **3417.4 ms**
- `make perf` BareScript: **16749.0 ms** (109.1x slower than native Python)

Pre-existing optimized C runtime (for context only — deleted in Phase 1):
- `make test-include`: 1346.7 ms
- `make perf` BareScript: 3105.0 ms (20.3x slower)

Goal: improve **the new from-scratch C port baseline** by 90% (10x speedup).
