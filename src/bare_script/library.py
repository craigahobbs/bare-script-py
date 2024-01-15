# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript library
"""

import calendar
import datetime
import functools
import json
import math
import random
import re
import urllib

from schema_markdown import JSONEncoder, TYPE_MODEL, parse_schema_markdown, validate_type, validate_type_model

from .value import R_NUMBER_CLEANUP, round_number, value_boolean, value_compare, value_string, value_type


# The default maximum statements for executeScript
DEFAULT_MAX_STATEMENTS = 1e9


def default_args(args, defaults, last_arg_array=False):
    """
    Helper function to fill-in default arguments
    """
    len_args = len(args)
    yield from ((args[ix] if ix < len_args else default) for ix, default in enumerate(defaults))
    if last_arg_array:
        yield args[len_args - 1:]


#
# Array functions
#


# $function: arrayCopy
# $group: Array
# $doc: Create a copy of an array
# $arg array: The array to copy
# $return: The array copy
def _array_copy(args, unused_options):
    array, = default_args(args, (None,))
    if not isinstance(array, list):
        return None

    return list(array)


# $function: arrayExtend
# $group: Array
# $doc: Extend one array with another
# $arg array: The array to extend
# $arg array2: The array to extend with
# $return: The extended array
def _array_extend(args, unused_options):
    array, array2 = default_args(args, (None, None))
    if not isinstance(array, list) or not isinstance(array2, list):
        return None

    array.extend(array2)
    return array


# $function: arrayGet
# $group: Array
# $doc: Get an array element
# $arg array: The array
# $arg index: The array element's index
# $return: The array element
def _array_get(args, unused_options):
    array, index = default_args(args, (None, None))
    if not isinstance(array, list) or not isinstance(index, (int, float)) or int(index) != index or index < 0 or index >= len(array):
        return None

    return array[int(index)]


# $function: arrayIndexOf
# $group: Array
# $doc: Find the index of a value in an array
# $arg array: The array
# $arg value: The value to find in the array, or a match function, f(value) -> bool
# $arg index: Optional (default is 0). The index at which to start the search.
# $return: The first index of the value in the array; -1 if not found.
def _array_index_of(args, options):
    array, value, index = default_args(args, (None, None, 0))
    if not isinstance(array, list) or not isinstance(index, (int, float)) or int(index) != index or index < 0 or index >= len(array):
        return -1

    if callable(value):
        for ix in range(int(index), len(array)):
            if value([array[ix]], options):
                return ix
    else:
        for ix in range(int(index), len(array)):
            if value_compare(array[ix], value) == 0:
                return ix

    return -1


# $function: arrayJoin
# $group: Array
# $doc: Join an array with a separator string
# $arg array: The array
# $arg separator: The separator string
# $return: The joined string
def _array_join(args, unused_options):
    array, separator = default_args(args, (None, None))
    if not isinstance(array, list) or not isinstance(separator, str):
        return None

    return separator.join(value_string(value) for value in array)


# $function: arrayLastIndexOf
# $group: Array
# $doc: Find the last index of a value in an array
# $arg array: The array
# $arg value: The value to find in the array, or a match function, f(value) -> bool
# $arg index: Optional (default is the end of the array). The index at which to start the search.
# $return: The last index of the value in the array; -1 if not found.
def _array_last_index_of(args, options):
    array, value, index = default_args(args, (None, None, None))
    if isinstance(array, list) and index is None:
        index = len(array) - 1
    if not isinstance(array, list) or not isinstance(index, (int, float)) or int(index) != index or index < 0 or index >= len(array):
        return -1

    if callable(value):
        for ix in range(int(index), -1, -1):
            if value([array[ix]], options):
                return ix
    else:
        for ix in range(int(index), -1, -1):
            if value_compare(array[ix], value) == 0:
                return ix

    return -1


# $function: arrayLength
# $group: Array
# $doc: Get the length of an array
# $arg array: The array
# $return: The array's length; null if not an array
def _array_length(args, unused_options):
    array, = default_args(args, (None,))
    if not isinstance(array, list):
        return 0

    return len(array)


# $function: arrayNew
# $group: Array
# $doc: Create a new array
# $arg values...: The new array's values
# $return: The new array
def _array_new(args, unused_options):
    return args


# $function: arrayNewSize
# $group: Array
# $doc: Create a new array of a specific size
# $arg size: Optional (default is 0). The new array's size.
# $arg value: Optional (default is 0). The value with which to fill the new array.
# $return: The new array
def _array_new_size(args, unused_options):
    size, value = default_args(args, (0, 0))
    if not isinstance(size, (int, float)) or int(size) != size or size < 0:
        return None

    return list(value for _ in range(int(size)))


# $function: arrayPop
# $group: Array
# $doc: Remove the last element of the array and return it
# $arg array: The array
# $return: The last element of the array; null if the array is empty.
def _array_pop(args, unused_options):
    array, = default_args(args, (None,))
    if not isinstance(array, list) or len(array) == 0:
        return None

    return array.pop()


# $function: arrayPush
# $group: Array
# $doc: Add one or more values to the end of the array
# $arg array: The array
# $arg values...: The values to add to the end of the array
# $return: The array
def _array_push(args, unused_options):
    array, values = default_args(args, (None,), True)
    if not isinstance(array, list):
        return None

    array.extend(values)
    return array


# $function: arraySet
# $group: Array
# $doc: Set an array element value
# $arg array: The array
# $arg index: The index of the element to set
# $arg value: The value to set
# $return: The value
def _array_set(args, unused_options):
    array, index, value = default_args(args, (None, None, None))
    if not isinstance(array, list) or index < 0 or index >= len(array):
        return None

    array[index] = value
    return value


# $function: arrayShift
# $group: Array
# $doc: Remove the first element of the array and return it
# $arg array: The array
# $return: The first element of the array; null if the array is empty.
def _array_shift(args, unused_options):
    array, = default_args(args, (None,))
    if not isinstance(array, list) or len(array) == 0:
        return None

    result = array[0]
    del array[0]
    return result


# $function: arraySlice
# $group: Array
# $doc: Copy a portion of an array
# $arg array: The array
# $arg start: Optional (default is 0). The start index of the slice.
# $arg end: Optional (default is the end of the array). The end index of the slice.
# $return: The new array slice
def _array_slice(args, unused_options):
    array, start, end = default_args(args, (None, 0, None))
    if isinstance(array, list) and end is None:
        end = len(array)
    if not isinstance(array, list) or not isinstance(start, (int, float)) or int(start) != start or start < 0 or start >= len(array) or \
       not isinstance(end, (int, float)) or int(end) != end or end < 0 or end > len(array):
        return None

    return array[int(start):int(end)]


# $function: arraySort
# $group: Array
# $doc: Sort an array
# $arg array: The array
# $arg compareFn: Optional (default is null). The comparison function.
# $return: The sorted array
def _array_sort(args, options):
    array, compare_fn = default_args(args, (None, None))
    if not isinstance(array, list) or (compare_fn is not None and not callable(compare_fn)):
        return None

    if compare_fn is None:
        array.sort(key=functools.cmp_to_key(value_compare))
    else:
        array.sort(key=functools.cmp_to_key(lambda v1, v2: compare_fn([v1, v2], options)))
    return array


#
# Datetime functions
#


# $function: datetimeDay
# $group: Datetime
# $doc: Get the day of the month of a datetime
# $arg datetime: The datetime
# $return: The day of the month
def _datetime_day(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.day


# $function: datetimeHour
# $group: Datetime
# $doc: Get the hour of a datetime
# $arg datetime: The datetime
# $return: The hour
def _datetime_hour(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.hour


# $function: datetimeISOFormat
# $group: Datetime
# $doc: Format the datetime as an ISO date/time string
# $arg datetime: The datetime
# $arg isDate: If true, format the datetime as an ISO date
# $return: The formatted datetime string
def _datetime_iso_format(args, unused_options):
    datetime_, is_date = default_args(args, (None, False))
    if not isinstance(datetime_, datetime.datetime):
        return None

    if value_boolean(is_date):
        return datetime.date(datetime_.year, datetime_.month, datetime_.day).isoformat()
    return datetime_.astimezone(datetime.timezone.utc).isoformat()


# $function: datetimeISOParse
# $group: Datetime
# $doc: Parse an ISO date/time string
# $arg str: The ISO date/time string
# $return: The datetime, or null if parsing fails
def _datetime_iso_parse(args, unused_options):
    string, = default_args(args, (None,))
    if not isinstance(string, str):
        return None

    try:
        return datetime.datetime.fromisoformat(_R_ZULU.sub('+00:00', string))
    except ValueError:
        return None

_R_ZULU = re.compile(r'Z$')


# $function: datetimeMillisecond
# $group: Datetime
# $doc: Get the millisecond of a datetime
# $arg datetime: The datetime
# $return: The millisecond
def _datetime_millisecond(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return int(round_number(datetime_.microsecond / 1000, 0))


# $function: datetimeMinute
# $group: Datetime
# $doc: Get the minute of a datetime
# $arg datetime: The datetime
# $return: The minute
def _datetime_minute(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.minute


# $function: datetimeMonth
# $group: Datetime
# $doc: Get the month (1-12) of a datetime
# $arg datetime: The datetime
# $return: The month
def _datetime_month(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.month


# $function: datetimeNew
# $group: Datetime
# $doc: Create a new datetime
# $arg year: The full year
# $arg month: The month (1-12)
# $arg day: The day of the month
# $arg hour: Optional (default is 0). The hour (0-23).
# $arg minute: Optional (default is 0). The minute.
# $arg second: Optional (default is 0). The second.
# $arg millisecond: Optional (default is 0). The millisecond.
# $return: The new datetime
def _datetime_new(args, unused_options):
    year, month, day, hour, minute, second, millisecond = default_args(args, (None, None, None, 0, 0, 0, 0))
    return _datetime_new_helper(year, month, day, hour, minute, second, millisecond, None)


# $function: datetimeNewUTC
# $group: Datetime
# $doc: Create a new UTC datetime
# $arg year: The full year
# $arg month: The month (1-12)
# $arg day: The day of the month
# $arg hour: Optional (default is 0). The hour (0-23).
# $arg minute: Optional (default is 0). The minute.
# $arg second: Optional (default is 0). The second.
# $arg millisecond: Optional (default is 0). The millisecond.
# $return: The new UTC datetime
def _datetime_new_utc(args, unused_options):
    year, month, day, hour, minute, second, millisecond = default_args(args, (None, None, None, 0, 0, 0, 0))
    return _datetime_new_helper(year, month, day, hour, minute, second, millisecond, tzinfo=datetime.timezone.utc)


# datetimeNew helper function
def _datetime_new_helper(year, month, day, hour, minute, second, millisecond, tzinfo):
    if not isinstance(year, (int, float)) or int(year) != year or \
       not isinstance(month, (int, float)) or int(month) != month or \
       not isinstance(day, (int, float)) or int(day) != day or day < -10000 or day > 10000 or \
       not isinstance(hour, (int, float)) or int(hour) != hour or \
       not isinstance(minute, (int, float)) or int(minute) != minute or \
       not isinstance(second, (int, float)) or int(second) != second or \
       not isinstance(millisecond, (int, float)) or int(millisecond) != millisecond:
        return None

    # Adjust millisecond
    if millisecond < 0 or millisecond >= 1000:
        extra_seconds = millisecond // 1000
        millisecond -= extra_seconds * 1000
        second += extra_seconds

    # Adjust seconds
    if second < 0 or second >= 60:
        extra_minutes = second // 60
        second -= extra_minutes * 60
        minute += extra_minutes

    # Adjust minutes
    if minute < 0 or minute >= 60:
        extra_hours = minute // 60
        minute -= extra_hours * 60
        hour += extra_hours

    # Adjust hours
    if hour < 0 or hour >= 24:
        extra_days = hour // 24
        hour -= extra_days * 24
        day += extra_days

    # Adjust month
    if month < 1 or month > 12:
        extra_years = (month - 1) // 12
        month -= extra_years * 12
        year += extra_years

    # Adjust day
    if day < 1:
        while day < 1:
            year = year if month != 1 else year - 1
            month = month - 1 if month != 1 else 12
            _, month_days = calendar.monthrange(year, month)
            day += month_days
    elif day > 28:
        _, month_days = calendar.monthrange(year, month)
        while day > month_days:
            day -= month_days
            year = year if month != 12 else year + 1
            month = month + 1 if month != 12 else 1
            _, month_days = calendar.monthrange(year, month)

    # Return the datetime
    result = datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), int(millisecond) * 1000, tzinfo)
    return result if tzinfo is not None else result.astimezone()


# $function: datetimeNow
# $group: Datetime
# $doc: Get the current datetime
# $return: The current datetime
def _datetime_now(unused_args, unused_options):
    return datetime.datetime.now()


# $function: datetimeSecond
# $group: Datetime
# $doc: Get the second of a datetime
# $arg datetime: The datetime
# $return: The second
def _datetime_second(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.second


# $function: datetimeToday
# $group: Datetime
# $doc: Get today's datetime
# $return: Today's datetime
def _datetime_today(unused_args, unused_options):
    today = datetime.date.today()
    return datetime.datetime(today.year, today.month, today.day)


# $function: datetimeYear
# $group: Datetime
# $doc: Get the full year of a datetime
# $arg datetime: The datetime
# $return: The full year
def _datetime_year(args, unused_options):
    datetime_, = default_args(args, (None,))
    if not isinstance(datetime_, datetime.datetime):
        return None

    return datetime_.year


#
# JSON functions
#


# $function: jsonParse
# $group: JSON
# $doc: Convert a JSON string to an object
# $arg string: The JSON string
# $return: The object
def _json_parse(args, unused_options):
    string, = default_args(args, (None,))
    if not isinstance(string, str):
        return None

    return json.loads(string)


# $function: jsonStringify
# $group: JSON
# $doc: Convert an object to a JSON string
# $arg value: The object
# $arg space: Optional (default is null). The indentation string or number.
# $return: The JSON string
def _json_stringify(args, unused_options):
    value, space = default_args(args, (None, None))
    if space is not None and (not isinstance(space, (int, float)) or int(space) != space or space < 0):
        return None

    if space is not None:
        separators = (',', ': ')
        space = int(space)
    else:
        separators = (',', ':')
    return JSONEncoder(allow_nan=False, indent=space, separators=separators, sort_keys=True).encode(value)


#
# Math functions
#


# $function: mathAbs
# $group: Math
# $doc: Compute the absolute value of a number
# $arg x: The number
# $return: The absolute value of the number
def _math_abs(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return abs(x)


# $function: mathAcos
# $group: Math
# $doc: Compute the arccosine, in radians, of a number
# $arg x: The number
# $return: The arccosine, in radians, of the number
def _math_acos(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.acos(x)


# $function: mathAsin
# $group: Math
# $doc: Compute the arcsine, in radians, of a number
# $arg x: The number
# $return: The arcsine, in radians, of the number
def _math_asin(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.asin(x)


# $function: mathAtan
# $group: Math
# $doc: Compute the arctangent, in radians, of a number
# $arg x: The number
# $return: The arctangent, in radians, of the number
def _math_atan(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.atan(x)


# $function: mathAtan2
# $group: Math
# $doc: Compute the angle, in radians, between (0, 0) and a point
# $arg y: The Y-coordinate of the point
# $arg x: The X-coordinate of the point
# $return: The angle, in radians
def _math_atan2(args, unused_options):
    y, x = default_args(args, (None, None))
    if not isinstance(y, (int, float)) or not isinstance(x, (int, float)):
        return None

    return math.atan2(y, x)


# $function: mathCeil
# $group: Math
# $doc: Compute the ceiling of a number (round up to the next highest integer)
# $arg x: The number
# $return: The ceiling of the number
def _math_ceil(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.ceil(x)


# $function: mathCos
# $group: Math
# $doc: Compute the cosine of an angle, in radians
# $arg x: The angle, in radians
# $return: The cosine of the angle
def _math_cos(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.cos(x)


# $function: mathFloor
# $group: Math
# $doc: Compute the floor of a number (round down to the next lowest integer)
# $arg x: The number
# $return: The floor of the number
def _math_floor(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.floor(x)


# $function: mathLn
# $group: Math
# $doc: Compute the natural logarithm (base e) of a number
# $arg x: The number
# $return: The natural logarithm of the number
def _math_ln(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)) or x <= 0:
        return None

    return math.log(x)


# $function: mathLog
# $group: Math
# $doc: Compute the logarithm (base 10) of a number
# $arg x: The number
# $arg base: Optional (default is 10). The logarithm base.
# $return: The logarithm of the number
def _math_log(args, unused_options):
    x, base = default_args(args, (None, 10))
    if not isinstance(x, (int, float)) or x <= 0 or not isinstance(base, (int, float)) or base <= 0 or base == 1:
        return None

    return math.log(x, base)


# $function: mathMax
# $group: Math
# $doc: Compute the maximum value
# $arg values...: The values
# $return: The maximum value
def _math_max(args, unused_options):
    for x in args:
        if not isinstance(x, (int, float)):
            return None

    return max(*args)


# $function: mathMin
# $group: Math
# $doc: Compute the minimum value
# $arg values...: The values
# $return: The minimum value
def _math_min(args, unused_options):
    for x in args:
        if not isinstance(x, (int, float)):
            return None

    return min(*args)


# $function: mathPi
# $group: Math
# $doc: Return the number pi
# $return: The number pi
def _math_pi(unused_args, unused_options):
    return math.pi


# $function: mathRandom
# $group: Math
# $doc: Compute a random number between 0 and 1, inclusive
# $return: A random number
def _math_random(unused_args, unused_options):
    return random.random()


# $function: mathRound
# $group: Math
# $doc: Round a number to a certain number of decimal places
# $arg x: The number
# $arg digits: Optional (default is 0). The number of decimal digits to round to.
# $return: The rounded number
def _math_round(args, unused_options):
    x, digits = default_args(args, (None, 0))
    if not isinstance(x, (int, float)) or not isinstance(digits, (int, float)) or int(digits) != digits or digits < 0:
        return None

    return round_number(x, digits)


# $function: mathSign
# $group: Math
# $doc: Compute the sign of a number
# $arg x: The number
# $return: -1 for a negative number, 1 for a positive number, and 0 for zero
def _math_sign(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return -1 if x < 0 else (0 if x == 0 else 1)


# $function: mathSin
# $group: Math
# $doc: Compute the sine of an angle, in radians
# $arg x: The angle, in radians
# $return: The sine of the angle
def _math_sin(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.sin(x)


# $function: mathSqrt
# $group: Math
# $doc: Compute the square root of a number
# $arg x: The number
# $return: The square root of the number
def _math_sqrt(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)) or x < 0:
        return None

    return math.sqrt(x)


# $function: mathTan
# $group: Math
# $doc: Compute the tangent of an angle, in radians
# $arg x: The angle, in radians
# $return: The tangent of the angle
def _math_tan(args, unused_options):
    x, = default_args(args, (None,))
    if not isinstance(x, (int, float)):
        return None

    return math.tan(x)


#
# Number functions
#


# $function: numberParseFloat
# $group: Number
# $doc: Parse a string as a floating point number
# $arg string: The string
# $return: The number
def _number_parse_float(args, unused_options):
    string, = default_args(args, (None,))
    if not isinstance(string, str):
        return None

    try:
        return float(string)
    except ValueError:
        return None


# $function: numberParseInt
# $group: Number
# $doc: Parse a string as an integer
# $arg string: The string
# $arg radix: Optional (default is 10). The number base.
# $return: The integer
def _number_parse_int(args, unused_options):
    string, radix = default_args(args, (None, 10))
    if not isinstance(string, str) or not isinstance(radix, (int, float)) or int(radix) != radix or radix < 2 or radix > 36:
        return None

    try:
        return int(string, int(radix))
    except ValueError:
        return None


# $function: numberToFixed
# $group: Number
# $doc: Format a number using fixed-point notation
# $arg x: The number
# $arg digits: Optional (default is 2). The number of digits to appear after the decimal point.
# $arg trim: Optional (default is false). If true, trim trailing zeroes and decimal point.
# $return: The fixed-point notation string
def _number_to_fixed(args, unused_options):
    x, digits, trim = default_args(args, (None, 2, False))
    if not isinstance(x, (int, float)) or not isinstance(digits, (int, float)) or int(digits) != digits or digits < 0:
        return None

    result = f'{round_number(x, digits):.{int(digits)}f}'
    if value_boolean(trim):
        return R_NUMBER_CLEANUP.sub('', result)
    return result


#
# Object functions
#


# $function: objectAssign
# $group: Object
# $doc: Assign the keys/values of one object to another
# $arg object: The object to assign to
# $arg object2: The object to assign
# $return: The updated object
def _object_assign(args, unused_options):
    object_, object2 = default_args(args, (None, None))
    if not isinstance(object_, dict) or not isinstance(object2, dict):
        return None

    object_.update(object2)
    return object_


# $function: objectCopy
# $group: Object
# $doc: Create a copy of an object
# $arg object: The object to copy
# $return: The object copy
def _object_copy(args, unused_options):
    object_, = default_args(args, (None,))
    if not isinstance(object_, dict):
        return None

    return dict(object_)


# $function: objectDelete
# $group: Object
# $doc: Delete an object key
# $arg object: The object
# $arg key: The key to delete
def _object_delete(args, unused_options):
    object_, key = default_args(args, (None, None))
    if not isinstance(object_, dict) or not isinstance(key, str):
        return None

    if key in object_:
        del object_[key]
    return None


# $function: objectGet
# $group: Object
# $doc: Get an object key's value
# $arg object: The object
# $arg key: The key
# $arg defaultValue: The default value (optional)
# $return: The value or null if the key does not exist
def _object_get(args, unused_options):
    object_, key, default_value = default_args(args, (None, None, None))
    if not isinstance(object_, dict) or not isinstance(key, str):
        return default_value

    return object_.get(key, default_value)


# $function: objectHas
# $group: Object
# $doc: Test if an object contains a key
# $arg object: The object
# $arg key: The key
# $return: true if the object contains the key, false otherwise
def _object_has(args, unused_options):
    object_, key = default_args(args, (None, None))
    if not isinstance(object_, dict) or not isinstance(key, str):
        return False

    return key in object_


# $function: objectKeys
# $group: Object
# $doc: Get an object's keys
# $arg object: The object
# $return: The array of keys; null if not an object
def _object_keys(args, unused_options):
    object_, = default_args(args, (None,))
    if not isinstance(object_, dict):
        return None

    return list(object_.keys())


# $function: objectNew
# $group: Object
# $doc: Create a new object
# $arg keyValues...: The object's initial key and value pairs
# $return: The new object
def _object_new(args, unused_options):
    args_length = len(args)
    object_ = {}
    ix = 0
    while ix < args_length:
        object_[args[ix]] = (args[ix + 1] if ix + 1 < len(args) else None)
        ix += 2
    return object_


# $function: objectSet
# $group: Object
# $doc: Set an object key's value
# $arg object: The object
# $arg key: The key
# $arg value: The value to set
# $return: The value to set
def _object_set(args, unused_options):
    object_, key, value = default_args(args, (None, None, None))
    if not isinstance(object_, dict) or not isinstance(key, str):
        return None

    object_[key] = value
    return value


#
# Regular expression functions
#


# $function: regexNew
# $group: Regex
# $doc: Create a regular expression
# $arg pattern: The regular expression pattern string
# $arg flags: The [regular expression flags
# $arg flags: ](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Regular_Expressions#advanced_searching_with_flags)
# $return: The regular expression or null if the pattern is invalid
def _regex_new(unused_args, unused_options):
    return None


# Regex escape regular expression
_R_REGEX_ESCAPE = re.compile(r'[.*+?^${}()|[\]\\]')


#
# Schema functions
#

# $function: schemaParse
# $group: Schema
# $doc: Parse the [Schema Markdown](https://craigahobbs.github.io/schema-markdown-js/language/) text
# $arg lines...: The [Schema Markdown](https://craigahobbs.github.io/schema-markdown-js/language/)
# $arg lines...: text lines (may contain nested arrays of un-split lines)
# $return: The schema's [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
def _schema_parse(args, unused_options):
    return parse_schema_markdown(args)


# $function: schemaParseEx
# $group: Schema
# $doc: Parse the [Schema Markdown](https://craigahobbs.github.io/schema-markdown-js/language/) text with options
# $arg lines: The array of [Schema Markdown](https://craigahobbs.github.io/schema-markdown-js/language/)
# $arg lines: text lines (may contain nested arrays of un-split lines)
# $arg types: Optional. The [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types').
# $arg filename: Optional (default is ""). The file name.
# $return: The schema's [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
def _schema_parse_ex(args, unused_options):
    lines, types, filename = default_args(args, (None, {}, ''))
    if not isinstance(lines, (list, str)) or not isinstance(types, dict) or not isinstance(filename, str):
        return None

    return parse_schema_markdown(lines, types, filename)


# $function: schemaTypeModel
# $group: Schema
# $doc: Get the [Schema Markdown Type Model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
# $return: The [Schema Markdown Type Model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
def _schema_type_model(unused_args, unused_options):
    return TYPE_MODEL


# $function: schemaValidate
# $group: Schema
# $doc: Validate an object to a schema type
# $arg types: The [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
# $arg typeName: The type name
# $arg value: The object to validate
# $return: The validated object or null if validation fails
def _schema_validate(args, unused_options):
    types, type_name, value = default_args(args, (None, None, None))
    if not isinstance(types, dict) or not isinstance(type_name, str):
        return None

    validate_type_model(types)
    return validate_type(types, type_name, value)


# $function: schemaValidateTypeModel
# $group: Schema
# $doc: Validate a [Schema Markdown Type Model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
# $arg types: The [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types') to validate
# $return: The validated [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
def _schema_validate_type_model(args, unused_options):
    types, = default_args(args, (None,))
    if not isinstance(types, dict):
        return None

    return validate_type_model(types)


#
# String functions
#


# $function: stringCharCodeAt
# $group: String
# $doc: Get a string index's character code
# $arg string: The string
# $arg index: The character index
# $return: The character code
def _string_char_code_at(args, unused_options):
    string, index = args
    return ord(string[index]) if isinstance(string, str) else None


# $function: stringEndsWith
# $group: String
# $doc: Determine if a string ends with a search string
# $arg string: The string
# $arg searchString: The search string
# $return: true if the string ends with the search string, false otherwise
def _string_ends_with(args, unused_options):
    string, search_string = args
    return string.endswith(search_string) if isinstance(string, str) else None


# $function: stringFromCharCode
# $group: String
# $doc: Create a string of characters from character codes
# $arg charCodes...: The character codes
# $return: The string of characters
def _string_from_char_code(args, unused_options):
    return ''.join(chr(code) for code in args)


# $function: stringIndexOf
# $group: String
# $doc: Find the first index of a search string in a string
# $arg string: The string
# $arg searchString: The search string
# $arg index: Optional (default is 0). The index at which to start the search.
# $return: The first index of the search string; -1 if not found.
def _string_index_of(args, unused_options):
    string, search_string, index = default_args(args, (None, None, None))
    return string.find(search_string, index) if isinstance(string, str) else -1


# $function: stringLastIndexOf
# $group: String
# $doc: Find the last index of a search string in a string
# $arg string: The string
# $arg searchString: The search string
# $arg index: Optional (default is the end of the string). The index at which to start the search.
# $return: The last index of the search string; -1 if not found.
def _string_last_index_of(args, unused_options):
    string, search_string, index = default_args(args, (None, None, None))
    return string.rfind(search_string, index) if isinstance(string, str) else -1


# $function: stringLength
# $group: String
# $doc: Get the length of a string
# $arg string: The string
# $return: The string's length; null if not a string
def _string_length(args, unused_options):
    string, = args
    return len(string) if isinstance(string, str) else None


# $function: stringLower
# $group: String
# $doc: Convert a string to lower-case
# $arg string: The string
# $return: The lower-case string
def _string_lower(args, unused_options):
    string, = args
    return string.lower() if isinstance(string, str) else None


# $function: stringNew
# $group: String
# $doc: Create a new string from a value
# $arg value: The value
# $return: The new string
def _string_new(args, unused_options):
    value, = args
    return value_string(value)


# $function: stringRepeat
# $group: String
# $doc: Repeat a string
# $arg string: The string to repeat
# $arg count: The number of times to repeat the string
# $return: The repeated string
def _string_repeat(args, unused_options):
    string, count = args
    return string * count if isinstance(string, str) else None


# $function: stringReplace
# $group: String
# $doc: Replace all instances of a string with another string
# $arg string: The string to update
# $arg substr: The string to replace
# $arg newSubstr: The replacement string
# $return: The updated string
def _string_replace(args, unused_options):
    string, substr, new_substr = args
    if not isinstance(string, str):
        return None
    return string.replace(substr, new_substr)


# $function: stringSlice
# $group: String
# $doc: Copy a portion of a string
# $arg string: The string
# $arg start: Optional (default is 0). The start index of the slice.
# $arg end: Optional (default is the end of the string). The end index of the slice.
# $return: The new string slice
def _string_slice(args, unused_options):
    string, begin_index, end_index = args
    return string[begin_index:end_index] if isinstance(string, str) else None


# $function: stringSplit
# $group: String
# $doc: Split a string
# $arg string: The string to split
# $arg separator: The separator string or regular expression
# $arg limit: The maximum number of strings to split into
# $return: The array of split-out strings
def _string_split(args, unused_options):
    string, separator, limit = default_args(args, (None, None, -1))
    return string.split(separator, limit) if isinstance(string, str) else None


# $function: stringStartsWith
# $group: String
# $doc: Determine if a string starts with a search string
# $arg string: The string
# $arg searchString: The search string
# $return: true if the string starts with the search string, false otherwise
def _string_starts_with(args, unused_options):
    string, search_string = args
    return string.startswith(search_string) if isinstance(string, str) else None


# $function: stringTrim
# $group: String
# $doc: Trim the whitespace from the beginning and end of a string
# $arg string: The string
# $return: The trimmed string
def _string_trim(args, unused_options):
    string, = args
    return string.strip() if isinstance(string, str) else None


# $function: stringUpper
# $group: String
# $doc: Convert a string to upper-case
# $arg string: The string
# $return: The upper-case string
def _string_upper(args, unused_options):
    string, = args
    return string.upper() if isinstance(string, str) else None


#
# System functions
#


# $function: systemFetch
# $group: System
# $doc: Retrieve a remote JSON or text resource
# $arg url: The resource URL or array of URLs
# $arg options: Optional (default is null). The [fetch options](https://developer.mozilla.org/en-US/docs/Web/API/fetch#parameters).
# $arg isText: Optional (default is false). If true, retrieve the resource as text.
# $return: The resource object/string or array of objects/strings; null if an error occurred.
def _system_fetch(args, options):
    urls, unused_fetch_options, is_text = default_args(args, (None, None, False))
    is_array = isinstance(urls, list)
    if not is_array:
        urls = [urls]
    log_fn = options.get('logFn') if options is not None else None
    url_fn = options.get('urlFn') if options is not None else None
    fetch_fn = options.get('fetchFn') if options is not None else None
    values = []
    for url in urls:
        # Update the URL
        if url_fn is not None:
            url = url_fn(url)

        # Fetch the URL
        value = None
        if fetch_fn is not None:
            try:
                value = fetch_fn(url)
                if not value_boolean(is_text):
                    value = json.loads(value)
            except: # pylint: disable=bare-except
                pass
        values.append(value)

        # Log failure
        if value is None and log_fn is not None and options.get('debug'):
            log_fn(f'BareScript: Function "systemFetch" failed for {"text" if is_text else "JSON"} resource "{url}"')

    return values if is_array else values[0]


# $function: systemGlobalGet
# $group: System
# $doc: Get a global variable value
# $arg name: The global variable name
# $return: The global variable's value or null if it does not exist
def _system_global_get(args, options):
    name, = args
    globals_ = options.get('globals') if options is not None else None
    return globals_[name] if globals_ is not None else None


# $function: systemGlobalSet
# $group: System
# $doc: Set a global variable value
# $arg name: The global variable name
# $arg value: The global variable's value
# $return: The global variable's value
def _system_global_set(args, options):
    name, value = args
    globals_ = options.get('globals') if options is not None else None
    if globals_ is not None:
        globals_[name] = value
    return value


# $function: systemLog
# $group: System
# $doc: Log a message to the console
# $arg string: The message
def _system_log(args, options):
    string, = args
    log_fn = options.get('logFn') if options is not None else None
    if log_fn is not None:
        log_fn(string)


# $function: systemLogDebug
# $group: System
# $doc: Log a message to the console, if in debug mode
# $arg string: The message
def _system_log_debug(args, options):
    string, = args
    log_fn = options.get('logFn') if options is not None else None
    if log_fn is not None and options.get('debug'):
        log_fn(string)


# $function: systemPartial
# $group: System
# $doc: Return a new function which behaves like "func" called with "args".
# $doc: If additional arguments are passed to the returned function, they are appended to "args".
# $arg func: The function
# $arg args...: The function arguments
# $return: The new function called with "args"
def _system_partial(args, unused_options):
    return functools.partial(args[0], *args[1:])


# $function: systemType
# $group: System
# $doc: Get a value's type string
# $arg value: The value
# $return: The type string of the value.
# $return: Valid values are: 'array', 'boolean', 'datetime', 'function', 'null', 'number', 'object', 'regex', 'string'.
def _system_type(args, unused_options):
    value, = args
    return value_type(value)


#
# URL functions
#


# $function: urlEncode
# $group: URL
# $doc: Encode a URL
# $arg url: The URL string
# $arg extra: Optional (default is true). If true, encode extra characters for wider compatibility.
# $return: The encoded URL string
def _url_encode(args, unused_options):
    url, extra = default_args(args, (None, True))
    if not isinstance(url, str):
        return None

    safe = ':/&(' if value_boolean(extra) else ':/&()'
    return urllib.parse.quote(url, safe=safe)


# $function: urlEncodeComponent
# $group: URL
# $doc: Encode a URL component
# $arg url: The URL component string
# $arg extra: Optional (default is true). If true, encode extra characters for wider compatibility.
# $return: The encoded URL component string
def _url_encode_component(args, unused_options):
    url, extra = default_args(args, (None, True))
    if not isinstance(url, str):
        return None

    safe = '(' if value_boolean(extra) else '()'
    return urllib.parse.quote(url, safe=safe)


# The built-in script functions
SCRIPT_FUNCTIONS = {
    'arrayCopy': _array_copy,
    'arrayExtend': _array_extend,
    'arrayGet': _array_get,
    'arrayIndexOf': _array_index_of,
    'arrayJoin': _array_join,
    'arrayLastIndexOf': _array_last_index_of,
    'arrayLength': _array_length,
    'arrayNew': _array_new,
    'arrayNewSize': _array_new_size,
    'arrayPop': _array_pop,
    'arrayPush': _array_push,
    'arraySet': _array_set,
    'arrayShift': _array_shift,
    'arraySlice': _array_slice,
    'arraySort': _array_sort,
    'datetimeDay': _datetime_day,
    'datetimeHour': _datetime_hour,
    'datetimeISOFormat': _datetime_iso_format,
    'datetimeISOParse': _datetime_iso_parse,
    'datetimeMillisecond': _datetime_millisecond,
    'datetimeMinute': _datetime_minute,
    'datetimeMonth': _datetime_month,
    'datetimeNew': _datetime_new,
    'datetimeNewUTC': _datetime_new_utc,
    'datetimeNow': _datetime_now,
    'datetimeSecond': _datetime_second,
    'datetimeToday': _datetime_today,
    'datetimeYear': _datetime_year,
    'jsonParse': _json_parse,
    'jsonStringify': _json_stringify,
    'mathAbs': _math_abs,
    'mathAcos': _math_acos,
    'mathAsin': _math_asin,
    'mathAtan': _math_atan,
    'mathAtan2': _math_atan2,
    'mathCeil': _math_ceil,
    'mathCos': _math_cos,
    'mathFloor': _math_floor,
    'mathLn': _math_ln,
    'mathLog': _math_log,
    'mathMax': _math_max,
    'mathMin': _math_min,
    'mathPi': _math_pi,
    'mathRandom': _math_random,
    'mathRound': _math_round,
    'mathSign': _math_sign,
    'mathSin': _math_sin,
    'mathSqrt': _math_sqrt,
    'mathTan': _math_tan,
    'numberParseInt': _number_parse_int,
    'numberParseFloat': _number_parse_float,
    'numberToFixed': _number_to_fixed,
    'objectAssign': _object_assign,
    'objectCopy': _object_copy,
    'objectDelete': _object_delete,
    'objectGet': _object_get,
    'objectHas': _object_has,
    'objectKeys': _object_keys,
    'objectNew': _object_new,
    'objectSet': _object_set,
    'regexNew': _regex_new,
    'schemaParse': _schema_parse,
    'schemaParseEx': _schema_parse_ex,
    'schemaTypeModel': _schema_type_model,
    'schemaValidate': _schema_validate,
    'schemaValidateTypeModel': _schema_validate_type_model,
    'stringCharCodeAt': _string_char_code_at,
    'stringEndsWith': _string_ends_with,
    'stringFromCharCode': _string_from_char_code,
    'stringIndexOf': _string_index_of,
    'stringLastIndexOf': _string_last_index_of,
    'stringLength': _string_length,
    'stringLower': _string_lower,
    'stringNew': _string_new,
    'stringRepeat': _string_repeat,
    'stringReplace': _string_replace,
    'stringSlice': _string_slice,
    'stringSplit': _string_split,
    'stringStartsWith': _string_starts_with,
    'stringTrim': _string_trim,
    'stringUpper': _string_upper,
    'systemFetch': _system_fetch,
    'systemGlobalGet': _system_global_get,
    'systemGlobalSet': _system_global_set,
    'systemLog': _system_log,
    'systemLogDebug': _system_log_debug,
    'systemPartial': _system_partial,
    'systemType': _system_type,
    'urlEncode': _url_encode,
    'urlEncodeComponent': _url_encode_component
}


# The built-in expression function name script function name map
EXPRESSION_FUNCTION_MAP = {
    'abs': 'mathAbs',
    'acos': 'mathAcos',
    'asin': 'mathAsin',
    'atan': 'mathAtan',
    'atan2': 'mathAtan2',
    'ceil': 'mathCeil',
    'charCodeAt': 'stringCharCodeAt',
    'cos': 'mathCos',
    'date': 'datetimeNew',
    'day': 'datetimeDay',
    'endsWith': 'stringEndsWith',
    'indexOf': 'stringIndexOf',
    'fixed': 'numberToFixed',
    'floor': 'mathFloor',
    'fromCharCode': 'stringFromCharCode',
    'hour': 'datetimeHour',
    'lastIndexOf': 'stringLastIndexOf',
    'len': 'stringLength',
    'lower': 'stringLower',
    'ln': 'mathLn',
    'log': 'mathLog',
    'max': 'mathMax',
    'min': 'mathMin',
    'millisecond': 'datetimeMillisecond',
    'minute': 'datetimeMinute',
    'month': 'datetimeMonth',
    'now': 'datetimeNow',
    'parseInt': 'numberParseInt',
    'parseFloat': 'numberParseFloat',
    'pi': 'mathPi',
    'rand': 'mathRandom',
    'replace': 'stringReplace',
    'rept': 'stringRepeat',
    'round': 'mathRound',
    'second': 'datetimeSecond',
    'sign': 'mathSign',
    'sin': 'mathSin',
    'slice': 'stringSlice',
    'sqrt': 'mathSqrt',
    'startsWith': 'stringStartsWith',
    'text': 'stringNew',
    'tan': 'mathTan',
    'today': 'datetimeToday',
    'trim': 'stringTrim',
    'upper': 'stringUpper',
    'year': 'datetimeYear'
}


# The built-in expression functions
EXPRESSION_FUNCTIONS = dict(
    (expr_fn_name, SCRIPT_FUNCTIONS[script_fn_name]) for expr_fn_name, script_fn_name in EXPRESSION_FUNCTION_MAP.items()
)
