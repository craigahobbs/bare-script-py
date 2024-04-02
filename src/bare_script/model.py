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


# A script statement
union ScriptStatement

    # An expression
    ExpressionStatement expr

    # A jump statement
    JumpStatement jump

    # A return statement
    ReturnStatement return

    # A label definition
    string label

    # A function definition
    FunctionStatement function

    # An include statement
    IncludeStatement include


# An expression statement
struct ExpressionStatement

    # The variable name to assign the expression value
    optional string name

    # The expression to evaluate
    Expression expr


# A jump statement
struct JumpStatement

    # The label to jump to
    string label

    # The test expression
    optional Expression expr


# A return statement
struct ReturnStatement

    # The expression to return
    optional Expression expr


# A function definition statement
struct FunctionStatement

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
struct IncludeStatement

    # The list of include scripts to load and execute in the global scope
    IncludeScript[len > 0] includes


# An include script
struct IncludeScript

    # The include script URL
    string url

    # If true, this is a system include
    optional bool system


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


def lint_script(script):
    """
    Lint a BareScript script model

    :param script: The `BareScript model <./model/#var.vName='BareScript'>`__
    :type script: dict
    :return: The list of lint warnings
    :rtype: list[str]
    """

    warnings = []

    # Empty script?
    if len(script['statements']) == 0:
        warnings.append('Empty script')

    # Variable used before assignment?
    var_assigns = {}
    var_uses = {}
    _get_variable_assignments_and_uses(script['statements'], var_assigns, var_uses)
    for var_name in sorted(var_assigns.keys()):
        if var_name in var_uses and var_uses[var_name] <= var_assigns[var_name]:
            warnings.append(
                f'Global variable "{var_name}" used (index {var_uses[var_name]}) before assignment (index {var_assigns[var_name]})'
            )

    # Iterate global statements
    functions_defined = {}
    labels_defined = {}
    labels_used = {}
    for ix_statement, statement in enumerate(script['statements']):
        statement_key = next(iter(statement.keys()))

        # Function definition checks
        if statement_key == 'function':
            function_name = statement['function']['name']

            # Function redefinition?
            if function_name in functions_defined:
                warnings.append(f'Redefinition of function "{function_name}" (index {ix_statement})')
            else:
                functions_defined[function_name] = ix_statement

            # Variable used before assignment?
            fn_var_assigns = {}
            fn_var_uses = {}
            args = statement['function'].get('args')
            _get_variable_assignments_and_uses(statement['function']['statements'], fn_var_assigns, fn_var_uses)
            for var_name in sorted(fn_var_assigns.keys()):
                # Ignore re-assigned function arguments
                if args is not None and var_name in args:
                    continue
                if var_name in fn_var_uses and fn_var_uses[var_name] <= fn_var_assigns[var_name]:
                    warnings.append(
                        f'Variable "{var_name}" of function "{function_name}" used (index {fn_var_uses[var_name]}) ' +
                            f'before assignment (index {fn_var_assigns[var_name]})'
                    )

            # Unused variables?
            for var_name in sorted(fn_var_assigns.keys()):
                if var_name not in fn_var_uses:
                    warnings.append(
                        f'Unused variable "{var_name}" defined in function "{function_name}" (index {fn_var_assigns[var_name]})'
                    )

            # Function argument checks
            if args is not None:
                args_defined = set()
                for arg in args:
                    # Duplicate argument?
                    if arg in args_defined:
                        warnings.append(f'Duplicate argument "{arg}" of function "{function_name}" (index {ix_statement})')
                    else:
                        args_defined.add(arg)

                        # Unused argument?
                        if arg not in fn_var_uses:
                            warnings.append(f'Unused argument "{arg}" of function "{function_name}" (index {ix_statement})')

            # Iterate function statements
            fn_labels_defined = {}
            fn_labels_used = {}
            for ix_fn_statement, fn_statement in enumerate(statement['function']['statements']):
                fn_statement_key = next(iter(fn_statement.keys()))

                # Function expression statement checks
                if fn_statement_key == 'expr':
                    # Pointless function expression statement?
                    if 'name' not in fn_statement['expr'] and _is_pointless_expression(fn_statement['expr']['expr']):
                        warnings.append(f'Pointless statement in function "{function_name}" (index {ix_fn_statement})')

                # Function label statement checks
                elif fn_statement_key == 'label':
                    # Label redefinition?
                    fn_statement_label = fn_statement['label']
                    if fn_statement_label in fn_labels_defined:
                        warnings.append(
                            f'Redefinition of label "{fn_statement_label}" in function "{function_name}" (index {ix_fn_statement})'
                        )
                    else:
                        fn_labels_defined[fn_statement_label] = ix_fn_statement

                # Function jump statement checks
                elif fn_statement_key == 'jump':
                    fn_labels_used[fn_statement['jump']['label']] = ix_fn_statement

            # Unused function labels?
            for label in sorted(fn_labels_defined.keys()):
                if label not in fn_labels_used:
                    warnings.append(f'Unused label "{label}" in function "{function_name}" (index {fn_labels_defined[label]})')

            # Unknown function labels?
            for label in sorted(fn_labels_used.keys()):
                if label not in fn_labels_defined:
                    warnings.append(f'Unknown label "{label}" in function "{function_name}" (index {fn_labels_used[label]})')

        # Global expression statement checks
        elif statement_key == 'expr':
            # Pointless global expression statement?
            if 'name' not in statement['expr'] and _is_pointless_expression(statement['expr']['expr']):
                warnings.append(f'Pointless global statement (index {ix_statement})')

        # Global label statement checks
        elif statement_key == 'label':
            # Label redefinition?
            statement_label = statement['label']
            if statement_label in labels_defined:
                warnings.append(f'Redefinition of global label "{statement_label}" (index {ix_statement})')
            else:
                labels_defined[statement_label] = ix_statement

        # Global jump statement checks
        elif statement_key == 'jump':
            labels_used[statement['jump']['label']] = ix_statement

    # Unused global labels?
    for label in sorted(labels_defined.keys()):
        if label not in labels_used:
            warnings.append(f'Unused global label "{label}" (index {labels_defined[label]})')

    # Unknown global labels?
    for label in sorted(labels_used.keys()):
        if label not in labels_defined:
            warnings.append(f'Unknown global label "{label}" (index {labels_used[label]})')

    return warnings


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
