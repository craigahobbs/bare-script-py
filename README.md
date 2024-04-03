# bare-script

[![PyPI - Status](https://img.shields.io/pypi/status/bare-script)](https://pypi.org/project/bare-script/)
[![PyPI](https://img.shields.io/pypi/v/bare-script)](https://pypi.org/project/bare-script/)
[![GitHub](https://img.shields.io/github/license/craigahobbs/bare-script-py)](https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/bare-script)](https://pypi.org/project/bare-script/)

[BareScript](https://craigahobbs.github.io/bare-script/language/)
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

- [The BareScript Language](https://craigahobbs.github.io/bare-script/language/)
- [The BareScript Library](https://craigahobbs.github.io/bare-script-py/library/)
- [The BareScript Expression Library](https://craigahobbs.github.io/bare-script-py/library/expression.html)
- [API Documentation](https://craigahobbs.github.io/bare-script-py/)
- [Source code](https://github.com/craigahobbs/bare-script-py)


## Executing BareScript Scripts

To execute a BareScript script, parse the script using the
[parse_script](https://craigahobbs.github.io/bare-script-py/scripts.html#parse-script)
function. Then execute the script using the
[execute_script](https://craigahobbs.github.io/bare-script-py/scripts.html#execute-script)
function. For example:

~~~ python
from bare_script import execute_script, parse_script

# Parse the script
script = parse_script('''\
# Double a number
function double(n):
    return n * 2
endfunction

return N + ' times 2 is ' + double(N)
''')

# Execute the script
globals = {'N': 10}
print(execute_script(script, {'globals': globals}))
~~~

This outputs:

~~~
10 times 2 is 20
~~~


### The BareScript Library

[The BareScript Library](https://craigahobbs.github.io/bare-script-py/library/)
includes a set of built-in functions for mathematical operations, object manipulation, array
manipulation, regular expressions, HTTP fetch and more. The following example demonstrates the use
of the
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='System'&systemfetch),
[objectGet](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='Object'&objectget), and
[arrayLength](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='Array'&arraylength)
functions.

~~~ python
import urllib.request

from bare_script import execute_script, fetch_http, parse_script

# Parse the script
script = parse_script('''\
# Fetch the BareScript library documentation JSON
docs = jsonParse(systemFetch('https://craigahobbs.github.io/bare-script-py/library/library.json'))

# Return the number of library functions
return 'The BareScript Library has ' + arrayLength(objectGet(docs, 'functions')) + ' functions'
''')

# Execute the script
print(execute_script(script, {'fetchFn': fetch_http}))
~~~

This outputs:

~~~
The BareScript Library has 105 functions
~~~


## Evaluating BareScript Expressions

To evaluate a
[BareScript expression](https://craigahobbs.github.io/bare-script/language/#expressions),
parse the expression using the
[parse_expression](https://craigahobbs.github.io/bare-script-py/expressions.html#parse-expression)
function. Then evaluate the expression using the
[evaluate_expression](https://craigahobbs.github.io/bare-script-py/expressions.html#evaluate-expression)
function.

Expression evaluation includes the
[BareScript Expression Library](https://craigahobbs.github.io/bare-script-py/library/expression.html),
a set of built-in, spreadsheet-like functions.

For example:

~~~ python
from bare_script import evaluate_expression, parse_expression

# Parse the expression
expr = parse_expression('2 * max(a, b, c)')

# Evaluate the expression
variables = {'a': 1, 'b': 2, 'c': 3}
print(evaluate_expression(expr, None, variables))
~~~

This outputs:

~~~
6
~~~


## The BareScript Command-Line Interface (CLI)

You can run BareScript from the command line using the BareScript CLI, "bare". BareScript script
files use the ".bare" file extension.

~~~
bare script.bare
~~~

**Note:** In the BareScript CLI, import statements and the
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='System'&systemfetch)
function read non-URL paths from the local file system.
[systemFetch](https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='System'&systemfetch)
calls with a non-URL path and a
[request body](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='SystemFetchRequest')
write the body to the path.


## MarkdownUp, a Markdown Viewer with BareScript

[MarkdownUp](https://craigahobbs.github.io/markdown-up/)
is a Markdown Viewer that executes BareScript embedded within Markdown documents.
MarkdownUp includes the
[MarkdownUp Library](https://craigahobbs.github.io/markdown-up/library/),
which extends the
[BareScript Library](https://craigahobbs.github.io/bare-script-py/library/)
with functions for dynamically rendering Markdown text, drawing SVG images, etc.

For example:

```
# Markdown Application

This is a Markdown document with embedded BareScript:

~~~ markdown-script
markdownPrint('Hello, Markdown!')
~~~
```


## Development

This package is developed using [python-build](https://github.com/craigahobbs/python-build#readme).
It was started using [python-template](https://github.com/craigahobbs/python-template#readme) as follows:

~~~
template-specialize python-template/template/ bare-script-py/ -k package bare-script -k name 'Craig A. Hobbs' -k email 'craigahobbs@gmail.com' -k github 'craigahobbs'
~~~
