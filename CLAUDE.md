# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

BareScript is a lightweight, embeddable scripting and expression language with a Python-like syntax. This repository is the **Python implementation**; a companion **JavaScript implementation** lives at `../bare-script/` and shares the same include-library `.bare` files and unit tests (synced via `make sync`). Both implementations are kept at 100% test coverage with identical test suites — changes here generally need a mirrored change in the JavaScript repo.

## Authoring BareScript code

When writing, modifying, or reviewing BareScript code (`.bare` files, `markdown-script` blocks, MarkdownUp apps, or BareScript unit tests), first read `SKILL.md` at the repo root. It's the model-agnostic reference for the language, built-in library, include library, MarkdownUp app pattern, and unit-test / mocking pattern.

## Common commands

Build driven by `Makefile` + `Makefile.base` (the latter downloaded from `python-build`). Set `USE_DOCKER=1` or `USE_PODMAN=1` to containerize.

- `make test` — run Python unit tests
- `TEST=src/tests/test_runtime.py make test` — run a single Python test module
- `make lint` — pylint (100% compliance required)
- `make cover` — coverage (100% line + branch required)
- `make doc` — Sphinx docs + library docs build (writes to `build/doc/`)
- `make commit` — full pre-publish gate (test + lint + doc + cover), re-runs test + test-include with the C runtime
- `make test-include` — run the `.bare` test suite under `src/bare_script/include/test/` via the `bare` CLI
- `TEST=<name> make test-include` — single `.bare` test. This is an **exact** test name, not a glob or pattern
  (`unittest.bare` compares with `!=`), so a prefix like `testSchemaValidate` silently runs 0 tests
- `make perf` — benchmark BareScript (PyC), BareScript (Py), and Python across the `perf/` test suite (mandelbrot,
  schemaParse, schemaValidate, markdownParse, markdownElements, urlEncode, urlDecode, and the BareScript-only
  qrcodeMatrix; the markdown and qrcode tests aren't supported by the native Python program. urlEncode/urlDecode race
  `urlEncodeQueryString`/`urlDecodeQueryString` against schema-markdown's `encode_query_string`/`decode_query_string`,
  the closest native analog even though they differ in percent-encoding scheme); if `../bare-script` exists, its
  `make perf` (BareScript (JS)
  and JavaScript) also runs and its data is merged into the report. Each `perf/test.*` program takes a language label and an optional test name (all tests when omitted;
  iteration counts are tuned per test) and outputs `language,test,runs,timeMs` CSV rows — e.g.
  `build/venv/system/bin/python3 perf/test.py "Python" mandelbrot` (the venv provides `schema-markdown`) or
  `bare perf/test.bare -v vLanguage "'BareScript (PyC)'" -v vTest "'schemaParse'"`
- `make perf TEST=<name>` — run a single perf test across all languages (a program silently skips a test it doesn't
  implement; an unknown test name fails the run)
- `make sync` — push `src/bare_script/include/` and `static/` to the JavaScript repo
- `make clean` / `make superclean` — remove `build/`, downloaded base files, container images

By default, targets use the pure-Python runtime (`BARESCRIPT_RUNTIME_PY=1`). Set `BARESCRIPT_RUNTIME_C=1` to exercise the compiled C runtime instead; `make commit` runs both.

`make perf` benchmarks the runtime itself. For optimizing an individual include file, write a throwaway `.bare` harness under `perf/` and run with `bare perf/<file>.bare` — `perf/` is outside the shipped package and isn't synced cross-repo, so harnesses can live there until you're done and then be removed (regenerate as needed).

## Architecture

### Modules

- **The parser is self-hosted**: `src/bare_script/include/barescriptParser.bare` (a line-for-line port of the former `src/bare_script/parser.py`) is the only parser implementation. `src/bare_script/include_source.py` embeds **every include as its parser-compiled JSON script model** — dictionary-compressed, chunked, and decoded at module load, with `scriptLines` omitted (unused at runtime for system includes) — and the runtimes' system-include code JSON-parses any system include whose text starts with `{`; that's how the parser loads without a native parser and how all system includes skip parsing. `src/bare_script/runtime.py` exports the native-API wrappers `barescript_parse_script` / `barescript_parse_expression` (lazy bootstrap, raise `BareScriptParserError`), used by the CLI, non-system include parsing, and `runtime_c.c`. The parsed model is validated against the schema in `src/bare_script/include/barescriptModel.bare`.
- `src/bare_script/runtime.py` — pure-Python `execute_script` / `evaluate_expression`. Implements statement counting (`maxStatements`), coverage recording, and the core interpreter loop. The reference implementation. System includes (`include <name.bare>`) execute from the embedded `SYSTEM_INCLUDES` map in `include_source.py`. Also exports `barescript_lint_script`, an include-like stub that lazily executes the embedded `barescriptLint.bare` include library and computes the async-function names from the globals — used by the CLI's `-x`/`-s` modes and the runtimes' debug-mode include linting (`runtime_c.c` imports it from here).
- `src/bare_script/include_source.py` — **generated** module (Makefile target; regenerated when `src/bare_script/include/*.bare` or the Makefile's generator script changes) exporting each include file's parser-compiled script model as JSON text (compressed; decoded at module load) plus the `SYSTEM_INCLUDES` file-name → model-JSON map. Checked in; never edit by hand — run `make src/bare_script/include_source.py`. Caveat: regeneration parses the includes with the **previous** embed's parser, so a `barescriptParser.bare` change that alters generated script models needs a second regen pass (`touch src/bare_script/include/barescriptParser.bare && make src/bare_script/include_source.py`) to reach a fixed point; semantics-neutral parser edits converge in one pass. Never delete the generated file to force a rebuild — the generator imports `bare_script`, which needs the embed to exist.
- `src/bare_script/runtime_c.c` — CPython extension that mirrors `runtime.py` for performance (see "C extension" below).
- `src/bare_script/library.py` — the 100 built-in functions registered in `SCRIPT_FUNCTIONS` (and the 47-alias expression-only set in `EXPRESSION_FUNCTIONS`).
- `src/bare_script/include.py` — executes the include library (barescriptModel, data, markdown, qrcode, schema, url, etc.) from the embedded include source into a single module-private globals at module import, and exports native stub functions for the include libraries' public functions (`barescript_validate_script`, `data_aggregate`, `markdown_parse`, `schema_parse`, `schema_validate`, `url_encode`, etc.), imported from `bare_script.include`. MarkdownUp-render, app-main, and async include functions are not stubbed. Only the doc build (and the tests) depends on it, so `import bare_script` skips the include bootstrap. The adjacent `src/bare_script/include/` `.bare` directory is a plain data directory — it must not contain an `__init__.py`, which would shadow this module.
- `src/bare_script/value.py` — type coercion and comparison primitives (`value_type`, `value_compare`, `value_args_validate`, etc.). Argument validation is declarative via `value_args_model`.
- `src/bare_script/options.py` — fetch implementations: HTTP via urllib3 and local files.
- `src/bare_script/__init__.py` — public surface (`execute_script`, `barescript_parse_script`, `barescript_parse_expression`, `evaluate_expression`, `barescript_lint_script`, plus fetch/log helpers). Imports from `runtime_c` when the compiled `.so` is present unless `BARESCRIPT_RUNTIME_PY=1` is set. The include module is not imported or re-exported here — import its stubs from `bare_script.include` (e.g. `from bare_script.include import schema_parse`). Otherwise, callers should import from `bare_script`, not submodules.

### CLI

`src/bare_script/bare.py` implements the `bare` CLI: argument parsing, `-c`/`-m`/`-d`/`-v`/`-x` flags, HTML/MarkdownUp render modes, and the `-x` lint/syntax-check mode. The package entry point also exposes `python -m bare_script`.

### Include library (`src/bare_script/include/*.bare`)

Pure-BareScript libraries (args parsing, data aggregation/charts, markdown rendering, diff, unittest framework, etc.) live under `src/bare_script/include/`. They are part of the **shipped package** and are loaded via `include <name.bare>` from the embedded source map in the generated `src/bare_script/include_source.py`. Each has a `testXxx.bare` counterpart in `src/bare_script/include/test/` driven by `unittest.bare`. Modify with `make test-include` (not just `make test`).

### C extension

`runtime_c.c` implements the core execution loop in C for performance. It is compiled via `setup.py` using `OptionalBuildExt`, which swallows build failures so the package still installs and the pure-Python runtime takes over. Only `runtime_c.c` is checked in; the compiled `.so` is gitignored and built locally (e.g. via `pip install -e .` or the standard `make` venv build).

When optimizing `runtime_c.c`, do **not** target debug-mode-only paths such as coverage recording (`record_statement_coverage`). `make test-include` runs in debug mode (`bare -d`), so coverage shows up hot in profiles, but production BareScript runs without it. Optimize the non-debug execution path: expression evaluation, statement dispatch, function call setup, dict lookups, value coercion.

`make runtime-c` invokes Claude Code (configurable via `RUNTIME_C_MODEL`, `RUNTIME_C_EFFORT`) against the prompt in `perf/claude-runtime-c.md` to drive porting/optimization work on the extension.

### Library function documentation

`library.py` and `.bare` files use the `# $function:` doc-comment convention. `baredocCLI.bare` (run via the `bare` CLI in the `doc` target) reads these to generate the library documentation model JSON (e.g. `library-builtin.json`). To add a new built-in function:

1. Implement in `library.py`, register in `SCRIPT_FUNCTIONS` (and `EXPRESSION_FUNCTIONS` if expression-callable, plus `EXPRESSION_FUNCTION_MAP` if the expression-context name differs).
2. Add the `$function: / $group: / $doc: / $arg:` doc block above it.
3. Add test cases in `src/tests/test_library.py`.

`make doc` (and therefore `make commit`) also renders single-page Markdown versions of the library docs — `build/doc/html/library/barescript-library.md`, `barescript-library-model.md`, and `barescript-expression-library.md`, plus the runtime model as `build/doc/html/model/barescript-model.md` — published under <https://craigahobbs.github.io/bare-script-py/library/> and <https://craigahobbs.github.io/bare-script-py/model/>. Together with the language reference (published raw at <https://craigahobbs.github.io/bare-script-py/language/README.md>), these are the Markdown equivalents of the HTML docs, intended for fetching into an AI assistant's context alongside `SKILL.md`.

## Conventions

- pylint runs with the project `pylintrc`; 100% compliance required.
- The `.bare` include library is held to 100% too, by a separate mechanism: the include-test runners pass
  `'coverageMin': 100`, so a change that adds an unreached branch fails `make test-include` — not `make cover`.
  Either cover the new path with a test or drop it; the same dead-defensive-check caution below applies.
- All `src/bare_script/` code must keep line + branch coverage at 100%. New code without tests will fail `make commit`. Beware: defensive checks that become unreachable after a refactor (e.g. a `continue` guard left in place when the surrounding logic now guarantees its condition is false) will break coverage. Either remove the dead check and rely on the proven invariant, or add a test that exercises the defensive path.
- `runtime.py` and `runtime_c.c` are kept structurally aligned — when changing one, mirror the change in the other. `runtime.py` is the reference implementation.
- BareScript literals: write objects as `{}` / `{'key': value}` and arrays as `[]` / `[a, b]` — never `objectNew()`
  or `arrayNew()`. The parser lowers both literal forms to the same `objectNew` / `arrayNew` AST nodes, so this is
  purely stylistic with no perf difference. (`arrayNewSize(n, value)` is a different function and stays.)
- Argument validation goes through `value_args_model` / `value_args_validate` from `value.py`; do not hand-roll type checks in library functions.
- Only one runtime dependency (`urllib3`); avoid adding more.

## Perf measurement

When optimizing an include file, measure within a single session — system load drifts noticeably between runs minutes apart and will produce false-positive or false-negative wins. The reliable pattern:

```bash
git diff src/bare_script/include/foo.bare > /tmp/foo.patch
git checkout src/bare_script/include/foo.bare
bare perf/foo.bare    # BEFORE
git apply /tmp/foo.patch
bare perf/foo.bare    # AFTER
```

Have the harness run each scenario 3–5 times; the first iteration is usually slow due to runtime warmup — focus on the steady-state numbers. Treat changes under ~2% as noise. Optimization ideas that look promising in isolation often regress in real workloads — measure each candidate against a same-session baseline before committing.

The perf report aggregates by **best** per-run timing per language, not mean, which is why best-of-N interleaving is
the right protocol. The report's non-BareScript rows (`JavaScript`, `Python`) never touch the include library, so
their deltas in the same runs are a free noise control.

Same-session alone is not enough for small deltas — load drifts a few percent even within minutes, enough to fake or mask a win. For A/B comparisons, interleave the configurations in one loop (baseline, then candidate, repeated 3×) and compare best-of-N per configuration. This works for runtime changes too: save baseline and candidate copies of the changed module (e.g. `src/bare_script/runtime.py`) and copy the right one into place before each perf invocation — each `bare` run is a fresh process, so swapping files between invocations is safe.

To find pure-Python runtime hot spots, profile a perf test directly:

```bash
BARESCRIPT_RUNTIME_PY=1 build/venv/system/bin/python -m cProfile -s tottime -m bare_script \
    perf/test.bare -v vLanguage "'Py'" -v vTest "'schemaValidate'"
```

The interpreter loop dominates every workload — `_evaluate_expression_helper` recursion, dict lookups, and Python call overhead, not the library functions — so pure-Python optimization effort goes to eliminating per-node calls and per-call work.

Prefer a *real* document over a synthetic one for the harness input. The distribution of features in real content — span density, link patterns, code-block sizes, paragraph length — reflects what users actually feed the library; a hand-built blob can over-weight one feature and miss the actual bottleneck. For markdown-rendering work, `static/language/README.md` is a convenient ~14 KB sample. Two practical notes:

- `systemFetch` is async, so a harness that calls it needs `async function main():`.
- `systemFetch` resolves relative paths against the script's directory, not the process CWD. From `perf/foo.bare`, the README is `'../static/language/README.md'`.

When an optimization is behaviorally correct but fails a test, consider whether the test is asserting on a "don't care" edge case — for example, a code-block-line input with a baked-in trailing `\n` that the parser pipeline never actually produces. Modifying the test input is sometimes the right call. Check whether the corner case is documented behavior first.

### Finding the hot spots: the statement profiler

`cProfile` finds hot spots in the *runtime*; it cannot tell you which lines of a `.bare` include file are hot. For that, use the runtime's coverage recorder as a per-line statement profiler. Coverage is skipped for system includes (`not script.system`), so the target must be included as a *local* file — copy it into `perf/` and include it by path, which also overrides the system definitions loaded earlier:

```
include <unittest.bare>
include 'fooVariant.bare'          # copy of src/bare_script/include/foo.bare

unittestCoverageStart()
fooEntryPoint(input)               # one representative call
unittestCoverageStop()

scripts = objectGet(unittestCoverageGlobal(), 'scripts')
for scriptName in objectKeys(scripts):
    covered = objectGet(objectGet(scripts, scriptName), 'covered')
    for lineno in objectKeys(covered):
        systemLog(scriptName + ' ' + lineno + ' ' + objectGet(objectGet(covered, lineno), 'count'))
    endfor
endfor
```

Annotating the source with those counts is what surfaces structural waste that reading the code does not — e.g. a guard chain whose remaining tests are still walked after a match, or a loop iterating declared members when most are absent from the value. Note that a `for ... in` loop costs ~4 recorded statements per iteration of index bookkeeping, and each `elif` costs ~2, so those lines look hot even when the body is trivial.

### Statement count is only a proxy when the statements do real work

Reducing recorded statements does **not** reliably reduce time. Measured on `schemaValidate` under the JS runtime: statements removed that were jump/label/assignment bookkeeping cost about **5.5 ns each**, while `objectHas`-and-loop-work statements cost about **36 ns** and the overall average was about **71 ns**. A change that removed 5.7% of statements (converting every branch to an explicit return, eliminating the shared `valueNew = value` / `return valueNew` tail) delivered **0.4%** — noise. A change that removed a comparable share but included 160 `regexMatch` calls per run delivered nearly its full statement share.

So before trusting a statement-count estimate, check *what kind* of statement the change removes. Prioritize eliminating built-in calls (especially `regexMatch`/`regexReplace`), allocations, and interpreted function calls. Deprioritize eliminating jumps, `endif` labels, and plain assignments — and always confirm with an interleaved A/B before committing to the idea. Pure Python rewards statement elimination somewhat more than V8 does, but the ranking of *which* statements matter is the same in both.

Two related traps worth remembering: the perf report's non-BareScript languages (`Python`, `JavaScript`) never touch the include library, so their deltas in the same runs are a free noise control — if they move as much as the BareScript numbers, you have measured nothing. And a candidate that adds a per-call memo only pays when one call does repeated work; it is a net loss on small inputs.

## Cross-repo workflow / tandem development

The Python and JS implementations are mirrors of each other — great effort has been made to keep `src/bare_script/*.py` and the corresponding `lib/*.js` files (runtime, value, parser, library, options, etc.) as close to line-for-line identical as possible, and they must stay that way. **Any change to one implementation needs a parallel change to the other in the same working session** — features, bug fixes, refactors, optimizations, and test additions all apply.

**`make sync` pushes outward, and the mirror repo defines the same target pushing the other way.** Always invoke it
as `make -C <repo> sync` — a shell left sitting in the mirror repo will silently sync in reverse and revert the work
you just finished.

Workflow for a tandem change:

- Changes to `src/bare_script/include/` or `static/` (the shared `.bare` sources and include-library tests): make the change here, run `make test-include`, then `make sync` to push to `../bare-script/`. Do not hand-edit those files in the JavaScript repo.
- Changes to `src/bare_script/*.py`: make the parallel edit in `../bare-script/`'s corresponding module. Keep structure, naming, and ordering aligned so the two files diff cleanly.
- After editing both repos, run the full gate in each: `make commit` (tests + lint + 100% coverage), plus `make test-include`. For perf-sensitive changes also run `make perf` in both.
- For optimization work specifically: measure interleaved in both repos before recommending, and favor wins that make `bare-script` (JavaScript) faster, since JS is the more performance-sensitive target. Line-for-line parity beats one-sided gains — an optimization that requires structural divergence between the ports is dropped even if it wins big in one engine. (Verified: inlining leaf-expression evaluation into the expression evaluator's binary/argument sites gained 10–20% in CPython, which rewards eliminating function calls, but cost V8 8–40% by bloating the JIT-inlined hot function; it was rejected to keep the ports identical.) Stage the changes in each repo with a prepared commit message but don't commit until the measured deltas confirm the change helps — or at least doesn't regress — both implementations.

### The schema-markdown reference ports

`schema.bare`, `schemaParser.bare`, `schemaTypeModel.bare`, and `schemaUtil.bare` are ports of the **reference Schema
Markdown implementations**, which live in two more repositories:

- `../schema-markdown-js/lib/schema.js` and `lib/parser.js` (JavaScript)
- `../schema-markdown/src/schema_markdown/schema.py` and `parser.py` (Python)

These are kept as close to line-for-line identical with the `.bare` sources as the languages allow, so **a change to the
schema include files needs a matching change in both reference repos in the same session** — and vice versa. Each has its
own `make commit` gate (tests + lint + 100% coverage) that must pass. They are separate repositories with their own
branches; nothing syncs automatically.

Two corollaries, both learned the hard way:

- **Port changes that are perf-neutral in native code anyway.** A branch reorder or a restructured conditional may win
  several percent in the BareScript interpreter and nothing in JS/Python — port it regardless, to keep the sources
  aligned. A pure block move with no line-level churn is the ideal shape; verify it as one by comparing the sorted line
  multiset against `HEAD` before and after.
- **Drop optimizations that force structural divergence.** The reference implementations raise/throw on validation error
  and thread no state, so a BareScript optimization that hangs a per-call memo off the threaded `error` object has
  nowhere to live in them without adding a parameter to every recursive call. Prefer the change that keeps all four
  sources parallel, even when it measures slower.

