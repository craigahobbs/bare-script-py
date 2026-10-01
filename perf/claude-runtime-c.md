Port src/bare_script/runtime.py to src/bare_script/runtime_c.c from scratch, then make it as fast,
lean, small, and simple as you can through alternating profile-guided optimization and
simplification loops, repeated until neither finds anything more.

This runs on a feature branch. Commit each validated change on its own as soon as it passes the
gate - there is no need to batch or to ask. Do not push, and do not open a pull request.

Provide frequent, "fancy" status reports at all phases of the process: the current phase and loop
round, the idea being worked on and its estimate, the running ledger of kept and rejected ideas,
and the cumulative deltas on all four axes (see **The measurement gate**) against the initial port,
the prior runtime, and the pure-Python runtime.

---

## Constraints

These hold for every phase. Do not relax them to hit a performance goal.

- **Correctness first.** `runtime.py` is the reference implementation and the source of truth for
  behavior. The C runtime must be observably identical: same results, same errors, same edge cases,
  same statement counts. A faster runtime that diverges from `runtime.py` is a regression, not an
  optimization.
- **The full gate must pass.** `make commit` (test + lint + doc + 100% line/branch coverage, plus
  `test` and `test-include` again with `BARESCRIPT_RUNTIME_C=1`) must pass. Never commit a change
  that breaks it.
- **Optimize the production path only.** `make test-include` runs in debug mode (`bare -d`), so
  coverage recording and statement counting show up hot in its profiles. Production BareScript runs
  without debug. Do **not** optimize debug-only paths - target expression evaluation, statement
  dispatch, function-call setup, dict lookups, and value coercion. (Debug paths must still not
  *regress*: the include suite is one of the measured workloads.)
- **Python 3.10+ only.** You may use any C API available in CPython 3.10. Guard anything newer with
  `#if PY_VERSION_HEX >= 0x030X0000`. Do not use APIs removed or deprecated-to-removal before 3.10,
  and do not require anything past what 3.10 ships. Avoid private `_Py*` APIs - they move between
  minor versions.
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
    The same applies to per-object mutable state such as a compiled body, a call-site cache, or a
    reusable frame hung off a function object: two threads can run one function at once.
  - Do not rely on the GIL for refcount safety of objects shared across threads. Keep a strong
    reference for the duration you touch a borrowed object; under free-threading a borrowed reference
    can be invalidated concurrently. Wrap `PyDict_GetItemRef`/`PyList_GetItemRef` (3.13+) in shims
    that fall back to borrowed-get-plus-`Py_INCREF` on 3.10–3.12, and use the shims everywhere.
  - The free-threaded build defines `Py_GIL_DISABLED`. If a code path must differ between builds,
    branch on that macro rather than on the Python version.
  - Verify at runtime on a free-threaded interpreter - see **GIL and FT testing** below; do not
    skip it.
- **Scope.** Change only `runtime_c.c` and, where needed, `setup.py` and `src/tests/test_runtime.py`
  (tests that pass under *both* runtimes). Do not change `runtime.py`, the library, the include
  library, or other public behavior to make the C port easier.

---

## Environment discipline

- **The development shell may export `BARESCRIPT_RUNTIME_PY=1`**, which silently forces the
  pure-Python runtime for any `python`/`bare` you run directly - your tests and measurements would
  pass without ever executing your C code. Always run direct commands with
  `env -u BARESCRIPT_RUNTIME_PY`, and make every hand-written harness *assert* the C runtime is
  active: `assert 'built-in' in repr(execute_script)`. (Setting `BARESCRIPT_RUNTIME_C=1` in the
  environment does nothing outside make - it is a make variable, not a runtime switch.)
- The `make` targets handle the environment correctly: `make test BARESCRIPT_RUNTIME_C=1` and
  `make test-include BARESCRIPT_RUNTIME_C=1` test the C runtime, and `make perf` measures both
  runtimes in one run (`PERF_MERGE=` skips the JavaScript repo's suite).
- The venv's editable install builds the extension and depends on `runtime_c.c`, so a plain `make
  test` after an edit rebuilds it - no `make clean` is needed between iterations. After a build, a
  `src/bare_script/runtime_c.*.so` file exists - if it doesn't, the extension build failed
  (setup.py swallows compile errors by design). Iterate fast with a direct syntax check before
  rebuilding:
  `cc -fsyntax-only -Wall -Wextra -Wno-unused-parameter -I"$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["include"])')" src/bare_script/runtime_c.c`
- The extension must compile warning-free under `-Wall -Wextra` on clang and gcc.
- Keep throwaway harnesses, `.so` snapshots, profiles, and the ledger in your session scratchpad
  directory (or `/tmp` if you have none), never in the repository, so a commit cannot pick them up.

---

## The measurement gate

Every candidate change - in either loop - is judged on four axes against the last accepted build.
Set this machinery up in Phase 0 and use it for every change after the initial port.

### Snapshots and conformance

- Keep a copy of every accepted build's `.so` in the scratchpad, named by commit hash. A regression
  noticed later then bisects in seconds by copying snapshots into `src/bare_script/`.
- **Conformance diff.** The C runtime's output must be byte-identical to the pure-Python runtime's
  on the include suites, after filtering only the `BareScript executed in` timing line:
  `bare -d -m src/bare_script/include/test/runTests.bare`,
  `bare -d -v vUnittestReport true src/bare_script/include/test/runTestsMarkdownUp.bare`,
  `bare -x -m src/bare_script/include/*.bare src/bare_script/include/test/test*.bare`, and
  `bare -d -m static/creator/test/runTests.bare`. Record the pure-Python outputs once in Phase 0 and
  diff every candidate against them. A difference is a bug, never a new baseline.

### The four axes

Measure each axis for the baseline and the candidate **interleaved in one session**: copy the
baseline `.so` into place, run, copy the candidate, run, three rounds or more, and compare
**best-of-N** per configuration. Each `bare` run is a fresh process, so swapping `.so` files between
runs is safe. Wall time drifts 5–10% over a day and a few percent within minutes; never compare runs
from different sessions.

1. **Performance.** Run each workload as its own process under `/usr/bin/time -l` (macOS; on Linux
   `perf stat -e instructions,cycles`) and record **instructions retired** (stable to about ±0.3%,
   the deciding metric), cycles, and wall time. Workloads:
   - each `perf/test.bare` test alone (`-v vTest "'name'"`), leaving `vTimeFloor` unset so every run
     does the same fixed work;
   - the include suite (`bare -d -m src/bare_script/include/test/runTests.bare`) - the parser and
     linter are themselves BareScript, so this is also a parse-heavy workload;
   - your own scratchpad harnesses so a win is not judged on one workload shape: call-heavy (a
     tight script-function loop, including recursion), accessor-heavy (object/array/string builtins
     in a loop), string-comparison-heavy, and global-variable-heavy;
   - an empty script, for startup cost - subtract its instructions from the others to see a
     workload's own share.
2. **Memory.** `maximum resident set size` and `peak memory footprint` from the same `time -l`
   runs, on the empty script, the perf tests, and the include suite. A change touching reference
   counting also gets the leak harness (see **Leak testing**) on at least `gil-dbg`; a leak is
   invisible to every test.
3. **Size.** The extension's code size: `size -m src/bare_script/runtime_c.*.so` (`__text`; `size -A`
   `.text` on Linux). When it moves more than a few hundred bytes, find out why - `nm -n` both
   builds and difference adjacent symbol addresses for per-function sizes. Slimming a function can
   get it inlined at every hot call site and grow the binary by kilobytes.
4. **Simplicity.** Code lines in `runtime_c.c` (non-blank, non-comment:
   `grep -cvE '^\s*(//.*)?$' src/bare_script/runtime_c.c`), the number of functions, and the number
   of special cases and fallback paths - plus your honest judgment of whether the code reads more
   clearly.

Before the first comparison, measure the noise on each axis by comparing the baseline against
itself (two copies of the same `.so`, interleaved). Use those figures as the thresholds below;
under about 2% of wall time or 0.5% of instructions is noise regardless.

### Accepting a change

**Keep a change only if it improves at least one axis beyond noise and leaves the other three flat
within noise.** Otherwise revert it (`git checkout -- <files>`) and record it in the ledger.

The one exception: a large performance win (several percent or more on the workloads it targets)
may carry a *proportionate* cost in size or simplicity - a new instruction form, a new cache. State
the trade and the measured numbers in the commit message. Never accept a memory regression or any
conformance difference, and reject marginal gains that cost complexity.

For each change:

1. State the hypothesis and a conservative estimate, taken from the profile.
2. Implement the smallest version that tests the hypothesis; iterate with the syntax check and
   `make test BARESCRIPT_RUNTIME_C=1`.
3. Run the full gate, chained so a failure cannot be missed:
   `if make commit > gate.log 2>&1; then echo PASS; else grep -n -i -E 'fail|error' gate.log; fi`.
4. Run the conformance diff.
5. Measure the four axes interleaved against the last accepted snapshot.
6. If the change touched caches, shared state, or call paths, re-run the FT stress; if it touched
   reference counting, run the leak harness.
7. Keep: commit with a one-line imperative message that names the measured deltas, and snapshot the
   `.so`. Reject: revert.
8. Record the idea, the estimate, the measured result, and the verdict in the ledger either way -
   the ledger is what stops a measured-neutral idea from being retried.

---

## GIL and FT testing

### Local GIL and FT interpreters

Build four CPython interpreters under `build/cpython/`, all from one source tarball matching the
system Python version. `make clean` deletes `build/`, so do not run it once they are built - the
iteration loop does not need it.

| Prefix dir | configure flags | Purpose |
| ---------- | --------------- | ------- |
| `gil`      | `--enable-optimizations` | PGO GIL - representative perf, apples-to-apples vs FT |
| `ft`       | `--disable-gil --enable-optimizations` | PGO free-threaded - FT behavior + perf |
| `gil-dbg`  | `--with-pydebug` | C-API assertions + `sys.gettotalrefcount()` leak precision |
| `ft-dbg`   | `--with-pydebug --disable-gil` | Both of the above under free threading |

Add `--with-openssl=$(brew --prefix openssl@3)` on macOS. Build each in its own out-of-tree build
dir with absolute paths. You do not need pip in these interpreters: compile the extension per ABI
with `cc -O3 -bundle -undefined dynamic_lookup -I<includes> src/bare_script/runtime_c.c -o
src/bare_script/runtime_c$EXT_SUFFIX`, and run with
`PYTHONPATH=src:build/venv/system/lib/python3.*/site-packages` to reuse the venv's pure-Python
dependencies. The `ft`, `gil-dbg`, and `ft-dbg` suffixes differ from the venv's, so those `.so`
files coexist in `src/bare_script/`; the `gil` build's suffix is the *same* as the venv's, so
compiling for it replaces the venv's copy - rebuild the venv's (`touch src/bare_script/runtime_c.c
&& make test BARESCRIPT_RUNTIME_C=1`) before measuring anything. Remove the per-ABI `.so` files
before committing.

Run on **all four**: the unit suite (`-m unittest discover -t src/ -s src/tests/`) and the include
suite (`-m bare_script -d -m src/bare_script/include/test/runTests.bare`). The pydebug builds catch
C-API contract violations the release builds miss.

### FT verification

- After importing the extension on an FT build, `sys._is_gil_enabled()` must be `False` - the
  `Py_mod_gil` slot working end-to-end.
- Run a multi-threaded stress (8+ threads, both `ft` and `ft-dbg`) covering, in phases:
  1. isolated scripts in parallel (shared `SCRIPT_FUNCTIONS` dict, shared model dicts);
  2. one shared script-function object called from all threads (races any lazily-published
     per-object cache or reusable frame - first concurrent calls must CAS cleanly);
  3. library calls mutating *shared* containers (one dict/list touched by all threads).

### Leak testing

Measure, don't just review. Build one harness and run it on all four interpreters:

- The workload must cover **every runtime path**: expressions of all kinds, function
  definitions/calls (fresh per iteration so caches are allocated and freed), includes with a
  `fetchFn`, coverage-enabled runs, `evaluate_expression` entry points, and - critically - **error
  paths** (unknown function, unknown label, max-statements, argument errors, error-message logging),
  since error-handling code is where refcount mistakes hide.
- Use fixed scripts/names across iterations (so interning and caches stabilize), warm up ~50
  iterations, then snapshot between rounds: `gc.collect()` twice, `sys.getallocatedblocks()`,
  `sys.gettotalrefcount()` (pydebug only - the gold standard), and `ru_maxrss`.
- Interpret growth by *shape*: decaying increments are freelist/intern settling; **linear growth is
  a leak**. Discriminate per-round artifacts (the harness's own snapshot/print allocations) from
  per-iteration leaks by scaling iterations-per-round 5x - a real leak scales, an artifact stays
  constant per round.
- Also run the full unit suite under `PYTHONMALLOC=debug` (buffer overruns, double frees), and use
  targeted `sys.getrefcount()` before/after probes on objects threaded through globals to catch
  per-call drift in specific handlers.

---

## Phase 0 - Baseline

1. Confirm you are on a feature branch, not `main`. If you are on `main`, create a branch
   (`runtime-c-<date>`) before anything else.
2. `make clean` and `make commit` to verify all checks and tests pass.
3. Snapshot the existing extension's `.so` as `prior` - the bar to beat. Measure it on the four
   axes, but do not read its source.
4. Record the pure-Python conformance outputs (see **Snapshots and conformance**) and measure the
   pure-Python runtime on the perf workloads (`make perf PERF_MERGE=` covers both runtimes and
   native Python).
5. Write your scratchpad harnesses and the measurement script that runs the interleaved four-axis
   comparison of two `.so` files, and measure the noise floor by comparing `prior` against itself.

---

## Phase 1 - Port `runtime.py` to `runtime_c.c` from scratch

Delete the existing `src/bare_script/runtime_c.c` entirely and do not refer to it.

Port `runtime.py` to a new `runtime_c.c`. Read these files:

- `src/bare_script/runtime.py` - **source of truth**; port this to C
- `src/bare_script/__init__.py` - which symbols the module must export
- `setup.py` - C extension build configuration
- `src/tests/test_runtime.py` - test suite; understand coverage requirements

Honor the **Constraints** while porting - in particular, stand up the multi-phase module init with
the `Py_mod_gil` slot from the start rather than retrofitting it later.

Choose the port's architecture deliberately. A faithful port is the correctness baseline, but you
are free to make it the architecture the strategy catalog below points at (for example, compiling
to bytecode) from the start, if you can do so while keeping it provably faithful - rebuilding the
core architecture later costs more than choosing it now. Either way, the dict-walking semantics of
`runtime.py` stay the reference every later change is checked against.

High-level porting advice (hard-won - read before writing code):

- **Get it working and committed before optimizing.** Reuse the pure-Python parser/library/value
  modules via imports; raise the *same* exception classes (`BareScriptRuntimeError` from
  `bare_script.runtime`, `ValueArgsError` from `bare_script.value`) by calling them - constructing
  errors through the Python classes gets message fidelity for free.
- **Fidelity traps that bite** (each was a real divergence at least once):
  - key *present-with-None* differs from *absent* (`'expr' in stmt` vs `.get`); mirror containment
    semantics exactly.
  - `bool` is not a number: `type(x) is int` means `PyLong_CheckExact`, which excludes `bool`; but
    `value_args_validate` uses `isinstance`, so subclasses of the base types count there.
  - `except:` (bare) vs `except Exception:` - the include fetch uses bare except; function-call
    error handling lets `BaseException` propagate.
  - Validation and error **order** is observable (per-arg checks in order, then too-many-args, then
    any body-level bounds check); error *return values* and exact messages are observable in debug
    logs.
  - `options` is live, observable state: `options['statementCount']` must be current whenever
    arbitrary Python can read it, and any C-side counter must sync out before such calls and back
    in afterwards - **symmetrically on error-recovery paths**, or the counter rewinds and
    `maxStatements` can be bypassed.
  - `evaluate_expression` contexts differ from execution contexts (no globals subscript, no counter
    setdefault) - a script function invoked from an expression context must take the path that
    performs the reference's per-call setup.
  - Callers can pass models `runtime.py` accepts that the parser never produces (missing keys,
    non-dict parts, tuples for lists), and the errors must surface at execution time exactly where
    the reference raises them. Anything the fast path cannot represent needs a faithful slower path.
  - Don't bake in CPython behaviors that vary by version (math-module error message wording
    changed in 3.14) or by magnitude (`math.log` has a big-int path; float conversion overflows).
- **Refcount discipline**: with shared `goto done` cleanup labels, *transfer* ownership explicitly
  (`result = part; part = NULL;`) - a missed transfer is a use-after-free that surfaces as a flaky
  crash far from the cause. `PyDict_Next` yields borrowed references. Zero-fill (`PyMem_Calloc`)
  compound structures so partial-build error paths can use one shared free function.
- **Crash debugging**: run suites with `-X faulthandler` and `PYTHONMALLOC=debug`; on macOS, read
  `~/Library/Logs/DiagnosticReports/*.ips` for C backtraces of past crashes - they name the exact
  function.

When `make test BARESCRIPT_RUNTIME_C=1`, `make commit`, and the conformance diff all pass, commit the
initial port. Measure it on the four axes against `prior`; this is the starting point of the loops,
not subject to the acceptance rule.

---

## Phase 2 - Harden the port

Build the four local interpreters and run the full GIL and FT test matrix, the FT verification, and
the leak harness (see **GIL and FT testing**) against the initial port, and fix what they find
before optimizing - a leak or race found now has one suspect; found later, it has dozens. Keep the
interpreters and harnesses: the loops re-run them after relevant changes.

---

## Phase 3 - The optimization cycle

Alternate the two loops below. Each loop runs until it runs dry; then switch to the other. Stop the
cycle when one full round of *both* loops keeps no change. Re-run `make perf PERF_MERGE=` at the end
of each loop for a report-level view of the progress.

### Loop A - Profile-guided optimization

Profile first, change what the profile names, measure, keep or revert.

- **Profile the production path.** Build a symbolized variant (the build's own flags from
  `sysconfig.get_config_var('CFLAGS')` plus `-g`, compiled directly as in **Local GIL and FT
  interpreters**), run a workload in a loop, and sample it (macOS `sample <pid> 5 -file out.txt`,
  or `py-spy --native` / `perf record` on Linux). Aggregate **self time per function** (a node's
  count minus its children's). Read the top-of-stack symbols: dict-machinery symbols
  (`unicodekeys_lookup_unicode`, `_Py_dict_lookup`, `insertdict`) mean model/locals/globals dict
  traffic; `_PyEval_EvalFrameDefault` means Python library-function frames; allocator symbols mean
  per-call or per-operation allocation. Inlining folds frames together - a `-fno-inline` variant
  separates them when attribution is unclear.
- **Count as well as time.** For questions a sampler cannot answer - which opcodes or node kinds
  run most, which adjacent pairs recur, how often a cache misses, how often a fallback path is
  taken - add temporary counters behind a `#ifdef` and remove them before committing.
- Take candidates from the top of the profile, one at a time. Estimate conservatively, prefer
  simplicity and improved core architecture over side cases, and do not be afraid of aggressive
  changes when the profile says they are where the time is.
- The loop runs dry when the top of the profile yields no keep after several honest attempts, or
  when what remains is time the runtime cannot remove (CPython's own dict/unicode/allocation
  work on behalf of the library, the Python library functions themselves).

### Loop B - Simplification

A full-code review whose only aims are **less code, more consistency, and clearer expression** -
nothing else. Performance, memory, and size belong to Loop A; here they must stay flat within noise.

- Review the whole file, not the recent diff: module state, helpers, compiler, interpreter, call
  paths, intrinsics, error paths, and the module init. Two mechanical scans find what reading
  misses: a **repeated-window scan** (normalized six-line windows across `runtime_c.c`, looking for
  sequences that recur) and an **unused-declaration scan** (each static function, struct field,
  enum member, and module-state member counted across the file).
- **C line coverage finds dead code.** The Python coverage gate does not measure `runtime_c.c`.
  Build a coverage-instrumented variant (`-fprofile-instr-generate -fcoverage-mapping` or `--coverage`),
  run the unit and include suites, and read the report: an unreached line is either dead - delete
  it - or an untested behavior - add a test to `src/tests/test_runtime.py` that passes under both
  runtimes. Do not leave code nothing reaches.
- A candidate is fewer lines, a more consistent form, or a clearer expression of the same behavior:
  a shared helper for a repeated sequence, an unread field or parameter, a special case a general
  path already covers, a flag that restates state another value carries, a fallback made
  unnecessary by a later change, names and control flow that match their neighbors. A change whose
  purpose is fewer instructions, less memory, or a smaller binary is not a candidate here.
- Do not trade an invariant the code relies on for a few lines - trace what a change lets later
  operations assume before taking it. Inside the interpreter's hot loop, keep a simplification only
  if the performance numbers stay flat; code layout shifts there move unrelated benchmarks.
- Apply per logical group, run the gate and the four-axis measurement, and commit or revert each on
  its own, until a full review finds nothing that passes.

---

## Strategy catalog

What has worked before, what has not, and why. **This is a starting point, not a ceiling.** Each
entry is a hypothesis to re-measure in *this* build - the numbers were measured on other code, and
the ranking can differ in a CPython extension, where values are Python objects and CPython owns
the dict, string, and allocation machinery. Ideas the profile suggests that appear nowhere here are
welcome; so is a better way to achieve what an entry achieves.

### From the previous CPython-extension port

That port walked C node trees compiled from the model dicts. Its measured ladder (Mandelbrot unless
stated; ~33x faster than pure Python overall):

1. C statement counter in an execution-context struct, synced to `options` only at observable
   boundaries (−10%).
2. First-key model dispatch - valid statement/expression models are single-key dicts; dispatch on
   the first key via interned-pointer identity, prefetch inner fields in one dict walk with lazy
   hashed fallback at each exact use point (−38%).
3. Direct script-function invocation on the caller's context, bypassing the generic call machinery
   (−13% call-heavy).
4. Compile the model dict-AST once per function body (literals, operator enums, keyword variables,
   jump-label indexes resolved at compile time; variable and assignment names interned so dict
   probes hit on pointer equality), with anything irregular compiled to a **fallback** that defers
   to a dict-walking evaluator kept as the semantic reference (−52%). The fallback's granularity -
   per node, or the whole body - is a design choice; a coarser one is simpler.
5. C fast paths for `value_compare`/`value_boolean` common types (−14% string workloads).
6. Slot-based locals for fully-compiled function bodies - local names (declared args ∪ assignment
   targets) are a statically known set; reads become array loads, writes pointer swaps, with a NULL
   slot mirroring a dict miss (−21%, −37% call-heavy).
7. Depth-capped compiled expression trees, removing the per-node recursion guard (−9%).
8. Guarded library intrinsics - C implementations of trivial `library.py` functions
   (math/array/object/string accessors), run only when the call site resolves to the *original*
   library function object by pointer identity (captured once at module init); overrides and
   shadowing fall back to the generic call. Each replicates its function's `value_args_validate`
   model exactly, including error order and error return values; skip functions whose error messages
   are CPython-version-dependent (−58% math-heavy, −78% accessor-heavy).

### From bare-script-c

`../bare-script-c` is a standalone C runtime (its own value system, no CPython) tuned through many
rounds of exactly these loops; its `DESIGN.md` and the "Performance work" section of its `CLAUDE.md`
describe the design and the measured results, and are worth reading before Loop A. Its value-system
work (NaN-boxed values, string pools, object hash indexes) does not transfer here, but its execution
architecture does, and that is where its largest wins came from:

- **Flat register bytecode instead of a tree walk.** Compiling to bytecode and then to *register*
  code were each large wins. An instruction names a destination and two operand registers; a
  frame's registers are the slots, then temporaries the compiler allocates stack-fashion, then the
  chunk's constants copied in when the frame is built - so a local or a literal feeds an operator or
  a call with no instruction of its own, and a call's arguments are operand words following it.
  Dispatch through a label table (computed goto) under GNU C, with a `switch` fallback, advancing a
  pointer to the instruction rather than an index; keep every threaded dispatch jump a distinct
  indirect branch. Jump labels resolve to instruction addresses at compile time.
- **Definite-assignment analysis.** A local read before assignment falls through to the global of
  the same name, which costs every slot read a test. A forward must-analysis over a function body's
  basic blocks proves most reads definitely assigned; read those as bare registers and leave the
  test to the rest.
- **Conditions compiled as jumps.** A comparison under `jumpif` is one compare-and-jump; `&&`/`||`
  short-circuit through jumps of their own; a leading `!` flips the jump's sense instead of
  computing a boolean. An `objectGet`/`objectHas` call whose result only decides a jump can jump on
  the result directly.
- **Statement counting a basic block at a time** - one marker per run of statements between labels,
  jumps, and returns, instead of one per statement. bare-script-c accepted a small observable
  difference at the statement limit; here that is not allowed, so the block charge must be exact -
  e.g. take the per-statement path for a block that could cross `maxStatements`.
- **Per-site caches.** Global function calls, global reads, and global writes each cache their
  resolution at the call site, re-resolved only when the cache's guard fails. In CPython there is no
  stable pointer into a dict's value storage, and the dict version tag is private and deprecated since
  3.12; the public invalidation primitive is a dict watcher (`PyDict_AddWatcher`, 3.12+), with a
  plain interned-key lookup on older versions. Measure whether a watcher-based cache beats an
  interned-key lookup before committing to the complexity. A cheaper form that did win: verify a
  site's resolved function **once per function object** - remember the object last seen and what it
  resolved to (intrinsic, script function, other), so the per-call check is one pointer compare.
- **Intrinsics as opcodes.** The single-shape hot accessors (`arrayGet`, `arrayLength`, `arrayPush`,
  `arraySet`, `objectGet`, `objectHas`, `objectSet`, `stringCharCodeAt`, `stringLength`,
  `stringSlice`, and the one-argument math functions sharing one opcode chosen by the site's
  function) became call opcodes of their own, guarded by the site's cache; the rest go through an
  intrinsic switch in the general call path. A miss - wrong shape, cold or shadowed site - takes the
  general call, which is the reference behavior.
- **Resident frames.** A function called more than once keeps its frame: constants stay in place, a
  call fills only its arguments, and owned registers are released on the way out; a recursive (or
  here, concurrent) call finding the frame busy builds its own. Under the FT build the busy flag
  must be claimed atomically. Small frames on the C stack instead of the heap also won.
- **Equality and comparison by identity.** Decide equality of two strings by pointer when equal, and
  compare content only when needed; decide mixed-type comparisons from the types alone.
- **In-place string append.** `s = s + piece` where `s` is a local holding the only reference can
  append in place, making the loop linear. `PyUnicode_Append` already does the uniqueness check and
  in-place resize safely (including under FT); the win is in handing it the slot's reference.
- **Superinstructions.** Fusing a chunk's commonest adjacent instruction pairs won; find the pairs by
  counting, not guessing.
- **Keep cold paths out of line.** Error handling, fallbacks, and rare shapes marked `noinline` keep
  the interpreter loop small; changing a body the loop inlines moved unrelated benchmarks ±1.5% until
  it was moved out of line.

Measured neutral or harmful in bare-script-c - do not retry as-is without a new reason: an intrinsic
"express lane" in the general call path (did not replicate); a fused call instruction that loads
simple arguments; an `objectNew` call opcode; copying constants into a frame with a loop instead of
`memcpy`; `-O3` over `-O2` (no difference) and `-Os` (7% slower - the inlining is worth more than the
instruction-cache savings); raising inline thresholds.

### From this port

The register-bytecode port (October 2026) took the include suite from 891 to 375 ms per 100 runs,
mandelbrot from 11,100 to 1,722, schemaValidate from 105 to 28, and qrcodeMatrix from 871 to 306.
Its measured ladder, in the order kept (instructions on the workload named; each against the build
before it):

1. Definite assignment first - it turns local reads into operands, which is what lets in-place float
   reuse pay (mandelbrot −5%; float reuse was −5% before it and −16% after).
2. Run the bundled parser on this runtime for includes rather than runtime.py (include suite −45%).
3. A dict watcher epoch for "is this function's model unchanged", then the per-call setup reads
   (globals, maxStatements, coverage) cached on the execution context (call −24% each).
4. Library replicas: exact-type happy paths that return `DEFER` to the real library function for
   anything else, verified with a per-function argument-shape differential (accessor −78%, urlDecode
   −52%, schemaParse −42% over three batches). Go after the functions the profile shows running as
   Python bytecode - `_PyEval_EvalFrameDefault` in a C-runtime profile is a library function worth
   replicating. jsonParse/jsonStringify through the library's own coder objects (qrcode −11%) and
   regexReplace's `$N` translation (qrcode −3%) came from that signal late in the work.
5. `value_compare` in C for exact types (schemaValidate −19%), and a global call cache on the
   context validated by a globals epoch *and* the globals dict (accessor −14%).

What did not pay, measured: a per-statement exact block charge (ceiling under 1%); an in-place
`mathSqrt` result (the sentinel check cost other calls as much as it saved); sharing the call cache
across contexts (an unsafe upper-bound build saved under 0.6% - misses are cheap); call-site shapes
for `objectSet`/`objectNew` (under 1%); an `arraySort` replica (one workload, 1.8 KB).

Changing a script model during execution is implementation-defined - a runtime may compile the model
to a faster form and keep using it - so a review finding that an in-place statement edit goes unseen
is not a divergence. Do not add per-call model checks for it (one cost schemaValidate +9%).

Process lessons:

- Count before optimizing a call path: an instrumented copy built in the scratchpad that counts each
  intrinsic's call shapes and cache-miss reasons settled three ideas in minutes.
- Build an unsafe upper-bound variant before implementing a correctness-heavy idea; if the ceiling is
  under 1%, stop.
- Mark the general call machinery (`vm_call`, `call_function`) always-inline once a fast path calls
  into it, or the compiler stops inlining it and every call regresses 1-5%.
- The adversarial review found what the differentials did not: state cached on the context that a
  replica mutates without invalidating, a cache keyed on too little, a float-to-integer bound at
  2^63, and Python callbacks changing `options` mid-run. Point the next review there first.
- Never `git stash` with staged user edits in the tree - a bare stash's pop restores them unstaged.
  To test a change against `HEAD`, copy the file aside and restore it from `git show HEAD:<path>`
  instead.

---

## Phase 4 - Final review

When the optimization cycle has ended, re-confirm the **Constraints** hold and hunt for memory,
reference, and fidelity bugs in three parts - each has caught real bugs the test suites missed:

1. **Independent adversarial review.** Launch a separate review agent over the C source with a
   focused brief: refcount correctness on every error path, borrowed-reference escapes, FT safety of
   every piece of mutable shared state, and line-by-line semantic fidelity against
   `runtime.py`/`value.py`/`library.py`. Have it *empirically verify* suspected divergences by
   running the same input under both runtimes (`BARESCRIPT_RUNTIME_PY=1` vs the C runtime) rather
   than reasoning alone.
2. **GIL + FT testing.** Run the full test matrix and FT verification on all four interpreters.
3. **Leak measurement.** Run the leak harness on all four interpreters.

For every divergence found, add a regression test to `src/tests/test_runtime.py` that passes under
*both* runtimes; if the behavior is shared with the JavaScript implementation, note that the test
should be mirrored to `../bare-script/test/testRuntime.js` (and its async twin). Commit each fix on
its own.

Run the full gate one last time (`make commit`) and a final `make perf PERF_MERGE=`.

---

## Phase 5 - Record what was learned

1. Replace the header comment of `runtime_c.c` with one that describes how it was created and the
   progression of kept optimizations with their measured wins. Commit.
2. Update this prompt's **Strategy catalog** (`perf/claude-runtime-c.md`) with what this run
   learned - new wins with their numbers, entries that did not replicate, and the ledger's
   measured-neutral ideas - so the next reimplementation starts further ahead. Keep it a catalog of
   hypotheses, not a recipe. Commit it separately so it can be reviewed on its own.
3. Finish with a summary report: the four axes for `prior`, the initial port, and the final build;
   the kept and rejected ideas; and anything left unresolved.

You are done (even if you did not reach a performance goal).
