# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript data manipulation library
"""

import datetime

from schema_markdown import parse_schema_markdown

from .parser import parse_expression
from .runtime import evaluate_expression
from .value import parse_datetime, parse_number, value_json


def validate_data(data, csv=False):
    """
    Determine data field types and parse/validate field values

    :param data: The data array. Row objects are updated with parsed/validated values.
    :type data: list[dict]
    :param csv: If true, parse number and null strings
    :type csv: bool
    :return: The map of field name to field type ("datetime", "number", "string")
    :rtype: dict
    :raises TypeError: Data is invalid
    """

    # Determine field types
    types = {}
    for row in data:
        for field, value in row.items():
            if field not in types:
                if isinstance(value, bool):
                    types[field] = 'boolean'
                elif isinstance(value, (int, float)):
                    types[field] = 'number'
                elif isinstance(value, datetime.datetime):
                    types[field] = 'datetime'
                elif isinstance(value, str) and (not csv or value != 'null'):
                    if parse_datetime(value) is not None:
                        types[field] = 'datetime'
                    elif csv and value in ('true', 'false'):
                        types[field] = 'boolean'
                    elif csv and parse_number(value) is not None:
                        types[field] = 'number'
                    else:
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
                    number_value = parse_number(value)
                    if number_value is None:
                        throw_field_error(field, field_type, value)
                    row[field] = number_value
                elif value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool)):
                    throw_field_error(field, field_type, value)

            # Datetime field
            elif field_type == 'datetime':
                if isinstance(value, str):
                    datetime_value = parse_datetime(value)
                    if datetime_value is None:
                        throw_field_error(field, field_type, value)
                    row[field] = datetime_value
                elif value is not None and not isinstance(value, datetime.datetime):
                    throw_field_error(field, field_type, value)

            # Boolean field
            elif field_type == 'boolean':
                if csv and isinstance(value, str):
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
            unique_name = field_name
            ix_unique = 2
            unique_name = f'{field_name}{ix_unique}'
            right_names[field_name] = unique_name
            while unique_name in left_names or unique_name in right_names_raw:
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


def add_calculated_field(unused_unused_data, unused_field_name, unused_expr, unused_variables=None, unused_options=None):
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

    return None

    # # Parse the calculation expression
    # calcExpr = parseExpression(expr)

    # # Create the evaluation options object
    # evalOptions = options
    # if variables != null:
    #     evalOptions = (options != null ? {...options} : {})
    #     if 'globals' in evalOptions:
    #         evalOptions.globals = {...evalOptions.globals, ...variables}
    #     else:
    #         evalOptions.globals = variables
    #     }
    # }

    # # Compute the calculated field for each row
    # for (row of data) {
    #     row[fieldName] = evaluateExpression(calcExpr, evalOptions, row)
    # }
    # return data


def filter_data(unused_data, unused_expr, unused_variables=None, unused_options=None):
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
    return None

    # result = []

    # # Parse the filter expression
    # filterExpr = parseExpression(expr)

    # # Create the evaluation options object
    # evalOptions = options
    # if variables != null:
    #     evalOptions = (options != null ? {...options} : {})
    #     if 'globals' in evalOptions:
    #         evalOptions.globals = {...evalOptions.globals, ...variables}
    #     else:
    #         evalOptions.globals = variables
    #     }
    # }

    # # Filter the data
    # for (row of data) {
    #     if evaluateExpression(filterExpr, evalOptions, row):
    #         result.push(row)
    #     }
    # }

    # return result


def aggregate_data(unused_data, unused_aggregation):
    """
    Aggregate data rows

    :param data: The data array
    :type data: list[dict]
    :param aggregation: The `aggregation model <https://craigahobbs.github.io/bare-script/library/model.html#var.vName='Aggregation'>`__
    :type aggregation: dict
    :return: The aggregated data array
    :rtype: list[dict]
    """

    return None

    # Validate the aggregation model
    # validate_type(AGGREGATION_TYPES, 'Aggregation', aggregation)

    # categories = aggregation.categories ?? null

    # # Create the aggregate rows
    # categoryRows = {}
    # for (row of data) {
    #     # Compute the category values
    #     categoryValues = (categories != null ? categories.map((categoryField) => row[categoryField]) : null)

    #     # Get or create the aggregate row
    #     aggregateRow
    #     rowKey = (categoryValues != null ? jsonStringifySortKeys(categoryValues) : '')
    #     if rowKey in categoryRows:
    #         aggregateRow = categoryRows[rowKey]
    #     else:
    #         aggregateRow = {}
    #         categoryRows[rowKey] = aggregateRow
    #         if categories != null:
    #             for (ixCategoryField = 0; ixCategoryField < categories.length; ixCategoryField++) {
    #                 aggregateRow[categories[ixCategoryField]] = categoryValues[ixCategoryField]
    #             }
    #         }
    #     }

    #     # Add to the aggregate measure values
    #     for (measure of aggregation.measures) {
    #         field = measure.name ?? measure.field
    #         value = row[measure.field] ?? null
    #         if !(field in aggregateRow):
    #             aggregateRow[field] = []
    #         }
    #         if value != null:
    #             aggregateRow[field].push(value)
    #         }
    #     }
    # }

    # # Compute the measure values aggregate function value
    # aggregateRows = Object.values(categoryRows)
    # for (aggregateRow of aggregateRows) {
    #     for (measure of aggregation.measures) {
    #         field = measure.name ?? measure.field
    #         func = measure.function
    #         measureValues = aggregateRow[field]
    #         if !measureValues.length:
    #             aggregateRow[field] = null
    #         elif func == 'count':
    #             aggregateRow[field] = measureValues.length
    #         elif func == 'max':
    #             aggregateRow[field] = measureValues.reduce((max, val) => (val > max ? val : max))
    #         elif func == 'min':
    #             aggregateRow[field] = measureValues.reduce((min, val) => (val < min ? val : min))
    #         elif func == 'sum':
    #             aggregateRow[field] = measureValues.reduce((sum, val) => sum + val, 0)
    #         elif func == 'stddev':
    #             average = measureValues.reduce((sum, val) => sum + val, 0) / measureValues.length
    #             aggregateRow[field] = Math.sqrt(measureValues.reduce((sum, val) => sum + (val - average) ** 2, 0) / measureValues.length)
    #         else:
    #             # func == 'average'
    #             aggregateRow[field] = measureValues.reduce((sum, val) => sum + val, 0) / measureValues.length
    #         }
    #     }
    # }

    # return aggregateRows


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


def sort_data(unused_data, unused_sorts):
    """
    Sort data rows

    :param data: The data array
    :type data: list[dict]
    :param sorts: The sort field-name/descending-sort tuples
    :type sorts: list[list]
    :return: The sorted data array
    :rtype: list[dict]
    """

    return None

    # return data.sort((row1, row2) => sorts.reduce((result, sort) => {
    #     if result != 0:
    #         return result
    #     }
    #     [field, desc = false] = sort
    #     value1 = row1[field] ?? null
    #     value2 = row2[field] ?? null
    #     compare = compareValues(value1, value2)
    #     return desc ? -compare : compare
    # }, 0))


def top_data(unused_data, unused_count, unused_category_fields=None):
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

    return None

    # # Bucket rows by category
    # categoryRows = {}
    # categoryOrder = []
    # for (row of data) {
    #     categoryKey = categoryFields == null ? ''
    #         : jsonStringifySortKeys(categoryFields.map((field) => (field in row ? row[field] : null)))
    #     if !(categoryKey in categoryRows):
    #         categoryRows[categoryKey] = []
    #         categoryOrder.push(categoryKey)
    #     }
    #     categoryRows[categoryKey].push(row)
    # }
    # # Take only the top rows
    # dataTop = []
    # topCount = count
    # for (categoryKey of categoryOrder) {
    #     categoryKeyRows = categoryRows[categoryKey]
    #     categoryKeyLength = categoryKeyRows.length
    #     for (ixRow = 0; ixRow < topCount && ixRow < categoryKeyLength; ixRow++) {
    #         dataTop.push(categoryKeyRows[ixRow])
    #     }
    # }
    # return dataTop
