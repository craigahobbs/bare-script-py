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

Faithful port written from scratch. All 405 Python tests pass.

| Benchmark    | Pure Python | C port    | Speedup |
|--------------|-------------|-----------|---------|
| test-include | 3404.2 ms   | 1647.4 ms | 2.07x   |
| perf         | 16721.0 ms  | 5060.0 ms | 3.30x   |

Reductions: 52% and 70%. Target is 90% — need another 4.8x for test-include and 3.0x for perf.

## Phase 2 — Optimization Ideas (ranked)

1. **Hoist per-call constants out of statement loop** in execute_script_helper:
   max_statements, coverage_global, has_coverage. Currently dict-lookup every statement.
   Estimate: 20-30%.

2. **Local statement counter**: keep `long long` in C; flush to options dict only on
   error/return. Estimate: 15-30%.

3. **Identity check before PyUnicode_Compare for AST keys**: CPython interns short
   string literals; AST keys like 'expr', 'binary', etc. are interned by the parser.
   Replace `PyUnicode_Compare(k, KS_X) == 0` with `(k == KS_X || PyUnicode_Compare(...))`.
   Estimate: 10-15% (lots of these in hot path).

4. **Hash-based dispatch** for expression keys (number/string/variable/function/binary/unary/group):
   small lookup table or switch on first-char + length. Estimate: 5-10%.

5. **Avoid is_integer_valued repeated work**: cache integer coercion across &, |, ^, <<, >>.
   Low priority.

6. **Coverage fast-path**: only check coverage state on first statement; once recorded, the
   inner script body won't change script.system or coverage_global pointer. We can cache
   has_coverage in helper frame. Already partially captured by #1.

7. **ScriptFunction local dict reuse**: minor.

Priority order: 1+2+3 combined first (overlapping code regions). Then 4 if needed.
