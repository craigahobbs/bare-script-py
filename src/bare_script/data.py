# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript data manipulation library
"""

import re

from schema_markdown import parse_schema_markdown


def validate_data(unused_data, unused_csv=False):
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
    return None

    # # Determine field types
    # types = {}
    # for (row of data) {
    #     for ([field, value] of Object.entries(row)) {
    #         if !(field in types)) {
    #             if typeof value == 'number') {
    #                 types[field] = 'number'
    #             elif value instanceof Date:
    #                 types[field] = 'datetime'
    #             elif typeof value == 'string' && (!csv || value != 'null'):
    #                 if parseDatetime(value) != null:
    #                     types[field] = 'datetime'
    #                 elif csv && parseNumber(value) != null:
    #                     types[field] = 'number'
    #                 else:
    #                     types[field] = 'string'
    #                 }
    #             }
    #         }
    #     }
    # }

    # # Validate field values
    # throwFieldError = (field, fieldType, fieldValue) => {
    #     throw new Error(`Invalid "${field}" field value ${JSON.stringify(fieldValue)}, expected type ${fieldType}`)
    # }
    # for (row of data) {
    #     for ([field, value] of Object.entries(row)) {
    #         fieldType = types[field]

    #         # Null string?
    #         if csv && value == 'null':
    #             row[field] = null

    #         # Number field
    #         elif fieldType == 'number':
    #             if csv && typeof value == 'string':
    #                 numberValue = parseNumber(value)
    #                 if numberValue == null:
    #                     throwFieldError(field, fieldType, value)
    #                 }
    #                 row[field] = numberValue
    #             elif value != null && typeof value != 'number':
    #                 throwFieldError(field, fieldType, value)
    #             }

    #         # Datetime field
    #         elif fieldType == 'datetime':
    #             if typeof value == 'string':
    #                 datetimeValue = parseDatetime(value)
    #                 if datetimeValue == null:
    #                     throwFieldError(field, fieldType, value)
    #                 }
    #                 row[field] = datetimeValue
    #             elif value != null && !(value instanceof Date):
    #                 throwFieldError(field, fieldType, value)
    #             }

    #         # String field
    #         else:
    #             if value != null && typeof value != 'string':
    #                 throwFieldError(field, fieldType, value)
    #             }
    #         }
    #     }
    # }

    # return types


def _parse_number(unused_text):
    return None

    # value = Number.parseFloat(text)
    # if Number.isNaN(value) || !Number.isFinite(value):
    #     return null
    # }
    # return value


def _parse_datetime(unused_text):
    return None

    # mDate = text.match(rDate)
    # if mDate != null:
    #     year = Number.parseInt(mDate.groups.year, 10)
    #     month = Number.parseInt(mDate.groups.month, 10)
    #     day = Number.parseInt(mDate.groups.day, 10)
    #     return new Date(year, month - 1, day)
    # elif rDatetime.test(text):
    #     return new Date(text)
    # }
    # return null

R_DATE = re.compile(r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$')
R_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$')


def join_data(unused_left_data, unused_right_data, unused_join_expr, unused_right_expr=None, unused_is_left_join=False,
              unused_variables=None, unused_options=None):
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

    return None

    # # Compute the map of row field name to joined row field name
    # leftNames = {}
    # for (row of leftData) {
    #     for (fieldName of Object.keys(row)) {
    #         if !(fieldName in leftNames):
    #             leftNames[fieldName] = fieldName
    #         }
    #     }
    # }
    # rightNames = {}
    # for (row of rightData) {
    #     for (fieldName of Object.keys(row)) {
    #         if !(fieldName in rightNames):
    #             if !(fieldName in leftNames):
    #                 rightNames[fieldName] = fieldName
    #             else:
    #                 uniqueName = fieldName
    #                 ixUnique = 2
    #                 do {
    #                     uniqueName = `${fieldName}${ixUnique}`
    #                     ixUnique += 1
    #                 } while (uniqueName in leftNames || uniqueName in rightNames)
    #                 rightNames[fieldName] = uniqueName
    #             }
    #         }
    #     }
    # }

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

    # # Parse the left and right expressions
    # leftExpression = parseExpression(joinExpr)
    # rightExpression = (rightExpr != null ? parseExpression(rightExpr) : leftExpression)

    # # Bucket the right rows by the right expression value
    # rightCategoryRows = {}
    # for (rightRow of rightData) {
    #     categoryKey = jsonStringifySortKeys(evaluateExpression(rightExpression, evalOptions, rightRow))
    #     if !(categoryKey in rightCategoryRows):
    #         rightCategoryRows[categoryKey] = []
    #     }
    #     rightCategoryRows[categoryKey].push(rightRow)
    # }

    # # Join the left with the right
    # data = []
    # for (leftRow of leftData) {
    #     categoryKey = jsonStringifySortKeys(evaluateExpression(leftExpression, evalOptions, leftRow))
    #     if categoryKey in rightCategoryRows:
    #         for (rightRow of rightCategoryRows[categoryKey]) {
    #             joinRow = {...leftRow}
    #             for ([rightName, rightValue] of Object.entries(rightRow)) {
    #                 joinRow[rightNames[rightName]] = rightValue
    #             }
    #             data.push(joinRow)
    #         }
    #     elif !isLeftJoin:
    #         data.push({...leftRow})
    #     }
    # }

    # return data


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
