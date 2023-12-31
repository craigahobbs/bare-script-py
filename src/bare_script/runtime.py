# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript runtime
"""

from functools import partial
import re

from .library import DEFAULT_MAX_STATEMENTS, EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS, default_args
from .model import lint_script
from .parser import BareScriptParserError, parse_script
from .values import value_boolean, value_compare, value_string


def execute_script(script, options=None):
    """
    Execute a BareScript model

    :param script: The `BareScript model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='BareScript'>`__
    :type script: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict or None, optional
    :returns: The script result
    :raises BareScriptRuntimeError: A script runtime error occurred
    """

    if options is None:
        options = {}

    # Create the global variable object, if necessary
    globals_ = options.get('globals')
    if globals_ is None:
        globals_ = {}
        options['globals'] = globals_

    # Set the script function globals variables
    for script_func_name, script_func in SCRIPT_FUNCTIONS.items():
        if script_func_name not in globals_:
            globals_[script_func_name] = script_func

    # Execute the script
    options['statementCount'] = 0
    return _execute_script_helper(script['statements'], options, None)


def _execute_script_helper(statements, options, locals_):
    globals_ = options['globals']

    # Iterate each script statement
    label_indexes = None
    statements_length = len(statements)
    ix_statement = 0
    while ix_statement < statements_length:
        statement = statements[ix_statement]
        statement_key = next(iter(statement.keys()))

        # Increment the statement counter
        max_statements = options.get('maxStatements', DEFAULT_MAX_STATEMENTS)
        if max_statements > 0:
            options['statementCount'] = options.get('statementCount', 0) + 1
            if options['statementCount'] > max_statements:
                raise BareScriptRuntimeError(f'Exceeded maximum script statements ({max_statements})')

        # Expression?
        if statement_key == 'expr':
            expr_value = evaluate_expression(statement['expr']['expr'], options, locals_, False)
            expr_name = statement['expr'].get('name')
            if expr_name is not None:
                if locals_ is not None:
                    locals_[expr_name] = expr_value
                else:
                    globals_[expr_name] = expr_value

        # Jump?
        elif statement_key == 'jump':
            # Evaluate the expression (if any)
            if 'expr' not in statement['jump'] or value_boolean(evaluate_expression(statement['jump']['expr'], options, locals_, False)):
                # Find the label
                if label_indexes is not None and statement['jump']['label'] in label_indexes:
                    ix_statement = label_indexes[statement['jump']['label']]
                else:
                    ix_label = next(
                        (ix_stmt for ix_stmt, stmt in enumerate(statements) if stmt.get('label') == statement['jump']['label']),
                        -1
                    )
                    if ix_label == -1:
                        raise BareScriptRuntimeError(f"Unknown jump label \"{statement['jump']['label']}\"")
                    if label_indexes is None:
                        label_indexes = {}
                    label_indexes[statement['jump']['label']] = ix_label
                    ix_statement = ix_label

        # Return?
        elif statement_key == 'return':
            if 'expr' in statement['return']:
                return evaluate_expression(statement['return']['expr'], options, locals_, False)
            return None

        # Function?
        elif statement_key == 'function':
            globals_[statement['function']['name']] = partial(_script_function, statement['function'])

        # Include?
        elif statement_key == 'include':
            system_prefix = options.get('systemPrefix')
            fetch_fn = options.get('fetchFn')
            log_fn = options.get('logFn')
            url_fn = options.get('urlFn')
            for include in statement['include']['includes']:
                url = include['url']

                # Fixup system include URL
                if include.get('system') and system_prefix is not None and _is_relative_url(url):
                    url = f'{system_prefix}{url}'
                elif url_fn is not None:
                    url = url_fn(url)

                # Fetch the URL
                try:
                    script_text = fetch_fn(url) if fetch_fn is not None else None
                except: # pylint: disable=bare-except
                    script_text = None
                if script_text is None:
                    raise BareScriptRuntimeError(f'Include of "{url}" failed')

                # Parse the include script
                try:
                    script = parse_script(script_text)
                except BareScriptParserError as exc:
                    raise BareScriptParserError(exc.error, exc.line, exc.column_number, exc.line_number, f'Included from "{url}"')

                # Run the bare-script linter?
                if log_fn is not None and options.get('debug'):
                    warnings = lint_script(script)
                    warning_prefix = f'BareScript: Include "{url}" static analysis...'
                    if warnings:
                        log_fn(f'{warning_prefix} {len(warnings)} warning${"s" if len(warnings) > 1 else ""}:')
                        for warning in warnings:
                            log_fn(f'BareScript:     {warning}')

                # Execute the include script
                include_options = options.copy()
                include_options['urlFn'] = partial(_include_url_fn, url)
                _execute_script_helper(script['statements'], include_options, None)

        # Increment the statement counter
        ix_statement += 1

    return None


# Include url function
def _include_url_fn(include_url, url):
    return f'{_get_base_url(include_url)}{url}' if _is_relative_url(url) else url


def _is_relative_url(url):
    return not r_not_relative_url.match(url)

r_not_relative_url = re.compile(r'^(?:[a-z]+:|\/|\?|#)')


def _get_base_url(url):
    return url[:url.rfind('/') + 1]


# Runtime script function implementation
def _script_function(function, args, options):
    func_locals = {}
    func_args = function.get('args')
    if func_args is not None:
        args_length = len(args)
        func_args_length = len(func_args)
        ix_arg_last = function.get('lastArgArray', None) and (func_args_length - 1)
        for ix_arg in range(func_args_length):
            arg_name = func_args[ix_arg]
            if ix_arg < args_length:
                func_locals[arg_name] = args[ix_arg] if ix_arg != ix_arg_last else args[ix_arg:]
            else:
                func_locals[arg_name] = [] if ix_arg == ix_arg_last else None
    return _execute_script_helper(function['statements'], options, func_locals)


def evaluate_expression(expr, options=None, locals_=None, builtins=True):
    """
    Evaluate an expression model

    :param script: The `expression model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='Expression'>`__
    :type script: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict or None, optional
    :param locals_: The local variables
    :type locals_: dict or None, optional
    :param builtins: If true, include the
        `built-in expression functions <https://craigahobbs.github.io/bare-script-py/library/expression.html>`__
    :type builtins: bool, optional
    :returns: The expression result
    :raises BareScriptRuntimeError: A script runtime error occurred
    """

    expr_key, = expr.keys()
    globals_ = options.get('globals') if options is not None else None

    # Number
    if expr_key == 'number':
        return expr['number']

    # String
    if expr_key == 'string':
        return expr['string']

    # Variable
    if expr_key == 'variable':
        # Keywords
        if expr['variable'] == 'null':
            return None
        if expr['variable'] == 'false':
            return False
        if expr['variable'] == 'true':
            return True

        # Get the local or global variable value or None if undefined
        if locals_ is not None and expr['variable'] in locals_:
            var_value = locals_[expr['variable']]
        else:
            var_value = globals_.get(expr['variable']) if globals_ is not None else None
        return var_value

    # Function
    if expr_key == 'function':
        # "if" built-in function?
        func_name = expr['function']['name']
        if func_name == 'if':
            value_expr, true_expr, false_expr = default_args(expr['function'].get('args', ()), (None, None, None))
            value = evaluate_expression(value_expr, options, locals_, builtins) if value_expr else False
            result_expr = true_expr if value_boolean(value) else false_expr
            return evaluate_expression(result_expr, options, locals_, builtins) if result_expr else None

        # Compute the function arguments
        func_args = [evaluate_expression(arg, options, locals_, builtins) for arg in expr['function']['args']] \
            if 'args' in expr['function'] else None

        # Global/local function?
        if locals_ is not None and func_name in locals_:
            func_value = locals_[func_name]
        elif globals_ is not None and func_name in globals_:
            func_value = globals_[func_name]
        else:
            func_value = EXPRESSION_FUNCTIONS.get(func_name) if builtins else None
        if func_value is not None:
            # Call the function
            try:
                return func_value(func_args, options)
            except BareScriptRuntimeError:
                raise
            except Exception as error: # pylint: disable=broad-exception-caught
                # Log and return null
                if options is not None and 'logFn' in options and options.get('debug'):
                    options['logFn'](f'BareScript: Function "{func_name}" failed with error: {error}')
                return None

        raise BareScriptRuntimeError(f'Undefined function "{func_name}"')

    # Binary expression
    if expr_key == 'binary':
        bin_op = expr['binary']['op']
        left_value = evaluate_expression(expr['binary']['left'], options, locals_, builtins)

        # Short-circuiting binary operators
        if bin_op == '&&':
            if not value_boolean(left_value):
                return left_value
            else:
                return evaluate_expression(expr['binary']['right'], options, locals_, builtins)
        elif bin_op == '||':
            if value_boolean(left_value):
                return left_value
            else:
                return evaluate_expression(expr['binary']['right'], options, locals_, builtins)

        # Non-short-circuiting binary operators
        right_value = evaluate_expression(expr['binary']['right'], options, locals_, builtins)
        if bin_op == '+':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value + right_value
            elif isinstance(left_value, str) and isinstance(right_value, str):
                return left_value + right_value
            elif isinstance(left_value, str):
                return left_value + value_string(right_value)
            elif isinstance(right_value, str):
                return value_string(left_value) + right_value
        elif bin_op == '-':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value - right_value
        elif bin_op == '*':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value * right_value
        elif bin_op == '/':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value / right_value
        elif bin_op == '==':
            return value_compare(left_value, right_value) == 0
        elif bin_op == '!=':
            return value_compare(left_value, right_value) != 0
        elif bin_op == '<=':
            return value_compare(left_value, right_value) <= 0
        elif bin_op == '<':
            return value_compare(left_value, right_value) < 0
        elif bin_op == '>=':
            return value_compare(left_value, right_value) >= 0
        elif bin_op == '>':
            return value_compare(left_value, right_value) > 0
        elif bin_op == '%':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value % right_value
        else:
            # bin_op == '**':
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value ** right_value

        # Invalid operation values
        return None

    # Unary expression
    if expr_key == 'unary':
        unary_op = expr['unary']['op']
        value = evaluate_expression(expr['unary']['expr'], options, locals_, builtins)
        if unary_op == '!':
            return not value_boolean(value)
        else:
            # unary_op == '-'
            if isinstance(value, (int, float)):
                return -value # pylint: disable=invalid-unary-operand-type

        # Invalid operation value
        return None

    # Expression group
    # expr_key == 'group'
    return evaluate_expression(expr['group'], options, locals_, builtins)


class BareScriptRuntimeError(Exception):
    """
    A BareScript runtime error

    :param message: The runtime error message
    :type message: str
    """
    def __init__(self, message):
        super().__init__(message)
