# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script command-line interface (CLI)
"""

import argparse
from functools import partial
import importlib.resources
import os
import sys
import time

from .library import SYSTEM_GLOBAL_INCLUDES_NAME
from .model import lint_script
from .options import fetch_read_write, log_stdout, url_file_relative
from .parser import parse_expression, parse_script
from .runtime import evaluate_expression, execute_script
from .value import value_boolean


def main(argv=None):
    """
    BareScript command-line interface (CLI) main entry point
    """

    # Command line arguments
    parser = argparse.ArgumentParser(prog='bare', description='The BareScript command-line interface')
    parser.add_argument('file', nargs='*', action=_FileScriptAction, help='files to process')
    parser.add_argument('-c', '--code', action=_InlineScriptAction, help='execute the BareScript code')
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug mode')
    parser.add_argument('-m', '--markdown-up', action='store_true', help='run with MarkdownUp stubs')
    parser.add_argument('-s', '--static', dest='static', action='store_const', const='s', help='perform static analysis')
    parser.add_argument('-x', '--staticx', dest='static', action='store_const', const='x', help='perform static analysis with execution')
    parser.add_argument('-v', '--var', nargs=2, action='append', metavar=('VAR', 'EXPR'), default = [],
                        help='set a global variable to an expression value')
    args = parser.parse_args(args=argv)
    if not args.scripts:
        parser.print_help()
        parser.exit()

    status_code = 0
    inline_count = 0
    try:
        # Evaluate the global variable expression arguments
        globals_ = {}
        for var_name, var_expr in args.var:
            globals_[var_name] = evaluate_expression(parse_expression(var_expr))

        # Get the scripts to run
        scripts = args.scripts
        ix_user_script = 0
        if args.markdown_up:
            scripts = [('code', 'include <markdownUp.bare>'), *scripts]
            ix_user_script = 1

            # Add unittest.bare argument globals
            globals_['vUnittestReport'] = True
            if args.static:
                globals_['vUnittestDisabled'] = True

        # Parse and execute all source files in order
        for ix_script, [script_type, script_value] in enumerate(scripts):
            # Get the script source
            if script_type == 'file':
                script_name = script_value
                script_source = None
                try:
                    script_source = fetch_read_write({'url': script_value})
                except:
                    pass
                if script_source is None:
                    raise ValueError(f'Failed to load "{script_value}"')
            else:
                inline_count += 1
                inline_display = inline_count - ix_user_script
                script_name = f'<string{inline_display if inline_display > 1 else ""}>'
                script_source = script_value

            # Parse the script source
            script = parse_script(script_source, 1, script_name)

            # Execute?
            static_globals = None
            if args.static != 's':
                # Set the globals to use for static analysis (below)
                if not args.static or ix_script < ix_user_script:
                    static_globals = globals_
                else:
                    # Copy global to keep each script as isolated as possible
                    static_globals = dict(globals_)
                    global_includes = static_globals.get(SYSTEM_GLOBAL_INCLUDES_NAME)
                    if global_includes is not None and isinstance(global_includes, dict):
                        static_globals[SYSTEM_GLOBAL_INCLUDES_NAME] = dict(global_includes)

                # Execute the script
                time_begin = time.time()
                result = execute_script(script, {
                    'debug': args.debug or False,
                    'fetchFn': _fetch_include,
                    'globals': static_globals,
                    'logFn': log_stdout,
                    'systemPrefix': _FETCH_INCLUDE_PREFIX,
                    'urlFn': partial(url_file_relative, script_value) if script_type == 'file' else None
                })
                if isinstance(result, (int, float)) and int(result) == result and 0 <= result <= 255:
                    status_code = int(result) or status_code
                else:
                    status_code = (1 if value_boolean(result) else 0) or status_code

                # Log script execution end with timing
                if args.debug and ix_script >= ix_user_script:
                    time_end = time.time()
                    print(f'BareScript executed in {1000 * (time_end - time_begin):.1f} milliseconds')

            # Run the bare-script linter?
            if args.static and ix_script >= ix_user_script:
                warnings = lint_script(script, static_globals)
                if not warnings:
                    print(f'BareScript static analysis "{script_name}" ... OK')
                else:
                    print(f'BareScript static analysis "{script_name}" ... {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                    for warning in warnings:
                        print(warning)
                    status_code = 1

            # Stop on error status code
            if status_code != 0 and not args.static:
                break

    except Exception as exc:
        print(str(exc).strip())
        status_code = 1

    # Return the status code
    sys.exit(status_code)


def _fetch_include(request):
    # Is this a bare system include?
    url = request['url']
    if url.startswith(_FETCH_INCLUDE_PREFIX):
        path = url[len(_FETCH_INCLUDE_PREFIX):]
        with importlib.resources.files('bare_script.include').joinpath(path).open('rb') as cm_inc:
            return cm_inc.read().decode(encoding='utf-8')

    return fetch_read_write(request)


_FETCH_INCLUDE_PREFIX = f':bare-include:{os.sep}'


class _InlineScriptAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if 'scripts' not in namespace:
            setattr(namespace, 'scripts', [])
        namespace.scripts.append(('code', values))


class _FileScriptAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if 'scripts' not in namespace:
            setattr(namespace, 'scripts', [])
        namespace.scripts.extend(('file', value) for value in values)
