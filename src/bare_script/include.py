# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
Include library script globals and native stub functions
"""

import os

if not os.environ.get('BARESCRIPT_RUNTIME_PY'): # pragma: no cover
    try:
        from .runtime_c import execute_script
    except ImportError:
        from .runtime import execute_script
else:
    from .runtime import execute_script


# The include library script globals - execute the include library script
_INCLUDE_GLOBALS = {}
execute_script(
    {
        'statements': [
            {'include': {'includes': [
                {'url': 'data.bare', 'system': True},
                {'url': 'dataLineChart.bare', 'system': True},
                {'url': 'dataTable.bare', 'system': True},
                {'url': 'elementModel.bare', 'system': True},
                {'url': 'markdown.bare', 'system': True},
                {'url': 'markdownElements.bare', 'system': True},
                {'url': 'markdownParser.bare', 'system': True},
                {'url': 'qrcode.bare', 'system': True},
                {'url': 'schema.bare', 'system': True},
                {'url': 'schemaDoc.bare', 'system': True},
                {'url': 'schemaParser.bare', 'system': True},
                {'url': 'schemaTypeModel.bare', 'system': True},
                {'url': 'url.bare', 'system': True}
            ]}}
        ]
    },
    {
        'globals': _INCLUDE_GLOBALS
    }
)


# The include library log function
_INCLUDE_LOG_FN = None


def include_set_log_fn(log_fn):
    """
    Set the include library stub function log function. Include library logging is debug-level,
    so setting a log function also enables debug logging for the stub function calls.

    :param log_fn: The log function, or None to disable logging
    :type log_fn: function or None
    """

    # pylint: disable-next=global-statement
    global _INCLUDE_LOG_FN
    _INCLUDE_LOG_FN = log_fn


def _include_options():
    # Create an include library stub function execute options object
    if _INCLUDE_LOG_FN is not None:
        return {'globals': _INCLUDE_GLOBALS, 'logFn': _INCLUDE_LOG_FN, 'debug': True}
    return {'globals': _INCLUDE_GLOBALS}


#
# data.bare
#


def data_aggregate(data, aggregation):
    """
    Aggregate a data array

    :param data: The data array
    :type data: list(dict)
    :param aggregation: The aggregation model
    :type aggregation: dict
    :return: The aggregated data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataAggregate']([data, aggregation], _include_options())


def data_calculated_field(data, field_name, expr, variables=None):
    """
    Add a calculated field to a data array

    :param data: The data array
    :type data: list(dict)
    :param str field_name: The calculated field name
    :param str expr: The calculated field expression
    :param variables: The expression variables object
    :type variables: dict or None, optional
    :return: The updated data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataCalculatedField']([data, field_name, expr, variables], _include_options())


def data_filter(data, expr, variables=None):
    """
    Filter a data array

    :param data: The data array
    :type data: list(dict)
    :param str expr: The filter expression
    :param variables: The expression variables object
    :type variables: dict or None, optional
    :return: The filtered data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataFilter']([data, expr, variables], _include_options())


def data_join(left_data, right_data, join_expr, right_expr=None, is_left_join=None, variables=None):
    """
    Join two data arrays

    :param left_data: The left data array
    :type left_data: list(dict)
    :param right_data: The right data array
    :type right_data: list(dict)
    :param str join_expr: The join expression
    :param right_expr: The right join expression
    :type right_expr: str or None, optional
    :param is_left_join: If True, perform a left join (always include left row)
    :type is_left_join: bool or None, optional
    :param variables: The join expression variables object
    :type variables: dict or None, optional
    :return: The joined data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataJoin'](
        [left_data, right_data, join_expr, right_expr, is_left_join, variables], _include_options()
    )


def data_parse_csv(text):
    """
    Parse CSV text to a data array

    :param str text: The CSV text
    :return: The data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataParseCSV']([text], _include_options())


def data_sort(data, sorts):
    """
    Sort a data array

    :param data: The data array
    :type data: list(dict)
    :param sorts: The array of sort tuples, [field] or [field, descending]
    :type sorts: list(list)
    :return: The sorted data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataSort']([data, sorts], _include_options())


def data_top(data, count=None, category_fields=None):
    """
    Keep the top rows for each category

    :param data: The data array
    :type data: list(dict)
    :param count: The number of rows to keep (default is 1)
    :type count: int or None, optional
    :param category_fields: The category fields
    :type category_fields: list(str) or None, optional
    :return: The top data array
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['dataTop']([data, count, category_fields], _include_options())


def data_validate(data, csv=None):
    """
    Validate a data array

    :param data: The data array
    :type data: list(dict)
    :param csv: If True, parse value strings
    :type csv: bool or None, optional
    :return: The map of field name to field type
    :rtype: dict
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['dataValidateEx']([data, csv], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'])
    return result['result']


#
# dataLineChart.bare
#


def data_line_chart_elements(data, line_chart, options=None):
    """
    Render a line chart as an element model

    :param data: The data array
    :type data: list(dict)
    :param line_chart: The line chart model
    :type line_chart: dict
    :param options: The line chart options object
    :type options: dict or None, optional
    :return: The line chart element model
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['dataLineChartElements']([data, line_chart, options], _include_options())


def data_line_chart_validate(line_chart):
    """
    Validate a line chart model

    :param line_chart: The line chart model
    :type line_chart: dict
    :return: The validated line chart model
    :rtype: dict
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['dataLineChartValidateEx']([line_chart], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'], result['memberFqn'])
    return result['result']


#
# dataTable.bare
#


def data_table_elements(data, data_table=None):
    """
    Render a data table as an element model

    :param data: The data array
    :type data: list(dict)
    :param data_table: The data table model
    :type data_table: dict or None, optional
    :return: The data table element model
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['dataTableElements']([data, data_table], _include_options())


def data_table_markdown(data, model=None):
    """
    Create the array of Markdown table line strings

    :param data: The array of row objects
    :type data: list(dict)
    :param model: The data table model
    :type model: dict or None, optional
    :return: The array of Markdown table line strings
    :rtype: list(str)
    """

    return _INCLUDE_GLOBALS['dataTableMarkdown']([data, model], _include_options())


def data_table_validate(data_table):
    """
    Validate a data table model

    :param data_table: The data table model
    :type data_table: dict
    :return: The validated data table model
    :rtype: dict
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['dataTableValidateEx']([data_table], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'], result['memberFqn'])
    return result['result']


#
# elementModel.bare
#


def element_model_to_string(elements, indent=None):
    """
    Render an element model to an HTML or SVG string

    :param elements: The element model
    :type elements: dict or list or None
    :param indent: The indentation string or number of spaces
    :type indent: str or int or None, optional
    :return: The HTML or SVG string
    :rtype: str
    """

    return _INCLUDE_GLOBALS['elementModelToString']([elements, indent], _include_options())


def element_model_validate(elements):
    """
    Validate an element model

    :param elements: The element model
    :type elements: dict or list or None
    :return: The validated element model
    :rtype: dict or list or None
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['elementModelValidateEx']([elements], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'])
    return result['result']


#
# markdown.bare
#


def markdown_escape(text):
    """
    Escape a string for inclusion in Markdown text

    :param str text: The text to escape
    :return: The escaped text
    :rtype: str
    """

    return _INCLUDE_GLOBALS['markdownEscape']([text], _include_options())


def markdown_header_id(text):
    """
    Generate a Markdown header ID from text

    :param str text: The text
    :return: The header element ID
    :rtype: str
    """

    return _INCLUDE_GLOBALS['markdownHeaderId']([text], _include_options())


def markdown_paragraph_text(paragraph):
    """
    Get a Markdown paragraph model's text

    :param paragraph: The Markdown paragraph model
    :type paragraph: dict
    :return: The paragraph text string
    :rtype: str
    """

    return _INCLUDE_GLOBALS['markdownParagraphText']([paragraph], _include_options())


def markdown_title(markdown):
    """
    Get a Markdown model's title

    :param markdown: The Markdown model
    :type markdown: dict
    :return: The title string or None
    :rtype: str or None
    """

    return _INCLUDE_GLOBALS['markdownTitle']([markdown], _include_options())


def markdown_validate(markdown):
    """
    Validate a Markdown model

    :param markdown: The Markdown model
    :type markdown: dict
    :return: The validated Markdown model
    :rtype: dict
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['markdownValidateEx']([markdown], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'], result['memberFqn'])
    return result['result']


#
# markdownElements.bare
#


def markdown_elements(markdown, options=None):
    """
    Generate an element model from a Markdown model

    :param markdown: The Markdown model
    :type markdown: dict
    :param options: The Markdown elements options object
    :type options: dict or None, optional
    :return: The Markdown's element model
    :rtype: list
    """

    return _INCLUDE_GLOBALS['markdownElements']([markdown, options], _include_options())


#
# markdownParser.bare
#


def markdown_parse(text):
    """
    Parse Markdown text into a Markdown model

    :param text: The Markdown text
    :type text: str or list(str)
    :return: The Markdown model
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['markdownParse']([text], _include_options())


#
# qrcode.bare
#


def qrcode_elements(message, size, level=None):
    """
    Generate the element model for a QR code

    :param message: The QR code message or the QR code matrix
    :type message: str or list(list)
    :param int size: The size of the QR code, in pixels
    :param level: The error correction level: 'low', 'medium', 'quartile', or 'high'
    :type level: str or None, optional
    :return: The QR code SVG element model
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['qrcodeElements']([message, size, level], _include_options())


def qrcode_matrix(message, level=None):
    """
    Generate a QR code pixel matrix

    :param str message: The QR code message
    :param level: The error correction level: 'low', 'medium', 'quartile', or 'high'
    :type level: str or None, optional
    :return: The QR code pixel matrix
    :rtype: list(list)
    """

    return _INCLUDE_GLOBALS['qrcodeMatrix']([message, level], _include_options())


#
# schema.bare
#


def schema_get_enum_values(types, enum_model):
    """
    Get an enum's values (inherited values first)

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :type types: dict
    :param enum_model: The enum model
    :type enum_model: dict
    :return: The array of enum value models
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['schemaGetEnumValues']([types, enum_model], _include_options())


def schema_get_referenced_types(types, type_name, referenced_types=None):
    """
    Get a user type's referenced type model

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :type types: dict
    :param str type_name: The type name
    :param referenced_types: A map of referenced user type name to user type model to update
    :type referenced_types: dict or None, optional
    :return: The referenced type model
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['schemaGetReferencedTypes']([types, type_name, referenced_types], _include_options())


def schema_get_struct_members(types, struct):
    """
    Get a struct's members (inherited members first)

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :type types: dict
    :param struct: The struct model
    :type struct: dict
    :return: The array of struct member models
    :rtype: list(dict)
    """

    return _INCLUDE_GLOBALS['schemaGetStructMembers']([types, struct], _include_options())


def schema_validate(types, type_name, value):
    """
    Validate a value using a schema type model

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :type types: dict
    :param str type_name: The type name
    :param value: The value to validate
    :return: The validated, transformed value
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['schemaValidateEx']([types, type_name, value], _include_options())
    if 'error' in result:
        raise SchemaValidationError(result['error'], result['memberFqn'])
    return result['result']


#
# schemaDoc.bare
#


def schema_doc_markdown(types, type_name, options=None):
    """
    Generate the Schema Markdown user type documentation as an array of Markdown text lines

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :type types: dict
    :param str type_name: The type name
    :param options: The schema documentation options object
    :type options: dict or None, optional
    :return: The array of Markdown text lines
    :rtype: list(str)
    """

    return _INCLUDE_GLOBALS['schemaDocMarkdown']([types, type_name, options], _include_options())


#
# schemaParser.bare
#


def schema_parse(text):
    """
    Parse Schema Markdown text

    :param text: The `Schema Markdown <https://craigahobbs.github.io/schema-markdown-js/language/>`__ text
    :type text: str or list(str)
    :return: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :rtype: dict
    :raises SchemaParserError: A parsing error occurred
    """

    result = _INCLUDE_GLOBALS['schemaParseEx']([text], _include_options())
    if 'errors' in result:
        raise SchemaParserError(result['errors'])
    return result['result']


#
# schemaTypeModel.bare
#


def schema_type_model():
    """
    Get the Schema Markdown type model

    :return: The Schema Markdown `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__
    :rtype: dict
    """

    return _INCLUDE_GLOBALS['schemaTypeModel']([], _include_options())


def schema_type_model_validate(types):
    """
    Validate a Schema Markdown type model

    :param types: The schema's `type model <https://craigahobbs.github.io/bare-script/model/#var.vName='Types'>`__ to validate
    :type types: dict
    :return: The validated type model
    :rtype: dict
    :raises SchemaValidationError: A validation error occurred
    """

    result = _INCLUDE_GLOBALS['schemaTypeModelValidateEx']([types], _include_options())
    if 'errors' in result:
        raise SchemaValidationError('\n'.join(result['errors']))
    return result['result']


#
# url.bare
#


def url_decode_component(string):
    """
    Decode a percent-encoded string component

    :param str string: The string component to decode
    :return: The decoded string, or None on failure
    :rtype: str or None
    """

    return _INCLUDE_GLOBALS['urlDecodeComponent']([string], _include_options())


def url_decode_query_string(query_string):
    """
    Decode a URL query string to an object

    :param str query_string: The query string to decode
    :return: The decoded query string object, or None on failure
    :rtype: dict or None
    """

    return _INCLUDE_GLOBALS['urlDecodeQueryString']([query_string], _include_options())


def url_encode(url):
    """
    Encode a URL

    :param str url: The URL to encode
    :return: The encoded URL
    :rtype: str
    """

    return _INCLUDE_GLOBALS['urlEncode']([url], _include_options())


def url_encode_component(url):
    """
    Encode a URL component

    :param str url: The URL component to encode
    :return: The encoded URL component
    :rtype: str
    """

    return _INCLUDE_GLOBALS['urlEncodeComponent']([url], _include_options())


def url_encode_query_string(obj):
    """
    Encode an object as a URL query string

    :param obj: The object to encode
    :type obj: dict
    :return: The encoded query string
    :rtype: str
    """

    return _INCLUDE_GLOBALS['urlEncodeQueryString']([obj], _include_options())


#
# Errors
#


class SchemaParserError(Exception):
    """
    A Schema Markdown parser error

    :param errors: The list of error strings
    :type errors: list(str)
    """

    __slots__ = ('errors',)

    def __init__(self, errors):
        super().__init__('\n'.join(errors))

        #: The list of error strings
        self.errors = errors


class SchemaValidationError(Exception):
    """
    A schema type model validation error

    :param str msg: The validation error message
    :param member_fqn: The fully-qualified member name or None
    :type member_fqn: str or None
    """

    __slots__ = ('member_fqn',)

    def __init__(self, msg, member_fqn=None):
        super().__init__(msg)

        #: The fully-qualified member name or None
        self.member_fqn = member_fqn
