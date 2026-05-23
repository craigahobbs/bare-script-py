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
- `TEST=testNameGlob make test-include` — single `.bare` test
- `make perf` — benchmark BareScript (C) vs BareScript (Py) vs Python
- `make sync` — push `src/bare_script/include/` and `static/` to the JavaScript repo
- `make clean` / `make superclean` — remove `build/`, downloaded base files, container images

By default, targets use the pure-Python runtime (`BARESCRIPT_RUNTIME_PY=1`). Set `BARESCRIPT_RUNTIME_C=1` to exercise the compiled C runtime instead; `make commit` runs both.

`make perf` benchmarks the runtime itself. For optimizing an individual include file, write a throwaway `.bare` harness under `perf/` and run with `bare perf/<file>.bare` — `perf/` is outside the shipped package and isn't synced cross-repo, so harnesses can live there until you're done and then be removed (regenerate as needed).

## Architecture

### Modules

- `src/bare_script/parser.py` — text → AST (the "BareScript model", a plain dict validated against the schema in `model.py`). `parse_script` and `parse_expression` are the entry points.
- `src/bare_script/runtime.py` — pure-Python `execute_script` / `evaluate_expression`. Implements statement counting (`maxStatements`), coverage recording, and the core interpreter loop. The reference implementation.
- `src/bare_script/runtime_c.c` — CPython extension that mirrors `runtime.py` for performance (see "C extension" below).
- `src/bare_script/library.py` — all ~200 built-in functions registered in `SCRIPT_FUNCTIONS` (and the smaller expression-only set in `EXPRESSION_FUNCTIONS`).
- `src/bare_script/model.py` — Schema-Markdown type model for the BareScript AST + `lint_script`.
- `src/bare_script/value.py` — type coercion and comparison primitives (`value_type`, `value_compare`, `value_args_validate`, etc.). Argument validation is declarative via `value_args_model`.
- `src/bare_script/options.py` — fetch implementations: HTTP via urllib3, local files, and the system include prefix (`FETCH_SYSTEM_PREFIX`).
- `src/bare_script/__init__.py` — public surface (`execute_script`, `parse_script`, `parse_expression`, `evaluate_expression`, `lint_script`, `validate_script`, `validate_expression`, plus fetch/log helpers). Imports from `runtime_c` when the compiled `.so` is present unless `BARESCRIPT_RUNTIME_PY=1` is set. Callers should import from `bare_script`, not submodules.

### CLI

`src/bare_script/bare.py` implements the `bare` CLI: argument parsing, `-c`/`-m`/`-d`/`-v`/`-x` flags, HTML/MarkdownUp render modes, and the `-x` lint/syntax-check mode. The package entry point also exposes `python -m bare_script`.

### Include library (`src/bare_script/include/*.bare`)

Pure-BareScript libraries (args parsing, data aggregation/charts, markdown rendering, diff, unittest framework, etc.) live under `src/bare_script/include/`. They are part of the **shipped package** and are loaded via `include <name.bare>` using the system include prefix. Each has a `testXxx.bare` counterpart in `src/bare_script/include/test/` driven by `unittest.bare`. Modify with `make test-include` (not just `make test`).

### C extension

`runtime_c.c` implements the core execution loop in C for performance. It is compiled via `setup.py` using `OptionalBuildExt`, which swallows build failures so the package still installs and the pure-Python runtime takes over. Only `runtime_c.c` is checked in; the compiled `.so` is gitignored and built locally (e.g. via `pip install -e .` or the standard `make` venv build).

When optimizing `runtime_c.c`, do **not** target debug-mode-only paths such as coverage recording (`record_statement_coverage`). `make test-include` runs in debug mode (`bare -d`), so coverage shows up hot in profiles, but production BareScript runs without it. Optimize the non-debug execution path: expression evaluation, statement dispatch, function call setup, dict lookups, value coercion.

`make runtime-c` invokes Claude Code (configurable via `RUNTIME_C_MODEL`, `RUNTIME_C_EFFORT`) against the prompt in `perf/claude-runtime-c.md` to drive porting/optimization work on the extension.

### Library function documentation

`library.py` and `.bare` files use the `# $function:` doc-comment convention. `baredoc` reads these to generate `library.json`. To add a new built-in function:

1. Implement in `library.py`, register in `SCRIPT_FUNCTIONS` (and `EXPRESSION_FUNCTIONS` if expression-callable, plus `EXPRESSION_FUNCTION_MAP` if the expression-context name differs).
2. Add the `$function: / $group: / $doc: / $arg:` doc block above it.
3. Add test cases in `src/tests/test_library.py`.

## Conventions

- pylint runs with the project `pylintrc`; 100% compliance required.
- All `src/bare_script/` code must keep line + branch coverage at 100%. New code without tests will fail `make commit`. Beware: defensive checks that become unreachable after a refactor (e.g. a `continue` guard left in place when the surrounding logic now guarantees its condition is false) will break coverage. Either remove the dead check and rely on the proven invariant, or add a test that exercises the defensive path.
- `runtime.py` and `runtime_c.c` are kept structurally aligned — when changing one, mirror the change in the other. `runtime.py` is the reference implementation.
- Argument validation goes through `value_args_model` / `value_args_validate` from `value.py`; do not hand-roll type checks in library functions.
- Only one runtime dependency (`schema-markdown`); avoid adding more.

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

Prefer a *real* document over a synthetic one for the harness input. The distribution of features in real content — span density, link patterns, code-block sizes, paragraph length — reflects what users actually feed the library; a hand-built blob can over-weight one feature and miss the actual bottleneck. For markdown-rendering work, `static/language/README.md` is a convenient ~14 KB sample. Two practical notes:

- `systemFetch` is async, so a harness that calls it needs `async function main():`.
- `systemFetch` resolves relative paths against the script's directory, not the process CWD. From `perf/foo.bare`, the README is `'../static/language/README.md'`.

When an optimization is behaviorally correct but fails a test, consider whether the test is asserting on a "don't care" edge case — for example, a code-block-line input with a baked-in trailing `\n` that the parser pipeline never actually produces. Modifying the test input is sometimes the right call. Check whether the corner case is documented behavior first.

## Cross-repo workflow / tandem development

The Python and JS implementations are mirrors of each other — great effort has been made to keep `src/bare_script/*.py` and the corresponding `lib/*.js` files (runtime, value, parser, library, model, options, etc.) as close to line-for-line identical as possible, and they must stay that way. **Any change to one implementation needs a parallel change to the other in the same working session** — features, bug fixes, refactors, optimizations, and test additions all apply.

Workflow for a tandem change:

- Changes to `src/bare_script/include/` or `static/` (the shared `.bare` sources and include-library tests): make the change here, run `make test-include`, then `make sync` to push to `../bare-script/`. Do not hand-edit those files in the JavaScript repo.
- Changes to `src/bare_script/*.py`: make the parallel edit in `../bare-script/`'s corresponding module. Keep structure, naming, and ordering aligned so the two files diff cleanly.
- After editing both repos, run the full gate in each: `make commit` (tests + lint + 100% coverage), plus `make test-include`. For perf-sensitive changes also run `make perf` in both.
- For optimization work specifically: an optimization should not disproportionately regress either implementation. Favor wins that make `bare-script` (JavaScript) faster, since JS is the more performance-sensitive target. Stage the changes in each repo with a prepared commit message but don't commit until you've made an accept/reject recommendation per project based on the measured deltas — an optimization can be worth keeping in one repo and rejecting in the other if perf diverges sharply.
