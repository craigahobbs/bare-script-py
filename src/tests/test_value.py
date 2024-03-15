# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import platform
import re
import unittest

from bare_script.value import value_boolean, value_compare, value_is, value_json, value_parse_datetime, \
    value_parse_integer, value_parse_number, value_round_number, value_string, value_type


class TestValue(unittest.TestCase):

    def test_value_type(self):
        # null
        self.assertEqual(value_type(None), 'null')

        # string
        self.assertEqual(value_type('abc'), 'string')

        # boolean
        self.assertEqual(value_type(True), 'boolean')
        self.assertEqual(value_type(False), 'boolean')

        # number
        self.assertEqual(value_type(5), 'number')
        self.assertEqual(value_type(5.5), 'number')
        self.assertEqual(value_type(0), 'number')
        self.assertEqual(value_type(0.), 'number')

        # datetime
        self.assertEqual(value_type(datetime.datetime.now()), 'datetime')

        # object
        self.assertEqual(value_type({}), 'object')

        # array
        self.assertEqual(value_type([]), 'array')

        # function
        self.assertEqual(value_type(value_type), 'function')

        # regex
        self.assertEqual(value_type(re.compile('^test')), 'regex')

        # unknown
        self.assertIsNone(value_type((1, 2, 3)))
        self.assertIsNone(value_type(()))


    def test_value_string(self):
        # null
        self.assertEqual(value_string(None), 'null')

        # string
        self.assertEqual(value_string('abc'), 'abc')
        self.assertEqual(value_string(''), '')

        # boolean
        self.assertEqual(value_string(True), 'true')
        self.assertEqual(value_string(False), 'false')

        # number
        self.assertEqual(value_string(5), '5')
        self.assertEqual(value_string(5.0), '5')
        self.assertEqual(value_string(5.5), '5.5')
        self.assertEqual(value_string(0), '0')
        self.assertEqual(value_string(0.), '0')

        # datetime
        d1 = datetime.datetime(2024, 1, 12, 6, 9)
        d2 = datetime.datetime(2023, 12, 7, 16, 19, 23, 123000)
        d3 = datetime.datetime(2023, 12, 7, 16, 19, 23, 12000)
        d4 = datetime.datetime(2023, 12, 7, 16, 19, 23, 1000)
        d5 = d1.replace(tzinfo=datetime.timezone.utc) + (d1.astimezone() - d1.replace(tzinfo=datetime.timezone.utc))
        def tz_suffix(dt):
            tz_offset = (dt.replace(tzinfo=datetime.timezone.utc) - dt.astimezone()).total_seconds() / 60
            tz_sign = '-' if tz_offset < 0 else '+'
            tz_hour = int(abs(tz_offset) / 60)
            tz_minute = int(abs(tz_offset)) - tz_hour * 60
            return f'{tz_sign}{tz_hour:0{2}d}:{tz_minute:0{2}d}'
        self.assertEqual(value_string(d1), f'2024-01-12T06:09:00{tz_suffix(d1)}')
        self.assertEqual(value_string(d2), f'2023-12-07T16:19:23.123{tz_suffix(d2)}')
        self.assertEqual(value_string(d3), f'2023-12-07T16:19:23.012{tz_suffix(d3)}')
        self.assertEqual(value_string(d4), f'2023-12-07T16:19:23.001{tz_suffix(d4)}')
        self.assertEqual(value_string(d5), f'2024-01-12T06:09:00{tz_suffix(d1)}')

        # https://github.com/python/cpython/issues/80940 - astimezone() fails on Windows for pre-epoch times
        if platform.system() != 'Windows': # pragma: no branch
            d6 = datetime.datetime(900, 1, 1)
            self.assertEqual(value_string(d6), f'0900-01-01T00:00:00{tz_suffix(d6)}')

        # object
        self.assertEqual(value_string({'value': 1}), '{"value":1}')
        self.assertEqual(value_string({}), '{}')

        # array
        self.assertEqual(value_string([1, 2, 3]), '[1,2,3]')
        self.assertEqual(value_string([]), '[]')

        # function
        self.assertEqual(value_string(value_string), '<function>')

        # regex
        self.assertEqual(value_string(re.compile('^test')), '<regex>')

        # unknown
        self.assertEqual(value_string((1, 2, 3)), '<unknown>')
        self.assertEqual(value_string(()), '<unknown>')


    def test_value_json(self):
        self.assertEqual(value_json({'value': 4, 'c': 3, 'a': 1, 'b': 2}), '{"a":1,"b":2,"c":3,"value":4}')
        self.assertEqual(value_json([1, 2, 3]), '[1,2,3]')

        # Indent
        self.assertEqual(value_json({'value': 1}, 2), '{\n  "value": 1\n}')

        # Datetime
        d1 = datetime.datetime(2024, 1, 12, 6, 9)
        d2 = datetime.datetime(2023, 12, 7, 16, 19, 23, 123)
        d3 = d1.replace(tzinfo=datetime.timezone.utc) + (d1.astimezone() - d1.replace(tzinfo=datetime.timezone.utc))
        self.assertEqual(value_json(d1), f'"{value_string(d1)}"')
        self.assertEqual(value_json(d2), f'"{value_string(d2)}"')
        self.assertEqual(value_json(d3), f'"{value_string(d3)}"')

        # Number
        self.assertEqual(value_json(5), '5')
        self.assertEqual(value_json(5.), '5')
        self.assertEqual(value_json({'a': 5}), '{"a":5}')
        self.assertEqual(value_json({'a': 5.}), '{"a":5}')
        self.assertEqual(value_json({'a': 5., 'b': 6.}, 4), '''\
{
    "a": 5,
    "b": 6
}''')

        # Invalid
        self.assertEqual(value_json({'A': 1, 'B': re.compile('^$')}), '{"A":1,"B":null}')
        self.assertEqual(value_json(re.compile('^$')), 'null')


    def test_value_boolean(self):
        # null
        self.assertEqual(value_boolean(None), False)

        # string
        self.assertEqual(value_boolean('abc'), True)
        self.assertEqual(value_boolean(''), False)

        # boolean
        self.assertEqual(value_boolean(True), True)
        self.assertEqual(value_boolean(False), False)

        # number
        self.assertEqual(value_boolean(5), True)
        self.assertEqual(value_boolean(5.5), True)
        self.assertEqual(value_boolean(0), False)
        self.assertEqual(value_boolean(0.), False)

        # datetime
        self.assertEqual(value_boolean(datetime.datetime.now()), True)

        # object
        self.assertEqual(value_boolean({'value': 1}), True)
        self.assertEqual(value_boolean({}), True)

        # array
        self.assertEqual(value_boolean([1, 2, 3]), True)
        self.assertEqual(value_boolean([]), False)

        # function
        self.assertEqual(value_boolean(value_boolean), True)

        # regex
        self.assertEqual(value_boolean(re.compile('^test')), True)

        # unknown
        self.assertEqual(value_boolean((1, 2, 3)), True)
        self.assertEqual(value_boolean(()), True)


    def test_value_is(self):
        # null
        self.assertEqual(value_is(None, None), True)
        self.assertEqual(value_is(None, 0), False)

        # string
        self.assertEqual(value_is('a', 'a'), True)
        self.assertEqual(value_is('a', 'b'), False)

        # boolean
        self.assertEqual(value_is(True, True), True)
        self.assertEqual(value_is(False, False), True)
        self.assertEqual(value_is(False, True), False)

        # number
        self.assertEqual(value_is(5, 5), True)
        self.assertEqual(value_is(5., 5.), True)
        self.assertEqual(value_is(5, 5.), True)
        self.assertEqual(value_is(5., 5), True)
        self.assertEqual(value_is(5, 6), False)
        self.assertEqual(value_is(5., 6.), False)

        # datetime
        d1 = value_parse_datetime('2024-01-12')
        d2 = value_parse_datetime('2024-01-12')
        self.assertEqual(value_is(d1, d1), True)
        self.assertEqual(value_is(d1, d2), False)

        # object
        o1 = {'value': 1}
        o2 = {'value': 1}
        self.assertEqual(value_is(o1, o1), True)
        self.assertEqual(value_is(o1, o2), False)

        # array
        a1 = [1, 2, 3]
        a2 = [1, 2, 3]
        self.assertEqual(value_is(a1, a1), True)
        self.assertEqual(value_is(a1, a2), False)

        # function
        def f1():
            pass
        def f2():
            pass
        f1()
        f2()
        self.assertEqual(value_is(f1, f1), True)
        self.assertEqual(value_is(f1, f2), False)

        # regex
        r1 = re.compile('^test')
        r2 = re.compile('^test')
        r3 = re.compile('^test2')
        self.assertEqual(value_is(r1, r1), True)
        self.assertEqual(value_is(r1, r2), True)
        self.assertEqual(value_is(r1, r3), False)


    def test_value_compare(self):
        # null
        self.assertEqual(value_compare(None, None), 0)
        self.assertEqual(value_compare(None, 0), -1)
        self.assertEqual(value_compare(0, None), 1)

        # string
        self.assertEqual(value_compare('a', 'a'), 0)
        self.assertEqual(value_compare('a', 'b'), -1)
        self.assertEqual(value_compare('b', 'a'), 1)

        # boolean
        self.assertEqual(value_compare(True, True), 0)
        self.assertEqual(value_compare(False, False), 0)
        self.assertEqual(value_compare(False, True), -1)
        self.assertEqual(value_compare(True, False), 1)

        # number
        self.assertEqual(value_compare(5, 5), 0)
        self.assertEqual(value_compare(5, 5.), 0)
        self.assertEqual(value_compare(5., 5), 0)
        self.assertEqual(value_compare(5., 5.), 0)
        self.assertEqual(value_compare(5, 6), -1)
        self.assertEqual(value_compare(5, 5.5), -1)
        self.assertEqual(value_compare(5.5, 6), -1)
        self.assertEqual(value_compare(5., 5.5), -1)
        self.assertEqual(value_compare(6, 5), 1)
        self.assertEqual(value_compare(5.5, 5), 1)
        self.assertEqual(value_compare(6, 5.5), 1)
        self.assertEqual(value_compare(5.5, 5.), 1)

        # datetime
        d1 = value_parse_datetime('2024-02-12')
        d2 = value_parse_datetime('2024-02-11')
        self.assertEqual(value_compare(d1, d1), 0)
        self.assertEqual(value_compare(d2, d1), -1)
        self.assertEqual(value_compare(d1, d2), 1)

        # object
        self.assertEqual(value_compare({'value': 1}, {'value': 1}), 0)
        self.assertEqual(value_compare({'value': 1}, {'value': 2}), 0)
        self.assertEqual(value_compare({'value': 2}, {'value': 1}), 0)

        # array
        self.assertEqual(value_compare([1, 2, 3], [1, 2, 3]), 0)
        self.assertEqual(value_compare([], []), 0)
        self.assertEqual(value_compare([1, 2, 3], [1, 2, 4]), -1)
        self.assertEqual(value_compare([1, 2], [1, 2, 3]), -1)
        self.assertEqual(value_compare([1, 2, 4], [1, 2, 3]), 1)
        self.assertEqual(value_compare([1, 2, 3], [1, 2]), 1)

        # function
        self.assertEqual(value_compare(value_compare, value_type), 0)

        # regex
        self.assertEqual(value_compare(re.compile('^test1'), re.compile('^test1')), 0)
        self.assertEqual(value_compare(re.compile('^test1'), re.compile('^test2')), 0)
        self.assertEqual(value_compare(re.compile('^test2'), re.compile('^test1')), 0)


    def test_value_compare_invalid(self):
        # array < boolean
        self.assertEqual(value_compare([1, 2, 3], True), -1)
        self.assertEqual(value_compare([1, 2, 3], False), -1)
        self.assertEqual(value_compare(True, [1, 2, 3]), 1)
        self.assertEqual(value_compare(False, [1, 2, 3]), 1)

        # boolean < datetime
        dt = datetime.datetime.now()
        self.assertEqual(value_compare(True, dt), -1)
        self.assertEqual(value_compare(False, dt), -1)
        self.assertEqual(value_compare(dt, True), 1)
        self.assertEqual(value_compare(dt, False), 1)

        # boolean < number
        self.assertEqual(value_compare(True, 1), -1)
        self.assertEqual(value_compare(False, 1), -1)
        self.assertEqual(value_compare(True, 0), -1)
        self.assertEqual(value_compare(False, 0), -1)
        self.assertEqual(value_compare(1, True), 1)
        self.assertEqual(value_compare(1, False), 1)
        self.assertEqual(value_compare(0, True), 1)
        self.assertEqual(value_compare(0, False), 1)

        # datetime < function
        self.assertEqual(value_compare(dt, value_compare), -1)
        self.assertEqual(value_compare(value_compare, dt), 1)

        # function < number
        self.assertEqual(value_compare(value_compare, 1), -1)
        self.assertEqual(value_compare(value_compare, 0), -1)
        self.assertEqual(value_compare(1, value_compare), 1)
        self.assertEqual(value_compare(0, value_compare), 1)

        # number < object
        self.assertEqual(value_compare(1, {}), -1)
        self.assertEqual(value_compare({}, 1), 1)

        # object < regex
        self.assertEqual(value_compare({}, re.compile('^test')), -1)
        self.assertEqual(value_compare(re.compile('^test'), {}), 1)

        # regex < string
        self.assertEqual(value_compare(re.compile('^test'), 'abc'), -1)
        self.assertEqual(value_compare('abc', re.compile('^test')), 1)

        # string < unknown
        self.assertEqual(value_compare('abc', (1, 2, 3)), -1)
        self.assertEqual(value_compare((1, 2, 3), 'abc'), 1)


    def test_value_round_number(self):
        self.assertEqual(value_round_number(1.5, 0), 2)
        self.assertEqual(value_round_number(2.5, 0), 3)
        self.assertEqual(value_round_number(1.25, 1), 1.3)
        self.assertEqual(value_round_number(1.35, 1), 1.4)


    def test_value_parse_number(self):
        self.assertEqual(value_parse_number('123.45'), 123.45)
        self.assertEqual(value_parse_number('-123.45'), -123.45)
        self.assertEqual(value_parse_number('123'), 123)
        self.assertEqual(value_parse_number('123.'), 123)
        self.assertEqual(value_parse_number('.45'), 0.45)
        self.assertEqual(value_parse_number('1.23e3'), 1230)
        self.assertEqual(value_parse_number('4.56E+3'), 4560)
        self.assertEqual(value_parse_number('0.123e-2'), 0.00123)
        self.assertEqual(value_parse_number('0'), 0)
        self.assertEqual(value_parse_number('0.0'), 0)
        self.assertEqual(value_parse_number('0e0'), 0)

        # Padding
        self.assertEqual(value_parse_number('  123.45  '), 123.45)

        # Special values
        self.assertIsNone(value_parse_number('NaN'))
        self.assertIsNone(value_parse_number('Infinity'))

        # Parse failure
        self.assertIsNone(value_parse_number('invalid'))
        self.assertIsNone(value_parse_number('1234.45asdf'))
        self.assertIsNone(value_parse_number('1234.45 asdf'))


    def test_value_parse_integer(self):
        self.assertEqual(value_parse_integer('123'), 123)
        self.assertEqual(value_parse_integer('-123'), -123)
        self.assertEqual(value_parse_integer('0'), 0)

        # Padding
        self.assertEqual(value_parse_integer('  123  '), 123)

        # No floating point
        self.assertEqual(value_parse_integer('123.'), None)
        self.assertEqual(value_parse_integer('.45'), None)
        self.assertEqual(value_parse_integer('1.23e3'), None)
        self.assertEqual(value_parse_integer('4.56E+3'), None)
        self.assertEqual(value_parse_integer('0.123e-2'), None)
        self.assertEqual(value_parse_integer('0.0'), None)
        self.assertEqual(value_parse_integer('0e0'), None)

        # Special values
        self.assertEqual(value_parse_integer('NaN'), None)
        self.assertEqual(value_parse_integer('Infinity'), None)

        # Parse failure
        self.assertEqual(value_parse_integer('invalid'), None)
        self.assertEqual(value_parse_integer('123asdf'), None)
        self.assertEqual(value_parse_integer('123 asdf'), None)


    def test_value_parse_datetime(self):
        self.assertEqual(
            value_parse_datetime('2022-08-29T15:08:00+00:00'),
            datetime.datetime(2022, 8, 29, 15, 8, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        )
        self.assertEqual(
            value_parse_datetime('2022-08-29T15:08:00Z'),
            datetime.datetime(2022, 8, 29, 15, 8, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        )
        self.assertEqual(
            value_parse_datetime('2022-08-29T15:08:00.123+00:00'),
            datetime.datetime(2022, 8, 29, 15, 8, 0, 123000, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        )
        self.assertEqual(
            value_parse_datetime('2022-08-29T15:08:00.123567+00:00'),
            datetime.datetime(2022, 8, 29, 15, 8, 0, 123000, tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
        )

        # Date
        self.assertEqual(
            value_parse_datetime('2022-08-29'),
            datetime.datetime(2022, 8, 29)
        )

        # Parse failure
        self.assertIsNone(value_parse_datetime('2022-08-29T15:08:00'))
        self.assertIsNone(value_parse_datetime('invalid'))
