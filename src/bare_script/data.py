# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript data manipulation library
"""

import datetime
import functools
import importlib
import statistics

from schema_markdown import parse_schema_markdown, validate_type

from .parser import parse_expression
from .value import value_boolean, value_compare, value_json, value_parse_datetime, value_parse_number


# Helper to dynamically import evaluate_expression to avoid the circular dependency
def _import_evaluate_expression():
    if not _EVALUATE_EXPRESSION:
        _EVALUATE_EXPRESSION.append(importlib.import_module('bare_script.runtime').evaluate_expression)
    return _EVALUATE_EXPRESSION[0]

_EVALUATE_EXPRESSION = []


def validate_data(data, csv=False):
    """
    Determine data field types and parse/validate field values

    :param data: The data array. Row objects are updated with parsed/validated values.
    :type data: list[dict]
    :param csv: If true, parse value strings
    :type csv: bool
    :return: The map of field name to field type ("boolean", "datetime", "number", "string")
    :rtype: dict
    :raises TypeError: Data is invalid
    """

    # Determine field types
    types = {}
    for row in data:
        for field, value in row.items():
            if types.get(field) is None:
                if isinstance(value, bool):
                    types[field] = 'boolean'
                elif isinstance(value, (int, float)):
                    types[field] = 'number'
                elif isinstance(value, datetime.date):
                    types[field] = 'datetime'
                elif isinstance(value, str):
                    # If we aren't parsing CSV strings, its just a string
                    if not csv:
                        types[field] = 'string'

                    # If its the null string we can't determine the type yet
                    elif value in ('', 'null'):
                        types[field] = None

                    # Can the string be parsed into another type?
                    elif value_parse_datetime(value) is not None:
                        types[field] = 'datetime'
                    elif value in ('true', 'false'):
                        types[field] = 'boolean'
                    elif value_parse_number(value) is not None:
                        types[field] = 'number'
                    else:
                        types[field] = 'string'

    # Set the type for fields with undetermined type
    for field, field_type in types.items():
        if field_type is None:
            types[field] = 'string'

    # Helper to format and raise validation errors
    def throw_field_error(field, field_type, field_value):
        raise TypeError(f'Invalid "{field}" field value {value_json(field_value)}, expected type {field_type}')

    # Validate field values
    for row in data:
        for field, value in row.items():
            field_type = types.get(field)
            if field_type is None:
                continue

            # Null string?
            if csv and value == 'null':
                row[field] = None

            # Number field
            elif field_type == 'number':
                if csv and isinstance(value, str):
                    if value == '':
                        number_value = None
                    else:
                        number_value = value_parse_number(value)
                        if number_value is None:
                            throw_field_error(field, field_type, value)
                    row[field] = number_value
                elif value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool)):
                    throw_field_error(field, field_type, value)

            # Datetime field
            elif field_type == 'datetime':
                if csv and isinstance(value, str):
                    if value == '':
                        datetime_value = None
                    else:
                        datetime_value = value_parse_datetime(value)
                        if datetime_value is None:
                            throw_field_error(field, field_type, value)
                    row[field] = datetime_value
                elif value is not None and not isinstance(value, datetime.date):
                    throw_field_error(field, field_type, value)

            # Boolean field
            elif field_type == 'boolean':
                if csv and isinstance(value, str):
                    if value == '':
                        boolean_value = None
                    else:
                        boolean_value = True if value == 'true' else (False if value == 'false' else None)
                        if boolean_value is None:
                            throw_field_error(field, field_type, value)
                    row[field] = boolean_value
                elif value is not None and not isinstance(value, bool):
                    throw_field_error(field, field_type, value)

            # String field
            else:
                if value is not None and not isinstance(value, str):
                    throw_field_error(field, field_type, value)

    return types


def join_data(left_data, right_data, join_expr, right_expr=None, is_left_join=False, variables=None, options=None):
    """
    Join two data arrays

    :param leftData: The left data array
    :type leftData: list[dict]
    :param rightData: The left data array
    :type rightData: list[dict]
    :param joinExpr: The join `expression <https://craigahobbs.github.io/bare-script/language/#expressions>`__
    :type joinExpr: str
    :param rightExpr: The right join `expression <https://craigahobbs.github.io/bare-script/language/#expressions>`__
    :type rightExpr: str
    :param isLeftJoin: If true, perform a left join (always include left row)
    :type isLeftJoin: bool
    :param variables: Additional variables for expression evaluation
    :type variables: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict
    :return: The joined data array
    :rtype: list[dict]
    """

    evaluate_expression = _import_evaluate_expression()

    # Compute the map of row field name to joined row field name
    left_names = {}
    right_names_raw = {}
    right_names = {}
    for row in left_data:
        for field_name in row:
            if field_name not in left_names:
                left_names[field_name] = field_name
    for row in right_data:
        for field_name in row:
            if field_name not in right_names_raw:
                right_names_raw[field_name] = field_name
    for field_name in right_names_raw:
        if field_name not in left_names:
            right_names[field_name] = field_name
        else:
            ix_unique = 2
            unique_name = f'{field_name}{ix_unique}'
            while unique_name in left_names or unique_name in right_names or unique_name in right_names_raw:
                ix_unique += 1
                unique_name = f'{field_name}{ix_unique}'
            right_names[field_name] = unique_name

    # Create the evaluation options object
    eval_options = options
    if variables is not None:
        eval_options = dict(options) if options is not None else {}
        if 'globals' in eval_options:
            eval_options['globals'] = {**eval_options['globals'], **variables}
        else:
            eval_options['globals'] = variables

    # Parse the left and right expressions
    left_expression = parse_expression(join_expr)
    right_expression = parse_expression(right_expr) if right_expr is not None else left_expression

    # Bucket the right rows by the right expression value
    right_category_rows = {}
    for right_row in right_data:
        category_key = value_json(evaluate_expression(right_expression, eval_options, right_row))
        if category_key not in right_category_rows:
            right_category_rows[category_key] = []
        right_category_rows[category_key].append(right_row)

    # Join the left with the right
    data = []
    for left_row in left_data:
        category_key = value_json(evaluate_expression(left_expression, eval_options, left_row))
        if category_key in right_category_rows:
            for right_row in right_category_rows[category_key]:
                join_row = dict(left_row)
                for right_name, right_value in right_row.items():
                    join_row[right_names[right_name]] = right_value
                data.append(join_row)
        elif not is_left_join:
            data.append(dict(left_row))

    return data


def add_calculated_field(data, field_name, expr, variables=None, options=None):
    """
    Add a calculated field to each row of a data array

    :param data: The data array. Row objects are updated with the calculated field values.
    :type data: list[dict]
    :param fieldName: The calculated field name
    :type fieldName: str
    :param expr: The calculated field expression
    :type expr: str
    :param variables:  Additional variables for expression evaluation
    :type variables: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict
    :return: The updated data array
    :rtype: list[dict]
    """

    evaluate_expression = _import_evaluate_expression()

    # Parse the calculation expression
    calc_expr = parse_expression(expr)

    # Create the evaluation options object
    eval_options = options
    if variables is not None:
        eval_options = dict(options) if options is not None else {}
        if 'globals' in eval_options:
            eval_options['globals'] = {**eval_options['globals'], **variables}
        else:
            eval_options['globals'] = variables

    # Compute the calculated field for each row
    for row in data:
        row[field_name] = evaluate_expression(calc_expr, eval_options, row)

    return data


def filter_data(data, expr, variables=None, options=None):
    """
    Filter data rows

    :param data: The data array
    :type data: list[dict]
    :param expr: The boolean filter `expression <https://craigahobbs.github.io/bare-script/language/#expressions>`__
    :type expr: str
    :param variables:  Additional variables for expression evaluation
    :type variables: dict
    :param options: The :class:`script execution options <ExecuteScriptOptions>`
    :type options: dict
    :return: The filtered data array
    :rtype: list[dict]
    """

    result = []
    evaluate_expression = _import_evaluate_expression()

    # Parse the filter expression
    filter_expr = parse_expression(expr)

    # Create the evaluation options object
    eval_options = options
    if variables is not None:
        eval_options = dict(options) if options is not None else {}
        if 'globals' in eval_options:
            eval_options['globals'] = {**eval_options['globals'], **variables}
        else:
            eval_options['globals'] = variables

    # Filter the data
    for row in data:
        if value_boolean(evaluate_expression(filter_expr, eval_options, row)):
            result.append(row)

    return result


def aggregate_data(data, aggregation):
    """
    Aggregate data rows

    :param data: The data array
    :type data: list[dict]
    :param aggregation: The `aggregation model <./library/model.html#var.vName='Aggregation'>`__
    :type aggregation: dict
    :return: The aggregated data array
    :rtype: list[dict]
    """

    # Validate the aggregation model
    validate_type(AGGREGATION_TYPES, 'Aggregation', aggregation)
    categories = aggregation.get('categories')

    # Create the aggregate rows
    category_rows = {}
    for row in data:
        # Compute the category values
        category_values = [row.get(category) for category in categories] if categories is not None else None

        # Get or create the aggregate row
        row_key = value_json(category_values) if category_values is not None else ''
        if row_key in category_rows:
            aggregate_row = category_rows[row_key]
        else:
            aggregate_row = {}
            category_rows[row_key] = aggregate_row
            if categories is not None:
                for ix_category_field, category in enumerate(categories):
                    aggregate_row[category] = category_values[ix_category_field]

        # Add to the aggregate measure values
        for measure in aggregation['measures']:
            field = measure.get('name', measure['field'])
            value = row.get(measure['field'])
            if field not in aggregate_row:
                aggregate_row[field] = []
            if value is not None:
                aggregate_row[field].append(value)

    # Compute the measure values aggregate function value
    aggregate_rows = list(category_rows.values())
    for aggregate_row in aggregate_rows:
        for measure in aggregation['measures']:
            field = measure.get('name', measure['field'])
            func = measure['function']
            measure_values = aggregate_row[field]
            if len(measure_values) == 0:
                aggregate_row[field] = None
            elif func == 'count':
                aggregate_row[field] = len(measure_values)
            elif func == 'max':
                aggregate_row[field] = max(measure_values)
            elif func == 'min':
                aggregate_row[field] = min(measure_values)
            elif func == 'sum':
                aggregate_row[field] = sum(measure_values)
            elif func == 'stddev':
                aggregate_row[field] = statistics.pstdev(measure_values)
            else: # func == 'average'
                aggregate_row[field] = statistics.mean(measure_values)

    return aggregate_rows


# The aggregation model
AGGREGATION_TYPES = parse_schema_markdown('''\
group "Aggregation"


# A data aggregation specification
struct Aggregation

    # The aggregation category fields
    optional string[len > 0] categories

    # The aggregation measures
    AggregationMeasure[len > 0] measures


# An aggregation measure specification
struct AggregationMeasure

    # The aggregation measure field
    string field

    # The aggregation function
    AggregationFunction function

    # The aggregated-measure field name
    optional string name


# An aggregation function
enum AggregationFunction

    # The average of the measure's values
    average

    # The count of the measure's values
    count

    # The greatest of the measure's values
    max

    # The least of the measure's values
    min

    # The standard deviation of the measure's values
    stddev

    # The sum of the measure's values
    sum
''')


def sort_data(data, sorts):
    """
    Sort data rows

    :param data: The data array
    :type data: list[dict]
    :param sorts: The sort field-name/descending-sort tuples
    :type sorts: list[list]
    :return: The sorted data array
    :rtype: list[dict]
    """

    data.sort(key=functools.cmp_to_key(functools.partial(_sort_data_fn, sorts)))
    return data


def _sort_data_fn(sorts, row1, row2):
    for sort in sorts:
        field = sort[0]
        desc = sort[1] if len(sort) > 1 else False
        value1 = row1.get(field)
        value2 = row2.get(field)
        result = value_compare(value2, value1) if desc else value_compare(value1, value2)
        if result != 0:
            return result
    return 0


def top_data(data, count, category_fields=None):
    """
    Top data rows

    :param data: The data array
    :type data: list[dict]
    :param count: The number of rows to keep
    :type count: int
    :param categoryFields: The category fields
    :type categoryFields: list[str]
    :return: The top data array
    :rtype: list[dict]
    """

    # Bucket rows by category
    category_rows = {}
    category_order = []
    for row in data:
        category_key = '' if category_fields is None else value_json([row.get(field) for field in category_fields])
        if category_key not in category_rows:
            category_rows[category_key] = []
            category_order.append(category_key)
        category_rows[category_key].append(row)

    # Take only the top rows
    data_top = []
    for category_key in category_order:
        category_key_rows = category_rows[category_key]
        for ix_row in range(min(count, len(category_key_rows))):
            data_top.append(category_key_rows[ix_row])

    return data_top
