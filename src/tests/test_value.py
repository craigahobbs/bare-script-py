# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import re
import unittest

from bare_script.value import value_boolean, value_compare, value_string, value_type


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
        self.assertEqual(value_type(lambda: None), 'function')

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
        self.assertEqual(value_string(datetime.datetime(2024, 1, 12, 6, 9, tzinfo=datetime.timezone.utc)), '2024-01-12T06:09:00+00:00')

        # object
        self.assertEqual(value_string({'value': 1}), '{"value": 1}')
        self.assertEqual(value_string({}), '{}')

        # array
        self.assertEqual(value_string([1, 2, 3]), '[1, 2, 3]')
        self.assertEqual(value_string([]), '[]')

        # function
        self.assertEqual(value_string(lambda: None), '<function>')

        # regex
        self.assertEqual(value_string(re.compile('^test')), '<regex>')

        # unknown
        self.assertEqual(value_string((1, 2, 3)), '<unknown>')
        self.assertEqual(value_string(()), '<unknown>')


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
        self.assertEqual(value_boolean(lambda: None), True)

        # regex
        self.assertEqual(value_boolean(re.compile('^test')), True)

        # unknown
        self.assertEqual(value_boolean((1, 2, 3)), False)
        self.assertEqual(value_boolean(()), False)


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
        self.assertEqual(value_compare(datetime.datetime(2024, 1, 12), datetime.datetime(2024, 1, 12)), 0)
        self.assertEqual(value_compare(datetime.datetime(2024, 1, 11), datetime.datetime(2024, 1, 12)), -1)
        self.assertEqual(value_compare(datetime.datetime(2024, 1, 12), datetime.datetime(2024, 1, 11)), 1)

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
        self.assertEqual(value_compare(lambda: 1, lambda: 1), 0)
        self.assertEqual(value_compare(lambda: 1, lambda: 2), 0)
        self.assertEqual(value_compare(lambda: 2, lambda: 1), 0)

        # regex
        self.assertEqual(value_compare(re.compile('^test1'), re.compile('^test1')), 0)
        self.assertEqual(value_compare(re.compile('^test1'), re.compile('^test2')), 0)
        self.assertEqual(value_compare(re.compile('^test2'), re.compile('^test1')), 0)


    #
    # array
    # boolean
    # datetime
    # function
    # null
    # number
    # object
    # regex
    # string
    # unknown
    #
    def test_value_compare_invalid(self):
        # array < boolean
        self.assertEqual(value_compare([1, 2, 3], True), -1)
        self.assertEqual(value_compare([1, 2, 3], False), -1)
        self.assertEqual(value_compare(True, [1, 2, 3]), 1)
        self.assertEqual(value_compare(False, [1, 2, 3]), 1)

        # boolean < datetime
        self.assertEqual(value_compare(True, datetime.datetime.now()), -1)
        self.assertEqual(value_compare(False, datetime.datetime.now()), -1)
        self.assertEqual(value_compare(datetime.datetime.now(), True), 1)
        self.assertEqual(value_compare(datetime.datetime.now(), False), 1)

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
        self.assertEqual(value_compare(datetime.datetime.now(), lambda: 1), -1)
        self.assertEqual(value_compare(lambda: 1, datetime.datetime.now()), 1)

        # function < number
        self.assertEqual(value_compare(lambda: 1, 1), -1)
        self.assertEqual(value_compare(lambda: 1, 0), -1)
        self.assertEqual(value_compare(1, lambda: 1), 1)
        self.assertEqual(value_compare(0, lambda: 1), 1)

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
