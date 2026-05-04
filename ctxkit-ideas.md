# runtime_c.c Optimization Ideas — Ranked by Estimated Impact

## Context
Current `make perf` shows BareScript C extension is ~23x slower than pure Python.
This is extremely unusual — a C extension should be faster. The issue is likely
systemic overhead from calling back into Python too frequently, excessive object
creation, or redundant work in hot paths.

---

## 1. Cache and reuse Python long objects for small integers (statement counter)
**Description:** Every statement increments `statement_count` as a C `long`, but
SYNC_COUNT_TO_OPTIONS creates a new PyLong on every sync. More critically, the
expression evaluator calls SYNC_COUNT_TO_OPTIONS/SYNC_COUNT_FROM_OPTIONS around
*every* expression evaluation in statements (expr, jump, return). Since expressions
can call user-defined functions which recursively execute statements, these syncs
happen on every single statement — creating and destroying PyLong objects constantly.
The fix: only sync around actual recursive calls (function calls and includes), not
around every expression evaluation. The C code already tracks `statement_count` as
a local `long` — it just syncs too aggressively.

**Estimated improvement:** 30-40% speedup (removes thousands of PyLong allocs per iteration)

---

## 2. Avoid calling value_boolean through Python for common types
**Description:** `call_value_boolean` makes a full Python function call via
`PyObject_CallOneArg` for every conditional check (if/while/jump/&&/||/!). For
common types (bool, int, float, str, list, None), the truthiness check can be done
entirely in C using `PyObject_IsTrue()` which is a single C call into the Python
runtime, much cheaper than calling a Python function.

**Estimated improvement:** 15-25% speedup (conditionals are extremely frequent)

---

## 3. Avoid calling value_compare through Python for number comparisons
**Description:** `call_value_compare` calls into Python for every ==, !=, <, >, <=,
>= operation. For the common case of number-vs-number comparison (int/float), this
can be done directly in C using `PyObject_RichCompareBool` or direct C arithmetic,
avoiding the Python function call overhead entirely.

**Estimated improvement:** 10-15% speedup (comparisons are very frequent in loops)

---

## 4. Avoid calling value_string through Python for string concatenation of numbers
**Description:** In `evaluate_binary_op` for '+', when one side is a string and the
other is not, it calls `g_value_string` (a Python function). For int/float, this can
be done directly in C with `PyObject_Str()` or even `PyUnicode_FromFormat`, which is
faster than calling into a Python function.

**Estimated improvement:** 5-8% speedup (string + non-string is common)

---

## 5. Fast-path for number arithmetic without PyNumber_* API
**Description:** For `+`, `-`, `*`, `/` on two `PyLong` or two `PyFloat` values, the
code uses `PyNumber_Add` etc. which goes through Python's abstract number protocol.
For the common case of int+int or float+float, direct C arithmetic (extract values,
compute, create result) would be faster, especially for small integers.

**Estimated improvement:** 5-10% speedup (arithmetic is the core of perf benchmarks)

---

## 6. Inline the "is_number" check more efficiently
**Description:** `is_number()` is called twice per binary operand (once for left,
once for right). It checks `PyBool_Check` then `PyLong_Check || PyFloat_Check`. Since
this is called in every arithmetic/comparison operation, using a macro or `__builtin_expect`
hints for the common int case would help branch prediction.

**Estimated improvement:** 2-4% speedup (micro-optimization on hot path)

---

## 7. Avoid redundant dict lookups in execute_script_helper for statement fields
**Description:** After `get_statement_key_value` returns the statement's inner dict,
the code does additional `fast_dict_get` calls for sub-fields (e.g., `expr.name`,
`expr.expr`, `jump.label`, `jump.expr`). Some of these could be pre-fetched or
combined. For example, for `expr` statements, both `name` and `expr` are always
needed — a single pass through the dict with `PyDict_Next` could get both.

**Estimated improvement:** 2-3% speedup

---

## 8. Pool or cache ScriptFunction objects
**Description:** Every `function` statement creates a new `ScriptFunctionObject`.
If the same function definition is encountered multiple times (e.g., in a loop that
re-includes), a new object is allocated each time. This is minor since function
definitions typically happen once, but the allocation overhead is non-zero.

**Estimated improvement:** <1% speedup (function definitions are rare in hot paths)

---

## 9. Use PyDict_SetDefault instead of Contains+SetItem for label_indexes cache
**Description:** The label index caching uses `fast_dict_get` then `PyDict_SetItem`.
Using `PyDict_SetDefault` would combine the lookup and insert into one hash operation
when the key is missing.

**Estimated improvement:** <1% speedup (label lookups are cached after first hit)

---

## 10. Remove Py_EnterRecursiveCall/Py_LeaveRecursiveCall from execute_script_helper
**Description:** `Py_EnterRecursiveCall` adds overhead to every function invocation.
Since BareScript already has `maxStatements` protection against infinite loops, the
Python recursion limit check is redundant protection. However, removing it risks
stack overflow for deeply recursive BareScript programs, so this is risky.

**Estimated improvement:** 1-2% speedup (called once per function invocation)

---

## Summary

The single biggest win is #1 (reducing SYNC_COUNT_TO/FROM_OPTIONS calls). The current
code syncs on every expression evaluation, which is catastrophically expensive because
it creates/parses PyLong objects thousands of times. Combined with #2 (inline boolean
checks) and #3 (inline number comparisons), these three changes alone could bring the
C extension from 23x slower to potentially faster than pure Python.

Total estimated improvement from all ideas: 70-100%+ (i.e., from 23x slower to
potentially 1-3x faster than pure Python)
