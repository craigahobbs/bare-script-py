# runtime_c.c Optimization Log

## Phase 0 — Baselines

| Measurement                       | Time (ms)  |
|-----------------------------------|-----------:|
| Pure Python `make test-include`   |    3381.2  |
| Pure Python `make perf` BareScript|   16952.0  |
| Old C runtime `make test-include` |    3396.1  |
| Old C runtime `make perf`         |   16829.0  |

The old runtime was effectively no faster than the pure Python implementation.

## Phase 1 — Fresh Port Baseline

| Measurement       | Time (ms) | vs. Python |
|-------------------|----------:|-----------:|
| test-include      |  1585.3   |  -53.1%    |
| perf (BareScript) |  4727.0   |  -72.1%    |

90% target: test-include ≤ 338 ms, perf ≤ 1695 ms.

## Phase 2 — Optimization Ideas

Ranked by estimated impact / simplicity:

1. **Interned-string identity dispatch** — replace `PyUnicode_Compare` with pointer-equality
   on interned strings for statement keys, expression keys, and binary/unary op chars.
   Hot-path dispatch is currently ~10 string compares per statement. Estimated 10–20%.

2. **Cache statementCount locally** — read once at function entry, write once at exit
   (or on errors that need the value). Saves a PyDict_GetItem + PyLong_FromLong + PyDict_SetItem
   per statement. Estimated 15–25%.

3. **Cache coverage_global per exec_script_helper call** — not per statement. Coverage globals
   don't change across the run. Estimated 5–10% in non-coverage runs (`make perf`).

4. **Vectorcall for ScriptFunction** — skip PyArg_UnpackTuple + PyDict_New overhead.
   Estimated 5–10%.

5. **Specialized comparison fast path** — for number/number and string/string, skip
   `value_compare` call. Estimated 5–10%.

6. **Inline statement[key] lookup** — when we already did `dict_first_key`, we can read
   the inner via PyDict_Next instead of a second lookup. Estimated 3–5%.

7. **Specialized binary +/- for number/number** — skip is_number checks (inline). Estimated 3–5%.

8. **Direct exec_script_helper call for ScriptFunction** — skip the tp_call indirection.
   Estimated 3–5%.

9. **`max_statements` cache** — like statementCount, hoist out of loop. Estimated 5%.

## Phase 3 — Iterative Optimization

(in progress)
