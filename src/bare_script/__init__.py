# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script package
"""

import os

from .lint import \
    lint_script

from .model import \
    validate_expression, \
    validate_script

from .options import \
    fetch_http, \
    fetch_read_only, \
    fetch_read_write, \
    log_stdout, \
    url_file_relative

from .parser import \
    BareScriptParserError, \
    parse_expression, \
    parse_script

from .runtime import \
    BareScriptRuntimeError

if not os.environ.get('BARESCRIPT_RUNTIME_PY'): # pragma: no cover
    try:
        from .runtime_c import evaluate_expression, execute_script
    except ImportError:
        from .runtime import evaluate_expression, execute_script
else:
    from .runtime import evaluate_expression, execute_script
