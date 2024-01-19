bare-script
===========

.. |badge-status| image:: https://img.shields.io/pypi/status/bare-script
   :alt: PyPI - Status
   :target: https://pypi.python.org/pypi/bare-script/

.. |badge-version| image:: https://img.shields.io/pypi/v/bare-script
   :alt: PyPI
   :target: https://pypi.python.org/pypi/bare-script/

.. |badge-license| image:: https://img.shields.io/github/license/craigahobbs/bare-script-py
   :alt: GitHub
   :target: https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

.. |badge-python| image:: https://img.shields.io/pypi/pyversions/bare-script
   :alt: PyPI - Python Version
   :target: https://www.python.org/downloads/

|badge-status| |badge-version| |badge-license| |badge-python|

BareScript is a light-weight scripting and expression language.


Links
-----

- `The BareScript Language <https://craigahobbs.github.io/bare-script/language/>`__
- `The BareScript Library <https://craigahobbs.github.io/bare-script-py/library/>`__
- `The BareScript Expression Library <https://craigahobbs.github.io/bare-script-py/library/expression.html>`__
- `API Documentation <https://craigahobbs.github.io/bare-script-py/>`__
- `Source code <https://github.com/craigahobbs/bare-script-py>`__


Executing BareScript
--------------------

To execute a BareScript script, parse the script using the
`parse_script <https://craigahobbs.github.io/bare-script-py/scripts.html#parse-script>`__
function. Then execute the script using the
`execute_script <https://craigahobbs.github.io/bare-script-py/scripts.html#execute-script>`__
function. For example:

>>> from bare_script import execute_script, parse_script
...
>>> # Parse the script
... script = parse_script('''\
... # Double a number
... function double(n):
...     return n * 2
... endfunction
...
... return N + ' times 2 is ' + double(N)
... ''')
...
>>> # Execute the script
... globals = {'N': 10}
>>> print(execute_script(script, {'globals': globals}))
10 times 2 is 20


The BareScript Library
^^^^^^^^^^^^^^^^^^^^^^

`The BareScript Library <https://craigahobbs.github.io/bare-script-py/library/>`__
includes a set of built-in functions for mathematical operations, object manipulation, array
manipulation, regular expressions, HTTP fetch and more. The following example demonstrates the use
of the
`systemFetch <https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='System'&systemfetch>`__,
`objectGet <https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='Object'&objectget>`__, and
`arrayLength <https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='Array'&arraylength>`__
functions.

>>> import urllib.request
...
>>> from bare_script import execute_script, fetch_http, parse_script
...
>>> # Parse the script
... script = parse_script('''\
... # Fetch the BareScript library documentation JSON
... docs = jsonParse(systemFetch('https://craigahobbs.github.io/bare-script-py/library/library.json'))
...
... # Return the number of library functions
... return 'The BareScript Library has ' + arrayLength(objectGet(docs, 'functions')) + ' functions'
... ''')
...
>>> # Execute the script
... print(execute_script(script, {'fetchFn': fetch_http}))
The BareScript Library has 106 functions


Evaluating BareScript Expressions
---------------------------------

To evaluate a
`BareScript expression <https://craigahobbs.github.io/bare-script/language/#expressions>`__,
parse the expression using the
`parse_expression <https://craigahobbs.github.io/bare-script-py/expressions.html#parse-expression>`__
function. Then evaluate the expression using the
`evaluate_expression <https://craigahobbs.github.io/bare-script-py/expressions.html#evaluate-expression>`__
function.

Expression evaluation includes the
`BareScript Expression Library <https://craigahobbs.github.io/bare-script-py/library/expression.html>`__,
a set of built-in, spreadsheet-like functions.

For example:

>>> from bare_script import evaluate_expression, parse_expression
...
>>> # Parse the expression
... expr = parse_expression('2 * max(a, b, c)')
...
>>> # Evaluate the expression
... variables = {'a': 1, 'b': 2, 'c': 3}
>>> print(evaluate_expression(expr, None, variables))
6.0


The BareScript Command-Line Interface (CLI)
-------------------------------------------

You can run BareScript from the command line using the BareScript CLI, "bare". BareScript script
files use the ".bare" file extension.

.. code-block:: sh

    bare script.bare

**Note:** In the BareScript CLI, import statements and the
`systemFetch <https://craigahobbs.github.io/bare-script-py/library/#var.vGroup='System'&systemfetch>`__
function read non-URL paths from the local file system.


MarkdownUp, a Markdown Viewer with BareScript
---------------------------------------------

`MarkdownUp <https://craigahobbs.github.io/markdown-up/>`__
is a Markdown Viewer that executes BareScript embedded within Markdown documents.
`MarkdownUp <https://craigahobbs.github.io/markdown-up/>`__
extends its
`standard library <https://craigahobbs.github.io/markdown-up/library/>`__
with functions for dynamically rendering Markdown text, drawing SVG images, etc.

For example:

.. code-block:: markdown

    # Markdown Application

    This is a Markdown document with embedded BareScript:

    ~~~ markdown-script
    markdownPrint('Hello, Markdown!')
    ~~~


Development
-----------

This package is developed using `python-build <https://github.com/craigahobbs/python-build#readme>`__.
It was started using `python-template <https://github.com/craigahobbs/python-template#readme>`__ as follows:

.. code-block:: sh

    template-specialize python-template/template/ bare-script/ -k package bare-script -k name 'Craig A. Hobbs' -k email 'craigahobbs@gmail.com' -k github 'craigahobbs'
