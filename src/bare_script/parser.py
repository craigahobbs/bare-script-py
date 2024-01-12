# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript language parser
"""

import re


# BareScript regex
R_SCRIPT_LINE_SPLIT = re.compile(r'\r?\n')
R_SCRIPT_CONTINUATION = re.compile(r'\\\s*$')
R_SCRIPT_COMMENT = re.compile(r'^\s*(?:#.*)?$')
R_SCRIPT_ASSIGNMENT = re.compile(r'^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<expr>.+)$')
R_SCRIPT_FUNCTION_BEGIN = re.compile(
    r'^(?P<async>\s*async)?\s*function\s+(?P<name>[A-Za-z_]\w*)\s*\('
    r'\s*(?P<args>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)?(?P<lastArgArray>\s*\.\.\.)?\s*\)\s*:\s*$'
)
R_SCRIPT_FUNCTION_ARG_SPLIT = re.compile(r'\s*,\s*')
R_SCRIPT_FUNCTION_END = re.compile(r'^\s*endfunction\s*$')
R_SCRIPT_LABEL = re.compile(r'^\s*(?P<name>[A-Za-z_]\w*)\s*:\s*$')
R_SCRIPT_JUMP = re.compile(r'^(?P<jump>\s*(?:jump|jumpif\s*\((?P<expr>.+)\)))\s+(?P<name>[A-Za-z_]\w*)\s*$')
R_SCRIPT_RETURN = re.compile(r'^(?P<return>\s*return(?:\s+(?P<expr>.+))?)\s*$')
R_SCRIPT_INCLUDE = re.compile(r'^\s*include\s+(?P<delim>\')(?P<url>(?:\\\'|[^\'])*)\'\s*$')
R_SCRIPT_INCLUDE_SYSTEM = re.compile(r'^\s*include\s+(?P<delim><)(?P<url>[^>]*)>\s*$')
R_SCRIPT_IF_BEGIN = re.compile(r'^\s*if\s+(?P<expr>.+)\s*:\s*$')
R_SCRIPT_IF_ELSE_IF = re.compile(r'^\s*elif\s+(?P<expr>.+)\s*:\s*$')
R_SCRIPT_IF_ELSE = re.compile(r'^\s*else\s*:\s*$')
R_SCRIPT_IF_END = re.compile(r'^\s*endif\s*$')
R_SCRIPT_FOR_BEGIN = re.compile(
    r'^\s*for\s+(?P<value>[A-Za-z_]\w*)(?:\s*,\s*(?P<index>[A-Za-z_]\w*))?\s+in\s+(?P<values>.+)\s*:\s*$'
)
R_SCRIPT_FOR_END = re.compile(r'^\s*endfor\s*$')
R_SCRIPT_WHILE_BEGIN = re.compile(r'^\s*while\s+(?P<expr>.+)\s*:\s*$')
R_SCRIPT_WHILE_END = re.compile(r'^\s*endwhile\s*$')
R_SCRIPT_BREAK = re.compile(r'^\s*break\s*$')
R_SCRIPT_CONTINUE = re.compile(r'^\s*continue\s*$')


def parse_script(script_text, start_line_number=1):
    """
    Parse a BareScript script

    :param script_text: The `script text <https://craigahobbs.github.io/bare-script/language/>`__
    :type script_text: str or ~collections.abc.Iterable(str)
    :param start_line_number: The script's starting line number
    :type start_line_number: int, optional
    :return: The `BareScript model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='BareScript'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """

    script = {'statements': []}

    # Line-split all script text
    lines = []
    if isinstance(script_text, str):
        lines.extend(R_SCRIPT_LINE_SPLIT.split(script_text))
    else:
        for script_text_part in script_text:
            lines.extend(R_SCRIPT_LINE_SPLIT.split(script_text_part))

    # Process each line
    line_continuation = []
    function_def = None
    function_label_def_depth = None
    label_defs = []
    label_index = 0
    for ix_line_part, line_part in enumerate(lines):
        statements = function_def['function']['statements'] if function_def is not None else script['statements']

        # Comment?
        if R_SCRIPT_COMMENT.match(line_part) is not None:
            continue

        # Set the line index
        is_continued = (len(line_continuation) != 0)
        if not is_continued:
            ix_line = ix_line_part

        # Line continuation?
        line_part_no_continuation = R_SCRIPT_CONTINUATION.sub('', line_part)
        if line_part != line_part_no_continuation:
            line_continuation.append(line_part_no_continuation.strip() if is_continued else line_part_no_continuation.rstrip())
            continue
        elif is_continued:
            line_continuation.append(line_part_no_continuation.strip())

        # Join the continued script lines, if necessary
        if is_continued:
            line = ' '.join(line_continuation)
            line_continuation.clear()
        else:
            line = line_part

        # Assignment?
        match_assignment = R_SCRIPT_ASSIGNMENT.match(line)
        if match_assignment:
            try:
                expr_statement = {
                    'expr': {
                        'name': match_assignment.group('name'),
                        'expr': parse_expression(match_assignment.group('expr'))
                    }
                }
                statements.append(expr_statement)
                continue
            except BareScriptParserError as error:
                column_number = len(line) - len(match_assignment.group('expr')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line)

        # Function definition begin?
        match_function_begin = R_SCRIPT_FUNCTION_BEGIN.match(line)
        if match_function_begin:
            # Nested function definitions are not allowed
            if function_def is not None:
                raise BareScriptParserError('Nested function definition', line, 1, start_line_number + ix_line)

            # Add the function definition statement
            function_label_def_depth = len(label_defs)
            function_def = {
                'function': {
                    'name': match_function_begin.group('name'),
                    'statements': []
                }
            }
            if match_function_begin.group('args') is not None:
                function_def['function']['args'] = R_SCRIPT_FUNCTION_ARG_SPLIT.split(match_function_begin.group('args'))
            if match_function_begin.group('async') is not None:
                function_def['function']['async'] = True
            if match_function_begin.group('lastArgArray') is not None:
                function_def['function']['lastArgArray'] = True
            statements.append(function_def)
            continue

        # Function definition end?
        match_function_end = R_SCRIPT_FUNCTION_END.match(line)
        if match_function_end:
            if function_def is None:
                raise BareScriptParserError('No matching function definition', line, 1, start_line_number + ix_line)

            # Check for un-matched label definitions
            if len(label_defs) > function_label_def_depth:
                label_def = label_defs.pop()
                def_key = next(iter(label_def))
                def_ = label_def[def_key]
                raise BareScriptParserError(f"Missing end{def_key} statement", def_['line'], 1, def_['lineNumber'])

            function_def = None
            function_label_def_depth = None
            continue

        # If-then begin?
        match_if_begin = R_SCRIPT_IF_BEGIN.match(line)
        if match_if_begin:
            # Add the if-then label definition
            ifthen = {
                'jump': {
                    'label': f"__bareScriptIf{label_index}",
                    'expr': {'unary': {'op': '!', 'expr': parse_expression(match_if_begin.group('expr'))}}
                },
                'done': f"__bareScriptDone{label_index}",
                'hasElse': False,
                'line': line,
                'lineNumber': start_line_number + ix_line
            }
            label_defs.append({'if': ifthen})
            label_index += 1

            # Add the if-then header statement
            statements.append({'jump': ifthen['jump']})
            continue

        # Else-if-then?
        match_if_else_if = R_SCRIPT_IF_ELSE_IF.match(line)
        if match_if_else_if:
            # Get the if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs[len(label_defs) - 1].get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line)

            # Cannot come after the else-then statement
            if ifthen['hasElse']:
                raise BareScriptParserError('Elif statement following else statement', line, 1, start_line_number + ix_line)

            # Generate the next if-then jump statement
            prev_label = ifthen['jump']['label']
            ifthen['jump'] = {
                'label': f"__bareScriptIf{label_index}",
                'expr': {'unary': {'op': '!', 'expr': parse_expression(match_if_else_if.group('expr'))}}
            }
            label_index += 1

            # Add the if-then else statements
            statements.extend([
                {'jump': {'label': ifthen['done']}},
                {'label': prev_label},
                {'jump': ifthen['jump']}
            ])
            continue

        # Else-then?
        match_if_else = R_SCRIPT_IF_ELSE.match(line)
        if match_if_else:
            # Get the if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs[len(label_defs) - 1].get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line)

            # Cannot have multiple else-then statements
            if ifthen['hasElse']:
                raise BareScriptParserError('Multiple else statements', line, 1, start_line_number + ix_line)
            ifthen['hasElse'] = True

            # Add the if-then else statements
            statements.extend([
                {'jump': {'label': ifthen['done']}},
                {'label': ifthen['jump']['label']}
            ])
            continue

        # If-then end?
        match_if_end = R_SCRIPT_IF_END.match(line)
        if match_if_end:
            # Pop the if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs.pop().get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line)

            # Update the previous jump statement's label, if necessary
            if not ifthen['hasElse']:
                ifthen['jump']['label'] = ifthen['done']

            # Add the if-then footer statement
            statements.append({'label': ifthen['done']})
            continue

        # While-do begin?
        match_while_begin = R_SCRIPT_WHILE_BEGIN.match(line)
        if match_while_begin:
            # Add the while-do label
            whiledo = {
                'loop': f'__bareScriptLoop{label_index}',
                'continue': f'__bareScriptLoop{label_index}',
                'done': f'__bareScriptDone{label_index}',
                'expr': parse_expression(match_while_begin.group('expr')),
                'line': line,
                'lineNumber': start_line_number + ix_line
            }
            label_defs.append({'while': whiledo})
            label_index += 1

            # Add the while-do header statements
            statements.append({'jump': {'label': whiledo['done'], 'expr': {'unary': {'op': '!', 'expr': whiledo['expr']}}}})
            statements.append({'label': whiledo['loop']})
            continue

        # While-do end?
        match_while_end = R_SCRIPT_WHILE_END.match(line)
        if match_while_end:
            # Pop the while-do definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            if len(label_defs) <= label_def_depth:
                raise BareScriptParserError('No matching while statement', line, 1, start_line_number + ix_line)

            whiledo = label_defs.pop().get('while')
            if not whiledo:
                raise BareScriptParserError('No matching while statement', line, 1, start_line_number + ix_line)

            # Add the while-do footer statements
            statements.append({'jump': {'label': whiledo['loop'], 'expr': whiledo['expr']}})
            statements.append({'label': whiledo['done']})
            continue

        # For-each begin?
        match_for_begin = R_SCRIPT_FOR_BEGIN.match(line)
        if match_for_begin:
            # Add the for-each label
            foreach = {
                'loop': f'__bareScriptLoop{label_index}',
                'continue': f'__bareScriptContinue{label_index}',
                'done': f'__bareScriptDone{label_index}',
                'index': match_for_begin.group('index') or f'__bareScriptIndex{label_index}',
                'values': f'__bareScriptValues{label_index}',
                'length': f'__bareScriptLength{label_index}',
                'value': match_for_begin.group('value'),
                'line': line,
                'lineNumber': start_line_number + ix_line
            }
            label_defs.append({'for': foreach})
            label_index += 1

            # Add the for-each header statements
            statements.extend([
                {'expr': {'name': foreach['values'], 'expr': parse_expression(match_for_begin.group('values'))}},
                {'expr': {
                    'name': foreach['length'],
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': foreach['values']}]}}
                }},
                {'jump': {'label': foreach['done'], 'expr': {'unary': {'op': '!', 'expr': {'variable': foreach['length']}}}}},
                {'expr': {'name': foreach['index'], 'expr': {'number': 0}}},
                {'label': foreach['loop']},
                {'expr': {
                    'name': foreach['value'],
                    'expr': {'function': {'name': 'arrayGet', 'args': [{'variable': foreach['values']}, {'variable': foreach['index']}]}}
                }}
            ])
            continue

        # For-each end?
        match_for_end = R_SCRIPT_FOR_END.match(line)
        if match_for_end:
            # Pop the foreach definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            if len(label_defs) <= label_def_depth:
                raise BareScriptParserError('No matching for statement', line, 1, start_line_number + ix_line)

            foreach = label_defs.pop().get('for')
            if not foreach:
                raise BareScriptParserError('No matching for statement', line, 1, start_line_number + ix_line)

            # Add the for-each footer statements
            if foreach.get('hasContinue'):
                statements.append({'label': foreach['continue']})
            statements.extend([
                {'expr': {
                    'name': foreach['index'],
                    'expr': {'binary': {'op': '+', 'left': {'variable': foreach['index']}, 'right': {'number': 1}}}
                }},
                {'jump': {
                    'label': foreach['loop'],
                    'expr': {'binary': {'op': '<', 'left': {'variable': foreach['index']}, 'right': {'variable': foreach['length']}}}
                }},
                {'label': foreach['done']}
            ])
            continue

        # Break statement?
        match_break = R_SCRIPT_BREAK.match(line)
        if match_break:
            # Get the loop definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ix_label_def = next((i for i, d in reversed(list(enumerate(label_defs))) if 'if' not in d), -1)
            if ix_label_def < label_def_depth:
                raise BareScriptParserError('Break statement outside of loop', line, 1, start_line_number + ix_line)
            label_def = label_defs[ix_label_def]
            label_key = next(iter(label_def))
            loop_def = label_def[label_key]

            # Add the break jump statement
            statements.append({'jump': {'label': loop_def['done']}})
            continue

        # Continue statement?
        match_continue = R_SCRIPT_CONTINUE.match(line)
        if match_continue:
            # Get the loop definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ix_label_def = next((i for i, d in reversed(list(enumerate(label_defs))) if 'if' not in d), -1)
            if ix_label_def < label_def_depth:
                raise BareScriptParserError('Continue statement outside of loop', line, 1, start_line_number + ix_line)
            label_def = label_defs[ix_label_def]
            label_key = next(iter(label_def))
            loop_def = label_def[label_key]

            # Add the continue jump statement
            loop_def['hasContinue'] = True
            statements.append({'jump': {'label': loop_def['continue']}})
            continue

        # Label definition?
        match_label = R_SCRIPT_LABEL.match(line)
        if match_label:
            statements.append({'label': match_label.group('name')})
            continue

        # Jump definition?
        match_jump = R_SCRIPT_JUMP.match(line)
        if match_jump:
            jump_statement = {'jump': {'label': match_jump.group('name')}}
            if match_jump.group('expr'):
                try:
                    jump_statement['jump']['expr'] = parse_expression(match_jump.group('expr'))
                except BareScriptParserError as error:
                    column_number = len(match_jump.group('jump')) - len(match_jump.group('expr')) - 1 + error.column_number
                    raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line)
            statements.append(jump_statement)
            continue

        # Return definition?
        match_return = R_SCRIPT_RETURN.match(line)
        if match_return:
            return_statement = {'return': {}}
            if match_return.group('expr'):
                try:
                    return_statement['return']['expr'] = parse_expression(match_return.group('expr'))
                except BareScriptParserError as error:
                    column_number = len(match_return.group('return')) - len(match_return.group('expr')) + error.column_number
                    raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line)
            statements.append(return_statement)
            continue

        # Include definition?
        match_include = R_SCRIPT_INCLUDE.match(line) or R_SCRIPT_INCLUDE_SYSTEM.match(line)
        if match_include:
            delim = match_include.group('delim')
            url = match_include.group('url') if delim == '<' else R_EXPR_STRING_ESCAPE.sub('\\1', match_include.group('url'))
            include_statement = statements[-1] if statements else None
            if include_statement is None or 'include' not in include_statement:
                include_statement = {'include': {'includes': []}}
                statements.append(include_statement)
            include_statement['include']['includes'].append({'url': url, 'system': True} if delim == '<' else {'url': url})
            continue

        # Expression
        try:
            expr_statement = {'expr': {'expr': parse_expression(line)}}
            statements.append(expr_statement)
        except BareScriptParserError as error:
            raise BareScriptParserError(error.error, line, error.column_number, start_line_number + ix_line)

    # Dangling label definitions?
    if label_defs:
        label_def = label_defs.pop()
        def_key = next(iter(label_def))
        def_ = label_def[def_key]
        raise BareScriptParserError(f"Missing end{def_key} statement", def_['line'], 1, def_['lineNumber'])

    return script


# BareScript expression regex
R_EXPR_BINARY_OP = re.compile(r'^\s*(\*\*|\*|\/|%|\+|-|<=|<|>=|>|==|!=|&&|\|\|)')
R_EXPR_UNARY_OP = re.compile(r'^\s*(!|-)')
R_EXPR_FUNCTION_OPEN = re.compile(r'^\s*([A-Za-z_]\w+)\s*\(')
R_EXPR_FUNCTION_SEPARATOR = re.compile(r'^\s*,')
R_EXPR_FUNCTION_CLOSE = re.compile(r'^\s*\)')
R_EXPR_GROUP_OPEN = re.compile(r'^\s*\(')
R_EXPR_GROUP_CLOSE = re.compile(r'^\s*\)')
R_EXPR_NUMBER = re.compile(r'^\s*([+-]?\d+(?:\.\d*)?(?:e[+-]\d+)?)')
R_EXPR_STRING = re.compile(r"^\s*'((?:\\\\|\\'|[^'])*)'")
R_EXPR_STRING_ESCAPE = re.compile(r'\\([\\\'])')
R_EXPR_STRING_DOUBLE = re.compile(r'^\s*"((?:\\\\|\\"|[^"])*)"')
R_EXPR_STRING_DOUBLE_ESCAPE = re.compile(r'\\([\\"])')
R_EXPR_VARIABLE = re.compile(r'^\s*([A-Za-z_]\w*)')
R_EXPR_VARIABLE_EX = re.compile(r'^\s*\[\s*((?:\\\]|[^\]])+)\s*\]')
R_EXPR_VARIABLE_EX_ESCAPE = re.compile(r'\\([\\\]])')


# Binary operator re-order map
BINARY_REORDER = {
    '**': {'*', '/', '%', '+', '-', '<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '*': {'+', '-', '<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '/': {'+', '-', '<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '%': {'+', '-', '<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '+': {'<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '-': {'<=', '<', '>=', '>', '==', '!=', '&&', '||'},
    '<=': {'==', '!=', '&&', '||'},
    '<': {'==', '!=', '&&', '||'},
    '>=': {'==', '!=', '&&', '||'},
    '>': {'==', '!=', '&&', '||'},
    '==': {'&&', '||'},
    '!=': {'&&', '||'},
    '&&': {'||'},
    '||': set()
}


def parse_expression(expr_text):
    """
    Parse a BareScript expression

    :param expr_text: The `expression text <https://craigahobbs.github.io/bare-script/language/#expressions>`__
    :type expr_text: str or ~collections.abc.Iterable(str)
    :return: The `expression model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='Expression'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """
    try:
        expr, next_text = _parse_binary_expression(expr_text)
        if next_text.strip() != '':
            raise BareScriptParserError('Syntax error', next_text)
        return expr
    except BareScriptParserError as error:
        column_number = len(expr_text) - len(error.line) + 1
        raise BareScriptParserError(error.error, expr_text, column_number)


# Helper function to parse a binary operator expression chain
def _parse_binary_expression(expr_text, bin_left_expr=None):
    # Parse the binary operator's left unary expression if none was passed
    if bin_left_expr is not None:
        bin_text = expr_text
        left_expr = bin_left_expr
    else:
        left_expr, bin_text = _parse_unary_expression(expr_text)

    # Match a binary operator - if not found, return the left expression
    match_binary_op = R_EXPR_BINARY_OP.match(bin_text)
    if match_binary_op is None:
        return [left_expr, bin_text]
    bin_op = match_binary_op.group(1)
    right_text = bin_text[len(match_binary_op.group(0)):]

    # Parse the right sub-expression
    right_expr, next_text = _parse_unary_expression(right_text)

    # Create the binary expression - re-order for binary operators as necessary
    bin_expr = None
    if 'binary' in left_expr and bin_op in BINARY_REORDER and left_expr['binary']['op'] in BINARY_REORDER[bin_op]:
        # Left expression has lower precedence - find where to put this expression within the left expression
        bin_expr = left_expr
        reorder_expr = left_expr
        while 'binary' in reorder_expr['binary']['right'] and reorder_expr['binary']['right']['binary']['op'] in BINARY_REORDER[bin_op]:
            reorder_expr = reorder_expr['binary']['right']
        reorder_expr['binary']['right'] = {'binary': {'op': bin_op, 'left': reorder_expr['binary']['right'], 'right': right_expr}}
    else:
        bin_expr = {'binary': {'op': bin_op, 'left': left_expr, 'right': right_expr}}

    # Parse the next binary expression in the chain
    return _parse_binary_expression(next_text, bin_expr)


# Helper function to parse a unary expression
def _parse_unary_expression(expr_text):
    # Group open?
    match_group_open = R_EXPR_GROUP_OPEN.match(expr_text)
    if match_group_open:
        group_text = expr_text[len(match_group_open.group(0)):]
        expr, next_text = _parse_binary_expression(group_text)
        match_group_close = R_EXPR_GROUP_CLOSE.match(next_text)
        if match_group_close is None:
            raise BareScriptParserError('Unmatched parenthesis', expr_text)
        return [{'group': expr}, next_text[len(match_group_close.group(0)):]]

    # Unary operator?
    match_unary = R_EXPR_UNARY_OP.match(expr_text)
    if match_unary:
        unary_text = expr_text[len(match_unary.group(0)):]
        expr, next_text = _parse_unary_expression(unary_text)
        unary_expr = {'unary': {'op': match_unary.group(1), 'expr': expr}}
        return [unary_expr, next_text]

    # Function?
    match_function_open = R_EXPR_FUNCTION_OPEN.match(expr_text)
    if match_function_open:
        arg_text = expr_text[len(match_function_open.group(0)):]
        args = []
        while True:
            # Function close?
            match_function_close = R_EXPR_FUNCTION_CLOSE.match(arg_text)
            if match_function_close:
                arg_text = arg_text[len(match_function_close.group(0)):]
                break

            # Function argument separator
            if args:
                match_function_separator = R_EXPR_FUNCTION_SEPARATOR.match(arg_text)
                if match_function_separator is None:
                    raise BareScriptParserError('Syntax error', arg_text)
                arg_text = arg_text[len(match_function_separator.group(0)):]

            # Get the argument
            arg_expr, next_arg_text = _parse_binary_expression(arg_text)
            args.append(arg_expr)
            arg_text = next_arg_text

        fn_expr = {'function': {'name': match_function_open.group(1), 'args': args}}
        return [fn_expr, arg_text]

    # Number?
    match_number = R_EXPR_NUMBER.match(expr_text)
    if match_number:
        number = float(match_number.group(1))
        expr = {'number': number}
        return [expr, expr_text[len(match_number.group(0)):]]

    # String?
    match_string = R_EXPR_STRING.match(expr_text)
    if match_string:
        string = R_EXPR_STRING_ESCAPE.sub('\\1', match_string.group(1))
        expr = {'string': string}
        return [expr, expr_text[len(match_string.group(0)):]]

    # String (double quotes)?
    match_string_double = R_EXPR_STRING_DOUBLE.match(expr_text)
    if match_string_double:
        string = R_EXPR_STRING_DOUBLE_ESCAPE.sub('\\1', match_string_double.group(1))
        expr = {'string': string}
        return [expr, expr_text[len(match_string_double.group(0)):]]

    # Variable?
    match_variable = R_EXPR_VARIABLE.match(expr_text)
    if match_variable:
        expr = {'variable': match_variable.group(1)}
        return [expr, expr_text[len(match_variable.group(0)):]]

    # Variable (brackets)?
    match_variable_ex = R_EXPR_VARIABLE_EX.match(expr_text)
    if match_variable_ex:
        variable_name = R_EXPR_VARIABLE_EX_ESCAPE.sub('\\1', match_variable_ex.group(1))
        expr = {'variable': variable_name}
        return [expr, expr_text[len(match_variable_ex.group(0)):]]

    raise BareScriptParserError('Syntax error', expr_text)


class BareScriptParserError(Exception):
    """
    A BareScript parser exception

    .. attribute:: error
       :type: str

       The error description

    .. attribute:: line
       :type: str

       The line text

    .. attribute:: column_number
       :type: int

       The error column number

    .. attribute:: line_number
       :type: int or None

       The error line number

    :param error: The error description
    :type error: str
    :param line: The line text
    :type line: str
    :param column_number: The error column number
    :type column_number: int, optional
    :param line_number: The error line number
    :type line_number: int or None, optional
    :param prefix: The error message prefix line
    :type prefix: str or None, optional
    """

    def __init__(self, error, line, column_number=1, line_number=None, prefix=None):
        # Parser error constants
        line_length_max = 120
        line_suffix = ' ...'
        line_prefix = '... '

        # Trim the error line, if necessary
        line_error = line
        line_column = column_number
        if len(line) > line_length_max:
            line_left = column_number - 1 - line_length_max // 2
            line_right = line_left + line_length_max
            if line_left < 0:
                line_error = line[:line_length_max] + line_suffix
            elif line_right > len(line):
                line_error = line_prefix + line[-line_length_max:]
                line_column -= line_left - len(line_prefix) - (line_right - len(line))
            else:
                line_error = line_prefix + line[int(line_left):int(line_right)] + line_suffix
                line_column -= line_left - len(line_prefix)

        # Format the message
        newline = '\n'
        message = f'''\
{(prefix + newline) if prefix is not None else ''}{error}{(', line number ' + str(line_number)) if line_number is not None else ''}:
{line_error}
{' ' * (line_column - 1)}^
'''
        super().__init__(message)
        self.error = error
        self.line = line
        self.column_number = column_number
        self.line_number = line_number
