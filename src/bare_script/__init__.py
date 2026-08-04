# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script package
"""

import os

from .options import \
    fetch_http, \
    fetch_read_only, \
    fetch_read_write, \
    log_stdout, \
    url_file_relative

from .runtime import \
    BareScriptParserError, \
    BareScriptRuntimeError, \
    barescript_lint_script, \
    barescript_parse_expression, \
    barescript_parse_script

if not os.environ.get('BARESCRIPT_RUNTIME_PY'): # pragma: no cover
    try:
        from .runtime_c import evaluate_expression, execute_script
    except ImportError:
        from .runtime import evaluate_expression, execute_script
else:
    from .runtime import evaluate_expression, execute_script
