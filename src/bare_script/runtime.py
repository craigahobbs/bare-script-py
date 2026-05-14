# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript runtime
"""

import datetime
import functools

from .library import EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS
from .model import lint_script
from .options import url_file_relative
from .parser import parse_script
from .value import ValueArgsError, value_boolean, value_compare, value_normalize_datetime, value_round_number, value_string


# The default maximum statements for executeScript
DEFAULT_MAX_STATEMENTS = 1e9


# Coverage configuration object global variable name
SYSTEM_GLOBAL_COVERAGE_NAME = '__barescriptCoverage'


# System includes object global variable name
SYSTEM_GLOBAL_INCLUDES_NAME = '__barescriptIncludes'


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
    return _execute_script_helper(script, script['statements'], options, None)


def _execute_script_helper(script, statements, options, locals_):
    globals_ = options['globals']
    max_statements = options.get('maxStatements', DEFAULT_MAX_STATEMENTS)
    options.setdefault('statementCount', 0)

    # Coverage configuration is invariant across this helper invocation
    coverage_global = globals_.get(SYSTEM_GLOBAL_COVERAGE_NAME)
    has_coverage = coverage_global is not None and isinstance(coverage_global, dict) and \
        coverage_global.get('enabled') and not script.get('system')

    # Iterate each script statement
    label_indexes = None
    statements_length = len(statements)
    ix_statement = 0
    while ix_statement < statements_length:
        statement = statements[ix_statement]

        # Increment the statement counter
        options['statementCount'] += 1
        if max_statements > 0 and options['statementCount'] > max_statements:
            raise BareScriptRuntimeError(script, statement, f'Exceeded maximum script statements ({max_statements})')

        # Record the statement coverage
        if has_coverage:
            statement_key = next(iter(statement.keys()))
            _record_statement_coverage(script, statement, statement_key, coverage_global)

        # Expression?
        if 'expr' in statement:
            stmt_expr = statement['expr']
            expr_value = evaluate_expression(stmt_expr['expr'], options, locals_, False, script, statement)
            expr_name = stmt_expr.get('name')
            if expr_name is not None:
                if locals_ is not None:
                    locals_[expr_name] = expr_value
                else:
                    globals_[expr_name] = expr_value

        # Jump?
        elif 'jump' in statement:
            stmt_jump = statement['jump']
            # Evaluate the expression (if any)
            if 'expr' not in stmt_jump or \
               value_boolean(evaluate_expression(stmt_jump['expr'], options, locals_, False, script, statement)):
                # Find the label
                jump_label = stmt_jump['label']
                if label_indexes is not None and jump_label in label_indexes:
                    ix_statement = label_indexes[jump_label]
                else:
                    ix_label = next(
                        (ix_stmt for ix_stmt, stmt in enumerate(statements) if 'label' in stmt and stmt['label']['name'] == jump_label),
                        -1
                    )
                    if ix_label == -1:
                        raise BareScriptRuntimeError(script, statement, f"Unknown jump label \"{jump_label}\"")
                    if label_indexes is None:
                        label_indexes = {}
                    label_indexes[jump_label] = ix_label
                    ix_statement = ix_label

                # Record the label statement coverage
                if has_coverage:
                    label_statement = statements[ix_statement]
                    label_statement_key = next(iter(label_statement.keys()))
                    _record_statement_coverage(script, label_statement, label_statement_key, coverage_global)

        # Return?
        elif 'return' in statement:
            stmt_return = statement['return']
            if 'expr' in stmt_return:
                return evaluate_expression(stmt_return['expr'], options, locals_, False, script, statement)
            return None

        # Function?
        elif 'function' in statement:
            stmt_function = statement['function']
            globals_[stmt_function['name']] = functools.partial(_script_function, script, stmt_function)

        # Include?
        elif 'include' in statement:
            system_prefix = options.get('systemPrefix')
            fetch_fn = options.get('fetchFn')
            log_fn = options.get('logFn')
            url_fn = options.get('urlFn')
            for include in statement['include']['includes']:
                include_url = include['url']

                # Fixup system include URL
                system_include = include.get('system')
                if system_include and system_prefix is not None:
                    include_url = url_file_relative(system_prefix, include_url)
                elif url_fn is not None:
                    include_url = url_fn(include_url)

                # Already included?
                global_includes = globals_.get(SYSTEM_GLOBAL_INCLUDES_NAME)
                if global_includes is None or not isinstance(global_includes, dict):
                    global_includes = {}
                    globals_[SYSTEM_GLOBAL_INCLUDES_NAME] = global_includes
                if global_includes.get(include_url):
                    continue
                global_includes[include_url] = True

                # Fetch the URL
                try:
                    include_text = fetch_fn({'url': include_url}) if fetch_fn is not None else None
                except:
                    include_text = None
                if include_text is None:
                    raise BareScriptRuntimeError(script, statement, f'Include of "{include_url}" failed')

                # Parse the include script
                include_script = parse_script(include_text, 1, include_url)
                if system_include:
                    include_script['system'] = True

                # Execute the include script
                include_options = options.copy()
                include_options['urlFn'] = functools.partial(url_file_relative, include_url)
                _execute_script_helper(include_script, include_script['statements'], include_options, None)

                # Run the bare-script linter?
                if log_fn is not None and options.get('debug'):
                    warnings = lint_script(include_script, globals_)
                    if warnings:
                        warning_prefix = f'BareScript: Include "{include_url}" static analysis...'
                        log_fn(f'{warning_prefix} {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                        for warning in warnings:
                            log_fn(f'BareScript: {warning}')

        # Increment the statement counter
        ix_statement += 1

    return None


# Helper function to record statement coverage
def _record_statement_coverage(script, statement, statement_key, coverage_global):
    # Get the script name and statement line number
    script_name = script.get('scriptName')
    lineno = statement[statement_key].get('lineNumber')
    if script_name is None or lineno is None:
        return

    # Record the statement/lineno coverage
    scripts = coverage_global.get('scripts')
    if scripts is None:
        scripts = coverage_global['scripts'] = {}
    script_coverage = scripts.get(script_name)
    if script_coverage is None:
        script_coverage = scripts[script_name] = {'script': script, 'covered': {}}

    # Increment the statement coverage count
    lineno_str = str(lineno)
    covered_statements = script_coverage['covered']
    covered_statement = covered_statements.get(lineno_str)
    if covered_statement is None:
        covered_statement = covered_statements[lineno_str] = {'statement': statement, 'count': 0}
    covered_statement['count'] += 1


# Runtime script function implementation
def _script_function(script, function, args, options):
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
    return _execute_script_helper(script, function['statements'], options, func_locals)


def evaluate_expression(expr, options=None, locals_=None, builtins=True, script=None, statement=None):
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

    globals_ = options.get('globals') if options is not None else None

    # Number
    if 'number' in expr:
        return expr['number']

    # String
    if 'string' in expr:
        return expr['string']

    # Variable
    if 'variable' in expr:
        variable = expr['variable']

        # Keywords
        if variable == 'null':
            return None
        if variable == 'false':
            return False
        if variable == 'true':
            return True

        # Get the local or global variable value or None if undefined
        if locals_ is not None and variable in locals_:
            return locals_[variable]
        else:
            return globals_.get(variable) if globals_ is not None else None

    # Function
    if 'function' in expr:
        func = expr['function']

        # "if" built-in function?
        func_name = func['name']
        if func_name == 'if':
            args_expr = func.get('args', ())
            args_expr_length = len(args_expr)
            value_expr = args_expr[0] if args_expr_length >= 1 else None
            true_expr = args_expr[1] if args_expr_length >= 2 else None
            false_expr = args_expr[2] if args_expr_length >= 3 else None
            value = evaluate_expression(value_expr, options, locals_, builtins, script, statement) \
                if value_expr is not None else False
            result_expr = true_expr if value_boolean(value) else false_expr
            return evaluate_expression(result_expr, options, locals_, builtins, script, statement) \
                if result_expr is not None else None

        # Compute the function arguments
        args_expr = func.get('args')
        func_args = [evaluate_expression(arg, options, locals_, builtins, script, statement) for arg in args_expr] \
            if args_expr is not None else None

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
            except Exception as error:
                # Log and return null
                if options is not None and 'logFn' in options and options.get('debug'):
                    error_message = BareScriptRuntimeError(
                        script, statement, f'BareScript: Function "{func_name}" failed with error: {error}'
                    )
                    options['logFn'](str(error_message))
                if isinstance(error, ValueArgsError):
                    return error.return_value
                return None

        raise BareScriptRuntimeError(script, statement, f'Undefined function "{func_name}"')

    # Binary expression
    if 'binary' in expr:
        binary = expr['binary']
        bin_op = binary['op']
        left_value = evaluate_expression(binary['left'], options, locals_, builtins, script, statement)

        # Short-circuiting "and" binary operator
        if bin_op == '&&':
            if not value_boolean(left_value):
                return left_value
            return evaluate_expression(binary['right'], options, locals_, builtins, script, statement)

        # Short-circuiting "or" binary operator
        elif bin_op == '||':
            if value_boolean(left_value):
                return left_value
            return evaluate_expression(binary['right'], options, locals_, builtins, script, statement)

        # Non-short-circuiting binary operators
        right_value = evaluate_expression(binary['right'], options, locals_, builtins, script, statement)
        left_type = type(left_value)
        right_type = type(right_value)
        if bin_op == '+':
            # number + number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value + right_value

            # string + string
            elif left_type is str and right_type is str:
                return left_value + right_value

            # string + <any>
            elif left_type is str:
                return left_value + value_string(right_value)
            elif right_type is str:
                return value_string(left_value) + right_value

            # datetime + number
            elif (isinstance(left_value, datetime.date) and
                  (right_type is int or right_type is float)):
                left_dt = value_normalize_datetime(left_value)
                return left_dt + datetime.timedelta(milliseconds=right_value)
            elif ((left_type is int or left_type is float) and
                  isinstance(right_value, datetime.date)):
                right_dt = value_normalize_datetime(right_value)
                return right_dt + datetime.timedelta(milliseconds=left_value)

        elif bin_op == '-':
            # number - number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value - right_value

            # datetime - datetime
            elif isinstance(left_value, datetime.date) and isinstance(right_value, datetime.date):
                left_dt = value_normalize_datetime(left_value)
                right_dt = value_normalize_datetime(right_value)
                return value_round_number((left_dt - right_dt).total_seconds() * 1000, 0)

        elif bin_op == '*':
            # number * number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value * right_value

        elif bin_op == '/':
            # number / number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value / right_value

        elif bin_op == '==':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value == right_value
            return value_compare(left_value, right_value) == 0

        elif bin_op == '!=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value != right_value
            return value_compare(left_value, right_value) != 0

        elif bin_op == '<=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value <= right_value
            return value_compare(left_value, right_value) <= 0

        elif bin_op == '<':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value < right_value
            return value_compare(left_value, right_value) < 0

        elif bin_op == '>=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value >= right_value
            return value_compare(left_value, right_value) >= 0

        elif bin_op == '>':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value > right_value
            return value_compare(left_value, right_value) > 0

        elif bin_op == '%':
            # number % number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value % right_value

        elif bin_op == '**':
            # number ** number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return left_value ** right_value

        elif bin_op == '&':
            # int & int
            if ((left_type is int or left_type is float) and int(left_value) == left_value and
                (right_type is int or right_type is float) and int(right_value) == right_value):
                return int(left_value) & int(right_value)

        elif bin_op == '|':
            # int & int
            if ((left_type is int or left_type is float) and int(left_value) == left_value and
                (right_type is int or right_type is float) and int(right_value) == right_value):
                return int(left_value) | int(right_value)

        elif bin_op == '^':
            # int & int
            if ((left_type is int or left_type is float) and int(left_value) == left_value and
                (right_type is int or right_type is float) and int(right_value) == right_value):
                return int(left_value) ^ int(right_value)

        elif bin_op == '<<':
            # int & int
            if ((left_type is int or left_type is float) and int(left_value) == left_value and
                (right_type is int or right_type is float) and int(right_value) == right_value):
                return int(left_value) << int(right_value)

        else: # bin_op == '>>':
            # int & int
            if ((left_type is int or left_type is float) and int(left_value) == left_value and
                (right_type is int or right_type is float) and int(right_value) == right_value):
                return int(left_value) >> int(right_value)

        # Invalid operation values
        return None

    # Unary expression
    if 'unary' in expr:
        unary = expr['unary']
        unary_op = unary['op']
        value = evaluate_expression(unary['expr'], options, locals_, builtins, script, statement)
        if unary_op == '!':
            return not value_boolean(value)
        val_type = type(value)
        if unary_op == '-':
            if val_type is int or val_type is float:
                return -value
        else: # unary_op == '~':
            if (val_type is int or val_type is float) and int(value) == value:
                return ~int(value)

        # Invalid operation value
        return None

    # Expression group
    # expr_key == 'group'
    return evaluate_expression(expr['group'], options, locals_, builtins, script, statement)


class BareScriptRuntimeError(Exception):
    """
    A BareScript runtime error

    :param message: The runtime error message
    :type message: str
    """

    def __init__(self, script, statement, message):
        if script and statement:
            statement_key = next(iter(statement.keys()))
            script_name = script.get('scriptName', '')
            lineno = statement[statement_key].get('lineNumber', '')
            message_script = f'{script_name}:{lineno}: {message}' if script_name or lineno else message
        else:
            message_script = message
        super().__init__(message_script)
