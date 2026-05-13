# runtime_c.c Optimization Log

## Phase 0 — Baseline (Pure Python)

- `make test-include`: **3382.6 ms**
- `make perf` BareScript: **16718.0 ms** (108.8× Python)

Goal: improve `runtime_c.c` perf by 90% over pure-Python baseline
- perf target: ≤ ~1672 ms
- test-include target: ≤ ~338 ms

## Phase 1 — Initial Port

Plan: faithful C port of runtime.py exposing `execute_script`,
`evaluate_expression`. Reuse Python helpers (value_boolean,
value_compare, value_string, value_normalize_datetime,
value_round_number) via the Python C API.

