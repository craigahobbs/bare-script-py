# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
The BareScript data manipulation library
"""

import re

from schema_markdown import parse_schema_markdown, validate_type


def parse_csv(unused_text):
    """
    Parse and validate CSV text to a data array

    @param {string} text - The CSV text
    @returns {Object[]} The data array
    """
    return None

    # # Line-split the text
    # const lines = [];
    # if (typeof text === 'string') {
    #     lines.push(...text.split(rCSVLineSplit));
    # } else {
    #     for (const textPart of text) {
    #         lines.push(...textPart.split(rCSVLineSplit));
    #     }
    # }

    # # Split lines into rows
    # const rows = lines.filter((line) => !line.match(rCSVBlankLine)).map((line) => {
    #     const row = [];
    #     let linePart = line;
    #     while (linePart !== '') {
    #         # Quoted field?
    #         const mQuoted = linePart.match(rCSVQuotedField) ?? linePart.match(rCSVQuotedFieldEnd);
    #         if (mQuoted !== null) {
    #             row.push(mQuoted[1].replaceAll(rCSVQuoteEscape, '"'));
    #             linePart = linePart.slice(mQuoted[0].length);
    #             continue;
    #         }

    #         # Non-quoted field
    #         const ixComma = linePart.indexOf(',');
    #         row.push(ixComma !== -1 ? linePart.slice(0, ixComma) : linePart);
    #         linePart = (ixComma !== -1 ? linePart.slice(ixComma + 1) : '');
    #     }
    #     return row;
    # });

    # # Assemble the data rows
    # const result = [];
    # if (rows.length >= 2) {
    #     const [fields] = rows;
    #     for (let ixLine = 1; ixLine < rows.length; ixLine += 1) {
    #         const row = rows[ixLine];
    #         result.push(Object.fromEntries(fields.map(
    #             (field, ixField) => [field, ixField < row.length ? row[ixField] : 'null']
    #         )));
    #     }
    # }

    # return result;


R_CSV_BLANK_LINE = re.compile(r'^\s*$')
R_CSV_QUOTED_FIELD = re.compile(r'^"((?:""|[^"])*)",')
R_CSV_QUOTED_FIELD_END = re.compile(r'^"((?:""|[^"])*)"\s*$')
R_CSV_QUOTE_ESCAPE = re.compile(r'""')


def validate_data(unused_data, unused_csv=False):
    """
    Determine data field types and parse/validate field values

    @param {Object[]} data - The data array. Row objects are updated with parsed/validated values.
    @param {boolean} [csv=false] - If true, parse number and null strings
    @returns {Object} The map of field name to field type ("datetime", "number", "string")
    @throws Throws an error if data is invalid
    """
    return None

    # # Determine field types
    # const types = {};
    # for (const row of data) {
    #     for (const [field, value] of Object.entries(row)) {
    #         if (!(field in types)) {
    #             if (typeof value === 'number') {
    #                 types[field] = 'number';
    #             } else if (value instanceof Date) {
    #                 types[field] = 'datetime';
    #             } else if (typeof value === 'string' && (!csv || value !== 'null')) {
    #                 if (parseDatetime(value) !== null) {
    #                     types[field] = 'datetime';
    #                 } else if (csv && parseNumber(value) !== null) {
    #                     types[field] = 'number';
    #                 } else {
    #                     types[field] = 'string';
    #                 }
    #             }
    #         }
    #     }
    # }

    # # Validate field values
    # const throwFieldError = (field, fieldType, fieldValue) => {
    #     throw new Error(`Invalid "${field}" field value ${JSON.stringify(fieldValue)}, expected type ${fieldType}`);
    # };
    # for (const row of data) {
    #     for (const [field, value] of Object.entries(row)) {
    #         const fieldType = types[field];

    #         # Null string?
    #         if (csv && value === 'null') {
    #             row[field] = null;

    #         # Number field
    #         } else if (fieldType === 'number') {
    #             if (csv && typeof value === 'string') {
    #                 const numberValue = parseNumber(value);
    #                 if (numberValue === null) {
    #                     throwFieldError(field, fieldType, value);
    #                 }
    #                 row[field] = numberValue;
    #             } else if (value !== null && typeof value !== 'number') {
    #                 throwFieldError(field, fieldType, value);
    #             }

    #         # Datetime field
    #         } else if (fieldType === 'datetime') {
    #             if (typeof value === 'string') {
    #                 const datetimeValue = parseDatetime(value);
    #                 if (datetimeValue === null) {
    #                     throwFieldError(field, fieldType, value);
    #                 }
    #                 row[field] = datetimeValue;
    #             } else if (value !== null && !(value instanceof Date)) {
    #                 throwFieldError(field, fieldType, value);
    #             }

    #         # String field
    #         } else {
    #             if (value !== null && typeof value !== 'string') {
    #                 throwFieldError(field, fieldType, value);
    #             }
    #         }
    #     }
    # }

    # return types;


def _parse_number(unused_text):
    return None

    # const value = Number.parseFloat(text);
    # if (Number.isNaN(value) || !Number.isFinite(value)) {
    #     return null;
    # }
    # return value;


def _parse_datetime(unused_text):
    return None

    # const mDate = text.match(rDate);
    # if (mDate !== null) {
    #     const year = Number.parseInt(mDate.groups.year, 10);
    #     const month = Number.parseInt(mDate.groups.month, 10);
    #     const day = Number.parseInt(mDate.groups.day, 10);
    #     return new Date(year, month - 1, day);
    # } else if (rDatetime.test(text)) {
    #     return new Date(text);
    # }
    # return null;

R_DATE = re.compile(r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$')
R_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$')


def join_data(unused_left_data, unused_right_data, unused_join_expr, unused_right_expr=None, unused_is_left_join=False,
              unused_variables=None, unused_options=None):
    """
    Join two data arrays

    @param {Object} leftData - The left data array
    @param {Object} rightData - The left data array
    @param {string} joinExpr - The join [expression]{@link https://craigahobbs.github.io/bare-script/language/#expressions}
    @param {?string} [rightExpr = null] - The right join [expression]{@link https://craigahobbs.github.io/bare-script/language/#expressions}
    @param {boolean} [isLeftJoin = false] - If true, perform a left join (always include left row)
    @param {?Object} [variables = null] - Additional variables for expression evaluation
    @param {?Object} [options = null] - The [script execution options]{@link module:lib/runtime~ExecuteScriptOptions}
    @returns {Object[]} The joined data array
    """

    return None

    # # Compute the map of row field name to joined row field name
    # const leftNames = {};
    # for (const row of leftData) {
    #     for (const fieldName of Object.keys(row)) {
    #         if (!(fieldName in leftNames)) {
    #             leftNames[fieldName] = fieldName;
    #         }
    #     }
    # }
    # const rightNames = {};
    # for (const row of rightData) {
    #     for (const fieldName of Object.keys(row)) {
    #         if (!(fieldName in rightNames)) {
    #             if (!(fieldName in leftNames)) {
    #                 rightNames[fieldName] = fieldName;
    #             } else {
    #                 let uniqueName = fieldName;
    #                 let ixUnique = 2;
    #                 do {
    #                     uniqueName = `${fieldName}${ixUnique}`;
    #                     ixUnique += 1;
    #                 } while (uniqueName in leftNames || uniqueName in rightNames);
    #                 rightNames[fieldName] = uniqueName;
    #             }
    #         }
    #     }
    # }

    # # Create the evaluation options object
    # let evalOptions = options;
    # if (variables !== null) {
    #     evalOptions = (options !== null ? {...options} : {});
    #     if ('globals' in evalOptions) {
    #         evalOptions.globals = {...evalOptions.globals, ...variables};
    #     } else {
    #         evalOptions.globals = variables;
    #     }
    # }

    # # Parse the left and right expressions
    # const leftExpression = parseExpression(joinExpr);
    # const rightExpression = (rightExpr !== null ? parseExpression(rightExpr) : leftExpression);

    # # Bucket the right rows by the right expression value
    # const rightCategoryRows = {};
    # for (const rightRow of rightData) {
    #     const categoryKey = jsonStringifySortKeys(evaluateExpression(rightExpression, evalOptions, rightRow));
    #     if (!(categoryKey in rightCategoryRows)) {
    #         rightCategoryRows[categoryKey] = [];
    #     }
    #     rightCategoryRows[categoryKey].push(rightRow);
    # }

    # # Join the left with the right
    # const data = [];
    # for (const leftRow of leftData) {
    #     const categoryKey = jsonStringifySortKeys(evaluateExpression(leftExpression, evalOptions, leftRow));
    #     if (categoryKey in rightCategoryRows) {
    #         for (const rightRow of rightCategoryRows[categoryKey]) {
    #             const joinRow = {...leftRow};
    #             for (const [rightName, rightValue] of Object.entries(rightRow)) {
    #                 joinRow[rightNames[rightName]] = rightValue;
    #             }
    #             data.push(joinRow);
    #         }
    #     } else if (!isLeftJoin) {
    #         data.push({...leftRow});
    #     }
    # }

    # return data;


def add_calculated_field(unused_unused_data, unused_field_name, unused_expr, unused_variables=None, unused_options=None):
    """
    Add a calculated field to each row of a data array

    @param {Object[]} data - The data array. Row objects are updated with the calculated field values.
    @param {string} fieldName - The calculated field name
    @param {string} expr - The calculated field expression
    @param {?Object} [variables = null] -  Additional variables for expression evaluation
    @param {?Object} [options = null] - The [script execution options]{@link module:lib/runtime~ExecuteScriptOptions}
    @returns {Object[]} The updated data array
    """
    return None

    # # Parse the calculation expression
    # const calcExpr = parseExpression(expr);

    # # Create the evaluation options object
    # let evalOptions = options;
    # if (variables !== null) {
    #     evalOptions = (options !== null ? {...options} : {});
    #     if ('globals' in evalOptions) {
    #         evalOptions.globals = {...evalOptions.globals, ...variables};
    #     } else {
    #         evalOptions.globals = variables;
    #     }
    # }

    # # Compute the calculated field for each row
    # for (const row of data) {
    #     row[fieldName] = evaluateExpression(calcExpr, evalOptions, row);
    # }
    # return data;


def filter_data(unused_data, unused_expr, unused_variables=None, unused_options=None):
    """
    Filter data rows

    @param {Object[]} data - The data array
    @param {string} expr - The boolean filter [expression]{@link https://craigahobbs.github.io/bare-script/language/#expressions}
    @param {?Object} [variables = null] -  Additional variables for expression evaluation
    @param {?Object} [options = null] - The [script execution options]{@link module:lib/runtime~ExecuteScriptOptions}
    @returns {Object[]} The filtered data array
    """
    return None

    # const result = [];

    # # Parse the filter expression
    # const filterExpr = parseExpression(expr);

    # # Create the evaluation options object
    # let evalOptions = options;
    # if (variables !== null) {
    #     evalOptions = (options !== null ? {...options} : {});
    #     if ('globals' in evalOptions) {
    #         evalOptions.globals = {...evalOptions.globals, ...variables};
    #     } else {
    #         evalOptions.globals = variables;
    #     }
    # }

    # # Filter the data
    # for (const row of data) {
    #     if (evaluateExpression(filterExpr, evalOptions, row)) {
    #         result.push(row);
    #     }
    # }

    # return result;


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


def validate_aggregation(aggregation):
    """
    Validate an aggregation model

    @param {Object} aggregation - The
     [aggregation model]{@link https://craigahobbs.github.io/bare-script/library/model.html#var.vName='Aggregation'}
    @returns {Object} The validated
     [aggregation model]{@link https://craigahobbs.github.io/bare-script/library/model.html#var.vName='Aggregation'}
    @throws [ValidationError]{@link https://craigahobbs.github.io/schema-markdown-js/module-lib_schema.ValidationError.html}
    """

    return validate_type(AGGREGATION_TYPES, 'Aggregation', aggregation)


def aggregate_data(unused_data, unused_aggregation):
    """
    Aggregate data rows

    @param {Object[]} data - The data array
    @param {Object} aggregation - The
     [aggregation model]{@link https://craigahobbs.github.io/bare-script/library/model.html#var.vName='Aggregation'}
    @returns {Object[]} The aggregated data array
    """

    return None

    # const categories = aggregation.categories ?? null;

    # # Create the aggregate rows
    # const categoryRows = {};
    # for (const row of data) {
    #     # Compute the category values
    #     const categoryValues = (categories !== null ? categories.map((categoryField) => row[categoryField]) : null);

    #     # Get or create the aggregate row
    #     let aggregateRow;
    #     const rowKey = (categoryValues !== null ? jsonStringifySortKeys(categoryValues) : '');
    #     if (rowKey in categoryRows) {
    #         aggregateRow = categoryRows[rowKey];
    #     } else {
    #         aggregateRow = {};
    #         categoryRows[rowKey] = aggregateRow;
    #         if (categories !== null) {
    #             for (let ixCategoryField = 0; ixCategoryField < categories.length; ixCategoryField++) {
    #                 aggregateRow[categories[ixCategoryField]] = categoryValues[ixCategoryField];
    #             }
    #         }
    #     }

    #     # Add to the aggregate measure values
    #     for (const measure of aggregation.measures) {
    #         const field = measure.name ?? measure.field;
    #         const value = row[measure.field] ?? null;
    #         if (!(field in aggregateRow)) {
    #             aggregateRow[field] = [];
    #         }
    #         if (value !== null) {
    #             aggregateRow[field].push(value);
    #         }
    #     }
    # }

    # # Compute the measure values aggregate function value
    # const aggregateRows = Object.values(categoryRows);
    # for (const aggregateRow of aggregateRows) {
    #     for (const measure of aggregation.measures) {
    #         const field = measure.name ?? measure.field;
    #         const func = measure.function;
    #         const measureValues = aggregateRow[field];
    #         if (!measureValues.length) {
    #             aggregateRow[field] = null;
    #         } else if (func === 'count') {
    #             aggregateRow[field] = measureValues.length;
    #         } else if (func === 'max') {
    #             aggregateRow[field] = measureValues.reduce((max, val) => (val > max ? val : max));
    #         } else if (func === 'min') {
    #             aggregateRow[field] = measureValues.reduce((min, val) => (val < min ? val : min));
    #         } else if (func === 'sum') {
    #             aggregateRow[field] = measureValues.reduce((sum, val) => sum + val, 0);
    #         } else if (func === 'stddev') {
    #             const average = measureValues.reduce((sum, val) => sum + val, 0) / measureValues.length;
    #             aggregateRow[field] = Math.sqrt(measureValues.reduce((sum, val) => sum + (val - average) ** 2, 0) / measureValues.length);
    #         } else {
    #             # func === 'average'
    #             aggregateRow[field] = measureValues.reduce((sum, val) => sum + val, 0) / measureValues.length;
    #         }
    #     }
    # }

    # return aggregateRows;


def sort_data(unused_data, unused_sorts):
    """
    Sort data rows

    @param {Object[]} data - The data array
    @param {Object[]} sorts - The sort field-name/descending-sort tuples
    @returns {Object[]} The sorted data array
    """

    return None

    # return data.sort((row1, row2) => sorts.reduce((result, sort) => {
    #     if (result !== 0) {
    #         return result;
    #     }
    #     const [field, desc = false] = sort;
    #     const value1 = row1[field] ?? null;
    #     const value2 = row2[field] ?? null;
    #     const compare = compareValues(value1, value2);
    #     return desc ? -compare : compare;
    # }, 0));


def top_data(unused_data, unused_count, unused_category_fields=None):
    """
    Top data rows

    @param {Object[]} data - The data array
    @param {number} count - The number of rows to keep
    @param {?string[]} [categoryFields = null] - The category fields
    @returns {Object[]} The top data array
    """

    return None

    # # Bucket rows by category
    # const categoryRows = {};
    # const categoryOrder = [];
    # for (const row of data) {
    #     const categoryKey = categoryFields === null ? ''
    #         : jsonStringifySortKeys(categoryFields.map((field) => (field in row ? row[field] : null)));
    #     if (!(categoryKey in categoryRows)) {
    #         categoryRows[categoryKey] = [];
    #         categoryOrder.push(categoryKey);
    #     }
    #     categoryRows[categoryKey].push(row);
    # }
    # # Take only the top rows
    # const dataTop = [];
    # const topCount = count;
    # for (const categoryKey of categoryOrder) {
    #     const categoryKeyRows = categoryRows[categoryKey];
    #     const categoryKeyLength = categoryKeyRows.length;
    #     for (let ixRow = 0; ixRow < topCount && ixRow < categoryKeyLength; ixRow++) {
    #         dataTop.push(categoryKeyRows[ixRow]);
    #     }
    # }
    # return dataTop;
