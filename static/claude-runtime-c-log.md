# runtime_c.c Optimization Log

## Goal

Improve measured performance by 90% (reduce time to 10% of original) vs. pure-Python `runtime.py`.

## Phase 0 — Pure-Python Baseline

Pure-Python `runtime.py` measurements (no C extension):

| Benchmark    | Time       |
|--------------|------------|
| test-include | 3404.2 ms  |
| perf         | 16721.0 ms |

90% improvement targets:
- test-include: ≤ 340 ms
- perf:         ≤ 1672 ms

## Phase 1 — Fresh Port

Plan: delete existing `runtime_c.c`, faithfully port `runtime.py` to C for Python 3.13+.
