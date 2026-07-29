# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

import math
from datetime import datetime
from sys import argv

from schema_markdown import decode_query_string, encode_query_string, parse_schema_markdown, validate_type


language = argv[1] if len(argv) > 1 else 'Python'
testArg = argv[2] if len(argv) > 2 else None

# The performance tests and their iteration counts - tuned so the fastest runtime's measurement stays well above
# millisecond timer resolution while the slowest runtime's measurement doesn't run excessively long
perfTests = {
    'mandelbrot': 1,
    'schemaParse': 250,
    'schemaValidate': 250,
    'urlEncode': 2000,
    'urlDecode': 2000
}

def main():
    for test in ([testArg] if testArg is not None else perfTests.keys()):
        # Skip tests this program doesn't implement (e.g. BareScript-only tests)
        runs = perfTests.get(test)
        if runs is None:
            continue
        timeMs = perfRun(test, runs)
        print(f'{language},{test},{runs},{timeMs}')


def perfRun(test, iterations):
    # mandelbrot?
    if test == 'mandelbrot':
        # Compute the "seahorse valley", a computationally dense region on the Mandelbrot set boundary
        timeBegin = datetime.now()
        for _ in range(iterations):
            mandelbrotSet(120, 80, -0.75, 0.1, 0.05, 60)
        timeEnd = datetime.now()

    # schemaParse?
    elif test == 'schemaParse':
        # Warmup
        parse_schema_markdown(schemaText)

        timeBegin = datetime.now()
        for _ in range(iterations):
            parse_schema_markdown(schemaText)
        timeEnd = datetime.now()

    # schemaValidate?
    elif test == 'schemaValidate':
        # Warmup
        types = parse_schema_markdown(schemaText)
        validate_type(types, 'Types', types)

        timeBegin = datetime.now()
        for _ in range(iterations):
            validate_type(types, 'Types', types)
        timeEnd = datetime.now()

    # urlEncode?
    elif test == 'urlEncode':
        # Warmup
        encode_query_string(urlArgs)

        timeBegin = datetime.now()
        for _ in range(iterations):
            encode_query_string(urlArgs)
        timeEnd = datetime.now()

    # urlDecode?
    elif test == 'urlDecode':
        # Warmup
        decode_query_string(urlHash)

        timeBegin = datetime.now()
        for _ in range(iterations):
            decode_query_string(urlHash)
        timeEnd = datetime.now()

    return (timeEnd - timeBegin).total_seconds() * 1000


def mandelbrotSet(width, height, xCoord, yCoord, xRange, maxIter):
    # Compute the set extents
    yRange = (height / width) * xRange
    xMin = xCoord - 0.5 * xRange
    yMin = yCoord - 0.5 * yRange

    # Compute each pixel in the set
    ix = 0
    while ix < width:
        iy = 0
        while iy < height:
            xValue = xMin + (ix / (width - 1)) * xRange
            yValue = yMin + (iy / (height - 1)) * yRange
            mandelbrotValue(xValue, yValue, maxIter)
            iy = iy + 1
        ix = ix + 1


def mandelbrotValue(xValue, yValue, maxIter):
    # c1 = complex(x, y)
    # c2 = complex(0, 0)
    c1r = xValue
    c1i = yValue
    c2r = 0
    c2i = 0

    # Iteratively compute the next c2 value
    iter_ = 1
    while iter_ <= maxIter:
        # Done?
        if math.sqrt(c2r * c2r + c2i * c2i) > 2:
            return iter_

        # c2 = c2 * c2 + c1
        c2rNew = c2r * c2r - c2i * c2i + c1r
        c2i = 2 * c2r * c2i + c1i
        c2r = c2rNew

        iter_ = iter_ + 1

    # Hit max iterations - the point is in the Mandelbrot set
    return 0


schemaText = '''\
# Map of user type name to user type model
typedef UserType{len > 0} Types


# Union representing a member type
union Type

    # A built-in type
    BuiltinType builtin

    # An array type
    Array array

    # A dictionary type
    Dict dict

    # A user type name
    string user


# A type or member's attributes
struct Attributes

    # If true, the value may be null
    optional bool nullable

    # The value is equal
    optional float eq

    # The value is less than
    optional float lt

    # The value is less than or equal to
    optional float lte

    # The value is greater than
    optional float gt

    # The value is greater than or equal to
    optional float gte

    # The length is equal to
    optional int lenEq

    # The length is less-than
    optional int lenLT

    # The length is less than or equal to
    optional int lenLTE

    # The length is greater than
    optional int lenGT

    # The length is greater than or equal to
    optional int lenGTE


# The built-in type enumeration
enum BuiltinType

    # The string type
    string

    # The integer type
    int

    # The float type
    float

    # The boolean type
    bool

    # A date formatted as an ISO-8601 date string
    date

    # A date/time formatted as an ISO-8601 date/time string
    datetime

    # A UUID formatted as string
    uuid

    # A value of any type
    any


# An array type
struct Array

    # The contained type
    Type type

    # The contained type's attributes
    optional Attributes attr


# A dictionary type
struct Dict

    # The contained value type
    Type type

    # The contained value type's attributes
    optional Attributes attr

    # The contained key type
    optional Type keyType

    # The contained key type's attributes
    optional Attributes keyAttr


# A user type
union UserType

    # An enumeration type
    Enum enum

    # A struct type
    Struct struct

    # A type definition
    Typedef typedef

    # A JSON web API (not reference-able)
    Action action


# User type base struct
struct UserBase

    # The user type name
    string name

    # The documentation markdown text lines
    optional string[] doc

    # The documentation group name
    optional string docGroup


# An enumeration type
struct Enum (UserBase)

    # The enum's base enumerations
    optional string[len > 0] bases

    # The enumeration values
    optional EnumValue[len > 0] values


# An enumeration type value
struct EnumValue

    # The value string
    string name

    # The documentation markdown text lines
    optional string[] doc


# A struct type
struct Struct (UserBase)

    # The struct's base classes
    optional string[len > 0] bases

    # If true, the struct is a union and exactly one of the optional members is present
    optional bool union

    # The struct members
    optional StructMember[len > 0] members


# A struct member
struct StructMember

    # The member name
    string name

    # The documentation markdown text lines
    optional string[] doc

    # The member type
    Type type

    # The member type attributes
    optional Attributes attr

    # If true, the member is optional and may not be present
    optional bool optional


# A typedef type
struct Typedef (UserBase)

    # The typedef's type
    Type type

    # The typedef's type attributes
    optional Attributes attr


# A JSON web service API
struct Action (UserBase)

    # The action's URLs
    optional ActionURL[len > 0] urls

    # The path parameters struct type name
    optional string path

    # The query parameters struct type name
    optional string query

    # The content body struct type name
    optional string input

    # The response body struct type name
    optional string output

    # The custom error response codes enum type name
    optional string errors


# An action URL model
struct ActionURL

    # The HTTP method. If not provided, matches all HTTP methods.
    optional string method

    # The URL path. If not provided, uses the default URL path of "/<actionName>".
    optional string path'''


# An arguments object to encode as a query string - the same shape a MarkdownUp application passes
# to urlEncodeQueryString when building a link's URL variables
urlArgs = {
    'url': 'doc/index.md',
    'name': 'Getting Started',
    'count': 17,
    'show': True,
    'filter': 'a & b',
    'rows': [1, 2, 3],
    'nested': {'alpha': 'one', 'beta': 'two 2', 'gamma': [10, 20]}
}


# A query string to decode - the application hash a MarkdownUp application decodes on page load
urlHash = 'url=doc%2Findex.md&var.vGroup=%27url.bare%27&var.vName=%27Getting%20Started%27&' \
    'var.vCount=17&var.vShow=true&var.vFilter=%27a%20%26%20b%27&var.vRows.0=1&var.vRows.1=2&var.vRows.2=3'


# Execute main
main()
