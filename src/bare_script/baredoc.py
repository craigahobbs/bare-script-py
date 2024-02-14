# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
bare-script library documentation tool
"""

import argparse
import json
import re
import sys


def main(argv=None):
    """
    BareScript library documentation tool main entry point
    """

    # Command line arguments
    parser = argparse.ArgumentParser(prog='bare', description='The BareScript library documentation tool')
    parser.add_argument('files', metavar='file', nargs='+', help='files to process')
    parser.add_argument('-o', dest='output', metavar='file', default='-', help='write output to file (default is "-")')
    args = parser.parse_args(args=argv)

    # Parse each source file line-by-line
    errors = []
    funcs = {}
    func = None
    for file_ in args.files:
        with open(file_, 'r', encoding='utf-8') as fh:
            source = fh.read()
        lines = R_SPLIT.split(source)
        for ix_line, line in enumerate(lines):
            # function/group/doc/return documentation keywords?
            match_key = R_KEY.match(line)
            if match_key is not None:
                key = match_key['key']
                text = match_key['text']
                text_trim = text.strip()

                # Keyword used outside of function?
                if key != 'function' and func is None:
                    errors.append(f'{file_}:{ix_line + 1}: {key} keyword outside function')
                    continue

                # Process the keyword
                if key == 'group':
                    if text_trim == '':
                        errors.append(f'{file_}:{ix_line + 1}: Invalid function group name "{text_trim}"')
                        continue
                    if 'group' in func:
                        errors.append(f'{file_}:{ix_line + 1}: Function "{func["name"]}" group redefinition')
                        continue

                    # Set the function group
                    func['group'] = text_trim

                elif key in ('doc', 'return'):
                    # Add the documentation line - don't add leading blank lines
                    func_doc = func.get(key)
                    if func_doc is not None or text_trim != '':
                        if func_doc is None:
                            func_doc = []
                            func[key] = func_doc
                        func_doc.append(text)

                else:
                    # key == 'function'
                    if text_trim == '':
                        errors.append(f'{file_}:{ix_line + 1}: Invalid function name "{text_trim}"')
                        continue
                    if text_trim in funcs:
                        errors.append(f'{file_}:{ix_line + 1}: Function "{text_trim}" redefinition')
                        continue

                    # Add the function
                    func = {'name': text_trim}
                    funcs[text_trim] = func

                continue

            # arg keyword?
            match_arg = R_ARG.match(line)
            if match_arg is not None:
                name = match_arg['name']
                text = match_arg['text']
                text_trim = text.strip()

                # Keyword used outside of function?
                if func is None:
                    errors.append(f'{file_}:{ix_line + 1}: Function argument "{name}" outside function')
                    continue

                # Add the function arg documentation line - don't add leading blank lines
                func_args = func.get('args')
                func_arg = None
                if func_args is not None:
                    func_arg = next((find_arg for find_arg in func_args if find_arg['name'] == name), None)
                if func_arg is not None or text_trim != '':
                    if func_args is None:
                        func_args = []
                        func['args'] = func_args
                    if func_arg is None:
                        func_arg = {'name': name, 'doc': []}
                        func_args.append(func_arg)
                    func_arg['doc'].append(text)

                continue

            # Unknown documentation comment?
            match_unknown = R_UNKNOWN.match(line)
            if match_unknown is not None:
                unknown = match_unknown.groups('unknown')
                errors.append(f'{file_}:{ix_line + 1}: Invalid documentation comment "{unknown}"')
                continue

    # Create the library documentation model
    library = {'functions': sorted(funcs.values(), key=lambda func: func['name'])}

    # Validate the library documentation model
    if len(library['functions']) == 0:
        errors.append('error: No library functions')
    for func in library['functions']:
        func_name = func['name']
        if 'group' not in func:
            errors.append(f'error: Function "{func_name}" missing group')
        if 'doc' not in func:
            errors.append(f'error: Function "{func_name}" missing documentation')

    # Errors?
    if len(errors) != 0:
        print('\n'.join(errors))
        sys.exit(1)

    # JSON-serialize the library documentation model
    library_json = json.dumps(library, separators=(',', ':'), sort_keys=True)

    # Output to stdout?
    if args.output == '-':
        print(library_json)

    # Output to file
    with open(args.output, 'w', encoding='utf-8') as fh:
        fh.write(library_json)


# Library documentation regular expressions
R_KEY = re.compile(r'^\s*(?:\/\/|#)\s*\$(?P<key>function|group|doc|return):\s?(?P<text>.*)$')
R_ARG = re.compile(r'^\s*(?:\/\/|#)\s*\$arg\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.\.\.)?):\s?(?P<text>.*)$')
R_UNKNOWN = re.compile(r'^\s*(?:\/\/|#)\s*\$(?P<unknown>[^:]+):')
R_SPLIT = re.compile(r'\r?\n')
