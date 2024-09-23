# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript value utilities
"""

import datetime
import json
import math
import re
import uuid

from schema_markdown import parse_schema_markdown, validate_type


def value_type(value):
    """
    Get a value's type string

    :param value: The value
    :return: The type string ('array', 'boolean', 'datetime', 'function', 'null', 'number', 'object', 'regex', 'string')
    :rtype: str
    """

    if value is None:
        return 'null'
    elif isinstance(value, str):
        return 'string'
    elif isinstance(value, bool):
        return 'boolean'
    elif isinstance(value, (int, float)):
        return 'number'
    elif isinstance(value, datetime.date):
        return 'datetime'
    elif isinstance(value, dict):
        return 'object'
    elif isinstance(value, list):
        return 'array'
    elif callable(value):
        return 'function'
    elif isinstance(value, REGEX_TYPE):
        return 'regex'

    # Unknown value type
    return None


REGEX_TYPE = type(re.compile(''))


def value_string(value):
    """
    Get a value's string representation

    :param value: The value
    :return: The value as a string
    :rtype: str
    """

    if value is None:
        return 'null'
    elif isinstance(value, str):
        return value
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return R_NUMBER_CLEANUP.sub('', str(value))
    elif isinstance(value, datetime.date):
        iso = value_normalize_datetime(value).astimezone().isoformat()
        match_microsecond = _R_DATETIME_MICROSECOND.search(iso)
        if match_microsecond is not None:
            microsecond_begin, microsecond_end = match_microsecond.span()
            millisecond = int(iso[microsecond_begin + 1:microsecond_end]) // 1000
            iso = f'{iso[0:microsecond_begin]}.{millisecond:0{3}d}{iso[microsecond_end:]}'
        return _R_DATETIME_TZ_CLEANUP.sub(r'\1', iso)
    elif isinstance(value, (dict)):
        return value_json(value)
    elif isinstance(value, (list)):
        return value_json(value)
    elif callable(value):
        return '<function>'
    elif isinstance(value, REGEX_TYPE):
        return '<regex>'

    # Additional types that can be stringified but are otherwise considered unknown
    elif isinstance(value, uuid.UUID):
        return str(value)

    # Unknown value type
    return '<unknown>'


R_NUMBER_CLEANUP = re.compile(r'\.0*$')
_R_DATETIME_MICROSECOND = re.compile(r'\.(\d{6})')
_R_DATETIME_TZ_CLEANUP = re.compile(r'([+-]\d\d:\d\d):\d\d$')


def value_json(value, indent=None):
    """
    Get a value's JSON string representation

    :param value: The value
    :param indent: The JSON indent
    :type indent: int
    :return: The value as a JSON string
    :rtype: str
    """

    if indent is not None and indent > 0:
        result = _JSONEncoder(allow_nan=False, indent=indent, separators=(',', ': '), sort_keys=True).encode(value)
    else:
        result = _JSON_ENCODER_DEFAULT.encode(value)
    result = _R_VALUE_JSON_NUMBER_CLEANUP.sub(r'', result)
    return _R_VALUE_JSON_NUMBER_CLEANUP2.sub(r'\1', result)


class _JSONEncoder(json.JSONEncoder):
    __slots__ = ()

    def default(self, o):
        if isinstance(o, datetime.date):
            return value_string(o)
        return None


_JSON_ENCODER_DEFAULT = _JSONEncoder(allow_nan=False, separators=(',', ':'), sort_keys=True)

_R_VALUE_JSON_NUMBER_CLEANUP = re.compile(r'\.0*$', re.MULTILINE)
_R_VALUE_JSON_NUMBER_CLEANUP2 = re.compile(r'\.0*([,}\]])')


def value_boolean(value):
    """
    Interpret the value as a boolean

    :param value: The value
    :return: The value as a boolean
    :rtype: bool
    """

    if value is None:
        return False
    elif isinstance(value, str):
        return value != ''
    elif isinstance(value, bool):
        return value
    elif isinstance(value, (int, float)):
        return value != 0
    elif isinstance(value, datetime.date):
        return True
    elif isinstance(value, list):
        return len(value) != 0

    # Everything else is true
    return True


def value_is(value1, value2):
    """
    Test if one value is the same object as another

    :param value1: The first value
    :param value2: The second value
    :return: True if values are the same object, false otherwise
    :rtype: bool
    """

    if isinstance(value1, (int, float)) and not isinstance(value1, bool) and \
       isinstance(value2, (int, float)) and not isinstance(value2, bool):
        return value1 == value2

    return value1 is value2


def value_compare(left, right):
    """
    Compare two values

    :param left: The left value
    :param right: The right value
    :return: -1 if the left value is less than the right value, 0 if equal, and 1 if greater than
    :rtype: int
    """

    if left is None:
        return 0 if right is None else -1
    elif right is None:
        return 1
    elif isinstance(left, str) and isinstance(right, str):
        return -1 if left < right else (0 if left == right else 1)
    elif isinstance(left, bool) and isinstance(right, bool):
        return -1 if left < right else (0 if left == right else 1)
    elif isinstance(left, (int, float)) and not isinstance(left, bool) and \
         isinstance(right, (int, float)) and not isinstance(right, bool):
        return -1 if left < right else (0 if left == right else 1)
    elif isinstance(left, datetime.date) and isinstance(right, datetime.date):
        left_dt = value_normalize_datetime(left)
        right_dt = value_normalize_datetime(right)
        return -1 if left_dt < right_dt else (0 if left_dt == right_dt else 1)
    elif isinstance(left, list) and isinstance(right, list):
        for ix in range(min(len(left), len(right))):
            item_compare = value_compare(left[ix], right[ix])
            if item_compare != 0:
                return item_compare
        return -1 if len(left) < len(right) else (0 if len(left) == len(right) else 1)

    # Invalid comparison - compare by type name
    type1 = value_type(left) or 'unknown'
    type2 = value_type(right) or 'unknown'
    return -1 if type1 < type2 else (0 if type1 == type2 else 1)


#
# Function arguments validation
#


def value_args_validate(fn_args, args, error_return_value=None):
    """
    Validate a function's arguments

    :param fn_args: The function arguments model
    :type fn_args: list[dict]
    :param args: The function arguments
    :type args: list
    :param error_return_value: The function's return value on error
    :return: The validated function arguments
    :rtype: list
    """

    for ix, fn_arg in enumerate(fn_args):
        arg_type = fn_arg.get('type')

        # Missing argument?
        if ix >= len(args):
            # Last argument array?
            if fn_arg.get('lastArgArray', False):
                args.append([])
                continue

            # Argument default?
            default_value = fn_arg.get('default')
            if default_value is not None:
                args.append(default_value)
                continue

            # Boolean argument?
            if arg_type == 'boolean':
                args.append(False)
                continue

            # Argument nullable?
            if arg_type is None or fn_arg.get('nullable'):
                args.append(None)
                continue

            # Invalid null value...
            raise ValueArgsError(fn_arg['name'], None, error_return_value)

        # Last arg array?
        if fn_arg.get('lastArgArray'):
            args[ix] = args[ix:]
            del args[ix + 1:]
            continue

        # Any type OK?
        if arg_type is None:
            continue

        # Boolean argument?
        arg_value = args[ix]
        if arg_type == 'boolean':
            args[ix] = value_boolean(arg_value)
            continue

        # Null value?
        if arg_value is None:
            # Argument nullable?
            if not fn_arg.get('nullable'):
                raise ValueArgsError(fn_arg['name'], arg_value, error_return_value)
            continue

        # Invalid value?
        if ((arg_type == 'number' and not isinstance(arg_value, (int, float))) or
            (arg_type == 'string' and not isinstance(arg_value, str)) or
            (arg_type == 'array' and not isinstance(arg_value, list)) or
            (arg_type == 'object' and not isinstance(arg_value, dict)) or
            (arg_type == 'datetime' and not isinstance(arg_value, datetime.date)) or
            (arg_type == 'regex' and not isinstance(arg_value, REGEX_TYPE)) or
            (arg_type == 'function' and not callable(arg_value))):
            raise ValueArgsError(fn_arg['name'], arg_value, error_return_value)

        # Number constraints
        if arg_type == 'number':
            arg_lt = fn_arg.get('lt')
            arg_lte = fn_arg.get('lte')
            arg_gt = fn_arg.get('gt')
            arg_gte = fn_arg.get('gte')
            if ((fn_arg.get('integer') and int(arg_value) != arg_value) or
                (arg_lt is not None and not (arg_value < arg_lt)) or
                (arg_lte is not None and not (arg_value <= arg_lte)) or
                (arg_gt is not None and not (arg_value > arg_gt)) or
                (arg_gte is not None and not (arg_value >= arg_gte))):
                raise ValueArgsError(fn_arg['name'], arg_value, error_return_value)

    # Extra arguments?
    if len(args) > len(fn_args):
        raise ValueArgsError(None, len(args), error_return_value)

    return args


class ValueArgsError(Exception):
    """
    A function arguments validation error

    .. attribute:: return_value

       The function's error return value

    :param arg_name: The function argument name. If `arg_name` is None, there are too many arguments,
        and `arg_value` is the number of arguments.
    :type arg_name: str
    :param arg_value: The function argument value
    :param return_value: The function's error return value
    """

    def __init__(self, arg_name, arg_value, return_value = None):
        if arg_name is None:
            message = f'Too many arguments ({value_json(arg_value)})'
        else:
            message = f'Invalid "{arg_name}" argument value, {value_json(arg_value)}'
        super().__init__(message)
        self.return_value = return_value


def value_args_model(fn_args):
    """
    Validate a function arguments model

    :param fn_args: The function arguments model
    :type fn_args: list[dict]
    :return: The validated function arguments model
    :rtype: list[dict]
    """

    validate_type(VALUE_ARGS_TYPES, 'FunctionArguments', fn_args)

    # Use nullable instead of default-null
    for fn_arg in fn_args:
        if 'default' in fn_arg and fn_arg['default'] is None:
            raise ValueError(f'Argument "{fn_arg["name"]}" has default value of null - use nullable instead')

    return fn_args


# Function arguments type model
VALUE_ARGS_TYPES = parse_schema_markdown('''\
# A function arguments model
typedef FunctionArgument[len > 0] FunctionArguments


# A function argument model
struct FunctionArgument

    # The argument name
    string name

    # The argument type
    optional FunctionArgumentType type

    # If true, the argument may be null
    optional bool nullable

    # The default argument value
    optional object default

    # If true, this argument is the array of remaining arguments
    optional object lastArgArray

    # If true, the number argument must be an integer
    optional bool integer

    # The number argument must be less-than
    optional object lt

    # The number argument must be less-than-or-equal-to
    optional object lte

    # The number argument must be greater-than
    optional object gt

    # The number argument must be greater-than-or-equal-to
    optional object gte


# The function argument types
enum FunctionArgumentType
    array
    boolean
    datetime
    function
    number
    object
    regex
    string
''')


#
# Number value functions
#


def value_round_number(value, digits):
    """
    Round a number

    :param value: The number to round
    :type value: int or float
    :param digits: The number of digits of precision
    :type digits: int
    :return: The rounded number
    :rtype: float
    """

    multiplier = 10 ** digits
    return int(value * multiplier + (0.5 if value >= 0 else -0.5)) / multiplier


def value_parse_number(text):
    """
    Parse a number string

    :param text: The string to parse as a number
    :type text: str
    :return: A number value or None if parsing fails
    :rtype: float or None
    """

    try:
        value = float(text)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except ValueError:
        return None


def value_parse_integer(text, radix=10):
    """
    Parse an integer string

    :param text: The string to parse as a integer
    :type text: str
    :param radix: The integer's radix (2 - 36). Default is 10.
    :type radix: int
    :return: An integer value or None if parsing fails
    :rtype: int or None
    """

    try:
        return int(text, radix)
    except ValueError:
        return None


#
# Datetime value functions
#


def value_parse_datetime(text):
    """
    Parse a datetime string

    :param text: The string to parse as a datetime
    :type text: str
    :return: A datetime value or None if parsing fails
    :rtype: datetime.datetime or None
    """

    m_date = _R_DATE.match(text)
    if m_date is not None:
        year = int(m_date.group('year'))
        month = int(m_date.group('month'))
        day = int(m_date.group('day'))
        return datetime.datetime(year, month, day)
    elif _R_DATETIME.match(text):
        result = datetime.datetime.fromisoformat(_R_DATETIME_ZULU.sub('+00:00', text)).astimezone().replace(tzinfo=None)
        return result.replace(microsecond=(result.microsecond // 1000) * 1000)

    return None

_R_DATE = re.compile(r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$')
_R_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$')
_R_DATETIME_ZULU = re.compile(r'Z$')


def value_normalize_datetime(value):
    """
    Normalize a datetime value

    :param value: The datetime value to normalize
    :type value: datetime
    :return: The normalized datetime value
    :rtype: datetime
    """

    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value
    return datetime.datetime(value.year, value.month, value.day)
