# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript language parser
"""

import re


def parse_script(script_text, start_line_number=1, script_name=None):
    """
    Parse a BareScript script

    :param script_text: The `script text <https://craigahobbs.github.io/bare-script-py/language/>`__
    :type script_text: str or ~collections.abc.Iterable(str)
    :param start_line_number: The script's starting line number
    :type start_line_number: int, optional
    :param script_name: The script name
    :type script_name: str or None, optional
    :return: The `BareScript model <./model/#var.vName='BareScript'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """

    lines = []
    script = {'statements': [], 'scriptLines': lines}
    if script_name is not None:
        script['scriptName'] = script_name

    # Line-split all script text
    if isinstance(script_text, str):
        lines.extend(_R_SCRIPT_LINE_SPLIT.split(script_text))
    else:
        for script_text_part in script_text:
            lines.extend(_R_SCRIPT_LINE_SPLIT.split(script_text_part))

    # Process each line
    line_continuation = []
    function_def = None
    function_label_def_depth = None
    label_defs = []
    label_index = 0
    for ix_line_part, line_part in enumerate(lines):
        statements = function_def['function']['statements'] if function_def is not None else script['statements']

        # Comment?
        if _R_SCRIPT_COMMENT.match(line_part) is not None:
            continue

        # Set the line index
        is_continued = (len(line_continuation) != 0)
        if not is_continued:
            ix_line = ix_line_part

        # Line continuation?
        line_part_no_continuation = _R_SCRIPT_CONTINUATION.sub('', line_part)
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

        # Base statement members
        line_number = ix_line + 1
        statement_base = {'lineNumber': line_number}
        if ix_line != ix_line_part:
            statement_base['lineCount'] = (ix_line_part - ix_line) + 1

        # Assignment?
        match_assignment = _R_SCRIPT_ASSIGNMENT.match(line)
        if match_assignment:
            # Parse the expression
            try:
                assignment_expr = parse_expression(match_assignment.group('expr'), line_number, script_name, True)
            except BareScriptParserError as error:
                column_number = len(line) - len(match_assignment.group('expr')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)

            # Add the expression statement
            expr_statement = {
                'expr': {
                    'name': match_assignment.group('name'),
                    'expr': assignment_expr,
                    **statement_base
                }
            }
            statements.append(expr_statement)
            continue

        # Function definition begin?
        match_function_begin = _R_SCRIPT_FUNCTION_BEGIN.match(line)
        if match_function_begin:
            # Nested function definitions are not allowed
            if function_def is not None:
                raise BareScriptParserError('Nested function definition', line, 1, start_line_number + ix_line, script_name)

            # Add the function definition statement
            function_label_def_depth = len(label_defs)
            function_def = {
                'function': {
                    'name': match_function_begin.group('name'),
                    'statements': [],
                    **statement_base
                }
            }
            if match_function_begin.group('args') is not None:
                function_def['function']['args'] = _R_SCRIPT_FUNCTION_ARG_SPLIT.split(match_function_begin.group('args'))
            if match_function_begin.group('async') is not None:
                function_def['function']['async'] = True
            if match_function_begin.group('lastArgArray') is not None:
                function_def['function']['lastArgArray'] = True
            statements.append(function_def)
            continue

        # Function definition end?
        match_function_end = _R_SCRIPT_FUNCTION_END.match(line)
        if match_function_end:
            if function_def is None:
                raise BareScriptParserError('No matching function definition', line, 1, start_line_number + ix_line, script_name)

            # Check for un-matched label definitions
            if len(label_defs) > function_label_def_depth:
                label_def = label_defs.pop()
                def_key = next(iter(label_def))
                def_ = label_def[def_key]
                raise BareScriptParserError(f"Missing end{def_key} statement", def_['line'], 1, def_['lineNumber'], script_name)

            function_def = None
            function_label_def_depth = None
            continue

        # If-then begin?
        match_if_begin = _R_SCRIPT_IF_BEGIN.match(line)
        if match_if_begin:
            # Parse the if-then expression
            try:
                ifthen_expr = parse_expression(match_if_begin.group('expr'), line_number, script_name, True)
            except BareScriptParserError as error:
                column_number = len(match_if_begin.group('if')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)

            # Add the if-then label definition
            ifthen = {
                'jump': {
                    'label': f"__bareScriptIf{label_index}",
                    'expr': {'unary': {'op': '!', 'expr': ifthen_expr}},
                    **statement_base
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
        match_if_else_if = _R_SCRIPT_IF_ELSE_IF.match(line)
        if match_if_else_if:
            # Get the else-if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs[len(label_defs) - 1].get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line, script_name)

            # Cannot come after the else-then statement
            if ifthen['hasElse']:
                raise BareScriptParserError('Elif statement following else statement', line, 1, start_line_number + ix_line, script_name)

            # Parse teh else-if-then expression
            try:
                if_else_if_expr = parse_expression(match_if_else_if.group('expr'), line_number, script_name, True)
            except BareScriptParserError as error:
                column_number = len(match_if_else_if.group('elif')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)

            # Generate the next if-then jump statement
            prev_label = ifthen['jump']['label']
            ifthen['jump'] = {
                'label': f"__bareScriptIf{label_index}",
                'expr': {'unary': {'op': '!', 'expr': if_else_if_expr}},
                **statement_base
            }
            label_index += 1

            # Add the if-then else statements
            statements.extend([
                {'jump': {'label': ifthen['done'], **statement_base}},
                {'label': {'name': prev_label, **statement_base}},
                {'jump': ifthen['jump']}
            ])
            continue

        # Else-then?
        match_if_else = _R_SCRIPT_IF_ELSE.match(line)
        if match_if_else:
            # Get the if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs[len(label_defs) - 1].get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line, script_name)

            # Cannot have multiple else-then statements
            if ifthen['hasElse']:
                raise BareScriptParserError('Multiple else statements', line, 1, start_line_number + ix_line, script_name)
            ifthen['hasElse'] = True

            # Add the if-then else statements
            statements.extend([
                {'jump': {'label': ifthen['done'], **statement_base}},
                {'label': {'name': ifthen['jump']['label'], **statement_base}}
            ])
            continue

        # If-then end?
        match_if_end = _R_SCRIPT_IF_END.match(line)
        if match_if_end:
            # Pop the if-then definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ifthen = label_defs.pop().get('if') if len(label_defs) > label_def_depth else None
            if ifthen is None:
                raise BareScriptParserError('No matching if statement', line, 1, start_line_number + ix_line, script_name)

            # Update the previous jump statement's label, if necessary
            if not ifthen['hasElse']:
                ifthen['jump']['label'] = ifthen['done']

            # Add the if-then footer statement
            statements.append({'label': {'name': ifthen['done'], **statement_base}})
            continue

        # While-do begin?
        match_while_begin = _R_SCRIPT_WHILE_BEGIN.match(line)
        if match_while_begin:
            # Parse the while-do expression
            try:
                while_begin_expr = parse_expression(match_while_begin.group('expr'), line_number, script_name, True)
            except BareScriptParserError as error:
                column_number = len(match_while_begin.group('while')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)

            # Add the while-do label
            whiledo = {
                'loop': f'__bareScriptLoop{label_index}',
                'continue': f'__bareScriptLoop{label_index}',
                'done': f'__bareScriptDone{label_index}',
                'expr': while_begin_expr,
                'line': line,
                'lineNumber': start_line_number + ix_line
            }
            label_defs.append({'while': whiledo})
            label_index += 1

            # Add the while-do header statements
            statements.extend([
                {'jump': {'label': whiledo['done'], 'expr': {'unary': {'op': '!', 'expr': whiledo['expr']}}, **statement_base}},
                {'label': {'name': whiledo['loop'], **statement_base}}
            ])
            continue

        # While-do end?
        match_while_end = _R_SCRIPT_WHILE_END.match(line)
        if match_while_end:
            # Pop the while-do definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            if len(label_defs) <= label_def_depth:
                raise BareScriptParserError('No matching while statement', line, 1, start_line_number + ix_line, script_name)

            whiledo = label_defs.pop().get('while')
            if not whiledo:
                raise BareScriptParserError('No matching while statement', line, 1, start_line_number + ix_line, script_name)

            # Add the while-do footer statements
            statements.extend([
                {'jump': {'label': whiledo['loop'], 'expr': whiledo['expr'], **statement_base}},
                {'label': {'name': whiledo['done'], **statement_base}}
            ])
            continue

        # For-each begin?
        match_for_begin = _R_SCRIPT_FOR_BEGIN.match(line)
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

            # Parse the for-each expression
            try:
                for_begin_expr = parse_expression(match_for_begin.group('values'), line_number, script_name, True)
            except BareScriptParserError as error:
                column_number = len(match_for_begin.group('for')) + error.column_number
                raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)

            # Add the for-each header statements
            statements.extend([
                {'expr': {
                    'name': foreach['values'],
                    'expr': for_begin_expr,
                    **statement_base
                }},
                {'expr': {
                    'name': foreach['length'],
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': foreach['values']}]}},
                    **statement_base
                }},
                {'jump': {
                    'label': foreach['done'],
                    'expr': {'unary': {'op': '!', 'expr': {'variable': foreach['length']}}},
                    **statement_base
                }},
                {'expr': {'name': foreach['index'], 'expr': {'number': 0}, **statement_base}},
                {'label': {'name': foreach['loop'], **statement_base}},
                {'expr': {
                    'name': foreach['value'],
                    'expr': {'function': {'name': 'arrayGet', 'args': [{'variable': foreach['values']}, {'variable': foreach['index']}]}},
                    **statement_base
                }}
            ])
            continue

        # For-each end?
        match_for_end = _R_SCRIPT_FOR_END.match(line)
        if match_for_end:
            # Pop the foreach definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            if len(label_defs) <= label_def_depth:
                raise BareScriptParserError('No matching for statement', line, 1, start_line_number + ix_line, script_name)

            foreach = label_defs.pop().get('for')
            if not foreach:
                raise BareScriptParserError('No matching for statement', line, 1, start_line_number + ix_line, script_name)

            # Add the for-each footer statements
            if foreach.get('hasContinue'):
                statements.append({'label': {'name': foreach['continue'], **statement_base}})
            statements.extend([
                {'expr': {
                    'name': foreach['index'],
                    'expr': {'binary': {'op': '+', 'left': {'variable': foreach['index']}, 'right': {'number': 1}}},
                    **statement_base
                }},
                {'jump': {
                    'label': foreach['loop'],
                    'expr': {'binary': {'op': '<', 'left': {'variable': foreach['index']}, 'right': {'variable': foreach['length']}}},
                    **statement_base
                }},
                {'label': {'name': foreach['done'], **statement_base}}
            ])
            continue

        # Break statement?
        match_break = _R_SCRIPT_BREAK.match(line)
        if match_break:
            # Get the loop definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ix_label_def = next((i for i, d in reversed(list(enumerate(label_defs))) if 'if' not in d), -1)
            if ix_label_def < label_def_depth:
                raise BareScriptParserError('Break statement outside of loop', line, 1, start_line_number + ix_line, script_name)
            label_def = label_defs[ix_label_def]
            label_key = next(iter(label_def))
            loop_def = label_def[label_key]

            # Add the break jump statement
            statements.append({'jump': {'label': loop_def['done'], **statement_base}})
            continue

        # Continue statement?
        match_continue = _R_SCRIPT_CONTINUE.match(line)
        if match_continue:
            # Get the loop definition
            label_def_depth = function_label_def_depth if function_def is not None else 0
            ix_label_def = next((i for i, d in reversed(list(enumerate(label_defs))) if 'if' not in d), -1)
            if ix_label_def < label_def_depth:
                raise BareScriptParserError('Continue statement outside of loop', line, 1, start_line_number + ix_line, script_name)
            label_def = label_defs[ix_label_def]
            label_key = next(iter(label_def))
            loop_def = label_def[label_key]

            # Add the continue jump statement
            loop_def['hasContinue'] = True
            statements.append({'jump': {'label': loop_def['continue'], **statement_base}})
            continue

        # Label definition?
        match_label = _R_SCRIPT_LABEL.match(line)
        if match_label:
            statements.append({'label': {'name': match_label.group('name'), **statement_base}})
            continue

        # Jump definition?
        match_jump = _R_SCRIPT_JUMP.match(line)
        if match_jump:
            jump_statement = {'jump': {'label': match_jump.group('name'), **statement_base}}
            if match_jump.group('expr'):
                try:
                    jump_statement['jump']['expr'] = parse_expression(match_jump.group('expr'), line_number, script_name, True)
                except BareScriptParserError as error:
                    column_number = len(match_jump.group('jump')) - len(match_jump.group('expr')) - 1 + error.column_number
                    raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)
            statements.append(jump_statement)
            continue

        # Return definition?
        match_return = _R_SCRIPT_RETURN.match(line)
        if match_return:
            return_statement = {'return': {**statement_base}}
            if match_return.group('expr'):
                try:
                    return_statement['return']['expr'] = parse_expression(match_return.group('expr'), line_number, script_name, True)
                except BareScriptParserError as error:
                    column_number = len(match_return.group('return')) - len(match_return.group('expr')) + error.column_number
                    raise BareScriptParserError(error.error, line, column_number, start_line_number + ix_line, script_name)
            statements.append(return_statement)
            continue

        # Include definition?
        match_include = _R_SCRIPT_INCLUDE.match(line) or _R_SCRIPT_INCLUDE_SYSTEM.match(line)
        if match_include:
            delim = match_include.group('delim')
            url = match_include.group('url') if delim == '<' else \
                _R_EXPR_STRING_ESCAPES.sub(_replace_string_escape, match_include.group('url'))
            include_statement = statements[-1] if statements else None
            if include_statement is None or 'include' not in include_statement:
                include_statement = {'include': {'includes': [], **statement_base}}
                statements.append(include_statement)
            else:
                include_statement['include']['lineCount'] = (ix_line_part - include_statement['include']['lineNumber']) + 2
            include_statement['include']['includes'].append({'url': url, 'system': True} if delim == '<' else {'url': url})
            continue

        # Expression
        try:
            expr_statement = {'expr': {'expr': parse_expression(line, line_number, script_name, True), **statement_base}}
            statements.append(expr_statement)
        except BareScriptParserError as error:
            raise BareScriptParserError(error.error, line, error.column_number, start_line_number + ix_line, script_name)

    # Dangling label definitions?
    if label_defs:
        label_def = label_defs.pop()
        def_key = next(iter(label_def))
        def_ = label_def[def_key]
        raise BareScriptParserError(f"Missing end{def_key} statement", def_['line'], 1, def_['lineNumber'], script_name)

    return script


# BareScript regex
_R_SCRIPT_LINE_SPLIT = re.compile(r'\r?\n')
_R_SCRIPT_CONTINUATION = re.compile(r'\\\s*$')
_R_SCRIPT_COMMENT = re.compile(r'^\s*(?:#.*)?$')
_R_SCRIPT_ASSIGNMENT = re.compile(r'^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<expr>.+)$')
_R_PART_COMMENT = r'\s*(#.*)?$'
_R_SCRIPT_FUNCTION_BEGIN = re.compile(
    r'^(?P<async>\s*async)?\s*function\s+(?P<name>[A-Za-z_]\w*)\s*\('
    r'\s*(?P<args>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)?(?P<lastArgArray>\s*\.\.\.)?\s*\)\s*:' + _R_PART_COMMENT
)
_R_SCRIPT_FUNCTION_ARG_SPLIT = re.compile(r'\s*,\s*')
_R_SCRIPT_FUNCTION_END = re.compile(r'^\s*endfunction' + _R_PART_COMMENT)
_R_SCRIPT_LABEL = re.compile(r'^\s*(?P<name>[A-Za-z_]\w*)\s*:' + _R_PART_COMMENT)
_R_SCRIPT_JUMP = re.compile(r'^(?P<jump>\s*(?:jump|jumpif\s*\((?P<expr>.+)\)))\s+(?P<name>[A-Za-z_]\w*)' + _R_PART_COMMENT)
_R_SCRIPT_RETURN = re.compile(r'^(?P<return>\s*return(?:\s+(?P<expr>[^#\s].*))?)' + _R_PART_COMMENT)
_R_SCRIPT_INCLUDE = re.compile(r"^\s*include\s+(?P<delim>')(?P<url>(?:\\'|[^'])*)'" + _R_PART_COMMENT)
_R_SCRIPT_INCLUDE_SYSTEM = re.compile(r'^\s*include\s+(?P<delim><)(?P<url>[^>]*)>' + _R_PART_COMMENT)
_R_SCRIPT_IF_BEGIN = re.compile(r'^(?P<if>\s*if\s+)(?P<expr>.+)\s*:' + _R_PART_COMMENT)
_R_SCRIPT_IF_ELSE_IF = re.compile(r'^(?P<elif>\s*elif\s+)(?P<expr>.+)\s*:' + _R_PART_COMMENT)
_R_SCRIPT_IF_ELSE = re.compile(r'^\s*else\s*:' + _R_PART_COMMENT)
_R_SCRIPT_IF_END = re.compile(r'^\s*endif' + _R_PART_COMMENT)
_R_SCRIPT_FOR_BEGIN = re.compile(
    r'^(?P<for>\s*for\s+(?P<value>[A-Za-z_]\w*)(?:\s*,\s*(?P<index>[A-Za-z_]\w*))?\s+in\s+)(?P<values>.+)\s*:' + _R_PART_COMMENT
)
_R_SCRIPT_FOR_END = re.compile(r'^\s*endfor' + _R_PART_COMMENT)
_R_SCRIPT_WHILE_BEGIN = re.compile(r'^(?P<while>\s*while\s+)(?P<expr>.+)\s*:' + _R_PART_COMMENT)
_R_SCRIPT_WHILE_END = re.compile(r'^\s*endwhile' + _R_PART_COMMENT)
_R_SCRIPT_BREAK = re.compile(r'^\s*break' + _R_PART_COMMENT)
_R_SCRIPT_CONTINUE = re.compile(r'^\s*continue' + _R_PART_COMMENT)


def parse_expression(expr_text, line_number=None, script_name=None, array_literals=False):
    """
    Parse a BareScript expression

    :param expr_text: The `expression text <https://craigahobbs.github.io/bare-script-py/language/#expressions>`__
    :type expr_text: str or ~collections.abc.Iterable(str)
    :param line_number: The script line number
    :type line_number: int or None, optional
    :param script_name: The script name
    :type script_name: str or None, optional
    :param array_literals: If True, allow parsing of array literals
    :type array_literals: bool, optional
    :return: The `expression model <./model/#var.vName='Expression'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """
    try:
        expr, next_text = _parse_binary_expression(expr_text, None, array_literals)
        if next_text.strip() != '':
            raise BareScriptParserError('Syntax error', next_text, 1, line_number, script_name)
        return expr
    except BareScriptParserError as error:
        column_number = len(expr_text) - len(error.line) + 1
        raise BareScriptParserError(error.error, expr_text, column_number, line_number, script_name)


# Helper function to parse a binary operator expression chain
def _parse_binary_expression(expr_text, bin_left_expr, array_literals):
    # Parse the binary operator's left unary expression if none was passed
    if bin_left_expr is not None:
        bin_text = expr_text
        left_expr = bin_left_expr
    else:
        left_expr, bin_text = _parse_unary_expression(expr_text, array_literals)

    # Match a binary operator - if not found, return the left expression
    match_binary_op = _R_EXPR_BINARY_OP.match(bin_text)
    if match_binary_op is None:
        # End-of-line comment?
        if _R_EXPR_COMMENT.match(bin_text):
            bin_text = ''

        return [left_expr, bin_text]
    bin_op = match_binary_op.group(1)
    right_text = bin_text[len(match_binary_op.group(0)):]

    # Parse the right sub-expression
    right_expr, next_text = _parse_unary_expression(right_text, array_literals)

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
    return _parse_binary_expression(next_text, bin_expr, array_literals)


# Binary operator re-order map
BINARY_REORDER = {
    '**': {'*', '/', '%', '+', '-', '<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '*': {'+', '-', '<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '/': {'+', '-', '<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '%': {'+', '-', '<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '+': {'<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '-': {'<<', '>>', '<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '<<': {'<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '>>': {'<=', '<', '>=', '>', '==', '!=', '&', '^', '|', '&&', '||'},
    '<=': {'==', '!=', '&', '^', '|', '&&', '||'},
    '<': {'==', '!=', '&', '^', '|', '&&', '||'},
    '>=': {'==', '!=', '&', '^', '|', '&&', '||'},
    '>': {'==', '!=', '&', '^', '|', '&&', '||'},
    '==': {'&', '^', '|', '&&', '||'},
    '!=': {'&', '^', '|', '&&', '||'},
    '&': {'^', '|', '&&', '||'},
    '^': {'|', '&&', '||'},
    '|': {'&&', '||'},
    '&&': {'||'},
    '||': set()
}


# Helper function to parse a unary expression
def _parse_unary_expression(expr_text, array_literals):
    # Group open?
    match_group_open = _R_EXPR_GROUP_OPEN.match(expr_text)
    if match_group_open:
        group_text = expr_text[len(match_group_open.group(0)):]
        expr, next_text = _parse_binary_expression(group_text, None, array_literals)
        match_group_close = _R_EXPR_GROUP_CLOSE.match(next_text)
        if match_group_close is None:
            raise BareScriptParserError('Unmatched parenthesis', expr_text, 1, None, None)
        return [{'group': expr}, next_text[len(match_group_close.group(0)):]]

    # Number?
    match_number = _R_EXPR_NUMBER.match(expr_text)
    if match_number:
        number_str = match_number.group(1)
        number = float(int(number_str, base=16)) if number_str.startswith('0x') else float(number_str)
        expr = {'number': number}
        return [expr, expr_text[len(match_number.group(0)):]]

    # String?
    match_string = _R_EXPR_STRING.match(expr_text)
    if match_string:
        string = _R_EXPR_STRING_ESCAPES.sub(_replace_string_escape, match_string.group(1))
        expr = {'string': string}
        return [expr, expr_text[len(match_string.group(0)):]]

    # String (double quotes)?
    match_string_double = _R_EXPR_STRING_DOUBLE.match(expr_text)
    if match_string_double:
        string = _R_EXPR_STRING_ESCAPES.sub(_replace_string_escape, match_string_double.group(1))
        expr = {'string': string}
        return [expr, expr_text[len(match_string_double.group(0)):]]

    # Unary operator?
    match_unary = _R_EXPR_UNARY_OP.match(expr_text)
    if match_unary:
        unary_text = expr_text[len(match_unary.group(0)):]
        expr, next_text = _parse_unary_expression(unary_text, array_literals)
        unary_expr = {'unary': {'op': match_unary.group(1), 'expr': expr}}
        return [unary_expr, next_text]

    # Function?
    match_function_open = _R_EXPR_FUNCTION_OPEN.match(expr_text)
    if match_function_open:
        arg_text = expr_text[len(match_function_open.group(0)):]
        args = []
        while True:
            # Function close?
            match_function_close = _R_EXPR_FUNCTION_CLOSE.match(arg_text)
            if match_function_close:
                arg_text = arg_text[len(match_function_close.group(0)):]
                break

            # Function argument separator
            if args:
                match_function_separator = _R_EXPR_FUNCTION_SEPARATOR.match(arg_text)
                if match_function_separator is None:
                    raise BareScriptParserError('Syntax error', arg_text, 1, None, None)
                arg_text = arg_text[len(match_function_separator.group(0)):]

            # Get the argument
            arg_expr, next_arg_text = _parse_binary_expression(arg_text, None, array_literals)
            args.append(arg_expr)
            arg_text = next_arg_text

        fn_expr = {'function': {'name': match_function_open.group(1), 'args': args}}
        return [fn_expr, arg_text]

    # Object creation?
    match_object_open = _R_EXPR_OBJECT_OPEN.match(expr_text)
    if match_object_open:
        arg_text = expr_text[len(match_object_open.group(0)):]
        args = []
        while True:
            # Object close?
            match_object_close = _R_EXPR_OBJECT_CLOSE.match(arg_text)
            if match_object_close:
                arg_text = arg_text[len(match_object_close.group(0)):]
                break

            # Key/value pair separator
            if args:
                match_object_separator = _R_EXPR_OBJECT_SEPARATOR.match(arg_text)
                if match_object_separator is None:
                    raise BareScriptParserError('Syntax error', arg_text, 1, None, None)
                arg_text = arg_text[len(match_object_separator.group(0)):]

            # Get the key
            arg_key, arg_text = _parse_binary_expression(arg_text, None, array_literals)
            args.append(arg_key)

            # Key/value separator
            match_object_separator_key = _R_EXPR_OBJECT_SEPARATOR_KEY.match(arg_text)
            if match_object_separator_key is None:
                raise BareScriptParserError('Syntax error', arg_text, 1, None, None)
            arg_text = arg_text[len(match_object_separator_key.group(0)):]

            # Get the value
            arg_value, arg_text = _parse_binary_expression(arg_text, None, array_literals)
            args.append(arg_value)

        fn_expr = {'function': {'name': 'objectNew', 'args': args}}
        return [fn_expr, arg_text]

    # Array creation?
    if array_literals:
        match_array_open = _R_EXPR_ARRAY_OPEN.match(expr_text)
        if match_array_open:
            arg_text = expr_text[len(match_array_open.group(0)):]
            args = []
            while True:
                # Array close?
                match_array_close = _R_EXPR_ARRAY_CLOSE.match(arg_text)
                if match_array_close:
                    arg_text = arg_text[len(match_array_close.group(0)):]
                    break

                # Array key separator
                if args:
                    match_array_separator = _R_EXPR_ARRAY_SEPARATOR.match(arg_text)
                    if match_array_separator is None:
                        raise BareScriptParserError('Syntax error', arg_text, 1, None, None)
                    arg_text = arg_text[len(match_array_separator.group(0)):]

                # Get the value
                arg_value, arg_text = _parse_binary_expression(arg_text, None, array_literals)
                args.append(arg_value)

            fn_expr = {'function': {'name': 'arrayNew', 'args': args}}
            return [fn_expr, arg_text]

    # Variable?
    match_variable = _R_EXPR_VARIABLE.match(expr_text)
    if match_variable:
        expr = {'variable': match_variable.group(1)}
        return [expr, expr_text[len(match_variable.group(0)):]]

    # Variable (brackets)?
    if not array_literals:
        match_variable_ex = _R_EXPR_VARIABLE_EX.match(expr_text)
        if match_variable_ex:
            variable_name = _R_EXPR_VARIABLE_EX_ESCAPE.sub('\\1', match_variable_ex.group(1))
            expr = {'variable': variable_name}
            return [expr, expr_text[len(match_variable_ex.group(0)):]]

    raise BareScriptParserError('Syntax error', expr_text, 1, None, None)


# BareScript expression regex
_R_EXPR_COMMENT = re.compile(r'^\s*#.*$')
_R_EXPR_BINARY_OP = re.compile(r'^\s*(\*\*|\*|\/|%|\+|-|<<|>>|<=|<|>=|>|==|!=|&&|\|\||&|\^|\|)')
_R_EXPR_UNARY_OP = re.compile(r'^\s*(!|-|~)')
_R_EXPR_FUNCTION_OPEN = re.compile(r'^\s*([A-Za-z_]\w+)\s*\(')
_R_EXPR_FUNCTION_SEPARATOR = re.compile(r'^\s*,')
_R_EXPR_FUNCTION_CLOSE = re.compile(r'^\s*\)')
_R_EXPR_GROUP_OPEN = re.compile(r'^\s*\(')
_R_EXPR_GROUP_CLOSE = re.compile(r'^\s*\)')
_R_EXPR_NUMBER = re.compile(r'^\s*(0x[A-Fa-f0-9]+|[+-]?\d+(?:\.\d*)?(?:e[+-]?\d+)?)')
_R_EXPR_ARRAY_OPEN = re.compile(r'^\s*\[')
_R_EXPR_ARRAY_SEPARATOR = re.compile(r'^\s*,')
_R_EXPR_ARRAY_CLOSE = re.compile(r'^\s*\]')
_R_EXPR_OBJECT_OPEN = re.compile(r'^\s*\{')
_R_EXPR_OBJECT_SEPARATOR_KEY = re.compile(r'^\s*:')
_R_EXPR_OBJECT_SEPARATOR = re.compile(r'^\s*,')
_R_EXPR_OBJECT_CLOSE = re.compile(r'^\s*\}')
_R_EXPR_STRING = re.compile(r"^\s*'((?:\\\\|\\'|[^'])*)'")
_R_EXPR_STRING_DOUBLE = re.compile(r'^\s*"((?:\\\\|\\"|[^"])*)"')
_R_EXPR_VARIABLE = re.compile(r'^\s*([A-Za-z_]\w*)')
_R_EXPR_VARIABLE_EX = re.compile(r'^\s*\[\s*((?:\\\]|[^\]])+)\s*\]')
_R_EXPR_VARIABLE_EX_ESCAPE = re.compile(r'\\([\\\]])')


# String literal escapes
_R_EXPR_STRING_ESCAPES = re.compile(r'\\([nrtbf\'"\\]|u[0-9a-fA-F]{4})')

def _replace_string_escape(match):
    esc = match.group(1)
    if esc.startswith('u'):
        return chr(int(esc[1:], 16))
    return _EXPR_STRING_ESCAPES[esc]

_EXPR_STRING_ESCAPES = {
    'n': '\n',
    'r': '\r',
    't': '\t',
    'b': '\b',
    'f': '\f',
    "'": "'",
    '"': '"',
    '\\': '\\'
}


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

    .. attribute:: script_name
       :type: str or None

       The script name

    :param error: The error description
    :type error: str
    :param line: The line text
    :type line: str
    :param column_number: The error column number
    :type column_number: int
    :param line_number: The error line number
    :type line_number: int or None
    :param script_name: The script name
    :type script_name: str or None
    """

    def __init__(self, error, line, column_number, line_number, script_name):
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
        error_prefix = f'{script_name or ""}:{line_number}: ' if line_number else ''
        message = f'''\
{error_prefix}{error}
{line_error}
{' ' * (line_column - 1)}^
'''
        super().__init__(message)
        self.error = error
        self.line = line
        self.column_number = column_number
        self.line_number = line_number
        self.script_name = script_name
