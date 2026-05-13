# runtime_c.c Optimization Log

## Phase 0 — Baselines (before re-port)

Existing runtime_c.c (the prior implementation, about to be deleted):

| Metric            | Time      |
|-------------------|-----------|
| perf BareScript   | 4304.0 ms |
| perf Python ref   | 154.7 ms  |
| test-include      | 1544.5 ms |

Pure Python runtime.py:

| Metric            | Time      |
|-------------------|-----------|
| perf BareScript   | 16642.0 ms |
| perf Python ref   | 154.0 ms  |
| test-include      | 3372.7 ms |

## Phase 1 baseline (fresh port, no optimizations)

| Metric            | Time      |
|-------------------|-----------|
| perf BareScript   | 4539.0 ms |
| perf Python ref   | 152.0 ms  |
| test-include      | 1562.3 ms |

## Goal

90% improvement over Phase 1 baseline → target ~454ms perf, ~156ms test-include.
