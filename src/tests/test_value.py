# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import platform
import re
import unittest
import uuid

from schema_markdown import ValidationError

from bare_script.value import ValueArgsError, value_args_model, value_args_validate, value_boolean, value_compare, value_is, value_json, \
    value_normalize_datetime, value_parse_datetime, value_parse_integer, value_parse_number, value_round_number, value_string, value_type


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

        # datetime (date)
        self.assertEqual(value_type(datetime.date.today()), 'datetime')

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

        # datetime (date)
        d6 = datetime.date(2024, 1, 12)
        self.assertEqual(value_string(d6), f'2024-01-12T00:00:00{tz_suffix(d1)}')

        # https://github.com/python/cpython/issues/80940 - astimezone() fails on Windows for pre-epoch times
        if platform.system() != 'Windows': # pragma: no cover
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

        # Additional stringify-able values
        self.assertEqual(value_string(uuid.UUID('47f833d3-4414-4c4a-ac02-ceb36898ff87')), '47f833d3-4414-4c4a-ac02-ceb36898ff87')

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

        # Datetime (date)
        d4 = datetime.date.today()
        self.assertEqual(value_json(d4), f'"{value_string(d4)}"')

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

        # Function
        self.assertEqual(value_json(value_boolean), '"<function>"')

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

        # datetime (date)
        self.assertEqual(value_boolean(datetime.date.today()), True)

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

        # datetime (date)
        d3 = datetime.date(2024, 1, 12)
        self.assertEqual(value_is(d3, d3), True)
        self.assertEqual(value_is(d3, d2), False)

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

        # datetime (date)
        d3 = datetime.date(2024, 2, 12)
        self.assertEqual(value_compare(d3, d3), 0)
        self.assertEqual(value_compare(d2, d3), -1)
        self.assertEqual(value_compare(d3, d2), 1)

        # object
        self.assertEqual(value_compare({'value': 1}, {'value': 1}), 0)
        self.assertEqual(value_compare({'value': 1}, {'value': 2}), -1)
        self.assertEqual(value_compare({'value': 2}, {'value': 1}), 1)
        self.assertEqual(value_compare({'a': 1}, {'b': 1}), -1)
        self.assertEqual(value_compare({'b': 1}, {'a': 1}), 1)
        self.assertEqual(value_compare({'a': 1}, {'b': 2, 'a': 1}), -1)
        self.assertEqual(value_compare({'b': 2, 'a': 1}, {'a': 1}), 1)

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

        # Nested
        self.assertEqual(value_compare({'a': [{'d': 1}]}, {'a': [{'d': 1}]}), 0)
        self.assertEqual(value_compare({'a': [{'d': 1}]}, {'a': [{'d': 2}]}), -1)
        self.assertEqual(value_compare({'a': [{'d': 2}]}, {'a': [{'d': 1}]}), 1)


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


    def test_value_args_validate(self):
        fn_args = value_args_model([
            {'name': 'argNumber', 'type': 'number'},
            {'name': 'argString', 'type': 'string'},
            {'name': 'argArray', 'type': 'array'},
            {'name': 'argObject', 'type': 'object'},
            {'name': 'argDatetime', 'type': 'datetime'},
            {'name': 'argRegex', 'type': 'regex'},
            {'name': 'argFunction', 'type': 'function'}
        ])
        array_value = []
        object_value = {}
        datetime_value = datetime.datetime.now()
        regex_value = re.compile(r'^abc$')
        def function_value():
            return 'Hello'
        args = [5, 'abc', array_value, object_value, datetime_value, regex_value, function_value]
        args_valid = value_args_validate(fn_args, args)
        self.assertEqual(function_value(), 'Hello')
        self.assertIs(args_valid, args)
        self.assertListEqual(
            args_valid,
            [5, 'abc', array_value, object_value, datetime_value, regex_value, function_value]
        )

        # Invalid arguments
        for ix_arg, fn_arg in enumerate(fn_args):
            arg_invalid = 5 if fn_arg['type'] == 'string' else 'abc'
            args_invalid = list(args)
            args_invalid[ix_arg] = arg_invalid
            with self.assertRaises(ValueArgsError) as cm_exc:
                value_args_validate(fn_args, args_invalid)
            self.assertEqual(str(cm_exc.exception), f'Invalid "{fn_arg["name"]}" argument value, {value_json(arg_invalid)}')
            self.assertIsNone(cm_exc.exception.return_value)

            # With return value
            with self.assertRaises(ValueArgsError) as cm_exc:
                value_args_validate(fn_args, args_invalid, -1)
            self.assertEqual(str(cm_exc.exception), f'Invalid "{fn_arg["name"]}" argument value, {value_json(arg_invalid)}')
            self.assertEqual(cm_exc.exception.return_value, -1)

        # Missing arguments
        for ix_arg, fn_arg in enumerate(fn_args):
            with self.assertRaises(ValueArgsError) as cm_exc:
                value_args_validate(fn_args, args[0:ix_arg])
            self.assertEqual(str(cm_exc.exception), f'Invalid "{fn_arg["name"]}" argument value, null')
            self.assertIsNone(cm_exc.exception.return_value)

            # With return value
            with self.assertRaises(ValueArgsError) as cm_exc:
                value_args_validate(fn_args, args[0:ix_arg], -1)
            self.assertEqual(str(cm_exc.exception), f'Invalid "{fn_arg["name"]}" argument value, null')
            self.assertEqual(cm_exc.exception.return_value, -1)


    def test_value_rgs_validate_last_arg_array(self):
        fn_args = value_args_model([
            {'name': 'str', 'type': 'string'},
            {'name': 'arr', 'lastArgArray': True}
        ])
        self.assertListEqual(
            value_args_validate(fn_args, ['abc', 1, 2, 3]),
            ['abc', [1, 2, 3]]
        )
        self.assertListEqual(
            value_args_validate(fn_args, ['abc', 1]),
            ['abc', [1]]
        )
        self.assertListEqual(
            value_args_validate(fn_args, ['abc']),
            ['abc', []]
        )


    def test_value_args_validate_default_and_nullable(self):
        fn_args = value_args_model([
            {'name': 'str', 'type': 'string', 'nullable': True},
            {'name': 'str2', 'type': 'string', 'default': ''}
        ])
        self.assertListEqual(
            value_args_validate(fn_args, ['abc', 'def']),
            ['abc', 'def']
        )
        self.assertListEqual(
            value_args_validate(fn_args, ['abc']),
            ['abc', '']
        )
        self.assertListEqual(
            value_args_validate(fn_args, [None]),
            [None, '']
        )
        self.assertListEqual(
            value_args_validate(fn_args, []),
            [None, '']
        )

        # Non-nullable
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [None, None])
        self.assertEqual(str(cm_exc.exception), 'Invalid "str2" argument value, null')
        self.assertIsNone(cm_exc.exception.return_value)

        # Non-nullable with return value
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [None, None], -1)
        self.assertEqual(str(cm_exc.exception), 'Invalid "str2" argument value, null')
        self.assertEqual(cm_exc.exception.return_value, -1)


    def test_value_args_validate_any_and_boolean(self):
        fn_args = value_args_model([
            {'name': 'any'},
            {'name': 'bool', 'type': 'boolean'}
        ])
        self.assertListEqual(
            value_args_validate(fn_args, ['abc', 1]),
            ['abc', True]
        )
        self.assertListEqual(
            value_args_validate(fn_args, [5, 0]),
            [5, False]
        )
        self.assertListEqual(
            value_args_validate(fn_args, [None, None]),
            [None, False]
        )
        self.assertListEqual(
            value_args_validate(fn_args, []),
            [None, False]
        )


    def test_value_args_validate_number_constraints(self):
        fn_args = value_args_model([
            {'name': 'int', 'type': 'number', 'integer': True, 'gt': 0, 'lt': 5},
            {'name': 'num', 'type': 'number', 'gte': 0, 'lte': 5},
        ])
        self.assertListEqual(
            value_args_validate(fn_args, [2, 3.5]),
            [2, 3.5]
        )
        self.assertListEqual(
            value_args_validate(fn_args, [2, 0]),
            [2, 0]
        )
        self.assertListEqual(
            value_args_validate(fn_args, [2, 5]),
            [2, 5]
        )

        # Bool integer
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [True, 3.5])
        self.assertEqual(str(cm_exc.exception), 'Invalid "int" argument value, true')
        self.assertIsNone(cm_exc.exception.return_value)

        # Bool float
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [2, False])
        self.assertEqual(str(cm_exc.exception), 'Invalid "num" argument value, false')
        self.assertIsNone(cm_exc.exception.return_value)

        # Non-integer
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [2.5, 3.5])
        self.assertEqual(str(cm_exc.exception), 'Invalid "int" argument value, 2.5')
        self.assertIsNone(cm_exc.exception.return_value)

        # Greater-than error
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [0, 3.5])
        self.assertEqual(str(cm_exc.exception), 'Invalid "int" argument value, 0')
        self.assertIsNone(cm_exc.exception.return_value)

        # Less-than error
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [5, 3.5])
        self.assertEqual(str(cm_exc.exception), 'Invalid "int" argument value, 5')
        self.assertIsNone(cm_exc.exception.return_value)

        # Greater-than-or-equal-to error
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [2, -1])
        self.assertEqual(str(cm_exc.exception), 'Invalid "num" argument value, -1')
        self.assertIsNone(cm_exc.exception.return_value)

        # Less-than-or-equal-to error
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [2, 6])
        self.assertEqual(str(cm_exc.exception), 'Invalid "num" argument value, 6')
        self.assertIsNone(cm_exc.exception.return_value)

        # Number constraint with return value
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, [2, 6], -1)
        self.assertEqual(str(cm_exc.exception), 'Invalid "num" argument value, 6')
        self.assertEqual(cm_exc.exception.return_value, -1)


    def test_value_args_validate_extra_arguments(self):
        fn_args = value_args_model([
            {'name': 'str', 'type': 'string'},
            {'name': 'num', 'type': 'number'}
        ])
        with self.assertRaises(ValueArgsError) as cm_exc:
            value_args_validate(fn_args, ['abc', 1, 2, 3])
        self.assertEqual(str(cm_exc.exception), 'Too many arguments (4)')
        self.assertEqual(cm_exc.exception.return_value, None)


    def test_value_args_error(self):
        with self.assertRaises(ValueArgsError) as cm_exc:
            raise ValueArgsError('myArg', None)
        self.assertEqual(str(cm_exc.exception), 'Invalid "myArg" argument value, null')
        self.assertEqual(cm_exc.exception.return_value, None)

        with self.assertRaises(ValueArgsError) as cm_exc:
            raise ValueArgsError('myArg', 'abc')
        self.assertEqual(str(cm_exc.exception), 'Invalid "myArg" argument value, "abc"')
        self.assertEqual(cm_exc.exception.return_value, None)

        with self.assertRaises(ValueArgsError) as cm_exc:
            raise ValueArgsError('myArg', [1, 2, 3])
        self.assertEqual(str(cm_exc.exception), 'Invalid "myArg" argument value, [1,2,3]')
        self.assertEqual(cm_exc.exception.return_value, None)

        # Return value
        with self.assertRaises(ValueArgsError) as cm_exc:
            raise ValueArgsError('myArg', None, -1)
        self.assertEqual(str(cm_exc.exception), 'Invalid "myArg" argument value, null')
        self.assertEqual(cm_exc.exception.return_value, -1)


    def test_value_args_model(self):
        fn_args = [
            {'name': 'str', 'type': 'string'},
            {'name': 'num', 'type': 'number', 'default': 0}
        ]
        self.assertEqual(value_args_model(fn_args), fn_args)

        # Invalid function arguments model
        with self.assertRaises(ValidationError) as cm_exc:
            value_args_model([])
        self.assertEqual(str(cm_exc.exception), "Invalid value [] (type 'list'), expected type 'FunctionArguments' [len > 0]")

        # Null default argument value error
        with self.assertRaises(ValueError) as cm_exc:
            value_args_model([
                {'name': 'num', 'type': 'number', 'default': None}
            ])
        self.assertEqual(str(cm_exc.exception), 'Argument "num" has default value of null - use nullable instead')


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


    def test_value_normalize_datetime(self):
        d1 = datetime.datetime(2024, 3, 19, 12, 21)
        d2 = d1.astimezone()
        d3 = datetime.date(2024, 3, 19)
        self.assertIs(value_normalize_datetime(d1), d1)
        self.assertEqual(value_normalize_datetime(d2), d1)
        self.assertEqual(value_normalize_datetime(d3), datetime.datetime(2024, 3, 19))


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
