# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript value utilities
"""

import datetime
import json
import math
import re


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
    elif isinstance(value, datetime.datetime):
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
    elif isinstance(value, datetime.datetime):
        iso = value.astimezone().isoformat()
        match_microsecond = _R_DATETIME_MICROSECOND.search(iso)
        if match_microsecond is not None:
            microsecond_begin, microsecond_end = match_microsecond.span()
            millisecond = int(iso[microsecond_begin + 1:microsecond_end]) // 1000
            millisecond_str = f'{"0" if millisecond < 100 else ""}{"0" if millisecond < 10 else ''}{millisecond}'
            iso = f'{iso[0:microsecond_begin]}.{millisecond_str}{iso[microsecond_end:]}'
        return iso
    elif isinstance(value, (dict)):
        return value_json(value)
    elif isinstance(value, (list)):
        return value_json(value)
    elif callable(value):
        return '<function>'
    elif isinstance(value, REGEX_TYPE):
        return '<regex>'

    # Unknown value type
    return '<unknown>'


R_NUMBER_CLEANUP = re.compile(r'\.0*$')
_R_DATETIME_MICROSECOND = re.compile(r'\.(\d{6})')


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
        if isinstance(o, datetime.datetime):
            return value_string(o)
        return None


_JSON_ENCODER_DEFAULT = _JSONEncoder(allow_nan=False, separators=(',', ':'), sort_keys=True)

_R_VALUE_JSON_NUMBER_CLEANUP = re.compile(r'.0$', re.MULTILINE)
_R_VALUE_JSON_NUMBER_CLEANUP2 = re.compile(r'\.0([,}\]])')


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
    elif isinstance(value, datetime.datetime):
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
    elif isinstance(left, datetime.datetime) and isinstance(right, datetime.datetime):
        return -1 if left < right else (0 if left == right else 1)
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
