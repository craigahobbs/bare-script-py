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

    :param script: The `BareScript model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='BareScript'>`__
    :type script: dict
    :return: The validated BareScript model
    :rtype: dict
    :raises ~schema_markdown.ValidationError: A validation error occurred
    """
    return validate_type(BARE_SCRIPT_TYPES, 'BareScript', script)


def validate_expression(expr):
    """
    Validate an expression model

    :param script: The `expression model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='Expression'>`__
    :type script: dict
    :return: The validated expression model
    :rtype: dict
    :raises ~schema_markdown.ValidationError: A validation error occurred
    """
    return validate_type(BARE_SCRIPT_TYPES, 'Expression', expr)


def lint_script(script):
    """
    Lint a BareScript script model

    :param script: The `BareScript model <https://craigahobbs.github.io/bare-script-py/model/#var.vName='BareScript'>`__
    :type script: dict
    :return: The list of lint warnings
    :rtype: list[str]
    """
    return [] if script else []
