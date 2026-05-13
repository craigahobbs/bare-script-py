/goal Port src/bare_script/runtime.py to src/bare_script/runtime_c.c from scratch and improve
measured performance measures by 90%.

Keep an optimization log in `static/claude-runtime-c-log.md`.

---

## Phase 0 — Measure existing `runtime_c.c` performance

First, `make clean` and `make commit` to verify all checks and tests pass.

Measure the pure-Python `runtime.py` performance by blending the following commands:

`bare -d` running `runTests.bare` reports the test execution time in milliseconds:

```
BARESCRIPT_RUNTIME_PY=1 build/venv/system/bin/bare -d -m src/bare_script/include/test/runTests.bare
```

perf/test.bare` reports runtime in milliseconds:

```
BARESCRIPT_RUNTIME_PY=1 build/venv/system/bin/bare perf/test.bare
```

---

## Phase 1 — Port `runtime.py` to `runtime_c.c` from scratch

Begin by deleting any existing `src/bare_script/runtime_c.c` entirely and do not refer to it.

Next, port `runtime.py` faithfully to a new `runtime_c.c` from scratch.

Do not do any AST pre-compilation optimizations in the initial port or during optimization later.

Read these files:

- `src/bare_script/runtime.py` — **source of truth**; port this to C
- `src/bare_script/__init__.py` — which symbols the module must export
- `setup.py` — C extension build configuration
- `src/tests/test_runtime.py` — test suite; understand coverage requirements

Build and test:

```
build/venv/system/bin/python3 setup.py build_ext --inplace 2>&1 && make commit 2>&1
```

Once all tests pass, commit the initial port with a brief description.

---

## Phase 2 — Optimization Planning

Analyze the `runtime_c.c` code looking for optimization ideas. Prefer simplication and
core-architecture to complex and side-cases. Conservatively estimate the expected improvement in
performance.

Prioritize tasks with judgement based on estimated performance impact and simplicity/complexity. Do
not be afraid of aggressive changes if you think they can work.

Please continue to update and re-prioritize our optimization throughout the optimization process.

---

## Phase 3 — Iterative Optimization

First, measure baseline performance of the `runtime_c.c` port.

```
unset BARESCRIPT_RUNTIME_PY; build/venv/system/bin/bare -d -m src/bare_script/include/test/runTests.bare
```

and:

```
unset BARESCRIPT_RUNTIME_PY; build/venv/system/bin/bare perf/test.bare
```

Next, iteratively plan and implement the current top optimization idea.

Next, rebuild (`build/venv/system/bin/python3 setup.py build_ext --inplace`), run `make commit` -
all tests must pass.

Next, measure `runtime_c.c` performance again and compute the percentage improvement. Revert
optimizations that don't improve performance. Also reject if the performance gain is small and the
change comparatively complex.

If accepting the optimization, commit with a brief comment.

Keep a log of all timings, optimizations, accept comments, and rejection reasions. I may harvest
this for data at a later time.

---

## Phase 4 - Final Review

When you have exhausted promising optimization ideas, stop the optimization.

Update the prioritized optimization list.

Next, do a careful review of runtime_c.c with an eye for memory and reference leaks.

Add a comment to `runtime_c.c` that describes the process by which it was created and the
progression of optimizations. Remove the optimization log. Commit.

You are done (even if goal hasn't been achieved).
