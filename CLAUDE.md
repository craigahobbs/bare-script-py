# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
make test          # Run Python unit tests
make lint          # Run pylint (100% compliance required)
make cover         # Coverage analysis (100% line + branch required)
make commit        # Full pre-commit check: test → lint → doc → cover
make doc           # Build Sphinx docs + BareScript include docs
make perf          # Run performance benchmarks (Python vs BareScript)
make test-include  # Run BareScript test suite via `bare` CLI
```

Run a single test module:

```sh
TEST=tests/test_runtime.py make test
```

## Architecture

BareScript is an interpreted scripting language. The Python package is organized into four layers:

1. **Parser** (`parser.py`) — Lexes and parses BareScript source into an AST defined by the model.

2. **Model** (`model.py`) — Schema-markdown type definitions for the AST and all BareScript types. Also provides script linting (`lint_script`).

3. **Runtime** (`runtime.py` / `runtime_c.c`) — Executes the AST. `runtime_c.c` is a C extension that mirrors `runtime.py` for performance; it is imported preferentially when available (compiled `.so`), with pure Python as fallback.

4. **Library** (`library.py`) — 209+ built-in functions (math, strings, arrays, objects, regex, HTTP, date/time, etc.). Each function is a plain Python callable registered in `SCRIPT_FUNCTIONS`.

**Additional modules:**

- `options.py` — `FetchOptions`-compatible fetch implementations: HTTP via urllib3, local files, and the built-in include path.
- `value.py` — Helpers for BareScript value type coercion (`value_boolean`, `value_number`, `value_string`, etc.).
- `bare.py` — CLI entry point (`bare` command). Parses args, wires together parser + runtime + options.
- `include/` — BareScript standard library scripts (`.bare` files) bundled with the package.

## C Extension

`runtime_c.c` implements the core execution loop in C for performance. It is compiled via `setup.py` (optional; pure Python works without it). The compiled `.so` is committed to the repo. When modifying the runtime, keep `runtime.py` and `runtime_c.c` in sync; `runtime.py` is the reference implementation.

## Public API

`__init__.py` re-exports the public surface: `execute_script`, `parse_script`, `lint_script`, `evaluate_expression`, `SCRIPT_FUNCTIONS`, `MARKDOWN_TYPES`, and option/value helpers. Callers should import only from `bare_script`, not from submodules directly.
