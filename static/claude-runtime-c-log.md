# runtime_c.c Optimization Log

## Baseline measurements (Phase 0)

Pure Python (`runtime.py`):
- `make perf` BareScript: **16562 ms** (107.4x slower than Python)
- `make test-include` debug suite: **3413 ms**
- `make test-include` non-debug: 97 ms

Pre-existing `runtime_c.c`:
- `make perf` BareScript: **4698 ms** (30.5x slower than Python)
- `make test-include` debug suite: **1611.8 ms**

Target: 90% improvement vs pure Python
- perf ≤ 1656 ms
- test-include ≤ 341 ms

