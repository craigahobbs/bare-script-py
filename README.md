# bare-script

[![PyPI - Status](https://img.shields.io/pypi/status/bare-script)](https://pypi.org/project/bare-script/)
[![PyPI](https://img.shields.io/pypi/v/bare-script)](https://pypi.org/project/bare-script/)
[![GitHub](https://img.shields.io/github/license/craigahobbs/bare-script-py)](https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/bare-script)](https://pypi.org/project/bare-script/)

[BareScript](https://craigahobbs.github.io/bare-script-py/language/)
is a simple, lightweight, and portable programming language. Its Pythonic syntax is influenced by
JavaScript, C, and the Unix Shell. BareScript also has a library of built-in functions for common
programming operations. BareScript can be embedded within applications or used as a stand-alone
programming language using the command-line interface.

There are two implementations of BareScript:
[BareScript for Python](https://github.com/craigahobbs/bare-script-py#readme)
(this package) and
[BareScript for JavaScript](https://github.com/craigahobbs/bare-script#readme).
Both implementations have 100% unit test coverage with identical unit test suites, so you can be
confident that BareScript will execute the same regardless of the underlying runtime environment.


## Links

- [The BareScript Language](https://craigahobbs.github.io/bare-script-py/language/)
- [The BareScript Library](https://craigahobbs.github.io/bare-script-py/library/)
- [The BareScript Include Library Tests](https://craigahobbs.github.io/bare-script/include/test/)
- [API Documentation](https://craigahobbs.github.io/bare-script-py/)
- [Source code](https://github.com/craigahobbs/bare-script-py)


## Executing BareScript Scripts

To execute a BareScript script, parse the script using the
[barescript_parse_script](https://craigahobbs.github.io/bare-script-py/scripts.html#barescript-parse-script)
function. Then execute the script using the
[execute_script](https://craigahobbs.github.io/bare-script-py/scripts.html#execute-script)
function. For example:

``` python
from bare_script import barescript_parse_script, execute_script

# Parse the script
script = barescript_parse_script('''\
# Double a number
function double(n):
    return n * 2
endfunction

return N + ' times 2 is ' + double(N)
''')

# Execute the script
globals = {'N': 10}
print(execute_script(script, {'globals': globals}))
```

This outputs:

```
10 times 2 is 20
```


### The BareScript Library

[The BareScript Library](https://craigahobbs.github.io/bare-script-py/library/)
includes a set of built-in functions for mathematical operations, object manipulation, array
manipulation, regular expressions, HTTP fetch and more. The following example demonstrates the use
of the
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='system'&systemfetch),
[objectGet](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='object'&objectget), and
[arrayLength](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='array'&arraylength)
functions.

``` python
import urllib.request

from bare_script import barescript_parse_script, execute_script, fetch_http

# Parse the script
script = barescript_parse_script('''\
# Fetch the BareScript builtin library documentation JSON
docs = jsonParse(systemFetch('https://craigahobbs.github.io/bare-script-py/library/library-builtin.json'))

# Return the number of builtin functions
return 'The BareScript Library has ' + arrayLength(objectGet(docs, 'functions')) + ' builtin functions'
''')

# Execute the script
print(execute_script(script, {'fetchFn': fetch_http}))
```

This outputs:

```
The BareScript Library has 108 builtin functions
```


## Evaluating BareScript Expressions

To evaluate a
[BareScript expression](https://craigahobbs.github.io/bare-script-py/language/#expressions),
parse the expression using the
[barescript_parse_expression](https://craigahobbs.github.io/bare-script-py/expressions.html#barescript-parse-expression)
function. Then evaluate the expression using the
[evaluate_expression](https://craigahobbs.github.io/bare-script-py/expressions.html#evaluate-expression)
function.

Expression evaluation includes the
[BareScript Expression Library](https://craigahobbs.github.io/bare-script-py/library/expression.html),
a set of built-in, spreadsheet-like functions.

For example:

``` python
from bare_script import barescript_parse_expression, evaluate_expression

# Parse the expression
expr = barescript_parse_expression('2 * max(a, b, c)')

# Evaluate the expression
variables = {'a': 1, 'b': 2, 'c': 3}
print(evaluate_expression(expr, None, variables))
```

This outputs:

```
6
```


## The Include Library Stub Functions

BareScript include library functions are callable directly from Python using the native stub functions
exported by the
[include module](https://craigahobbs.github.io/bare-script-py/include.html) — for example,
[data_aggregate](https://craigahobbs.github.io/bare-script-py/include.html#data-aggregate),
[markdown_parse](https://craigahobbs.github.io/bare-script-py/include.html#markdown-parse),
[qrcode_matrix](https://craigahobbs.github.io/bare-script-py/include.html#qrcode-matrix),
[schema_parse](https://craigahobbs.github.io/bare-script-py/include.html#schema-parse),
[schema_validate](https://craigahobbs.github.io/bare-script-py/include.html#schema-validate), and
[url_encode](https://craigahobbs.github.io/bare-script-py/include.html#url-encode).
Each stub function executes its corresponding include library function using the BareScript
runtime. For example:

``` python
from bare_script.include import markdown_parse, markdown_title

# Parse the Markdown text
markdown = markdown_parse('''\
# Hello, Markdown!

This is some text.
''')

# Print the Markdown title
print(markdown_title(markdown))
```

This outputs:

```
Hello, Markdown!
```


## The BareScript Command-Line Interface (CLI)

You can run BareScript from the command line using the BareScript CLI, "bare". BareScript script
files use the ".bare" file extension.

```
bare script.bare
```

**Note:** In the BareScript CLI, import statements and the
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='system'&systemfetch)
function read non-URL paths from the local file system.
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='system'&systemfetch)
calls with a non-URL path and a request body write the body to the path.


## MarkdownUp, a Markdown Viewer with BareScript

[MarkdownUp](https://craigahobbs.github.io/markdown-up/) is a Markdown Viewer that executes
BareScript embedded within Markdown documents. The MarkdownUp runtime contains functions for
dynamically rendering Markdown text, drawing SVG images, etc. For example:

~~~
# Markdown Application

This is a Markdown document with embedded BareScript:

``` markdown-script
markdownPrint('Hello, Markdown!')
```
~~~


## C Runtime

The package ships with an optional CPython C extension, `runtime_c`, that mirrors the pure-Python
runtime for faster script execution. The compiled extension is used automatically when available;
set the environment variable `BARESCRIPT_RUNTIME_PY=1` to force the pure-Python runtime.

The extension supports CPython 3.10 and later on both the default (GIL) and free-threaded Python
builds. See the Performance section below for benchmark results comparing the C runtime, the
pure-Python runtime, and native Python.


## Performance

The `make perf` target benchmarks the BareScript runtime with a suite of compute-intensive tests —
Mandelbrot set computation, Markdown parsing and rendering, QR code generation, Schema Markdown
parsing and validation, and URL encoding and decoding — and compares each test with an equivalent
native Python program (using the
[schema-markdown](https://pypi.org/project/schema-markdown/) package).

The following results are from `make perf PERF_MERGE=` (CPython 3.14, Apple M-series). "BareScript
(PyC)" is the C runtime; "BareScript (Py)" is the pure-Python runtime. Times are the best per-run
timing in milliseconds per 100 runs. Multiples are relative to the native Python time. Tests
without a native Python equivalent are omitted.

| Test             | Language         | Time (ms) | Multiple |
| ---------------- | ---------------- | --------: | -------: |
| mandelbrot       | Python           |    4720.8 |          |
|                  | BareScript (PyC) |   10800.0 |     2.3x |
|                  | BareScript (Py)  |  334100.0 |    70.8x |
| schemaValidate   | Python           |      21.0 |          |
|                  | BareScript (PyC) |     101.6 |     4.8x |
|                  | BareScript (Py)  |    1404.8 |    67.0x |
| urlEncode        | Python           |       1.1 |          |
|                  | BareScript (PyC) |       5.6 |     5.3x |
|                  | BareScript (Py)  |      39.1 |    37.1x |
| schemaParse      | Python           |      17.1 |          |
|                  | BareScript (PyC) |     120.4 |     7.1x |
|                  | BareScript (Py)  |     882.4 |    51.7x |
| urlDecode        | Python           |       1.2 |          |
|                  | BareScript (PyC) |      13.1 |    10.8x |
|                  | BareScript (Py)  |      68.5 |    56.6x |


## Using BareScript with an AI Assistant

This repository ships a
[`SKILL.md`](https://github.com/craigahobbs/bare-script-py/blob/main/SKILL.md)
file that teaches an AI coding assistant how to write idiomatic BareScript — language syntax, the
built-in and include libraries, the MarkdownUp application pattern, and the unit-test conventions.
It is plain Markdown and applies to either BareScript implementation.

For [Claude Code](https://claude.com/claude-code) and other tools that follow the
[Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
convention, install it as a project or user skill:

```
mkdir -p .claude/skills/bare-script
cp SKILL.md .claude/skills/bare-script/SKILL.md
```

Use `~/.claude/skills/bare-script/SKILL.md` instead to make it available across all projects. For
other assistants, include the file's contents in your system prompt or rules file.

Once installed, prompt the assistant with a task like:

```
claude "Build a MarkdownUp application that plays tic-tac-toe against the user, with a reset button and a running win/loss/draw tally rendered as a bar chart. Save it as ticTacToe.md"
```

To run the resulting MarkdownUp application locally, install the
[markdown-up](https://pypi.org/project/markdown-up/) viewer and point it at the Markdown file:

```
pip install markdown-up
markdown-up ticTacToe.md
```

The BareScript library is also documented as single-page Markdown, which can be fetched directly
into an assistant's context alongside `SKILL.md`:

- [The BareScript Library](https://craigahobbs.github.io/bare-script-py/library/barescript-library.md)
- [The BareScript Library Models](https://craigahobbs.github.io/bare-script-py/library/barescript-library-model.md)


## Development

This package is developed using [python-build](https://github.com/craigahobbs/python-build#readme).
It was started using [python-template](https://github.com/craigahobbs/python-template#readme) as follows:

```
template-specialize python-template/template/ bare-script-py/ -k package bare-script -k name 'Craig A. Hobbs' -k email 'craigahobbs@gmail.com' -k github 'craigahobbs'
```
