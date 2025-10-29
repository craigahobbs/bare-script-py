# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript runtime model and related utilities
"""

from schema_markdown import parse_schema_markdown, validate_type


#
# The BareScript type model
#
BARE_SCRIPT_TYPES = parse_schema_markdown('''\
# A BareScript script
struct BareScript

    # The script's statements
    ScriptStatement[] statements

    # The script name
    optional string scriptName

    # The script's lines
    optional string[] scriptLines

    # If true, this is a system include script
    optional bool system


# A script statement
union ScriptStatement

    # An expression
    ExpressionStatement expr

    # A jump statement
    JumpStatement jump

    # A return statement
    ReturnStatement return

    # A label definition
    LabelStatement label

    # A function definition
    FunctionStatement function

    # An include statement
    IncludeStatement include


# Script statement base struct
struct BaseStatement

    # The script statement's line number
    optional int lineNumber

    # The number of lines in the script statement (default is 1)
    optional int lineCount


# An expression statement
struct ExpressionStatement (BaseStatement)

    # The variable name to assign the expression value
    optional string name

    # The expression to evaluate
    Expression expr


# A jump statement
struct JumpStatement (BaseStatement)

    # The label to jump to
    string label

    # The test expression
    optional Expression expr


# A return statement
struct ReturnStatement (BaseStatement)

    # The expression to return
    optional Expression expr


# A label statement
struct LabelStatement (BaseStatement)

    # The label name
    string name


# A function definition statement
struct FunctionStatement (BaseStatement)

    # If true, the function is defined as async
    optional bool async

    # The function name
    string name

    # The function's argument names
    optional string[len > 0] args

    # If true, the function's last argument is the array of all remaining arguments
    optional bool lastArgArray

    # The function's statements
    ScriptStatement[] statements


# An include statement
struct IncludeStatement (BaseStatement)

    # The list of include scripts to load and execute in the global scope
    IncludeScript[len > 0] includes


# An include script
struct IncludeScript

    # The include script URL
    string url

    # If true, this is a system include
    optional bool system


# The coverage global configuration
struct CoverageGlobal

    # If true, coverage is enabled
    optional bool enabled

    # The map of script name to script coverage
    optional CoverageGlobalScript{} scripts


# The script coverage
struct CoverageGlobalScript

    # The script
    BareScript script

    # The map of script line number string to script statement coverage
    CoverageGlobalStatement{} covered


# The script statement coverage
struct CoverageGlobalStatement

    # The script statement
    ScriptStatement statement

    # The statement's coverage count
    int count


# An expression
union Expression

    # A number literal
    float number

    # A string literal
    string string

    # A variable value
    string variable

    # A function expression
    FunctionExpression function

    # A binary expression
    BinaryExpression binary

    # A unary expression
    UnaryExpression unary

    # An expression group
    Expression group


# A binary expression
struct BinaryExpression

    # The binary expression operator
    BinaryExpressionOperator op

    # The left expression
    Expression left

    # The right expression
    Expression right


# A binary expression operator
enum BinaryExpressionOperator

    # Exponentiation
    "**"

    # Multiplication
    "*"

    # Division
    "/"

    # Remainder
    "%"

    # Addition
    "+"

    # Subtraction
    "-"

    # Bitwise left shift
    "<<"

    # Bitwise right shift
    ">>"

    # Less than or equal
    "<="

    # Less than
    "<"

    # Greater than or equal
    ">="

    # Greater than
    ">"

    # Equal
    "=="

    # Not equal
    "!="

    # Bitwise AND
    "&"

    # Bitwise XOR
    "^"

    # Bitwise OR
    "|"

    # Logical AND
    "&&"

    # Logical OR
    "||"


# A unary expression
struct UnaryExpression

    # The unary expression operator
    UnaryExpressionOperator op

    # The expression
    Expression expr


# A unary expression operator
enum UnaryExpressionOperator

    # Unary negation
    "-"

    # Logical NOT
    "!"

    # Bitwise NOT
    "~"


# A function expression
struct FunctionExpression

    # The function name
    string name

    # The function arguments
    optional Expression[] args
''')


def validate_script(script):
    """
    Validate a BareScript script model

    :param script: The `BareScript model <./model/#var.vName='BareScript'>`__
    :type script: dict
    :return: The validated BareScript model
    :rtype: dict
    :raises ~schema_markdown.ValidationError: A validation error occurred
    """
    return validate_type(BARE_SCRIPT_TYPES, 'BareScript', script)


def validate_expression(expr):
    """
    Validate an expression model

    :param script: The `expression model <./model/#var.vName='Expression'>`__
    :type script: dict
    :return: The validated expression model
    :rtype: dict
    :raises ~schema_markdown.ValidationError: A validation error occurred
    """
    return validate_type(BARE_SCRIPT_TYPES, 'Expression', expr)


def lint_script(script, globals_=None):
    """
    Lint a BareScript script model

    :param script: The `BareScript model <./model/#var.vName='BareScript'>`__
    :type script: dict
    :param globals_: The script global variables
    :type globals_: dict or None, optional
    :return: The list of lint warnings
    :rtype: list[str]
    """

    warnings = []
    statements = script['statements']

    # Empty script?
    if len(script['statements']) == 0:
        _lint_script_warning(warnings, script, None, 'Empty script')

    # Variable used before assignment?
    var_assigns = {}
    var_uses = {}
    _get_variable_assignments_and_uses(script['statements'], var_assigns, var_uses)
    for var_name in sorted(var_assigns.keys()):
        if var_name in var_uses and var_uses[var_name] <= var_assigns[var_name]:
            _lint_script_warning(warnings, script, statements[var_uses[var_name]], f'Global variable "{var_name}" used before assignment')

    # Unknown global variable?
    if globals_ is not None:
        for var_name in sorted(var_uses.keys()):
            if var_name not in var_assigns and var_name not in globals_ and var_name not in _BUILTIN_GLOBALS:
                _lint_script_warning(warnings, script, statements[var_uses[var_name]], f'Unknown global variable "{var_name}"')

    # Iterate global statements
    functions_defined = {}
    labels_defined = {}
    labels_used = {}
    for ix_statement, statement in enumerate(statements):
        statement_key = next(iter(statement.keys()))

        # Function definition checks
        if statement_key == 'function':
            function_name = statement['function']['name']

            # Function redefinition?
            if function_name in functions_defined:
                _lint_script_warning(warnings, script, statement, f'Redefinition of function "{function_name}"')
            else:
                functions_defined[function_name] = ix_statement

            # Variable used before assignment?
            fn_var_assigns = {}
            fn_var_uses = {}
            args = statement['function'].get('args')
            fn_statements = statement['function']['statements']
            _get_variable_assignments_and_uses(fn_statements, fn_var_assigns, fn_var_uses)
            for var_name in sorted(fn_var_assigns.keys()):
                # Ignore re-assigned function arguments
                if args is not None and var_name in args:
                    continue
                if var_name in fn_var_uses and fn_var_uses[var_name] <= fn_var_assigns[var_name]:
                    _lint_script_warning(
                        warnings, script, fn_statements[fn_var_uses[var_name]],
                        f'Variable "{var_name}" of function "{function_name}" used before assignment'
                    )

            # Unused variables?
            for var_name in sorted(fn_var_assigns.keys()):
                if var_name not in fn_var_uses:
                    _lint_script_warning(
                        warnings, script, fn_statements[fn_var_assigns[var_name]],
                        f'Unused variable "{var_name}" defined in function "{function_name}"'
                    )

            # Unknown global variable?
            if globals_ is not None:
                for var_name in sorted(fn_var_uses.keys()):
                    if var_name not in fn_var_assigns and (args is None or var_name not in args) and \
                       var_name not in globals_ and var_name not in _BUILTIN_GLOBALS:
                        _lint_script_warning(
                            warnings, script, fn_statements[fn_var_uses[var_name]], f'Unknown global variable "{var_name}"'
                        )

            # Function argument checks
            if args is not None:
                args_defined = set()
                for arg in args:
                    # Duplicate argument?
                    if arg in args_defined:
                        _lint_script_warning(warnings, script, statement, f'Duplicate argument "{arg}" of function "{function_name}"')
                    else:
                        args_defined.add(arg)

                        # Unused argument?
                        if arg not in fn_var_uses:
                            _lint_script_warning(warnings, script, statement, f'Unused argument "{arg}" of function "{function_name}"')

            # Iterate function statements
            fn_labels_defined = {}
            fn_labels_used = {}
            for ix_fn_statement, fn_statement in enumerate(fn_statements):
                fn_statement_key = next(iter(fn_statement.keys()))

                # Function expression statement checks
                if fn_statement_key == 'expr':
                    # Pointless function expression statement?
                    if 'name' not in fn_statement['expr'] and _is_pointless_expression(fn_statement['expr']['expr']):
                        _lint_script_warning(warnings, script, statement, f'Pointless statement in function "{function_name}"')

                # Function label statement checks
                elif fn_statement_key == 'label':
                    # Label redefinition?
                    fn_statement_label = fn_statement['label']['name']
                    if fn_statement_label in fn_labels_defined:
                        _lint_script_warning(
                            warnings, script, statement,
                            f'Redefinition of label "{fn_statement_label}" in function "{function_name}"'
                        )
                    else:
                        fn_labels_defined[fn_statement_label] = ix_fn_statement

                # Function jump statement checks
                elif fn_statement_key == 'jump':
                    fn_labels_used[fn_statement['jump']['label']] = ix_fn_statement

            # Unused function labels?
            for label in sorted(fn_labels_defined.keys()):
                if label not in fn_labels_used:
                    _lint_script_warning(warnings, script, statement, f'Unused label "{label}" in function "{function_name}"')

            # Unknown function labels?
            for label in sorted(fn_labels_used.keys()):
                if label not in fn_labels_defined:
                    _lint_script_warning(warnings, script, statement, f'Unknown label "{label}" in function "{function_name}"')

        # Global expression statement checks
        elif statement_key == 'expr':
            # Pointless global expression statement?
            if 'name' not in statement['expr'] and _is_pointless_expression(statement['expr']['expr']):
                _lint_script_warning(warnings, script, statement, 'Pointless global statement')

        # Global label statement checks
        elif statement_key == 'label':
            # Label redefinition?
            statement_label = statement['label']['name']
            if statement_label in labels_defined:
                _lint_script_warning(warnings, script, statement, f'Redefinition of global label "{statement_label}"')
            else:
                labels_defined[statement_label] = ix_statement

        # Global jump statement checks
        elif statement_key == 'jump':
            labels_used[statement['jump']['label']] = ix_statement

    # Unused global labels?
    for label in sorted(labels_defined.keys()):
        if label not in labels_used:
            _lint_script_warning(warnings, script, statements[labels_defined[label]], f'Unused global label "{label}"')

    # Unknown global labels?
    for label in sorted(labels_used.keys()):
        if label not in labels_defined:
            _lint_script_warning(warnings, script, statements[labels_used[label]], f'Unknown global label "{label}"')

    return warnings


# Builtin global variable names
_BUILTIN_GLOBALS = set(['false', 'if', 'null', 'true'])


# Helper to format static analysis warnings
def _lint_script_warning(warnings, script, statement, message):
    script_name = script.get('scriptName', '')
    lineno = statement[next(iter(statement.keys()))].get('lineNumber', 1) if statement is not None else 1
    warnings.append(f'{script_name}:{lineno}: {message}')


# Helper function to determine if an expression statement's expression is pointless
def _is_pointless_expression(expr):
    expr_key = next(iter(expr.keys()))
    if expr_key == 'function':
        return False
    elif expr_key == 'binary':
        return _is_pointless_expression(expr['binary']['left']) and _is_pointless_expression(expr['binary']['right'])
    elif expr_key == 'unary':
        return _is_pointless_expression(expr['unary']['expr'])
    elif expr_key == 'group':
        return _is_pointless_expression(expr['group'])
    return True


# Helper function to set variable assignments/uses for a statements array
def _get_variable_assignments_and_uses(statements, assigns, uses):
    for ix_statement, statement in enumerate(statements):
        statement_key = next(iter(statement.keys()))
        if statement_key == 'expr':
            if 'name' in statement['expr']:
                if statement['expr']['name'] not in assigns:
                    assigns[statement['expr']['name']] = ix_statement
            _get_expression_variable_uses(statement['expr']['expr'], uses, ix_statement)
        elif statement_key == 'jump' and 'expr' in statement['jump']:
            _get_expression_variable_uses(statement['jump']['expr'], uses, ix_statement)
        elif statement_key == 'return' and 'expr' in statement['return']:
            _get_expression_variable_uses(statement['return']['expr'], uses, ix_statement)


# Helper function to set variable uses for an expression
def _get_expression_variable_uses(expr, uses, ix_statement):
    expr_key = next(iter(expr.keys()))
    if expr_key == 'variable':
        if expr['variable'] not in uses:
            uses[expr['variable']] = ix_statement
    elif expr_key == 'binary':
        _get_expression_variable_uses(expr['binary']['left'], uses, ix_statement)
        _get_expression_variable_uses(expr['binary']['right'], uses, ix_statement)
    elif expr_key == 'unary':
        _get_expression_variable_uses(expr['unary']['expr'], uses, ix_statement)
    elif expr_key == 'group':
        _get_expression_variable_uses(expr['group'], uses, ix_statement)
    elif expr_key == 'function':
        if expr['function']['name'] not in uses:
            uses[expr['function']['name']] = ix_statement
        if 'args' in expr['function']:
            for arg_expr in expr['function']['args']:
                _get_expression_variable_uses(arg_expr, uses, ix_statement)
