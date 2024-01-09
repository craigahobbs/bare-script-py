# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript value type utilities
"""

import datetime
import json
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
    elif isinstance(value, (int, float)):
        return 'number'
    elif isinstance(value, bool):
        return 'bool'
    elif isinstance(value, datetime.datetime):
        return 'datetime'
    elif isinstance(value, dict):
        return 'object'
    elif isinstance(value, list):
        return 'array'
    elif callable(value):
        return 'function'
    elif isinstance(value, _R_REGEX_TYPE):
        return 'regex'

    # Unknown value type
    return None

_R_REGEX_TYPE = type(re.compile(''))


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
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return R_NUMBER_CLEANUP.sub('', str(value))
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, datetime.datetime):
        return value.toISOFormat()
    elif isinstance(value, (dict)):
        return json.dumps(value)
    elif isinstance(value, (list)):
        return json.dumps(value)
    elif callable(value):
        return '<function>'
    elif isinstance(value, _R_REGEX_TYPE):
        return '<regex>'

    # Unknown value type
    return '<unknown>'

R_NUMBER_CLEANUP = re.compile(r'\.0*$')


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
    elif isinstance(value, (int, float)):
        return value != 0
    elif isinstance(value, bool):
        return value
    elif isinstance(value, datetime.datetime):
        return True
    elif isinstance(value, dict):
        return True
    elif isinstance(value, list):
        return len(value) != 0
    elif callable(value):
        return True
    elif isinstance(value, _R_REGEX_TYPE):
        return True

    # Unknown value type
    return False


def value_compare(value1, value2):
    """
    Compare two values

    :param value_left: The left value
    :param value_right: The right value
    :return: -1 if the left value is less than the right value, 0 if equal, and 1 if greater than
    :rtype: int
    """

    # Null?
    if value1 is None:
        return 0 if value2 is None else -1
    elif value2 is None:
        return 1

    # Compare like types
    if isinstance(value1, str) and isinstance(value2, str):
        return -1 if value1 < value2 else (0 if value1 == value2 else 1)
    elif isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
        return -1 if value1 < value2 else (0 if value1 == value2 else 1)
    elif isinstance(value1, bool) and isinstance(value2, bool):
        return -1 if value1 < value2 else (0 if value1 == value2 else 1)
    elif isinstance(value1, datetime.datetime) and isinstance(value2, datetime.datetime):
        return -1 if value1 < value2 else (0 if value1 == value2 else 1)
    elif isinstance(value1, list) and isinstance(value2, list):
        for ix in range(min(len(value1), len(value2))):
            item_compare = value_compare(value1[ix], value2[ix])
            if item_compare != 0:
                return item_compare
        return -1 if len(value1) < len(value2) else (0 if len(value1) == len(value2) else 1)

    # Invalid comparison - compare by type name
    type1 = value_type(value1)
    type2 = value_type(value2)
    return -1 if type1 < type2 else (0 if type1 == type2 else 1)
