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

## Initial port (Phase 1)

Faithful port baseline:
- `make perf` BareScript: **4310 ms** (27.6x slower than Python; 74% better than pure Python)
- `make test-include` debug: **1574 ms** (54% better than pure Python)

## Optimization ideas (Phase 2)

Hot paths analysis from runtime.py:
1. **Expression dispatch**: each call does ~5 PyUnicode_Compare to identify key. Pointer-identity on interned keys would be ~10x faster.
2. **Statement counter**: PyDict_GetItem + PyLong_FromLongLong + PyDict_SetItem every statement → expensive. Cache as C int in execute_script with periodic check.
3. **Coverage check overhead**: PyDict_GetItem on globals + isinstance + get('enabled') + script.get('system') every statement, even when coverage disabled. Hoist these checks out of the loop, only re-check when globals change (function calls).
4. **PyDict_GetItem with C strings** uses string hash but our interned globals could be checked via PyDict_GetItemWithError on cached PyObject* (already done in most places).
5. **value_boolean for Python builtins**: We already inline. Good.
6. **Binary op dispatch**: Currently long if/else chain on first char. Switch with hash on op[0] would be similar. Could split fast path: pure int/float +,-,*,/, ==, !=, <, > for the common case.
7. **Function calls**: PyObject_CallFunctionObjArgs creates tuple each time. Use vectorcall (`PyObject_Vectorcall`) for ~30% faster calls.
8. **eval_function args list build**: Could use vectorcall directly with arg eval inline.
9. **Variable lookup**: Two dict lookups (locals_ then globals). Common var lookups are hot.
10. **Coverage record_statement_coverage**: Used only in debug mode, fine.
11. **Hot statement: expr**: get_only_key + comparisons. Most statements are 'expr'. Order checks by frequency.

Priority:
- A. Hoist coverage check (one-time per script, then sticky), expect ~20% on non-debug.
- B. Avoid PyDict_GetItem/SetItem for statementCount; use a stack-local counter.
- C. Cache S_expr/S_jump/etc pointer-identity dispatch in main loop.
- D. Pointer-identity dispatch in evaluate_expression.
- E. Vectorcall for builtin function calls.


