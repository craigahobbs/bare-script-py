# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript library
"""

import calendar
import csv
import datetime
import functools
import json
import math
import random
import re
import urllib

from schema_markdown import TYPE_MODEL, parse_schema_markdown, validate_type, validate_type_model

from .data import aggregate_data, add_calculated_field, filter_data, join_data, sort_data, top_data, validate_data
from .value import R_NUMBER_CLEANUP, ValueArgsError, value_args_model, value_args_validate, \
    value_boolean, value_compare, value_is, value_json, value_normalize_datetime, value_parse_datetime, \
    value_parse_integer, value_parse_number, value_round_number, value_string, value_type


# The default maximum statements for executeScript
DEFAULT_MAX_STATEMENTS = 1e9


#
# Array functions
#


# $function: arrayCopy
# $group: Array
# $doc: Create a copy of an array
# $arg array: The array to copy
# $return: The array copy
def _array_copy(args, unused_options):
    array, = value_args_validate(_ARRAY_COPY_ARGS, args)
    return list(array)

_ARRAY_COPY_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'}
])


# $function: arrayDelete
# $group: Array
# $doc: Delete an array element
# $arg array: The array
# $arg index: The array element's index
# $return: The array element
def _array_delete(args, unused_options):
    array, index = value_args_validate(_ARRAY_DELETE_ARGS, args)
    if index >= len(array):
        raise ValueArgsError('index', index)

    del array[int(index)]

_ARRAY_DELETE_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'index', 'type': 'number', 'integer': True, 'gte': 0}
])


# $function: arrayExtend
# $group: Array
# $doc: Extend one array with another
# $arg array: The array to extend
# $arg array2: The array to extend with
# $return: The extended array
def _array_extend(args, unused_options):
    array, array2 = value_args_validate(_ARRAY_EXTEND_ARGS, args)
    array.extend(array2)
    return array

_ARRAY_EXTEND_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'array2', 'type': 'array'}
])


# $function: arrayGet
# $group: Array
# $doc: Get an array element
# $arg array: The array
# $arg index: The array element's index
# $return: The array element
def _array_get(args, unused_options):
    array, index = value_args_validate(_ARRAY_GET_ARGS, args)
    if index >= len(array):
        raise ValueArgsError('index', index)

    return array[int(index)]

_ARRAY_GET_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'index', 'type': 'number', 'integer': True, 'gte': 0}
])


# $function: arrayIndexOf
# $group: Array
# $doc: Find the index of a value in an array
# $arg array: The array
# $arg value: The value to find in the array, or a match function, f(value) -> bool
# $arg index: Optional (default is 0). The index at which to start the search.
# $return: The first index of the value in the array; -1 if not found.
def _array_index_of(args, options):
    array, value, index = value_args_validate(_ARRAY_INDEX_OF_ARGS, args, -1)
    if index >= len(array):
        raise ValueArgsError('index', index, -1)

    # Value function?
    if value_type(value) == 'function':
        for ix in range(int(index), len(array)):
            if value_boolean(value([array[ix]], options)):
                return ix
    else:
        for ix in range(int(index), len(array)):
            if value_compare(array[ix], value) == 0:
                return ix

    return -1

_ARRAY_INDEX_OF_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'value'},
    {'name': 'index', 'type': 'number', 'default': 0, 'integer': True, 'gte': 0}
])


# $function: arrayJoin
# $group: Array
# $doc: Join an array with a separator string
# $arg array: The array
# $arg separator: The separator string
# $return: The joined string
def _array_join(args, unused_options):
    array, separator = value_args_validate(_ARRAY_JOIN_ARGS, args)
    return separator.join(value_string(value) for value in array)

_ARRAY_JOIN_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'separator', 'type': 'string'}
])


# $function: arrayLastIndexOf
# $group: Array
# $doc: Find the last index of a value in an array
# $arg array: The array
# $arg value: The value to find in the array, or a match function, f(value) -> bool
# $arg index: Optional (default is the end of the array). The index at which to start the search.
# $return: The last index of the value in the array; -1 if not found.
def _array_last_index_of(args, options):
    array, value, index = value_args_validate(_ARRAY_LAST_INDEX_OF_ARGS, args, -1)
    if index is None:
        index = len(array) - 1
    if index >= len(array):
        raise ValueArgsError('index', index, -1)

    # Value function?
    if value_type(value) == 'function':
        for ix in range(int(index), -1, -1):
            if value_boolean(value([array[ix]], options)):
                return ix
    else:
        for ix in range(int(index), -1, -1):
            if value_compare(array[ix], value) == 0:
                return ix

    return -1

_ARRAY_LAST_INDEX_OF_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'value'},
    {'name': 'index', 'type': 'number', 'nullable': True, 'integer': True, 'gte': 0}
])


# $function: arrayLength
# $group: Array
# $doc: Get the length of an array
# $arg array: The array
# $return: The array's length; zero if not an array
def _array_length(args, unused_options):
    array, = value_args_validate(_ARRAY_LENGTH_ARGS, args, 0)
    return len(array)

_ARRAY_LENGTH_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'}
])


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
    size, value = value_args_validate(_ARRAY_NEW_SIZE_ARGS, args)
    return list(value for _ in range(int(size)))

_ARRAY_NEW_SIZE_ARGS = value_args_model([
    {'name': 'size', 'type': 'number', 'default': 0, 'integer': True, 'gte': 0},
    {'name': 'value', 'default': 0}
])


# $function: arrayPop
# $group: Array
# $doc: Remove the last element of the array and return it
# $arg array: The array
# $return: The last element of the array; null if the array is empty.
def _array_pop(args, unused_options):
    array, = value_args_validate(_ARRAY_POP_ARGS, args)
    if len(array) == 0:
        raise ValueArgsError('array', array)

    return array.pop()

_ARRAY_POP_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'}
])


# $function: arrayPush
# $group: Array
# $doc: Add one or more values to the end of the array
# $arg array: The array
# $arg values...: The values to add to the end of the array
# $return: The array
def _array_push(args, unused_options):
    array, values = value_args_validate(_ARRAY_PUSH_ARGS, args)
    array.extend(values)
    return array

_ARRAY_PUSH_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'values', 'lastArgArray': True}
])


# $function: arraySet
# $group: Array
# $doc: Set an array element value
# $arg array: The array
# $arg index: The index of the element to set
# $arg value: The value to set
# $return: The value
def _array_set(args, unused_options):
    array, index, value = value_args_validate(_ARRAY_SET_ARGS, args)
    if index >= len(array):
        raise ValueArgsError('index', index)

    array[index] = value
    return value

_ARRAY_SET_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'index', 'type': 'number', 'integer': True, 'gte': 0},
    {'name': 'value'}
])


# $function: arrayShift
# $group: Array
# $doc: Remove the first element of the array and return it
# $arg array: The array
# $return: The first element of the array; null if the array is empty.
def _array_shift(args, unused_options):
    array, = value_args_validate(_ARRAY_SHIFT_ARGS, args)
    if len(array) == 0:
        raise ValueArgsError('array', array)

    result = array[0]
    del array[0]
    return result

_ARRAY_SHIFT_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'}
])


# $function: arraySlice
# $group: Array
# $doc: Copy a portion of an array
# $arg array: The array
# $arg start: Optional (default is 0). The start index of the slice.
# $arg end: Optional (default is the end of the array). The end index of the slice.
# $return: The new array slice
def _array_slice(args, unused_options):
    array, start, end = value_args_validate(_ARRAY_SLICE_ARGS, args)
    if end is None:
        end = len(array)
    if start > len(array):
        raise ValueArgsError('start', start)
    if end > len(array):
        raise ValueArgsError('end', end)

    return array[int(start):int(end)]

_ARRAY_SLICE_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'start', 'type': 'number', 'default': 0, 'integer': True, 'gte': 0},
    {'name': 'end', 'type': 'number', 'nullable': True, 'integer': True, 'gte': 0}
])


# $function: arraySort
# $group: Array
# $doc: Sort an array
# $arg array: The array
# $arg compareFn: Optional (default is null). The comparison function.
# $return: The sorted array
def _array_sort(args, options):
    array, compare_fn = value_args_validate(_ARRAY_SORT_ARGS, args)
    if compare_fn is None:
        array.sort(key=functools.cmp_to_key(value_compare))
    else:
        array.sort(key=functools.cmp_to_key(lambda v1, v2: compare_fn([v1, v2], options)))
    return array

_ARRAY_SORT_ARGS = value_args_model([
    {'name': 'array', 'type': 'array'},
    {'name': 'compareFn', 'type': 'function', 'nullable': True}
])


#
# Data functions
#


# $function: dataAggregate
# $group: Data
# $doc: Aggregate a data array
# $arg data: The data array
# $arg aggregation: The [aggregation model](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='Aggregation')
# $return: The aggregated data array
def _data_aggregate(args, unused_options):
    data, aggregation = value_args_validate(_DATA_AGGREGATE_ARGS, args)
    return aggregate_data(data, aggregation)

_DATA_AGGREGATE_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'aggregation', 'type': 'object'}
])


# $function: dataCalculatedField
# $group: Data
# $doc: Add a calculated field to a data array
# $arg data: The data array
# $arg fieldName: The calculated field name
# $arg expr: The calculated field expression
# $arg variables: Optional (default is null). A variables object the expression evaluation.
# $return: The updated data array
def _data_calculated_field(args, options):
    data, field_name, expr, variables = value_args_validate(_DATA_CALCULATED_FIELD_ARGS, args)
    return add_calculated_field(data, field_name, expr, variables, options)

_DATA_CALCULATED_FIELD_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'fieldName', 'type': 'string'},
    {'name': 'expr', 'type': 'string'},
    {'name': 'variables', 'type': 'object', 'nullable': True}
])


# $function: dataFilter
# $group: Data
# $doc: Filter a data array
# $arg data: The data array
# $arg expr: The filter expression
# $arg variables: Optional (default is null). A variables object the expression evaluation.
# $return: The filtered data array
def _data_filter(args, options):
    data, expr, variables = value_args_validate(_DATA_FILTER_ARGS, args)
    return filter_data(data, expr, variables, options)

_DATA_FILTER_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'expr', 'type': 'string'},
    {'name': 'variables', 'type': 'object', 'nullable': True}
])


# $function: dataJoin
# $group: Data
# $doc: Join two data arrays
# $arg leftData: The left data array
# $arg rightData: The right data array
# $arg joinExpr: The [join expression](https://craigahobbs.github.io/bare-script/language/#expressions)
# $arg rightExpr: Optional (default is null).
# $arg rightExpr: The right [join expression](https://craigahobbs.github.io/bare-script/language/#expressions)
# $arg isLeftJoin: Optional (default is false). If true, perform a left join (always include left row).
# $arg variables: Optional (default is null). A variables object for join expression evaluation.
# $return: The joined data array
def _data_join(args, options):
    left_data, right_data, join_expr, right_expr, is_left_join, variables = value_args_validate(_DATA_JOIN_ARGS, args)
    return join_data(left_data, right_data, join_expr, right_expr, is_left_join, variables, options)

_DATA_JOIN_ARGS = value_args_model([
    {'name': 'leftData', 'type': 'array'},
    {'name': 'rightData', 'type': 'array'},
    {'name': 'joinExpr', 'type': 'string'},
    {'name': 'rightExpr', 'type': 'string', 'nullable': True},
    {'name': 'isLeftJoin', 'type': 'boolean', 'default': False},
    {'name': 'variables', 'type': 'object', 'nullable': True}
])


# $function: dataParseCSV
# $group: Data
# $doc: Parse CSV text to a data array
# $arg text...: The CSV text
# $return: The data array
def _data_parse_csv(args, unused_options):
    # Split the input CSV parts into lines
    lines = []
    for arg in args:
        if arg is None:
            continue
        if value_type(arg) != 'string':
            return None
        lines.extend(arg.splitlines())

    # Parse the CSV
    data = list(csv.DictReader(lines, skipinitialspace=True))

    # Validate the data (as CSV)
    validate_data(data, True)
    return data


# $function: dataSort
# $group: Data
# $doc: Sort a data array
# $arg data: The data array
# $arg sorts: The sort field-name/descending-sort tuples
# $return: The sorted data array
def _data_sort(args, unused_options):
    data, sorts = value_args_validate(_DATA_SORT_ARGS, args)
    return sort_data(data, sorts)

_DATA_SORT_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'sorts', 'type': 'array'}
])


# $function: dataTop
# $group: Data
# $doc: Keep the top rows for each category
# $arg data: The data array
# $arg count: The number of rows to keep (default is 1)
# $arg categoryFields: Optional (default is null). The category fields.
# $return: The top data array
def _data_top(args, unused_options):
    data, count, category_fields = value_args_validate(_DATA_TOP_ARGS, args)
    return top_data(data, count, category_fields)

_DATA_TOP_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'count', 'type': 'number', 'integer': True, 'gte': 1},
    {'name': 'categoryFields', 'type': 'array', 'nullable': True}
])


# $function: dataValidate
# $group: Data
# $doc: Validate a data array
# $arg data: The data array
# $arg csv: Optional (default is false). If true, parse value strings.
# $return: The validated data array
def _data_validate(args, unused_options):
    data, csv_ = value_args_validate(_DATA_VALIDATE_ARGS, args)
    validate_data(data, csv_)
    return data

_DATA_VALIDATE_ARGS = value_args_model([
    {'name': 'data', 'type': 'array'},
    {'name': 'csv', 'type': 'boolean', 'default': False}
])


#
# Datetime functions
#


# $function: datetimeDay
# $group: Datetime
# $doc: Get the day of the month of a datetime
# $arg datetime: The datetime
# $return: The day of the month
def _datetime_day(args, unused_options):
    datetime_, = value_args_validate(_DATETIME_DAY_ARGS, args)
    return value_normalize_datetime(datetime_).day

_DATETIME_DAY_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


# $function: datetimeHour
# $group: Datetime
# $doc: Get the hour of a datetime
# $arg datetime: The datetime
# $return: The hour
def _datetime_hour(args, unused_options):
    datetime_, = value_args_validate(_DATETIME_HOUR_ARGS, args)
    return value_normalize_datetime(datetime_).hour

_DATETIME_HOUR_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


# $function: datetimeISOFormat
# $group: Datetime
# $doc: Format the datetime as an ISO date/time string
# $arg datetime: The datetime
# $arg isDate: If true, format the datetime as an ISO date
# $return: The formatted datetime string
def _datetime_iso_format(args, unused_options):
    datetime_arg, is_date = value_args_validate(_DATETIMEISO_FORMAT_ARGS, args)

    datetime_ = value_normalize_datetime(datetime_arg)
    if is_date:
        return datetime.date(datetime_.year, datetime_.month, datetime_.day).isoformat()

    return value_string(datetime_)

_DATETIMEISO_FORMAT_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'},
    {'name': 'isDate', 'type': 'boolean', 'default': False}
])


# $function: datetimeISOParse
# $group: Datetime
# $doc: Parse an ISO date/time string
# $arg string: The ISO date/time string
# $return: The datetime, or null if parsing fails
def _datetime_iso_parse(args, unused_options):
    string, = value_args_validate(_DATETIMEISO_PARSE_ARGS, args)
    return value_parse_datetime(string)

_DATETIMEISO_PARSE_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: datetimeMillisecond
# $group: Datetime
# $doc: Get the millisecond of a datetime
# $arg datetime: The datetime
# $return: The millisecond
def _datetime_millisecond(args, unused_options):
    datetime_, = value_args_validate(_DATETIME_MILLISECOND_ARGS, args)
    return int(value_round_number(value_normalize_datetime(datetime_).microsecond / 1000, 0))

_DATETIME_MILLISECOND_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


# $function: datetimeMinute
# $group: Datetime
# $doc: Get the minute of a datetime
# $arg datetime: The datetime
# $return: The minute
def _datetime_minute(args, unused_options):
    datetime_, = value_args_validate(_DATETIME_MINUTE_ARGS, args)
    return value_normalize_datetime(datetime_).minute

_DATETIME_MINUTE_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


# $function: datetimeMonth
# $group: Datetime
# $doc: Get the month (1-12) of a datetime
# $arg datetime: The datetime
# $return: The month
def _datetime_month(args, unused_options):
    datetime_, = value_args_validate(_DATETIME_MONTH_ARGS, args)
    return value_normalize_datetime(datetime_).month

_DATETIME_MONTH_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


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
    year, month, day, hour, minute, second, millisecond = value_args_validate(_DATETIME_NEW_ARGS, args)

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
            _, month_days = calendar.monthrange(int(year), int(month))
            day += month_days
    elif day > 28:
        _, month_days = calendar.monthrange(int(year), int(month))
        while day > month_days:
            day -= month_days
            year = year if month != 12 else year + 1
            month = month + 1 if month != 12 else 1
            _, month_days = calendar.monthrange(int(year), int(month))

    # Return the datetime
    return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), int(millisecond) * 1000)

_DATETIME_NEW_ARGS = value_args_model([
    {'name': 'year', 'type': 'number', 'integer': True, 'gte': 100},
    {'name': 'month', 'type': 'number', 'integer': True},
    {'name': 'day', 'type': 'number', 'integer': True, 'gte': -10000, 'lte': 10000},
    {'name': 'hour', 'type': 'number', 'default': 0, 'integer': True},
    {'name': 'minute', 'type': 'number', 'default': 0, 'integer': True},
    {'name': 'second', 'type': 'number', 'default': 0, 'integer': True},
    {'name': 'millisecond', 'type': 'number', 'default': 0, 'integer': True}
])


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
    datetime_, = value_args_validate(_DATETIME_SECOND_ARGS, args)
    return value_normalize_datetime(datetime_).second

_DATETIME_SECOND_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


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
    datetime_, = value_args_validate(_DATETIME_YEAR_ARGS, args)
    return value_normalize_datetime(datetime_).year

_DATETIME_YEAR_ARGS = value_args_model([
    {'name': 'datetime', 'type': 'datetime'}
])


#
# JSON functions
#


# $function: jsonParse
# $group: JSON
# $doc: Convert a JSON string to an object
# $arg string: The JSON string
# $return: The object
def _json_parse(args, unused_options):
    string, = value_args_validate(_JSON_PARSE_ARGS, args)
    return json.loads(string)

_JSON_PARSE_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: jsonStringify
# $group: JSON
# $doc: Convert an object to a JSON string
# $arg value: The object
# $arg indent: Optional (default is null). The indentation number.
# $return: The JSON string
def _json_stringify(args, unused_options):
    value, indent = value_args_validate(_JSON_STRINGIFY_ARGS, args)
    return value_json(value, int(indent) if indent is not None else None)

_JSON_STRINGIFY_ARGS = value_args_model([
    {'name': 'value'},
    {'name': 'indent', 'type': 'number', 'nullable': True, 'integer': True, 'gte': 1}
])


#
# Math functions
#


# $function: mathAbs
# $group: Math
# $doc: Compute the absolute value of a number
# $arg x: The number
# $return: The absolute value of the number
def _math_abs(args, unused_options):
    x, = value_args_validate(_MATH_ABS_ARGS, args)
    return abs(x)

_MATH_ABS_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathAcos
# $group: Math
# $doc: Compute the arccosine, in radians, of a number
# $arg x: The number
# $return: The arccosine, in radians, of the number
def _math_acos(args, unused_options):
    x, = value_args_validate(_MATH_ACOS_ARGS, args)
    return math.acos(x)

_MATH_ACOS_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathAsin
# $group: Math
# $doc: Compute the arcsine, in radians, of a number
# $arg x: The number
# $return: The arcsine, in radians, of the number
def _math_asin(args, unused_options):
    x, = value_args_validate(_MATH_ASIN_ARGS, args)
    return math.asin(x)

_MATH_ASIN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathAtan
# $group: Math
# $doc: Compute the arctangent, in radians, of a number
# $arg x: The number
# $return: The arctangent, in radians, of the number
def _math_atan(args, unused_options):
    x, = value_args_validate(_MATH_ATAN_ARGS, args)
    return math.atan(x)

_MATH_ATAN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathAtan2
# $group: Math
# $doc: Compute the angle, in radians, between (0, 0) and a point
# $arg y: The Y-coordinate of the point
# $arg x: The X-coordinate of the point
# $return: The angle, in radians
def _math_atan2(args, unused_options):
    y, x = value_args_validate(_MATH_ATAN2_ARGS, args)
    return math.atan2(y, x)

_MATH_ATAN2_ARGS = value_args_model([
    {'name': 'y', 'type': 'number'},
    {'name': 'x', 'type': 'number'}
])


# $function: mathCeil
# $group: Math
# $doc: Compute the ceiling of a number (round up to the next highest integer)
# $arg x: The number
# $return: The ceiling of the number
def _math_ceil(args, unused_options):
    x, = value_args_validate(_MATH_CEIL_ARGS, args)
    return math.ceil(x)

_MATH_CEIL_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathCos
# $group: Math
# $doc: Compute the cosine of an angle, in radians
# $arg x: The angle, in radians
# $return: The cosine of the angle
def _math_cos(args, unused_options):
    x, = value_args_validate(_MATH_COS_ARGS, args)
    return math.cos(x)

_MATH_COS_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathFloor
# $group: Math
# $doc: Compute the floor of a number (round down to the next lowest integer)
# $arg x: The number
# $return: The floor of the number
def _math_floor(args, unused_options):
    x, = value_args_validate(_MATH_FLOOR_ARGS, args)
    return math.floor(x)

_MATH_FLOOR_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathLn
# $group: Math
# $doc: Compute the natural logarithm (base e) of a number
# $arg x: The number
# $return: The natural logarithm of the number
def _math_ln(args, unused_options):
    x, = value_args_validate(_MATH_LN_ARGS, args)
    return math.log(x)

_MATH_LN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number', 'gt': 0}
])


# $function: mathLog
# $group: Math
# $doc: Compute the logarithm (base 10) of a number
# $arg x: The number
# $arg base: Optional (default is 10). The logarithm base.
# $return: The logarithm of the number
def _math_log(args, unused_options):
    x, base = value_args_validate(_MATH_LOG_ARGS, args)
    if base == 1:
        raise ValueArgsError('base', base)

    return math.log(x, base)

_MATH_LOG_ARGS = value_args_model([
    {'name': 'x', 'type': 'number', 'gt': 0},
    {'name': 'base', 'type': 'number', 'default': 10, 'gt': 0}
])


# $function: mathMax
# $group: Math
# $doc: Compute the maximum value
# $arg values...: The values
# $return: The maximum value
def _math_max(values, unused_options):
    result = None
    is_first = True
    for value in values:
        if is_first:
            result = value
            is_first = False
        elif value_compare(value, result) > 0:
            result = value
    return result


# $function: mathMin
# $group: Math
# $doc: Compute the minimum value
# $arg values...: The values
# $return: The minimum value
def _math_min(values, unused_options):
    result = None
    is_first = True
    for value in values:
        if is_first:
            result = value
            is_first = False
        elif value_compare(value, result) < 0:
            result = value
    return result


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
    x, digits = value_args_validate(_MATH_ROUND_ARGS, args)
    return value_round_number(x, digits)

_MATH_ROUND_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'},
    {'name': 'digits', 'type': 'number', 'default': 0, 'integer': True, 'gte': 0}
])


# $function: mathSign
# $group: Math
# $doc: Compute the sign of a number
# $arg x: The number
# $return: -1 for a negative number, 1 for a positive number, and 0 for zero
def _math_sign(args, unused_options):
    x, = value_args_validate(_MATH_SIGN_ARGS, args)
    return -1 if x < 0 else (0 if x == 0 else 1)

_MATH_SIGN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathSin
# $group: Math
# $doc: Compute the sine of an angle, in radians
# $arg x: The angle, in radians
# $return: The sine of the angle
def _math_sin(args, unused_options):
    x, = value_args_validate(_MATH_SIN_ARGS, args)
    return math.sin(x)

_MATH_SIN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


# $function: mathSqrt
# $group: Math
# $doc: Compute the square root of a number
# $arg x: The number
# $return: The square root of the number
def _math_sqrt(args, unused_options):
    x, = value_args_validate(_MATH_SQRT_ARGS, args)
    return math.sqrt(x)

_MATH_SQRT_ARGS = value_args_model([
    {'name': 'x', 'type': 'number', 'gte': 0}
])


# $function: mathTan
# $group: Math
# $doc: Compute the tangent of an angle, in radians
# $arg x: The angle, in radians
# $return: The tangent of the angle
def _math_tan(args, unused_options):
    x, = value_args_validate(_MATH_TAN_ARGS, args)
    return math.tan(x)

_MATH_TAN_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'}
])


#
# Number functions
#


# $function: numberParseFloat
# $group: Number
# $doc: Parse a string as a floating point number
# $arg string: The string
# $return: The number
def _number_parse_float(args, unused_options):
    string, = value_args_validate(_NUMBER_PARSE_FLOAT_ARGS, args)
    return value_parse_number(string)

_NUMBER_PARSE_FLOAT_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: numberParseInt
# $group: Number
# $doc: Parse a string as an integer
# $arg string: The string
# $arg radix: Optional (default is 10). The number base.
# $return: The integer
def _number_parse_int(args, unused_options):
    string, radix = value_args_validate(_NUMBER_PARSE_INT_ARGS, args)
    return value_parse_integer(string, int(radix))

_NUMBER_PARSE_INT_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'radix', 'type': 'number', 'default': 10, 'integer': True, 'gte': 2, 'lte': 36}
])


# $function: numberToFixed
# $group: Number
# $doc: Format a number using fixed-point notation
# $arg x: The number
# $arg digits: Optional (default is 2). The number of digits to appear after the decimal point.
# $arg trim: Optional (default is false). If true, trim trailing zeroes and decimal point.
# $return: The fixed-point notation string
def _number_to_fixed(args, unused_options):
    x, digits, trim = value_args_validate(_NUMBER_TO_FIXED_ARGS, args)
    result = f'{value_round_number(x, digits):.{int(digits)}f}'
    if trim:
        return R_NUMBER_CLEANUP.sub('', result)
    return result

_NUMBER_TO_FIXED_ARGS = value_args_model([
    {'name': 'x', 'type': 'number'},
    {'name': 'digits', 'type': 'number', 'default': 2, 'integer': True, 'gte': 0},
    {'name': 'trim', 'type': 'boolean', 'default': False}
])


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
    object_, object2 = value_args_validate(_OBJECT_ASSIGN_ARGS, args)
    object_.update(object2)
    return object_

_OBJECT_ASSIGN_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'},
    {'name': 'object2', 'type': 'object'}
])


# $function: objectCopy
# $group: Object
# $doc: Create a copy of an object
# $arg object: The object to copy
# $return: The object copy
def _object_copy(args, unused_options):
    object_, = value_args_validate(_OBJECT_COPY_ARGS, args)
    return dict(object_)

_OBJECT_COPY_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'}
])


# $function: objectDelete
# $group: Object
# $doc: Delete an object key
# $arg object: The object
# $arg key: The key to delete
def _object_delete(args, unused_options):
    object_, key = value_args_validate(_OBJECT_DELETE_ARGS, args)
    if key in object_:
        del object_[key]

_OBJECT_DELETE_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'},
    {'name': 'key', 'type': 'string'}
])


# $function: objectGet
# $group: Object
# $doc: Get an object key's value
# $arg object: The object
# $arg key: The key
# $arg defaultValue: The default value (optional)
# $return: The value or null if the key does not exist
def _object_get(args, unused_options):
    default_value_arg = args[2] if len(args) >= 3 else None
    object_, key, default_value = value_args_validate(_OBJECT_GET_ARGS, args, default_value_arg)
    return object_.get(key, default_value)

_OBJECT_GET_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'},
    {'name': 'key', 'type': 'string'},
    {'name': 'defaultValue'}
])


# $function: objectHas
# $group: Object
# $doc: Test if an object contains a key
# $arg object: The object
# $arg key: The key
# $return: true if the object contains the key, false otherwise
def _object_has(args, unused_options):
    object_, key = value_args_validate(_OBJECT_HAS_ARGS, args, False)
    return key in object_

_OBJECT_HAS_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'},
    {'name': 'key', 'type': 'string'}
])


# $function: objectKeys
# $group: Object
# $doc: Get an object's keys
# $arg object: The object
# $return: The array of keys
def _object_keys(args, unused_options):
    object_, = value_args_validate(_OBJECT_KEYS_ARGS, args)
    return list(object_.keys())

_OBJECT_KEYS_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'}
])


# $function: objectNew
# $group: Object
# $doc: Create a new object
# $arg keyValues...: The object's initial key and value pairs
# $return: The new object
def _object_new(args, unused_options):
    object_ = {}
    for ix in range(0, len(args), 2):
        key = args[ix]
        value = args[ix + 1] if ix + 1 < len(args) else None
        if value_type(key) != 'string':
            raise ValueArgsError('keyValues', key)
        object_[key] = value
    return object_


# $function: objectSet
# $group: Object
# $doc: Set an object key's value
# $arg object: The object
# $arg key: The key
# $arg value: The value to set
# $return: The value to set
def _object_set(args, unused_options):
    object_, key, value = value_args_validate(_OBJECT_SET_ARGS, args)
    object_[key] = value
    return value

_OBJECT_SET_ARGS = value_args_model([
    {'name': 'object', 'type': 'object'},
    {'name': 'key', 'type': 'string'},
    {'name': 'value'}
])


#
# Regex functions
#


# $function: regexEscape
# $group: Regex
# $doc: Escape a string for use in a regular expression
# $arg string: The string to escape
# $return: The escaped string
def _regex_escape(args, unused_options):
    string, = value_args_validate(_REGEX_ESCAPE_ARGS, args)
    return re.escape(string)

_REGEX_ESCAPE_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: regexMatch
# $group: Regex
# $doc: Find the first match of a regular expression in a string
# $arg regex: The regular expression
# $arg string: The string
# $return: The [match object](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='RegexMatch'),
# $return: or null if no matches are found
def _regex_match(args, unused_options):
    regex, string = value_args_validate(_REGEX_MATCH_ARGS, args)
    match = regex.search(string)
    return _regex_match_groups(match) if match is not None else None

_REGEX_MATCH_ARGS = value_args_model([
    {'name': 'regex', 'type': 'regex'},
    {'name': 'string', 'type': 'string'}
])


# $function: regexMatchAll
# $group: Regex
# $doc: Find all matches of regular expression in a string
# $arg regex: The regular expression
# $arg string: The string
# $return: The array of [match objects](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='RegexMatch')
def _regex_match_all(args, unused_options):
    regex, string = value_args_validate(_REGEX_MATCH_ALL_ARGS, args)
    return [_regex_match_groups(match) for match in regex.finditer(string)]

_REGEX_MATCH_ALL_ARGS = value_args_model([
    {'name': 'regex', 'type': 'regex'},
    {'name': 'string', 'type': 'string'}
])


# Helper function to create a match model from a metch object
def _regex_match_groups(match):
    groups = {'0': match[0]}
    groups.update((f'{match_ix + 1}', match_text) for match_ix, match_text in enumerate(match.groups()))
    groups.update(match.groupdict())
    return {
        'index': match.start(),
        'input': match.string,
        'groups': groups
    }


# The regex match model
REGEX_MATCH_TYPES = parse_schema_markdown('''\
group "RegexMatch"


# A regex match model
struct RegexMatch

    # The zero-based index of the match in the input string
    int(>= 0) index

    # The input string
    string input

    # The matched groups. The "0" key is the full match text. Ordered (non-named) groups use keys "1", "2", and so on.
    string{} groups
''')


# $function: regexNew
# $group: Regex
# $doc: Create a regular expression
# pylint: disable=line-too-long
# $arg pattern: The [regular expression pattern string](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Regular_expressions#writing_a_regular_expression_pattern)
# pylint: enable=line-too-long
# $arg flags: The regular expression flags. The string may contain the following characters:
# $arg flags: - **i** - case-insensitive search
# $arg flags: - **m** - multi-line search - "^" and "$" matches next to newline characters
# $arg flags: - **s** - "." matches newline characters
# $return: The regular expression or null if the pattern is invalid
def _regex_new(args, unused_options):
    pattern, flags = value_args_validate(_REGEX_NEW_ARGS, args)

    # Translate JavaScript named group syntax to Python
    pattern = _R_REGEX_NEW_NAMED.sub(r'(?P<\1>', pattern)

    # Compute the flags mask
    flags_mask = 0
    if flags is not None:
        for flag in flags:
            if flag == 'i':
                flags_mask = flags_mask | re.I
            elif flag == 'm':
                flags_mask = flags_mask | re.M
            elif flag == 's':
                flags_mask = flags_mask | re.S
            else:
                return None

    return re.compile(pattern, flags_mask)

_REGEX_NEW_ARGS = value_args_model([
    {'name': 'pattern', 'type': 'string'},
    {'name': 'flags', 'type': 'string', 'nullable': True}
])


_R_REGEX_NEW_NAMED = re.compile(r'\(\?<(\w+)>')


# $function: regexReplace
# $group: Regex
# $doc: Replace regular expression matches with a string
# $arg regex: The replacement regular expression
# $arg string: The string
# $arg substr: The replacement string
# $return: The updated string
def _regex_replace(args, unused_options):
    regex, string, substr = value_args_validate(_REGEX_REPLACE_ARGS, args)

    # Escape Python escapes
    substr = substr.replace('\\', '\\\\')

    # Un-escape Javascript escapes
    substr = substr.replace('$$', '$')

    # Translate JavaScript replacers to Python replacers
    substr = _R_REGEX_REPLACE_INDEX.sub(r'\\\1', substr)
    substr = _R_REGEX_REPLACE_NAMED.sub(r'\\g<\1>', substr)

    return regex.sub(substr, string)

_REGEX_REPLACE_ARGS = value_args_model([
    {'name': 'regex', 'type': 'regex'},
    {'name': 'string', 'type': 'string'},
    {'name': 'substr', 'type': 'string'}
])


_R_REGEX_REPLACE_INDEX = re.compile(r'\$(\d+)')
_R_REGEX_REPLACE_NAMED = re.compile(r'\$<(?P<name>[^>]+)>')


# $function: regexSplit
# $group: Regex
# $doc: Split a string with a regular expression
# $arg regex: The regular expression
# $arg string: The string
# $return: The array of split parts
def _regex_split(args, unused_options):
    regex, string = value_args_validate(_REGEX_SPLIT_ARGS, args)
    return regex.split(string)

_REGEX_SPLIT_ARGS = value_args_model([
    {'name': 'regex', 'type': 'regex'},
    {'name': 'string', 'type': 'string'}
])


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
    lines, types, filename = value_args_validate(_SCHEMA_PARSE_EX_ARGS, args)
    lines_type = value_type(lines)
    types = types if types is not None else {}
    if lines_type not in ('array', 'string'):
        raise ValueArgsError('lines', lines)

    return parse_schema_markdown(lines, types, filename)

_SCHEMA_PARSE_EX_ARGS = value_args_model([
    {'name': 'lines'},
    {'name': 'types', 'type': 'object', 'nullable': True},
    {'name': 'filename', 'type': 'string', 'default': ''}
])


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
    types, type_name, value = value_args_validate(_SCHEMA_VALIDATE_ARGS, args)
    validate_type_model(types)
    return validate_type(types, type_name, value)

_SCHEMA_VALIDATE_ARGS = value_args_model([
    {'name': 'types', 'type': 'object'},
    {'name': 'typeName', 'type': 'string'},
    {'name': 'value'}
])


# $function: schemaValidateTypeModel
# $group: Schema
# $doc: Validate a [Schema Markdown Type Model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
# $arg types: The [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types') to validate
# $return: The validated [type model](https://craigahobbs.github.io/schema-markdown-doc/doc/#var.vName='Types')
def _schema_validate_type_model(args, unused_options):
    types, = value_args_validate(_SCHEMA_VALIDATE_TYPE_MODEL_ARGS, args)
    return validate_type_model(types)

_SCHEMA_VALIDATE_TYPE_MODEL_ARGS = value_args_model([
    {'name': 'types', 'type': 'object'}
])


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
    string, index = value_args_validate(_STRING_CHAR_CODE_AT_ARGS, args)
    if index >= len(string):
        raise ValueArgsError('index', index)

    return ord(string[int(index)])

_STRING_CHAR_CODE_AT_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'index', 'type': 'number', 'integer': True, 'gte': 0}
])


# $function: stringEndsWith
# $group: String
# $doc: Determine if a string ends with a search string
# $arg string: The string
# $arg search: The search string
# $return: true if the string ends with the search string, false otherwise
def _string_ends_with(args, unused_options):
    string, search = value_args_validate(_STRING_ENDS_WITH_ARGS, args)
    return string.endswith(search)

_STRING_ENDS_WITH_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'search', 'type': 'string'}
])


# $function: stringFromCharCode
# $group: String
# $doc: Create a string of characters from character codes
# $arg charCodes...: The character codes
# $return: The string of characters
def _string_from_char_code(char_codes, unused_options):
    for code in char_codes:
        if value_type(code) != 'number' or int(code) != code or code < 0:
            raise ValueArgsError('char_codes', code)

    return ''.join(chr(int(code)) for code in char_codes)


# $function: stringIndexOf
# $group: String
# $doc: Find the first index of a search string in a string
# $arg string: The string
# $arg search: The search string
# $arg index: Optional (default is 0). The index at which to start the search.
# $return: The first index of the search string; -1 if not found.
def _string_index_of(args, unused_options):
    string, search, index = value_args_validate(_STRING_INDEX_OF_ARGS, args, -1)
    if index >= len(string):
        raise ValueArgsError('index', index, -1)

    return string.find(search, int(index))

_STRING_INDEX_OF_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'search', 'type': 'string'},
    {'name': 'index', 'type': 'number', 'default': 0, 'integer': True, 'gte': 0}
])


# $function: stringLastIndexOf
# $group: String
# $doc: Find the last index of a search string in a string
# $arg string: The string
# $arg search: The search string
# $arg index: Optional (default is the end of the string). The index at which to start the search.
# $return: The last index of the search string; -1 if not found.
def _string_last_index_of(args, unused_options):
    string, search, index = value_args_validate(_STRING_LAST_INDEX_OF_ARGS, args, -1)
    index = index if index is not None else len(string) - 1
    if index >= len(string):
        raise ValueArgsError('index', index, -1)

    return string.rfind(search, 0, int(index) + len(search))

_STRING_LAST_INDEX_OF_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'search', 'type': 'string'},
    {'name': 'index', 'type': 'number', 'nullable': True, 'integer': True, 'gte': 0}
])


# $function: stringLength
# $group: String
# $doc: Get the length of a string
# $arg string: The string
# $return: The string's length; zero if not a string
def _string_length(args, unused_options):
    string, = value_args_validate(_STRING_LENGTH_ARGS, args, 0)
    return len(string)

_STRING_LENGTH_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: stringLower
# $group: String
# $doc: Convert a string to lower-case
# $arg string: The string
# $return: The lower-case string
def _string_lower(args, unused_options):
    string, = value_args_validate(_STRING_LOWER_ARGS, args)
    return string.lower()

_STRING_LOWER_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: stringNew
# $group: String
# $doc: Create a new string from a value
# $arg value: The value
# $return: The new string
def _string_new(args, unused_options):
    value, = value_args_validate(_STRING_NEW_ARGS, args)
    return value_string(value)

_STRING_NEW_ARGS = value_args_model([
    {'name': 'value'}
])


# $function: stringRepeat
# $group: String
# $doc: Repeat a string
# $arg string: The string to repeat
# $arg count: The number of times to repeat the string
# $return: The repeated string
def _string_repeat(args, unused_options):
    string, count = value_args_validate(_STRING_REPEAT_ARGS, args)
    return string * int(count)

_STRING_REPEAT_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'count', 'type': 'number', 'integer': True, 'gte': 0}
])


# $function: stringReplace
# $group: String
# $doc: Replace all instances of a string with another string
# $arg string: The string to update
# $arg substr: The string to replace
# $arg newSubstr: The replacement string
# $return: The updated string
def _string_replace(args, unused_options):
    string, substr, new_substr = value_args_validate(_STRING_REPLACE_ARGS, args)
    return string.replace(substr, new_substr)

_STRING_REPLACE_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'substr', 'type': 'string'},
    {'name': 'newSubstr', 'type': 'string'}
])


# $function: stringSlice
# $group: String
# $doc: Copy a portion of a string
# $arg string: The string
# $arg start: The start index of the slice
# $arg end: Optional (default is the end of the string). The end index of the slice.
# $return: The new string slice
def _string_slice(args, unused_options):
    string, start, end = value_args_validate(_STRING_SLICE_ARGS, args)
    end = end if end is not None else len(string)
    if start > len(string):
        raise ValueArgsError('start', start)
    if end > len(string):
        raise ValueArgsError('end', end)

    return string[int(start):int(end)]

_STRING_SLICE_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'start', 'type': 'number', 'integer': True, 'gte': 0},
    {'name': 'end', 'type': 'number', 'nullable': True, 'integer': True, 'gte': 0}
])


# $function: stringSplit
# $group: String
# $doc: Split a string
# $arg string: The string to split
# $arg separator: The separator string
# $return: The array of split-out strings
def _string_split(args, unused_options):
    string, separator = value_args_validate(_STRING_SPLIT_ARGS, args)
    return string.split(separator)

_STRING_SPLIT_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'separator', 'type': 'string'}
])


# $function: stringStartsWith
# $group: String
# $doc: Determine if a string starts with a search string
# $arg string: The string
# $arg search: The search string
# $return: true if the string starts with the search string, false otherwise
def _string_starts_with(args, unused_options):
    string, search = value_args_validate(_STRING_STARTS_WITH_ARGS, args)
    return string.startswith(search)

_STRING_STARTS_WITH_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'},
    {'name': 'search', 'type': 'string'}
])


# $function: stringTrim
# $group: String
# $doc: Trim the whitespace from the beginning and end of a string
# $arg string: The string
# $return: The trimmed string
def _string_trim(args, unused_options):
    string, = value_args_validate(_STRING_TRIM_ARGS, args)
    return string.strip()

_STRING_TRIM_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


# $function: stringUpper
# $group: String
# $doc: Convert a string to upper-case
# $arg string: The string
# $return: The upper-case string
def _string_upper(args, unused_options):
    string, = value_args_validate(_STRING_UPPER_ARGS, args)
    return string.upper()

_STRING_UPPER_ARGS = value_args_model([
    {'name': 'string', 'type': 'string'}
])


#
# System functions
#


# $function: systemBoolean
# $group: System
# $doc: Interpret a value as a boolean
# $arg value: The value
# $return: true or false
def _system_boolean(args, unused_options):
    value, = value_args_validate(_SYSTEM_BOOLEAN_ARGS, args)
    return value_boolean(value)

_SYSTEM_BOOLEAN_ARGS = value_args_model([
    {'name': 'value'}
])


# $function: systemCompare
# $group: System
# $doc: Compare two values
# $arg left: The left value
# $arg right: The right value
# $return: -1 if the left value is less than the right value, 0 if equal, and 1 if greater than
def _system_compare(args, unused_options):
    left, right = value_args_validate(_SYSTEM_COMPARE_ARGS, args)
    return value_compare(left, right)

_SYSTEM_COMPARE_ARGS = value_args_model([
    {'name': 'left'},
    {'name': 'right'}
])


# $function: systemFetch
# $group: System
# $doc: Retrieve a URL resource
# $arg url: The resource URL,
# $arg url: [request model](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='SystemFetchRequest'),
# $arg url: or array of URL and
# $arg url: [request model](https://craigahobbs.github.io/bare-script-py/library/model.html#var.vName='SystemFetchRequest')
# $return: The response string or array of strings; null if an error occurred
def _system_fetch(args, options):
    url, = value_args_validate(_SYSTEM_FETCH_ARGS, args)

    # Options
    fetch_fn = options.get('fetchFn') if options is not None else None
    log_fn = options.get('logFn') if options is not None and options.get('debug') else None
    url_fn = options.get('urlFn') if options is not None else None

    # Validate the URL argument
    requests = []
    is_response_array = False
    url_type = value_type(url)
    if url_type == 'string':
        requests.append({'url': url})
    elif url_type == 'object':
        requests.append(validate_type(SYSTEM_FETCH_TYPES, 'SystemFetchRequest', url))
    elif url_type == 'array':
        is_response_array = True
        for url_item in url:
            if value_type(url_item) == 'string':
                requests.append({'url': url_item})
            else:
                requests.append(validate_type(SYSTEM_FETCH_TYPES, 'SystemFetchRequest', url_item))
    else:
        raise ValueArgsError('url', url)

    # Get each response
    responses = []
    for request in requests:
        request_fetch = dict(request)

        # Update the URL
        if url_fn is not None:
            request_fetch['url'] = url_fn(request_fetch['url'])

        # Fetch the URL
        response = None
        if fetch_fn is not None:
            try:
                response = fetch_fn(request_fetch)
            except: # pylint: disable=bare-except
                pass
        responses.append(response)

        # Log failure
        if response is None and log_fn is not None:
            log_fn(f'BareScript: Function "systemFetch" failed for resource "{request_fetch["url"]}"')

    return responses if is_response_array else responses[0]

_SYSTEM_FETCH_ARGS = value_args_model([
    {'name': 'url'}
])


# The aggregation model
SYSTEM_FETCH_TYPES = parse_schema_markdown('''\
group "SystemFetch"


# A fetch request model
struct SystemFetchRequest

    # The resource URL
    string url

    # The request body
    optional string body

    # The request headers
    optional string{} headers
''')


# $function: systemGlobalGet
# $group: System
# $doc: Get a global variable value
# $arg name: The global variable name
# $arg defaultValue: The default value (optional)
# $return: The global variable's value or null if it does not exist
def _system_global_get(args, options):
    name, default_value = value_args_validate(_SYSTEM_GLOBAL_GET_ARGS, args)
    globals_ = options.get('globals') if options is not None else None
    return globals_.get(name, default_value) if globals_ is not None else default_value

_SYSTEM_GLOBAL_GET_ARGS = value_args_model([
    {'name': 'name', 'type': 'string'},
    {'name': 'defaultValue'}
])


# $function: systemGlobalSet
# $group: System
# $doc: Set a global variable value
# $arg name: The global variable name
# $arg value: The global variable's value
# $return: The global variable's value
def _system_global_set(args, options):
    name, value = value_args_validate(_SYSTEM_GLOBAL_SET_ARGS, args)
    globals_ = options.get('globals') if options is not None else None
    if globals_ is not None:
        globals_[name] = value
    return value

_SYSTEM_GLOBAL_SET_ARGS = value_args_model([
    {'name': 'name', 'type': 'string'},
    {'name': 'value'}
])


# $function: systemIs
# $group: System
# $doc: Test if one value is the same object as another
# $arg value1: The first value
# $arg value2: The second value
# $return: true if values are the same object, false otherwise
def _system_is(args, unused_options):
    value1, value2 = value_args_validate(_SYSTEM_IS_ARGS, args)
    return value_is(value1, value2)

_SYSTEM_IS_ARGS = value_args_model([
    {'name': 'value1'},
    {'name': 'value2'}
])


# $function: systemLog
# $group: System
# $doc: Log a message to the console
# $arg message: The log message
def _system_log(args, options):
    message, = value_args_validate(_SYSTEM_LOG_ARGS, args)
    log_fn = options.get('logFn') if options is not None else None
    if log_fn is not None:
        log_fn(value_string(message))

_SYSTEM_LOG_ARGS = value_args_model([
    {'name': 'message'}
])


# $function: systemLogDebug
# $group: System
# $doc: Log a message to the console, if in debug mode
# $arg message: The log message
def _system_log_debug(args, options):
    message, = value_args_validate(_SYSTEM_LOG_DEBUG_ARGS, args)
    log_fn = options.get('logFn') if options is not None else None
    if log_fn is not None and options.get('debug'):
        log_fn(value_string(message))

_SYSTEM_LOG_DEBUG_ARGS = value_args_model([
    {'name': 'message'}
])


# $function: systemPartial
# $group: System
# $doc: Return a new function which behaves like "func" called with "args".
# $doc: If additional arguments are passed to the returned function, they are appended to "args".
# $arg func: The function
# $arg args...: The function arguments
# $return: The new function called with "args"
def _system_partial(args, unused_options):
    func, func_args = value_args_validate(_SYSTEM_PARTIAL_ARGS, args)
    if len(func_args) < 1:
        raise ValueArgsError('args', func_args)

    return lambda args_extra, options: func([*func_args, *args_extra], options)

_SYSTEM_PARTIAL_ARGS = value_args_model([
    {'name': 'func', 'type': 'function'},
    {'name': 'args', 'lastArgArray': True}
])


# $function: systemType
# $group: System
# $doc: Get a value's type string
# $arg value: The value
# $return: The type string of the value.
# $return: Valid values are: 'array', 'boolean', 'datetime', 'function', 'null', 'number', 'object', 'regex', 'string'.
def _system_type(args, unused_options):
    value, = value_args_validate(_SYSTEM_TYPE_ARGS, args)
    return value_type(value)

_SYSTEM_TYPE_ARGS = value_args_model([
    {'name': 'value'}
])


#
# URL functions
#


# $function: urlEncode
# $group: URL
# $doc: Encode a URL
# $arg url: The URL string
# $return: The encoded URL string
def _url_encode(args, unused_options):
    url, = value_args_validate(_URL_ENCODE_ARGS, args)
    return urllib.parse.quote(url, safe="':/&+")

_URL_ENCODE_ARGS = value_args_model([
    {'name': 'url', 'type': 'string'}
])


# $function: urlEncodeComponent
# $group: URL
# $doc: Encode a URL component
# $arg url: The URL component string
# $return: The encoded URL component string
def _url_encode_component(args, unused_options):
    url, = value_args_validate(_URL_ENCODE_COMPONENT_ARGS, args)
    return urllib.parse.quote(url, safe="'")

_URL_ENCODE_COMPONENT_ARGS = value_args_model([
    {'name': 'url', 'type': 'string'}
])


# The built-in script functions
SCRIPT_FUNCTIONS = {
    'arrayCopy': _array_copy,
    'arrayDelete': _array_delete,
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
    'dataAggregate': _data_aggregate,
    'dataCalculatedField': _data_calculated_field,
    'dataFilter': _data_filter,
    'dataJoin': _data_join,
    'dataParseCSV': _data_parse_csv,
    'dataSort': _data_sort,
    'dataTop': _data_top,
    'dataValidate': _data_validate,
    'datetimeDay': _datetime_day,
    'datetimeHour': _datetime_hour,
    'datetimeISOFormat': _datetime_iso_format,
    'datetimeISOParse': _datetime_iso_parse,
    'datetimeMillisecond': _datetime_millisecond,
    'datetimeMinute': _datetime_minute,
    'datetimeMonth': _datetime_month,
    'datetimeNew': _datetime_new,
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
    'regexEscape': _regex_escape,
    'regexMatch': _regex_match,
    'regexMatchAll': _regex_match_all,
    'regexNew': _regex_new,
    'regexReplace': _regex_replace,
    'regexSplit': _regex_split,
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
    'systemBoolean': _system_boolean,
    'systemCompare': _system_compare,
    'systemFetch': _system_fetch,
    'systemGlobalGet': _system_global_get,
    'systemGlobalSet': _system_global_set,
    'systemIs': _system_is,
    'systemLog': _system_log,
    'systemLogDebug': _system_log_debug,
    'systemPartial': _system_partial,
    'systemType': _system_type,
    'urlEncode': _url_encode,
    'urlEncodeComponent': _url_encode_component
}


# The built-in expression functions
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
EXPRESSION_FUNCTIONS = dict(
    (expr_fn_name, SCRIPT_FUNCTIONS[script_fn_name])
    for expr_fn_name, script_fn_name in EXPRESSION_FUNCTION_MAP.items()
)
