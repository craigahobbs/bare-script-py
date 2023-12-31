# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script command-line interface (CLI) main module
"""

import argparse
from functools import partial
import re
import sys
import time
import urllib.request

from .model import lint_script
from .parser import parse_script
from .runtime import execute_script


def main(argv=None):
    """
    BareScript command-line interface (CLI) main entry point
    """

    # Command line arguments
    parser = argparse.ArgumentParser(prog='bare', description='The BareScript command-line interface')
    parser.add_argument('filename', nargs='*', action=_ScriptAction, help='files to process')
    parser.add_argument('-c', '--code', nargs=1, action=_ScriptAction, help='execute the BareScript code')
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug mode')
    parser.add_argument('-s', '--static', action='store_true', help='perform static analysis')
    parser.add_argument('-v', '--var', nargs=2, action='append', metavar=('VAR', 'EXPR'),
                        help='set a global variable to an expression value')
    args = parser.parse_args(args=argv)

    status_code = 0
    current_file = None
    try:
        # Parse and execute all source files in order
        globals_ = dict(args.var) if args.var is not None else {}
        for file_, source in args.files:
            current_file = file_

            # Parse the source
            script = parse_script(source if source is not None else _fetch_fn(file_))

            # Run the bare-script linter?
            if args.static or args.debug:
                warnings = lint_script(script)
                warning_prefix = f'BareScript: Static analysis "{file_}" ...'
                if not warnings:
                    print(f'{warning_prefix} OK')
                else:
                    print(f'{warning_prefix} {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                    for warning in warnings:
                        print(f'BareScript:     {warning}')
                    if args.static:
                        # pylint: disable=broad-exception-raised
                        raise Exception('Static analysis failed')
            if args.static:
                continue

            # Execute the script
            time_begin = time.time()
            result = execute_script(script, {
                'debug': args.debug or False,
                'fetchFn': _fetch_fn,
                'globals': globals_,
                'logFn': _log_fn,
                'systemPrefix': 'https://craigahobbs.github.io/markdown-up/include/',
                'urlFn': partial(_url_fn, file_)
            })
            if isinstance(result, (int, float)) and int(result) == result and 0 <= result <= 255:
                status_code = int(result)
            else:
                status_code = 1 if result else 0

            # Log script execution end with timing
            if args.debug:
                time_end = time.time()
                print(f'BareScript: Script executed in {1000 * (time_end - time_begin):.1f} milliseconds')

            # Stop on error status code
            if status_code != 0:
                break

    except Exception as e: # pylint: disable=broad-exception-caught
        if current_file is not None:
            print(f'{current_file}:')
        print(str(e))
        status_code = 1

    # Return the status code
    sys.exit(status_code)


# Custom argparse action for script file arguments
class _ScriptAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        files = getattr(namespace, 'files', [])
        if option_string in ['-c', '--code']:
            code_count = getattr(namespace, 'code_count', 0)
            code_count += 1
            setattr(namespace, 'code_count', code_count)
            for value in values:
                files.append((f'-c {code_count}', value))
        elif option_string is None:
            for value in values:
                files.append((value, None))
        setattr(namespace, 'files', files)


# The fetch function
def _fetch_fn(url):
    # URL?
    if R_URL.match(url) is not None:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                return response.read().decode('utf-8')
        # pylint: disable=broad-exception-raised
        raise Exception(f'Failed to load "{url}"')

    # File
    with open(url, 'r', encoding='utf-8') as fh:
        return fh.read()


# The log function
def _log_fn(message):
    print(message)


# The URL function
def _url_fn(file_, url):
    if re.match(R_URL, url) or url.startswith('/'):
        return url
    return f'{file_[:file_.rfind("/") + 1]}{url}'

R_URL = re.compile(r'^[a-z]+:')
