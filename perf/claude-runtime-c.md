Port src/bare_script/runtime.py to src/bare_script/runtime_c.c from scratch and optimize within
reason.

Provide frequent, "fancy" status reports with current optimization statistics and the current task
description at all phases of the process.

---

## Constraints

These hold for every phase. Do not relax them to hit the performance goal.

- **Correctness first.** `runtime.py` is the reference implementation and the source of truth for
  behavior. The C runtime must be observably identical: same results, same errors, same edge cases.
  A faster runtime that diverges from `runtime.py` is a regression, not an optimization.
- **The full gate must pass.** `make commit` (test + lint + doc + 100% line/branch coverage) and
  `make test-include` must pass with the C runtime active (`BARESCRIPT_RUNTIME_C=1`). Never commit a
  change that breaks them.
- **Optimize the production path only.** `make test-include` runs in debug mode (`bare -d`), so
  coverage recording (`record_statement_coverage`) and statement counting show up hot in profiles.
  Production BareScript runs without debug. Do **not** optimize debug-only paths — target expression
  evaluation, statement dispatch, function-call setup, dict lookups, and value coercion.
- **Python 3.10+ only.** You may use any C API available in CPython 3.10. Guard anything newer with
  `#if PY_VERSION_HEX >= 0x030X0000`. Do not use APIs removed or deprecated-to-removal before 3.10,
  and do not require anything past what 3.10 ships.
- **Must build and run correctly on both the default (GIL) and free-threaded (FT, no-GIL) CPython
  builds.** The same `runtime_c.c` source must compile cleanly and behave identically under both:
  - Use multi-phase initialization with a `Py_mod_gil` slot set to `Py_MOD_GIL_NOT_USED` so the
    module does not force the GIL back on under a free-threaded interpreter. `Py_mod_gil` exists only
    in 3.13+, so guard it with `#if PY_VERSION_HEX >= 0x030D0000`; on 3.10–3.12 (no free-threaded
    build exists) the guard simply compiles it out. Declaring
    `Py_mod_multiple_interpreters = Py_MOD_MULTIPLE_INTERPRETERS_NOT_SUPPORTED` (3.12+) permits
    init-once static module state.
  - Do not assume the GIL serializes access to shared mutable state. Module-level caches must be
    either populated once at module init and thereafter immutable, or published write-once with C11
    atomics under `#ifdef Py_GIL_DISABLED` (compare-and-swap; the losing builder frees its copy).
    Interned key objects and other init-time constants are fine; lazily mutated globals are not.
  - Do not rely on the GIL for refcount safety of objects shared across threads. Keep a strong
    reference for the duration you touch a borrowed object; under free-threading a borrowed reference
    can be invalidated concurrently. Wrap `PyDict_GetItemRef`/`PyList_GetItemRef` (3.13+) in shims
    that fall back to borrowed-get-plus-`Py_INCREF` on 3.10–3.12, and use the shims everywhere.
  - The free-threaded build defines `Py_GIL_DISABLED`. If a code path must differ between builds,
    branch on that macro rather than on the Python version.
  - Verify at runtime on a free-threaded interpreter — see **GIL and FT testing** below; do not
    skip it.

---

## Environment discipline

- **The development shell may export `BARESCRIPT_RUNTIME_PY=1`**, which silently forces the
  pure-Python runtime for any `python`/`bare` you run directly — your tests would pass without ever
  executing your C code. Always run direct commands with `env -u BARESCRIPT_RUNTIME_PY`, and make
  every hand-written harness *assert* the C runtime is active:
  `assert 'built-in' in repr(execute_script)`. (Setting `BARESCRIPT_RUNTIME_C=1` in the environment
  does nothing outside make — it is a make variable, not a runtime switch.)
- The `make` targets handle the environment correctly: plain `make perf` measures both runtimes
  in one run; `make test BARESCRIPT_RUNTIME_C=1` and `make test-include BARESCRIPT_RUNTIME_C=1`
  test the C runtime.
- After a successful build, a `src/bare_script/runtime_c.*.so` file exists — if it doesn't, the
  extension build failed (setup.py swallows compile errors by design). Iterate fast with a direct
  syntax check before rebuilding:
  `cc -fsyntax-only -Wall -Wextra -Wno-unused-parameter -I"$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["include"])')" src/bare_script/runtime_c.c`

---

## GIL and FT testing

### Local GIL and FT interpreters

Build four CPython interpreters under `build/cpython/` (note: `make clean` deletes `build/`), all
from one source tarball matching the system Python version:

| Prefix dir | configure flags | Purpose |
| ---------- | --------------- | ------- |
| `gil`      | `--enable-optimizations` | PGO GIL — representative perf, apples-to-apples vs FT |
| `ft`       | `--disable-gil --enable-optimizations` | PGO free-threaded — FT behavior + perf |
| `gil-dbg`  | `--with-pydebug` | C-API assertions + `sys.gettotalrefcount()` leak precision |
| `ft-dbg`   | `--with-pydebug --disable-gil` | Both of the above under free threading |

Add `--with-openssl=$(brew --prefix openssl@3)` on macOS. Build each in its own out-of-tree build
dir with absolute paths. You do not need pip in these interpreters: compile the extension per ABI
with `cc -O3 -bundle -undefined dynamic_lookup -I<includes> src/bare_script/runtime_c.c -o
src/bare_script/runtime_c$EXT_SUFFIX` (each build's `EXT_SUFFIX` differs — `.cpython-31Xt?d?-…`, so
all four `.so` files coexist in `src/bare_script/`), and run with
`PYTHONPATH=src:build/venv/system/lib/python3.*/site-packages` to reuse the venv's pure-Python
dependencies.

Run on **all four**: the unit suite (`-m unittest discover -t src/ -s src/tests/`) and the include
suite (`-m bare_script -d -m src/bare_script/include/test/runTests.bare`). The pydebug builds catch
C-API contract violations the release builds miss.

### FT verification

- After importing the extension on an FT build, `sys._is_gil_enabled()` must be `False` — the
  `Py_mod_gil` slot working end-to-end.
- Run a multi-threaded stress (8+ threads, both `ft` and `ft-dbg`) covering, in phases:
  1. isolated scripts in parallel (shared `SCRIPT_FUNCTIONS` dict, shared model dicts);
  2. one shared script-function object called from all threads (races any lazily-published
     per-object cache, e.g. a compiled body — first concurrent calls must CAS cleanly);
  3. library calls mutating *shared* containers (one dict/list touched by all threads).

### Leak testing

Measure, don't just review. Build one harness and run it on all four interpreters:

- The workload must cover **every runtime path**: expressions of all kinds, function
  definitions/calls (fresh per iteration so caches are allocated and freed), includes with a
  `fetchFn`, coverage-enabled runs, `evaluate_expression` entry points, and — critically — **error
  paths** (unknown function, unknown label, max-statements, argument errors, error-message logging),
  since error-handling code is where refcount mistakes hide.
- Use fixed scripts/names across iterations (so interning and caches stabilize), warm up ~50
  iterations, then snapshot between rounds: `gc.collect()` twice, `sys.getallocatedblocks()`,
  `sys.gettotalrefcount()` (pydebug only — the gold standard), and `ru_maxrss`.
- Interpret growth by *shape*: decaying increments are freelist/intern settling; **linear growth is
  a leak**. Discriminate per-round artifacts (the harness's own snapshot/print allocations) from
  per-iteration leaks by scaling iterations-per-round 5x — a real leak scales, an artifact stays
  constant per round.
- Also run the full unit suite under `PYTHONMALLOC=debug` (buffer overruns, double frees), and use
  targeted `sys.getrefcount()` before/after probes on objects threaded through globals to catch
  per-call drift in specific handlers.

---

## Phase 0 — Measure existing `runtime_c.c` performance

First, `make clean` and `make commit` to verify all checks and tests pass.

Measure the pure-Python `runtime.py` performance by blending the following commands:

```
make test-include
```

and:

```
make perf
```

---

## Phase 1 — Port `runtime.py` to `runtime_c.c` from scratch

Begin by deleting any existing `src/bare_script/runtime_c.c` entirely and do not refer to it.

Next, port `runtime.py` to a new `runtime_c.c` from scratch.

Read these files:

- `src/bare_script/runtime.py` — **source of truth**; port this to C
- `src/bare_script/__init__.py` — which symbols the module must export
- `setup.py` — C extension build configuration
- `src/tests/test_runtime.py` — test suite; understand coverage requirements

Honor the **Constraints** section above while porting — in particular, stand up the multi-phase
module init with the `Py_mod_gil` slot from the start rather than retrofitting it later.

High-level porting advice (hard-won — read before writing code):

- **Port faithfully first; optimize only against a working, committed baseline.** Reuse the
  pure-Python parser/library/value modules via imports; raise the *same* exception classes
  (`BareScriptRuntimeError` from `bare_script.runtime`, `ValueArgsError` from `bare_script.value`)
  by calling them — constructing errors through the Python classes gets message fidelity for free.
- **Fidelity traps that bite** (each was a real divergence at least once):
  - key *present-with-None* differs from *absent* (`'expr' in stmt` vs `.get`); mirror containment
    semantics exactly.
  - `bool` is not a number: `type(x) is int` means `PyLong_CheckExact`, which excludes `bool`.
  - `except:` (bare) vs `except Exception:` — the include fetch uses bare except; function-call
    error handling lets `BaseException` propagate.
  - Validation and error **order** is observable (per-arg checks in order, then too-many-args, then
    any body-level bounds check); error *return values* and exact messages are observable in debug
    logs.
  - `options` is live, observable state: `options['statementCount']` must be current whenever
    arbitrary Python can read it, and any C-side counter must sync out before such calls and back
    in afterwards — **symmetrically on error-recovery paths**, or the counter rewinds and
    `maxStatements` can be bypassed.
  - `evaluate_expression` contexts differ from execution contexts (no globals subscript, no
    counter setdefault) — a script function invoked from an expression context must take the path
    that performs the reference's per-call setup.
  - Don't bake in CPython behaviors that vary by version (math-module error message wording
    changed in 3.14) or by magnitude (`math.log` has a big-int path; float conversion overflows).
- **Refcount discipline**: with shared `goto done` cleanup labels, *transfer* ownership explicitly
  (`result = part; part = NULL;`) — a missed transfer is a use-after-free that surfaces as a flaky
  crash far from the cause. `PyDict_Next` yields borrowed references. Zero-fill (`PyMem_Calloc`)
  compound structures so partial-build error paths can use one shared free function.
- **Crash debugging**: run suites with `-X faulthandler` and `PYTHONMALLOC=debug`; on macOS, read
  `~/Library/Logs/DiagnosticReports/*.ips` for C backtraces of past crashes — they name the exact
  function.

Build and test:

```
make clean test
```

Check that a `src/bare_script/runtime_c.*.so` file exists — if it doesn't, the `runtime_c.c` build
failed.

Once all tests pass, commit the initial port with a brief description.

Measure baseline performance of the `runtime_c.c` port.

```
make test-include BARESCRIPT_RUNTIME_C=1
```

and:

```
make perf BARESCRIPT_RUNTIME_C=1
```

---

## Phase 2 — Optimization Planning

Analyze the `runtime_c.c` code looking for optimization ideas. Prefer simplicity and improved
core-architecture to complexity and side-cases. Conservatively estimate the expected improvement in
performance for each optimization.

Prioritize tasks with judgement based on estimated performance impact and simplicity/complexity. Do
not be afraid of aggressive changes if you think they can be highly impactful.

Please continue to update and re-prioritize the optimization ideas throughout the optimization
process.

Profile before guessing: sample a running `bare perf/test.bare` (macOS `sample`, or `py-spy`) and
read the top-of-stack symbols — dict-machinery symbols (`unicodekeys_lookup_unicode`,
`_Py_dict_lookup`, `insertdict`) mean model/locals dict traffic; `_PyEval_EvalFrameDefault` means
Python library-function frames.

A proven optimization ladder from a prior porting session (percentages are that session's
measured wins on the noted workloads, Mandelbrot unless stated; treat as candidates to
re-validate, not gospel):

1. C statement counter in an execution-context struct, synced to `options` only at observable
   boundaries (−10%).
2. First-key model dispatch — valid statement/expression models are single-key dicts; dispatch on
   the first key via interned-pointer identity, prefetch inner fields in one dict walk with lazy
   hashed fallback at each exact use point (−38%).
3. Direct script-function invocation on the caller's context, bypassing the generic call machinery
   (−13% call-heavy).
4. Compile the model dict-AST once per function body into C node trees (literals, operator enums,
   keyword variables, jump-label indexes resolved at compile time; intern variable/assignment names
   so dict probes hit on pointer equality). Anything irregular compiles to a **fallback node** that
   defers to the dict-walking evaluator, which stays in the binary forever as the semantic
   reference — this keeps edge-case fidelity while the hot path goes fast (−52%).
5. C fast paths for `value_compare`/`value_boolean` common types (−14% string workloads).
6. Slot-based locals for fully-compiled function bodies — local names (declared args ∪ assignment
   targets) are a statically known set; reads become array loads, writes pointer swaps, with a NULL
   slot mirroring a dict miss (−21%, −37% call-heavy).
7. Guarded library intrinsics — C implementations of trivial `library.py` functions
   (math/array/object/string accessors), run only when the compiled call site resolves to the
   *original* library function object by pointer identity (captured once at module init); overrides
   and shadowing fall back to the generic call. Replicate each function's `value_args_validate`
   model exactly, including error order and error return values; skip functions whose error
   messages are CPython-version-dependent (−58% math-heavy, −78% accessor-heavy).

---

## Phase 3 — Iterative Optimization

Implement the current top optimization idea.

Build and test:

```
make clean test BARESCRIPT_RUNTIME_C=1
```

Measure `runtime_c.c` performance again and compute the percent improvement. **Measure within a
single session with interleaved A/B runs** — build both variants, keep copies of the two `.so`
files, and alternate `cp` of each into `src/bare_script/` between timed runs; system load drift
makes non-interleaved comparisons unreliable, and anything under ~2% is noise. Keep several
throwaway harnesses under `/tmp` so wins aren't judged on one workload shape: statement-heavy
(`perf/test.bare`), call-heavy (a tight script-function loop), accessor-heavy (object/array/string
builtins in a loop), and string-comparison-heavy.

Revert optimizations that don't improve performance or meaningfully simplify. Reject if the
performance gain is small and the change comparatively complex.

Confirm each accepted optimization preserves correctness and keeps the **Constraints** satisfied —
especially that any new shared state stays safe under the free-threaded build (re-run the FT stress
after any change to caching or call paths).

If accepting the optimization, commit with a brief comment.

---

## Phase 4 — Final Review

When you have exhausted worthwhile optimization ideas, stop the optimization.

Re-confirm the **Constraints** hold and hunt for memory, reference, and fidelity bugs in three
parts — each has caught real bugs that the test suites missed:

1. **Independent adversarial review.** Launch a separate review agent over the C source with a
   focused brief: refcount correctness on every error path, borrowed-reference escapes, and
   line-by-line semantic fidelity against `runtime.py`/`value.py`/`library.py`. Have it
   *empirically verify* suspected divergences by running the same input under both runtimes
   (`BARESCRIPT_RUNTIME_PY=1` vs the C runtime) rather than reasoning alone.
2. **GIL + FT testing.** Build the four local interpreters and run the full test matrix and FT
   verification per **GIL and FT testing** above.
3. **Leak measurement.** Run the leak harness per **Leak testing** above on all four interpreters.

For every divergence found, add a regression test to `src/tests/test_runtime.py` that passes under
*both* runtimes; if the behavior is shared with the JavaScript implementation, note that the test
should be mirrored to `../bare-script/test/testRuntime.js` (and its async twin).

Run the full gate one last time with the C runtime active: `make commit` and `make test-include`
with `BARESCRIPT_RUNTIME_C=1`.

Add a comment to `runtime_c.c` that describes the process by which it was created and the
progression of optimizations. Commit.

You are done (even if the goal hasn't been achieved).
