# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript runtime
"""

import datetime
import functools
import json
import math
import sys
import threading

from .include_source import SYSTEM_INCLUDES
from .library import EXPRESSION_FUNCTIONS, INTRINSICS, SCRIPT_FUNCTIONS
from .options import url_file_relative
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
    _execute_script_init(options)
    return _execute_script_helper(script, script['statements'], options, None, _compute_label_indexes(script['statements']))


# Initialize the script execution options - create the globals dict, if necessary, set the built-in
# script function globals, and reset the statement counter
def _execute_script_init(options):
    globals_ = options.get('globals')
    if globals_ is None:
        globals_ = {}
        options['globals'] = globals_
    globals_.update(name_func for name_func in SCRIPT_FUNCTIONS.items() if name_func[0] not in globals_)
    options['statementCount'] = 0


# Compute a statements array's map of label name to statement index
def _compute_label_indexes(statements):
    return {statement['label']['name']: ix_statement for ix_statement, statement in enumerate(statements) if 'label' in statement}


def _execute_script_helper(script, statements, options, locals_, label_indexes):
    globals_ = options['globals']
    max_statements = options.get('maxStatements', DEFAULT_MAX_STATEMENTS)
    options.setdefault('statementCount', 0)

    # Coverage configuration is invariant across this helper invocation
    coverage_global = globals_.get(SYSTEM_GLOBAL_COVERAGE_NAME)
    has_coverage = coverage_global is not None and isinstance(coverage_global, dict) and \
        coverage_global.get('enabled') and not script.get('system')

    # Iterate each script statement
    statements_length = len(statements)
    ix_statement = 0
    while ix_statement < statements_length:
        statement = statements[ix_statement]

        # Increment the statement counter
        statement_count = options['statementCount'] + 1
        options['statementCount'] = statement_count
        if statement_count > max_statements > 0:
            raise BareScriptRuntimeError(script, statement, f'Exceeded maximum script statements ({max_statements})')

        # Record the statement coverage
        if has_coverage:
            statement_key = next(iter(statement.keys()))
            _record_statement_coverage(script, statement, statement_key, coverage_global)

        # Expression?
        if 'expr' in statement:
            stmt_expr = statement['expr']
            expr_value = _evaluate_expression_helper(stmt_expr['expr'], options, globals_, locals_, False, script, statement)
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
               value_boolean(_evaluate_expression_helper(stmt_jump['expr'], options, globals_, locals_, False, script, statement)):
                # Jump to the label
                jump_label = stmt_jump['label']
                ix_label = label_indexes.get(jump_label)
                if ix_label is None:
                    raise BareScriptRuntimeError(script, statement, f"Unknown jump label \"{jump_label}\"")
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
                return _evaluate_expression_helper(stmt_return['expr'], options, globals_, locals_, False, script, statement)
            return None

        # Function?
        elif 'function' in statement:
            stmt_function = statement['function']
            globals_[stmt_function['name']] = \
                functools.partial(_script_function, script, stmt_function, _compute_label_indexes(stmt_function['statements']))

        # Include?
        elif 'include' in statement:
            fetch_fn = options.get('fetchFn')
            log_fn = options.get('logFn')
            url_fn = options.get('urlFn')
            for include in statement['include']['includes']:
                include_url = include['url']

                # Fixup the non-system include URL
                system_include = include.get('system')
                if not system_include and url_fn is not None:
                    include_url = url_fn(include_url)

                # Already included? System include keys are bracketed so they can't collide with local include URLs.
                include_key = f'<{include_url}>' if system_include else include_url
                global_includes = globals_.get(SYSTEM_GLOBAL_INCLUDES_NAME)
                if global_includes is None or not isinstance(global_includes, dict):
                    global_includes = {}
                    globals_[SYSTEM_GLOBAL_INCLUDES_NAME] = global_includes
                if global_includes.get(include_key):
                    continue
                global_includes[include_key] = True

                # Get the include script text - system includes from the system include map, otherwise fetch
                if system_include:
                    include_text = SYSTEM_INCLUDES.get(include_url)
                else:
                    try:
                        include_text = fetch_fn({'url': include_url}) if fetch_fn is not None else None
                    except:
                        include_text = None
                if include_text is None:
                    raise BareScriptRuntimeError(script, statement, f'Include of "{include_url}" failed')

                # Parse the include script. A system include starting with "{" is the
                # parser-compiled JSON script model (all system includes are embedded pre-compiled).
                if system_include and include_text.startswith('{'):
                    include_script = json.loads(include_text)
                else:
                    include_script = barescript_parse_script(include_text, 1, include_url)
                if system_include:
                    include_script['system'] = True

                # Execute the include script
                include_options = options.copy()
                include_options['urlFn'] = functools.partial(url_file_relative, include_url)
                _execute_script_helper(
                    include_script, include_script['statements'], include_options, None,
                    _compute_label_indexes(include_script['statements'])
                )

                # Run the bare-script linter?
                if log_fn is not None and options.get('debug'):
                    warnings = barescript_lint_script(include_script, globals_)
                    if warnings:
                        warning_prefix = f'BareScript: Include "{include_url}" static analysis...'
                        log_fn(f'{warning_prefix} {len(warnings)} warning{"s" if len(warnings) > 1 else ""}:')
                        for warning in warnings:
                            log_fn(f'BareScript: {warning}')

        # Increment the statement counter
        ix_statement += 1

    return None


# Helper to execute a system include library script into a new globals dict
def _system_include_globals(url):
    globals_ = {}
    execute_script({'statements': [{'include': {'includes': [{'url': url, 'system': True}]}}]}, {'globals': globals_})
    return globals_


# The barescriptParser.bare include library script globals (lazily initialized under a lock)
_PARSER_GLOBALS = None
_PARSER_GLOBALS_INIT_LOCK = threading.Lock()


def _parser_globals_init():
    # Execute the barescriptParser.bare include library script, if necessary. The globals are published
    # only once complete so a concurrent first-use caller never observes a partially-initialized parser;
    # the lock serializes the one-time initialization.
    # pylint: disable-next=global-statement
    global _PARSER_GLOBALS
    with _PARSER_GLOBALS_INIT_LOCK:
        if _PARSER_GLOBALS is None:
            _PARSER_GLOBALS = _system_include_globals('barescriptParser.bare')


# Helper to unwrap a barescriptParser.bare parse result - raise on error. The interpreted parser runs
# under the BareScript runtime, whose arithmetic yields JS-parity floats, so line/column numbers are int-normalized.
def _parser_result(result):
    if 'error' in result:
        error = result['error']
        line_number = int(error['lineNumber']) if error['lineNumber'] is not None else None
        raise BareScriptParserError(error['error'], error['line'], int(error['columnNumber']), line_number, error['scriptName'])
    return result['result']


def _normalize_statements(statements):
    # Convert statement line numbers/counts to int. The interpreted parser runs under the
    # BareScript runtime, whose arithmetic yields JS-parity floats.
    for statement in statements:
        statement_value = statement[next(iter(statement))]
        statement_value['lineNumber'] = int(statement_value['lineNumber'])
        line_count = statement_value.get('lineCount')
        if line_count is not None:
            statement_value['lineCount'] = int(line_count)
        function_statements = statement_value.get('statements')
        if function_statements is not None:
            _normalize_statements(function_statements)


def barescript_parse_script(script_text, start_line_number=1, script_name=None):
    """
    Parse a BareScript script

    :param script_text: The `script text <https://craigahobbs.github.io/bare-script/language/>`__ (str or list of str)
    :param start_line_number: The script's starting line number
    :type start_line_number: int, optional
    :param script_name: The script name
    :type script_name: str or None, optional
    :return: The `BareScript model <https://craigahobbs.github.io/bare-script/model/#var.vName='BareScript'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """

    _parser_globals_init()
    script = _parser_result(
        _PARSER_GLOBALS['barescriptParseScriptEx']([script_text, start_line_number, script_name], {'globals': _PARSER_GLOBALS})
    )
    _normalize_statements(script['statements'])
    return script


def barescript_parse_expression(expr_text, line_number=None, script_name=None, array_literals=False):
    """
    Parse a BareScript expression

    :param expr_text: The `expression text <https://craigahobbs.github.io/bare-script/language/#expressions>`__
    :type expr_text: str
    :param line_number: The script line number
    :type line_number: int or None, optional
    :param script_name: The script name
    :type script_name: str or None, optional
    :param array_literals: If True, allow parsing of array literals
    :type array_literals: bool, optional
    :return: The `expression model <https://craigahobbs.github.io/bare-script/model/#var.vName='Expression'>`__
    :rtype: dict
    :raises BareScriptParserError: A parsing error occurred
    """

    _parser_globals_init()
    return _parser_result(
        _PARSER_GLOBALS['barescriptParseExpressionEx']([expr_text, line_number, script_name, array_literals], {'globals': _PARSER_GLOBALS})
    )


# The barescriptLint.bare include library script globals (lazily initialized under a lock)
_LINT_GLOBALS = None
_LINT_GLOBALS_INIT_LOCK = threading.Lock()


def _lint_globals_init():
    # Execute the barescriptLint.bare include library script, if necessary (see _parser_globals_init)
    # pylint: disable-next=global-statement
    global _LINT_GLOBALS
    with _LINT_GLOBALS_INIT_LOCK:
        if _LINT_GLOBALS is None:
            _LINT_GLOBALS = _system_include_globals('barescriptLint.bare')


def barescript_lint_script(script, globals_=None):
    """
    Lint a BareScript model

    :param script: The `BareScript model <./model/#var.vName='BareScript'>`__
    :type script: dict
    :param globals_: The script global variables
    :type globals_: dict or None, optional
    :return: The list of lint warnings
    :rtype: list[str]
    """

    # Call the barescriptLint.bare lint function. Async function detection is not possible in
    # Python (all functions execute synchronously), so the async lint checks are skipped.
    _lint_globals_init()
    return _LINT_GLOBALS['barescriptLintScript']([script, globals_, None], {'globals': _LINT_GLOBALS})


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
def _script_function(script, function, label_indexes, args, options):
    return _execute_script_helper(script, function['statements'], options, _script_function_locals(function, args), label_indexes)


# Helper to create a script function's local variables dict from its call arguments
def _script_function_locals(function, args):
    func_locals = {}
    func_args = function.get('args')
    if func_args is not None:
        args_length = len(args)
        func_args_length = len(func_args)
        if function.get('lastArgArray'):
            ix_arg_last = func_args_length - 1
            for ix_arg in range(func_args_length):
                arg_name = func_args[ix_arg]
                if ix_arg < args_length:
                    func_locals[arg_name] = args[ix_arg] if ix_arg != ix_arg_last else args[ix_arg:]
                else:
                    func_locals[arg_name] = [] if ix_arg == ix_arg_last else None
        else:
            for ix_arg in range(func_args_length):
                func_locals[func_args[ix_arg]] = args[ix_arg] if ix_arg < args_length else None
    return func_locals


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
    return _evaluate_expression_helper(expr, options, globals_, locals_, builtins, script, statement)


# Expression evaluation helper - threads the globals object to avoid a per-call options lookup
def _evaluate_expression_helper(expr, options, globals_, locals_, builtins, script, statement):
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
            value = _evaluate_expression_helper(value_expr, options, globals_, locals_, builtins, script, statement) \
                if value_expr is not None else False
            result_expr = true_expr if value_boolean(value) else false_expr
            return _evaluate_expression_helper(result_expr, options, globals_, locals_, builtins, script, statement) \
                if result_expr is not None else None

        # Compute the function arguments
        args_expr = func.get('args')
        func_args = [_evaluate_expression_helper(arg, options, globals_, locals_, builtins, script, statement) for arg in args_expr] \
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
                # Intrinsic fast path: run the body inline, skipping value_args_validate and the
                # call frame. Bad arguments raise ValueArgsError, handled by the except below exactly
                # as the normal call would; a call reaching one of these under a different name (an
                # alias) matches no branch and falls through to the normal call.
                if func_value in INTRINSICS:
                    # arrayNew has no argument validation - handled before the length access below
                    # because func_args is None when the function expression has no arguments
                    if func_name == 'arrayNew':
                        return func_args
                    func_args_length = len(func_args)
                    if func_name == 'arrayGet':
                        if func_args_length < 1:
                            raise ValueArgsError('array', None)
                        array_value = func_args[0]
                        if not isinstance(array_value, list):
                            raise ValueArgsError('array', array_value)
                        if func_args_length < 2:
                            raise ValueArgsError('index', None)
                        index_value = func_args[1]
                        if isinstance(index_value, float):
                            if index_value < 0 or not index_value.is_integer():
                                raise ValueArgsError('index', index_value)
                            index_value = int(index_value)
                        elif isinstance(index_value, int) and not isinstance(index_value, bool):
                            if index_value < 0:
                                raise ValueArgsError('index', index_value)
                        else:
                            raise ValueArgsError('index', index_value)
                        if func_args_length > 2:
                            raise ValueArgsError(None, func_args_length)
                        if index_value >= len(array_value):
                            raise ValueArgsError('index', index_value)
                        return array_value[index_value]
                    if func_name == 'arrayLength':
                        if func_args_length < 1:
                            raise ValueArgsError('array', None, 0)
                        array_value = func_args[0]
                        if not isinstance(array_value, list):
                            raise ValueArgsError('array', array_value, 0)
                        if func_args_length > 1:
                            raise ValueArgsError(None, func_args_length, 0)
                        return len(array_value)
                    if func_name == 'arrayPush':
                        if func_args_length < 1:
                            raise ValueArgsError('array', None)
                        array_value = func_args[0]
                        if not isinstance(array_value, list):
                            raise ValueArgsError('array', array_value)
                        array_value.extend(func_args[1:])
                        return array_value
                    if func_name == 'arraySet':
                        if func_args_length < 1:
                            raise ValueArgsError('array', None)
                        array_value = func_args[0]
                        if not isinstance(array_value, list):
                            raise ValueArgsError('array', array_value)
                        if func_args_length < 2:
                            raise ValueArgsError('index', None)
                        index_value = func_args[1]
                        if isinstance(index_value, float):
                            if index_value < 0 or not index_value.is_integer():
                                raise ValueArgsError('index', index_value)
                            index_value = int(index_value)
                        elif isinstance(index_value, int) and not isinstance(index_value, bool):
                            if index_value < 0:
                                raise ValueArgsError('index', index_value)
                        else:
                            raise ValueArgsError('index', index_value)
                        if func_args_length > 3:
                            raise ValueArgsError(None, func_args_length)
                        if index_value >= len(array_value):
                            raise ValueArgsError('index', index_value)
                        set_value = func_args[2] if func_args_length >= 3 else None
                        array_value[index_value] = set_value
                        return set_value
                    if func_name == 'mathSqrt':
                        if func_args_length < 1:
                            raise ValueArgsError('x', None)
                        x_value = func_args[0]
                        if not isinstance(x_value, (int, float)) or isinstance(x_value, bool) or not x_value >= 0:
                            raise ValueArgsError('x', x_value)
                        if func_args_length > 1:
                            raise ValueArgsError(None, func_args_length)
                        return math.sqrt(x_value)
                    if func_name == 'objectGet':
                        default_value = func_args[2] if func_args_length >= 3 else None
                        if func_args_length < 1:
                            raise ValueArgsError('object', None, default_value)
                        object_value = func_args[0]
                        if not isinstance(object_value, dict):
                            raise ValueArgsError('object', object_value, default_value)
                        if func_args_length < 2:
                            raise ValueArgsError('key', None, default_value)
                        key_value = func_args[1]
                        if not isinstance(key_value, str):
                            raise ValueArgsError('key', key_value, default_value)
                        if func_args_length > 3:
                            raise ValueArgsError(None, func_args_length, default_value)
                        return object_value.get(key_value, default_value)
                    if func_name == 'objectHas':
                        if func_args_length < 1:
                            raise ValueArgsError('object', None, False)
                        object_value = func_args[0]
                        if not isinstance(object_value, dict):
                            raise ValueArgsError('object', object_value, False)
                        if func_args_length < 2:
                            raise ValueArgsError('key', None, False)
                        key_value = func_args[1]
                        if not isinstance(key_value, str):
                            raise ValueArgsError('key', key_value, False)
                        if func_args_length > 2:
                            raise ValueArgsError(None, func_args_length, False)
                        return key_value in object_value
                    if func_name == 'objectKeys':
                        if func_args_length < 1:
                            raise ValueArgsError('object', None)
                        object_value = func_args[0]
                        if not isinstance(object_value, dict):
                            raise ValueArgsError('object', object_value)
                        if func_args_length > 1:
                            raise ValueArgsError(None, func_args_length)
                        return list(object_value.keys())
                    if func_name == 'objectSet':
                        if func_args_length < 1:
                            raise ValueArgsError('object', None)
                        object_value = func_args[0]
                        if not isinstance(object_value, dict):
                            raise ValueArgsError('object', object_value)
                        if func_args_length < 2:
                            raise ValueArgsError('key', None)
                        key_value = func_args[1]
                        if not isinstance(key_value, str):
                            raise ValueArgsError('key', key_value)
                        if func_args_length > 3:
                            raise ValueArgsError(None, func_args_length)
                        set_value = func_args[2] if func_args_length >= 3 else None
                        object_value[key_value] = set_value
                        return set_value
                    if func_name == 'stringLength':
                        if func_args_length < 1:
                            raise ValueArgsError('string', None, 0)
                        string_value = func_args[0]
                        if not isinstance(string_value, str):
                            raise ValueArgsError('string', string_value, 0)
                        if func_args_length > 1:
                            raise ValueArgsError(None, func_args_length, 0)
                        return len(string_value)

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
        left_value = _evaluate_expression_helper(binary['left'], options, globals_, locals_, builtins, script, statement)

        # Short-circuiting "and" binary operator
        if bin_op == '&&':
            if not value_boolean(left_value):
                return left_value
            return _evaluate_expression_helper(binary['right'], options, globals_, locals_, builtins, script, statement)

        # Short-circuiting "or" binary operator
        elif bin_op == '||':
            if value_boolean(left_value):
                return left_value
            return _evaluate_expression_helper(binary['right'], options, globals_, locals_, builtins, script, statement)

        # Non-short-circuiting binary operators
        right_value = _evaluate_expression_helper(binary['right'], options, globals_, locals_, builtins, script, statement)
        left_type = type(left_value)
        right_type = type(right_value)
        if bin_op == '+':
            # number + number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return _arithmetic_result(left_value + right_value)

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
                try:
                    return left_dt + datetime.timedelta(milliseconds=right_value)
                except OverflowError:
                    return None
            elif ((left_type is int or left_type is float) and
                  isinstance(right_value, datetime.date)):
                right_dt = value_normalize_datetime(right_value)
                try:
                    return right_dt + datetime.timedelta(milliseconds=left_value)
                except OverflowError:
                    return None

        elif bin_op == '-':
            # number - number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return _arithmetic_result(left_value - right_value)

            # datetime - datetime
            elif isinstance(left_value, datetime.date) and isinstance(right_value, datetime.date):
                left_dt = value_normalize_datetime(left_value)
                right_dt = value_normalize_datetime(right_value)
                return value_round_number((left_dt - right_dt).total_seconds() * 1000, 0)

        elif bin_op == '*':
            # number * number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                return _arithmetic_result(left_value * right_value)

        elif bin_op == '/':
            # number / number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                try:
                    return _arithmetic_result(left_value / right_value)
                except ZeroDivisionError:
                    return None

        elif bin_op == '<':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value < right_value
            return value_compare(left_value, right_value) < 0

        elif bin_op == '<=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value <= right_value
            return value_compare(left_value, right_value) <= 0

        elif bin_op == '>':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value > right_value
            return value_compare(left_value, right_value) > 0

        elif bin_op == '>=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value >= right_value
            return value_compare(left_value, right_value) >= 0

        elif bin_op == '==':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value == right_value
            return value_compare(left_value, right_value) == 0

        elif bin_op == '!=':
            if (left_type is int or left_type is float) and (right_type is int or right_type is float):
                return left_value != right_value
            return value_compare(left_value, right_value) != 0

        elif bin_op == '%':
            # number % number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                try:
                    return _arithmetic_result(left_value % right_value)
                except ZeroDivisionError:
                    return None

        elif bin_op == '**':
            # number ** number
            if ((left_type is int or left_type is float) and
                (right_type is int or right_type is float)):
                try:
                    return _arithmetic_result(left_value ** right_value)
                except (OverflowError, ZeroDivisionError):
                    return None

        elif bin_op == '&':
            # int & int
            if ((left_type is int or (left_type is float and left_value.is_integer())) and
                (right_type is int or (right_type is float and right_value.is_integer()))):
                return int(left_value) & int(right_value)

        elif bin_op == '|':
            # int & int
            if ((left_type is int or (left_type is float and left_value.is_integer())) and
                (right_type is int or (right_type is float and right_value.is_integer()))):
                return int(left_value) | int(right_value)

        elif bin_op == '^':
            # int & int
            if ((left_type is int or (left_type is float and left_value.is_integer())) and
                (right_type is int or (right_type is float and right_value.is_integer()))):
                return int(left_value) ^ int(right_value)

        elif bin_op == '<<':
            # int & int
            if ((left_type is int or (left_type is float and left_value.is_integer())) and
                (right_type is int or (right_type is float and right_value.is_integer()))):
                return int(left_value) << int(right_value)

        else: # bin_op == '>>':
            # int & int
            if ((left_type is int or (left_type is float and left_value.is_integer())) and
                (right_type is int or (right_type is float and right_value.is_integer()))):
                return int(left_value) >> int(right_value)

        # Invalid operation values
        return None

    # Unary expression
    if 'unary' in expr:
        unary = expr['unary']
        unary_op = unary['op']
        value = _evaluate_expression_helper(unary['expr'], options, globals_, locals_, builtins, script, statement)
        if unary_op == '!':
            return not value_boolean(value)
        val_type = type(value)
        if unary_op == '-':
            if val_type is int or val_type is float:
                return -value
        else: # unary_op == '~':
            if val_type is int or (val_type is float and value.is_integer()):
                return ~int(value)

        # Invalid operation value
        return None

    # Expression group
    # expr_key == 'group'
    return _evaluate_expression_helper(expr['group'], options, globals_, locals_, builtins, script, statement)


# Helper to normalize an arithmetic result - non-finite numbers (including out-of-double-range
# integers and complex results) are invalid operation values
def _arithmetic_result(result):
    result_type = type(result)
    if result_type is float:
        return result if math.isfinite(result) else None
    if result_type is int:
        return result if -sys.float_info.max <= result <= sys.float_info.max else None

    # complex - a float raised to a fractional power of a negative base
    return None


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
