# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript runtime
"""

import datetime
import functools

from .library import DEFAULT_MAX_STATEMENTS, EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS
from .model import lint_script
from .options import url_file_relative
from .parser import BareScriptParserError, parse_script
from .value import ValueArgsError, value_boolean, value_compare, value_normalize_datetime, value_round_number, value_string


def execute_script(script, options=None):
    """
    Execute a BareScript model

    :param script: The `BareScript model <./model/#var.vName='BareScript'>`__
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
    globals_.update(name_func for name_func in SCRIPT_FUNCTIONS.items() if name_func[0] not in globals_)

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
        options['statementCount'] += 1
        max_statements = options.get('maxStatements', DEFAULT_MAX_STATEMENTS)
        if max_statements > 0 and options['statementCount'] > max_statements:
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
                    jump_label = statement['jump']['label']
                    ix_label = next((ix_stmt for ix_stmt, stmt in enumerate(statements) if stmt.get('label') == jump_label), -1)
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
            globals_[statement['function']['name']] = functools.partial(_script_function, statement['function'])

        # Include?
        elif statement_key == 'include':
            system_prefix = options.get('systemPrefix')
            fetch_fn = options.get('fetchFn')
            log_fn = options.get('logFn')
            url_fn = options.get('urlFn')
            for include in statement['include']['includes']:
                url = include['url']

                # Fixup system include URL
                if include.get('system') and system_prefix is not None:
                    url = url_file_relative(system_prefix, url)
                elif url_fn is not None:
                    url = url_fn(url)

                # Fetch the URL
                try:
                    script_text = fetch_fn({'url': url}) if fetch_fn is not None else None
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
                    if warnings:
                        warning_prefix = f'BareScript: Include "{url}" static analysis...'
                        log_fn(f'{warning_prefix} {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                        for warning in warnings:
                            log_fn(f'BareScript:     {warning}')

                # Execute the include script
                include_options = options.copy()
                include_options['urlFn'] = functools.partial(url_file_relative, url)
                _execute_script_helper(script['statements'], include_options, None)

        # Increment the statement counter
        ix_statement += 1

    return None


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

    :param script: The `expression model <./model/#var.vName='Expression'>`__
    :type script: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict or None, optional
    :param locals_: The local variables
    :type locals_: dict or None, optional
    :param builtins: If true, include the `built-in expression functions <library/expression.html>`__
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
            return locals_[expr['variable']]
        else:
            return globals_.get(expr['variable']) if globals_ is not None else None

    # Function
    if expr_key == 'function':
        # "if" built-in function?
        func_name = expr['function']['name']
        if func_name == 'if':
            args_expr = expr['function'].get('args', ())
            args_expr_length = len(args_expr)
            value_expr = args_expr[0] if args_expr_length >= 1 else None
            true_expr = args_expr[1] if args_expr_length >= 2 else None
            false_expr = args_expr[2] if args_expr_length >= 3 else None
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
                if isinstance(error, ValueArgsError):
                    return error.return_value
                return None

        raise BareScriptRuntimeError(f'Undefined function "{func_name}"')

    # Binary expression
    if expr_key == 'binary':
        bin_op = expr['binary']['op']
        left_value = evaluate_expression(expr['binary']['left'], options, locals_, builtins)

        # Short-circuiting "and" binary operator
        if bin_op == '&&':
            if not value_boolean(left_value):
                return left_value
            return evaluate_expression(expr['binary']['right'], options, locals_, builtins)

        # Short-circuiting "or" binary operator
        elif bin_op == '||':
            if value_boolean(left_value):
                return left_value
            return evaluate_expression(expr['binary']['right'], options, locals_, builtins)

        # Non-short-circuiting binary operators
        right_value = evaluate_expression(expr['binary']['right'], options, locals_, builtins)
        if bin_op == '+':
            # number + number
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value + right_value

            # string + string
            elif isinstance(left_value, str) and isinstance(right_value, str):
                return left_value + right_value

            # string + <any>
            elif isinstance(left_value, str):
                return left_value + value_string(right_value)
            elif isinstance(right_value, str):
                return value_string(left_value) + right_value

            # datetime + number
            elif isinstance(left_value, datetime.date) and isinstance(right_value, (int, float)):
                left_dt = value_normalize_datetime(left_value)
                return left_dt + datetime.timedelta(milliseconds=right_value)
            elif isinstance(left_value, (int, float)) and isinstance(right_value, datetime.date):
                right_dt = value_normalize_datetime(right_value)
                return right_dt + datetime.timedelta(milliseconds=left_value)

        elif bin_op == '-':
            # number - number
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value - right_value

            # datetime - datetime
            elif isinstance(left_value, datetime.date) and isinstance(right_value, datetime.date):
                left_dt = value_normalize_datetime(left_value)
                right_dt = value_normalize_datetime(right_value)
                return value_round_number((left_dt - right_dt).total_seconds() * 1000, 0)

        elif bin_op == '*':
            # number * number
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value * right_value

        elif bin_op == '/':
            # number / number
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
            # number % number
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                return left_value % right_value

        else: # bin_op == '**'
            # number ** number
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
        elif unary_op == '-' and isinstance(value, (int, float)):
            return -value

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
