# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script command-line interface (CLI)
"""

import argparse
from functools import partial
import sys
import time

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
    parser.add_argument('-s', '--static', action='store_true', help='perform static analysis')
    parser.add_argument('-v', '--var', nargs=2, action='append', metavar=('VAR', 'EXPR'), default = [],
                        help='set a global variable to an expression value')
    args = parser.parse_args(args=argv)
    if not args.scripts:
        parser.print_help()
        parser.exit()

    status_code = 0
    inline_count = 0
    error_name = None
    try:
        # Evaluate the global variable expression arguments
        globals_ = {}
        for var_name, var_expr in args.var:
            globals_[var_name] = evaluate_expression(parse_expression(var_expr))

        # Parse and execute all source files in order
        for script_type, script_value in args.scripts:
            # Get the script source
            if script_type == 'file':
                script_name = script_value
                script_source = None
                try:
                    script_source = fetch_read_write({'url': script_value})
                except: # pylint: disable=bare-except
                    pass
                if script_source is None:
                    raise ValueError(f'Failed to load "{script_value}"')
            else:
                inline_count += 1
                script_name = f'-c {inline_count}'
                script_source = script_value

            # Parse the script source
            error_name = script_name
            script = parse_script(script_source)

            # Run the bare-script linter?
            if args.static or args.debug:
                warnings = lint_script(script)
                warning_prefix = f'BareScript: Static analysis "{script_name}" ...'
                if not warnings:
                    print(f'{warning_prefix} OK')
                else:
                    print(f'{warning_prefix} {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                    for warning in warnings:
                        print(f'BareScript:     {warning}')
                    if args.static:
                        status_code = 1
                        break
            if args.static:
                continue

            # Execute the script
            time_begin = time.time()
            result = execute_script(script, {
                'debug': args.debug or False,
                'fetchFn': fetch_read_write,
                'globals': globals_,
                'logFn': log_stdout,
                'systemPrefix': 'https://craigahobbs.github.io/markdown-up/include/',
                'urlFn': partial(url_file_relative, script_value) if script_type == 'file' else None
            })
            if isinstance(result, (int, float)) and int(result) == result and 0 <= result <= 255:
                status_code = int(result)
            else:
                status_code = 1 if value_boolean(result) else 0

            # Log script execution end with timing
            if args.debug:
                time_end = time.time()
                print(f'BareScript: Script executed in {1000 * (time_end - time_begin):.1f} milliseconds')

            # Stop on error status code
            if status_code != 0:
                break

    except Exception as e: # pylint: disable=broad-exception-caught
        if error_name is not None:
            print(f'{error_name}:')
        print(str(e).strip())
        status_code = 1

    # Return the status code
    sys.exit(status_code)


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
