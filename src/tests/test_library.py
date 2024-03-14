# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import json
import math
import re
import unittest

import schema_markdown

from bare_script.library import EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS
from bare_script.value import REGEX_TYPE, value_json, value_parse_datetime, value_string


class TestLibrary(unittest.TestCase):

    def test_built_in_expression_functions(self):
        self.assertListEqual(
            [(fn_name, callable(fn)) for fn_name, fn in EXPRESSION_FUNCTIONS.items()],
            [
                ('abs', True),
                ('acos', True),
                ('asin', True),
                ('atan', True),
                ('atan2', True),
                ('ceil', True),
                ('charCodeAt', True),
                ('cos', True),
                ('date', True),
                ('day', True),
                ('endsWith', True),
                ('indexOf', True),
                ('fixed', True),
                ('floor', True),
                ('fromCharCode', True),
                ('hour', True),
                ('lastIndexOf', True),
                ('len', True),
                ('lower', True),
                ('ln', True),
                ('log', True),
                ('max', True),
                ('min', True),
                ('millisecond', True),
                ('minute', True),
                ('month', True),
                ('now', True),
                ('parseInt', True),
                ('parseFloat', True),
                ('pi', True),
                ('rand', True),
                ('replace', True),
                ('rept', True),
                ('round', True),
                ('second', True),
                ('sign', True),
                ('sin', True),
                ('slice', True),
                ('sqrt', True),
                ('startsWith', True),
                ('text', True),
                ('tan', True),
                ('today', True),
                ('trim', True),
                ('upper', True),
                ('year', True)
            ]
        )


    #
    # Array functions
    #


    def test_array_copy(self):
        array = [1, 2, 3]
        result = SCRIPT_FUNCTIONS['arrayCopy']([array], None)
        self.assertListEqual(result, [1, 2, 3])
        self.assertIsNot(result, array)

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayCopy']([None], None))


    def test_array_extend(self):
        array = [1, 2, 3]
        array2 = [4, 5, 6]
        result = SCRIPT_FUNCTIONS['arrayExtend']([array, array2], None)
        self.assertListEqual(result, [1, 2, 3, 4, 5, 6])
        self.assertIs(result, array)

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayExtend']([None, None], None), None)

        # Second non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayExtend']([array, None], None))


    def test_array_get(self):
        array = [1, 2, 3]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 0], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 0.], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 1], None), 2)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 2], None), 3)

        # Non-array
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([None, 0], None), None)

        # Index outside valid range
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, -1], None), None)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 3], None), None)

        # Non-number index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, '1'], None), None)

        # Non-integer index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayGet']([array, 1.5], None), None)


    def test_array_index_of(self):
        array = [1, 2, 3, 2]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 1], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 3], None), 2)

        # Not found
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 4], None), -1)

        # Index provided
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, 2], None), 3)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, 2.], None), 3)

        # Match function
        def value_fn(args, value_options):
            self.assertEqual(len(args), 1)
            self.assertIs(value_options, options)
            return args[0] == value_fn_value
        value_fn_value = 2
        options = {}
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, value_fn], options), 1)

        # Match function, not found
        value_fn_value = 4
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, value_fn], options), -1)

        # Match function, index provided
        value_fn_value = 2
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, value_fn, 2], options), 3)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, value_fn, 2.], options), 3)

        # Non-array
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([None, 2], None), -1)

        # Index outside valid range
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, -1], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, 4], None), -1)

        # Non-number index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, 'abc'], None), -1)

        # Non-integer index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayIndexOf']([array, 2, 1.5], None), -1)


    def test_array_join(self):
        array = ['a', 2, None]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayJoin']([array, ', '], None), 'a, 2, null')

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayJoin']([None, ', '], None))

        # Non-string separator
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayJoin']([array, 1], None))


    def test_array_last_index_of(self):
        array = [1, 2, 3, 2]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 1], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2], None), 3)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 3], None), 2)

        # Not found
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 4], None), -1)

        # Index provided
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, 2], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, 2.], None), 1)

        # Match function
        def value_fn(args, value_options):
            self.assertEqual(len(args), 1)
            self.assertIs(value_options, options)
            return args[0] == value_fn_value
        value_fn_value = 2
        options = {}
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, value_fn], options), 3)

        # Match function, not found
        value_fn_value = 4
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, value_fn], options), -1)

        # Match function, index provided
        value_fn_value = 2
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, value_fn, 2], options), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, value_fn, 2.], options), 1)

        # Non-array
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([None, 2], None), -1)

        # Index outside valid range
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, -1], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, 4], None), -1)

        # Non-number index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, 'abc'], None), -1)

        # Non-integer index
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLastIndexOf']([array, 2, 1.5], None), -1)


    def test_array_length(self):
        array = [1, 2, 3]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLength']([array], None), 3)

        # Non-array
        self.assertEqual(SCRIPT_FUNCTIONS['arrayLength']([None], None), 0)


    def test_array_new(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNew']([], None), [])
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNew']([1, 2, 3], None), [1, 2, 3])


    def test_array_new_size(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNewSize']([3], None), [0, 0, 0])
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNewSize']([3.], None), [0, 0, 0])

        # Value provided
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNewSize']([3, 1], None), [1, 1, 1])

        # No args
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNewSize']([], None), [])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayNewSize']([None], None))

        # Negative size
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayNewSize']([-1], None))

        # Non-number size
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayNewSize'](['abc'], None))

        # Non-integer size
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayNewSize']([1.5], None))


    def test_array_pop(self):
        array = [1, 2, 3]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayPop']([array], None), 3)
        self.assertListEqual(array, [1, 2])

        # Empty array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayPop']([[]], None))

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayPop']([None], None))


    def test_array_push(self):
        array = [1, 2, 3]
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayPush']([array, 5], None), [1, 2, 3, 5])
        self.assertListEqual(array, [1, 2, 3, 5])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayPush']([None, 5], None))


    def test_array_set(self):
        array = [1, 2, 3]
        self.assertEqual(SCRIPT_FUNCTIONS['arraySet']([array, 1, 5], None), 5)
        self.assertListEqual(array, [1, 5, 3])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySet']([None, 1, 5], None))

        # Non-number index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySort']([array, 'abc'], None))

        # Non-integer index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySort']([array, 1.5], None))

        # Index outside valid range
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySet']([array, -1, 5], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySet']([array, 3, 5], None))


    def test_array_shift(self):
        array = [1, 2, 3]
        self.assertEqual(SCRIPT_FUNCTIONS['arrayShift']([array], None), 1)
        self.assertListEqual(array, [2, 3])

        # Empty array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayShift']([[]], None))

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arrayShift']([None], None))


    def test_array_slice(self):
        array = [1, 2, 3, 4]
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 0, 2], None), [1, 2])
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 0., 2.], None), [1, 2])
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 1, 3], None), [2, 3])
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 1, 4], None), [2, 3, 4])
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 1], None), [2, 3, 4])

        # Empty slice
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 4], None), [])
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 1, 1], None), [])

        # End index less than start index
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 2, 1], None), [])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 1, 3], None))

        # Start index outside valid range
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, -1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 5], None))

        # Non-number start index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 'abc'], None))

        # Non-integer start index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 1.5], None))

        # End index outside valid range
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 0, -1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 0, 5], None))

        # Non-number end index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 0, 'abc'], None))

        # Non-integer end index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([array, 0, 1.5], None))


    def test_array_sort(self):
        array = [3, 2, 1]
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySort']([array], None), [1, 2, 3])
        self.assertListEqual(array, [1, 2, 3])

        # Compare function
        def compare_fn(args, compare_options):
            a, b = args
            self.assertIs(compare_options, options)
            return 1 if a < b else (0 if a == b else -1)
        options = {}
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySort']([array, compare_fn], options), [3, 2, 1])
        self.assertListEqual(array, [3, 2, 1])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySort']([None], None))

        # Non-function cmopare function
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySort']([array, 'asdf'], None))
        self.assertListEqual(array, [3, 2, 1])


    #
    # Data functions
    #


    def test_data_aggregate(self):
        data = [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ]
        aggregation = {
            'categories': ['a'],
            'measures': [
                {'field': 'b', 'function': 'sum', 'name': 'sum_b'}
            ]
        }
        self.assertListEqual(SCRIPT_FUNCTIONS['dataAggregate']([data, aggregation], None), [
            {'a': 1, 'sum_b': 7},
            {'a': 2, 'sum_b': 5}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataAggregate']([None], None))

        # Non-dict aggregation model
        self.assertIsNone(SCRIPT_FUNCTIONS['dataAggregate']([data, 'invalid'], None))

        # Invalid aggregation model
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['dataAggregate']([data, {}], None)
        self.assertEqual(str(cm_exc.exception), "Required member 'measures' missing")


    def test_data_calculated_field(self):
        data = [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataCalculatedField']([data, 'c', 'a * b'], {}), [
            {'a': 1, 'b': 3, 'c': 3},
            {'a': 1, 'b': 4, 'c': 4},
            {'a': 2, 'b': 5, 'c': 10}
        ])

        # Variables
        self.assertListEqual(SCRIPT_FUNCTIONS['dataCalculatedField']([data, 'c', 'a * b * X', {'X': 2}], {}), [
            {'a': 1, 'b': 3, 'c': 6},
            {'a': 1, 'b': 4, 'c': 8},
            {'a': 2, 'b': 5, 'c': 20}
        ])

        # Globals
        options = {'globals': {'X': 2}}
        self.assertListEqual(SCRIPT_FUNCTIONS['dataCalculatedField']([data, 'c', 'a * b * X'], options), [
            {'a': 1, 'b': 3, 'c': 6},
            {'a': 1, 'b': 4, 'c': 8},
            {'a': 2, 'b': 5, 'c': 20}
        ])

        # Runtime integration
        data_runtime = [
            {'a': '/foo'},
            {'a': 'bar'}
        ]
        options = {
            'globals': {
                'documentURL': lambda args, func_options: func_options['urlFn'](args[0])
            },
            'urlFn': lambda url: (url if url.startswith('/') else f'/foo/{url}')
        }
        self.assertListEqual(SCRIPT_FUNCTIONS['dataCalculatedField']([data_runtime, 'b', 'documentURL(a)'], options), [
            {'a': '/foo', 'b': '/foo'},
            {'a': 'bar', 'b': '/foo/bar'}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataCalculatedField']([None, 'c', 'a * b'], None))

        # Non-string field name
        self.assertIsNone(SCRIPT_FUNCTIONS['dataCalculatedField']([data, None, 'a * b'], None))

        # Non-string expression
        self.assertIsNone(SCRIPT_FUNCTIONS['dataCalculatedField']([data, 'c', None], None))

        # Non-dict variables
        self.assertIsNone(SCRIPT_FUNCTIONS['dataCalculatedField']([data, 'c', 'a * b', 'invalid'], None))


    def test_data_filter(self):
        data = [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataFilter']([data, 'b > 3'], {}), [
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ])

        # Variables
        self.assertListEqual(SCRIPT_FUNCTIONS['dataFilter']([data, 'b > d', {'d': 3}], {}), [
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ])

        # Globals
        options = {'globals': {'c': 2}}
        self.assertListEqual(SCRIPT_FUNCTIONS['dataFilter']([data, 'a == c'], options), [
            {'a': 2, 'b': 5}
        ])

        # Runtime integration
        data_runtime = [
            {'a': '/foo'},
            {'a': 'bar'}
        ]
        options = {
            'globals': {
                'documentURL': lambda args, func_options: func_options['urlFn'](args[0])
            },
            'urlFn': lambda url: (url if url.startswith('/') else f'/foo/{url}')
        }
        self.assertListEqual(SCRIPT_FUNCTIONS['dataFilter']([data_runtime, 'documentURL(a) == "/foo/bar"'], options), [
            {'a': 'bar'}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataFilter']([None, 'a * b'], None))

        # Non-string expression
        self.assertIsNone(SCRIPT_FUNCTIONS['dataFilter']([data, None], None))

        # Non-dict variables
        self.assertIsNone(SCRIPT_FUNCTIONS['dataFilter']([data, 'a * b', 'invalid'], None))


    def test_data_join(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 1, 'b': 6},
            {'a': 2, 'b': 7},
            {'a': 3, 'b': 8}
        ]
        right_data = [
            {'a': 1, 'c': 10},
            {'a': 2, 'c': 11},
            {'a': 2, 'c': 12}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, 'a'], {}), [
            {'a': 1, 'b': 5, 'a2': 1, 'c': 10},
            {'a': 1, 'b': 6, 'a2': 1, 'c': 10},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 11},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 12},
            {'a': 3, 'b': 8}
        ])

        # Left join
        self.assertListEqual(SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, 'a', None, True], {}), [
            {'a': 1, 'b': 5, 'a2': 1, 'c': 10},
            {'a': 1, 'b': 6, 'a2': 1, 'c': 10},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 11},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 12}
        ])

        # Right expression and variables - left join
        self.assertListEqual(
            SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, 'a', 'a / denominator', True, {'denominator': 2}], {}),
            [
                {'a': 1, 'a2': 2, 'b': 5, 'c': 11},
                {'a': 1, 'a2': 2, 'b': 5, 'c': 12},
                {'a': 1, 'a2': 2, 'b': 6, 'c': 11},
                {'a': 1, 'a2': 2, 'b': 6, 'c': 12}
            ]
        )

        # Right expression and globals
        options = {'globals': {'denominator': 2}}
        self.assertListEqual(
            SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, 'a', 'a / denominator'], options),
            [
                {'a': 1, 'a2': 2, 'b': 5, 'c': 11},
                {'a': 1, 'a2': 2, 'b': 5, 'c': 12},
                {'a': 1, 'a2': 2, 'b': 6, 'c': 11},
                {'a': 1, 'a2': 2, 'b': 6, 'c': 12},
                {'a': 2, 'b': 7},
                {'a': 3, 'b': 8}
            ]
        )

        # Runtime integration
        options = {
            'globals': {
                'documentURL': lambda args, func_options: func_options['urlFn'](args[0])
            },
            'urlFn': lambda url: (url if url.startswith('/') else f'/foo/{url}')
        }
        left_data_runtime = [
            {'a': '/foo', 'c': 5},
            {'a': 'bar', 'c': 6}
        ]
        right_data_runtime = [
            {'b': '/foo', 'd': 10},
            {'b': '/foo/bar', 'd': 11}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataJoin']([left_data_runtime, right_data_runtime, 'documentURL(a)', 'b'], options), [
            {'a': '/foo', 'b': '/foo', 'c': 5, 'd': 10},
            {'a': 'bar', 'b': '/foo/bar', 'c': 6, 'd': 11}
        ])

        # Non-list left data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataJoin']([None, right_data, 'a'], None))

        # Non-list right data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataJoin']([left_data, None, 'a'], None))

        # Non-string expression
        self.assertIsNone(SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, None], None))

        # Non-string right expression
        self.assertIsNone(SCRIPT_FUNCTIONS['dataJoin']([left_data, right_data, 'a', 7], None))

        # Non-dict variables
        self.assertIsNone(SCRIPT_FUNCTIONS['dataFilter']([left_data, right_data, 'a', None, False, 'invalid'], None))


    def test_data_parse_csv(self):
        text = '''\
a,b, c
1,3,abc
'''
        text2 = '''\
1,4,
2,5
'''
        self.assertListEqual(SCRIPT_FUNCTIONS['dataParseCSV']([text, text2], None), [
            {'a': 1, 'b': 3, 'c': 'abc'},
            {'a': 1, 'b': 4, 'c': ''},
            {'a': 2, 'b': 5, 'c': None}
        ])

        # None arg
        self.assertListEqual(SCRIPT_FUNCTIONS['dataParseCSV']([text, None, text2], None), [
            {'a': 1, 'b': 3, 'c': 'abc'},
            {'a': 1, 'b': 4, 'c': ''},
            {'a': 2, 'b': 5, 'c': None}
        ])

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['dataParseCSV']([text, 7, text2], None))


    def test_data_sort(self):
        data = [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5},
            {'a': 3, 'b': 6},
            {'a': 4, 'b': 7}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataSort']([data, [['a', True], ['b']]], None), [
            {'a': 4, 'b': 7},
            {'a': 3, 'b': 6},
            {'a': 2, 'b': 5},
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataSort']([None, [['a', True], ['b']]], None))

        # Non-list sorts
        self.assertIsNone(SCRIPT_FUNCTIONS['dataSort']([data, None], None))


    def test_data_top(self):
        data = [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5},
            {'a': 3, 'b': 6},
            {'a': 4, 'b': 7}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataTop']([data, 3], None), [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ])
        self.assertListEqual(SCRIPT_FUNCTIONS['dataTop']([data, 1, ['a']], None), [
            {'a': 1, 'b': 3},
            {'a': 2, 'b': 5},
            {'a': 3, 'b': 6},
            {'a': 4, 'b': 7}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataTop']([None], None))

        # Non-number count
        self.assertIsNone(SCRIPT_FUNCTIONS['dataTop']([data, None], None))

        # Non-integer count
        self.assertIsNone(SCRIPT_FUNCTIONS['dataTop']([data, 3.5], None))

        # Negative count
        self.assertIsNone(SCRIPT_FUNCTIONS['dataTop']([data, -3], None))

        # Non-list category fields
        self.assertIsNone(SCRIPT_FUNCTIONS['dataTop']([data, 3, 'invalid'], None))


    def test_data_validate(self):
        data = [
            {'a': '1', 'b': 3},
            {'a': '1', 'b': 4},
            {'a': '2', 'b': 5}
        ]
        self.assertListEqual(SCRIPT_FUNCTIONS['dataValidate']([data], None), [
            {'a': '1', 'b': 3},
            {'a': '1', 'b': 4},
            {'a': '2', 'b': 5}
        ])

        # CSV
        self.assertListEqual(SCRIPT_FUNCTIONS['dataValidate']([data, True], None), [
            {'a': 1, 'b': 3},
            {'a': 1, 'b': 4},
            {'a': 2, 'b': 5}
        ])

        # Non-list data
        self.assertIsNone(SCRIPT_FUNCTIONS['dataValidate']([None], None))


    #
    # Datetime functions
    #


    def test_datetime_day(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([dt], None), 21)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([None], None), None)


    def test_datetime_hour(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([dt], None), 7)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([None], None), None)


    def test_datetime_iso_format(self):
        d1 = value_parse_datetime('2022-06-21T07:15:30+00:00')
        d2 = value_parse_datetime('2022-06-21T07:15:30.123567+00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([d1], None), value_string(d1))
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([d2], None), value_string(d2))

        # isDate
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(2022, 6, 21), True], None),
            '2022-06-21'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(2022, 10, 7), True], None),
            '2022-10-07'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(900, 10, 7), True], None),
            '0900-10-07'
        )

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([None], None), None)


    def test_datetime_iso_parse(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00+00:00'], None),
            datetime.datetime.fromisoformat('2022-08-29T15:08:00+00:00').astimezone().replace(tzinfo=None)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00Z'], None),
            datetime.datetime.fromisoformat('2022-08-29T15:08:00+00:00').astimezone().replace(tzinfo=None)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00-08:00'], None),
            datetime.datetime.fromisoformat('2022-08-29T15:08:00-08:00').astimezone().replace(tzinfo=None)
        )

        # Invalid datetime string
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOParse'](['invalid'], None), None)

        # Non-string datetime string
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOParse']([None], None), None)


    def test_datetime_millisecond(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100000)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMillisecond']([dt], None), 100)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMillisecond']([None], None), None)


    def test_datetime_minute(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([dt], None), 15)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([None], None), None)


    def test_datetime_month(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([dt], None), 6)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([None], None), None)


    def test_datetime_new(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 100], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000)
        )

        # Float arguments
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000)
        )

        # Required arguments only
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21], None), datetime.datetime(2022, 6, 21))

        # Extra months
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 26, 21, 12, 30, 15, 100], None),
            datetime.datetime(2024, 2, 21, 12, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, -14, 21, 12, 30, 15, 100], None),
            datetime.datetime(2020, 10, 21, 12, 30, 15, 100000)
        )

        # Extra days
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 7, 20, 12, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 250, 12, 30, 15, 100], None),
            datetime.datetime(2023, 2, 5, 12, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, -50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 4, 11, 12, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, -250, 12, 30, 15, 100], None),
            datetime.datetime(2021, 9, 23, 12, 30, 15, 100000)
        )

        # Extra hours
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 23, 2, 30, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, -50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 18, 22, 30, 15, 100000)
        )

        # Extra minutes
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 15, 20, 15, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, -200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 8, 40, 15, 100000)
        )

        # Extra seconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 33, 20, 100000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, -200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 26, 40, 100000)
        )

        # Extra milliseconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 17, 200000)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, -2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 12, 800000)
        )

        # Extra everything
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 12, 31, 23, 59, 59, 1000], None),
            datetime.datetime(2023, 1, 1, 0, 0, 0, 0)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2023, 1, 1, 0, 0, 0, -1000], None),
            datetime.datetime(2022, 12, 31, 23, 59, 59, 0)
        )

        # Invalid year
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([90, 7, 21, 12, 30, 15, 100], None))

        # Non-number arguments
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew'](['2022', 6, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, '6', 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, '21', 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, '12', 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, '30', 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, '15', 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, '100'], None))

        # Non-integer arguments
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022.5, 6, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6.5, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21.5, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12.5, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30.5, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15.5, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 100.5], None))


    def test_datetime_now(self):
        self.assertIsInstance(SCRIPT_FUNCTIONS['datetimeNow']([], None), datetime.datetime)


    def test_datetime_second(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([dt], None), 30)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([None], None), None)


    def test_datetime_today(self):
        today = SCRIPT_FUNCTIONS['datetimeToday']([], None)
        self.assertIsInstance(today, datetime.datetime)
        self.assertEqual(today.hour, 0)
        self.assertEqual(today.minute, 0)
        self.assertEqual(today.second, 0)
        self.assertEqual(today.microsecond, 0)


    def test_datetime_year(self):
        dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([dt], None), 2022)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([None], None), None)


    #
    # JSON functions
    #


    def test_json_parse(self):
        self.assertDictEqual(SCRIPT_FUNCTIONS['jsonParse'](['{"a": 1, "b": 2}'], None), {'a': 1, 'b': 2})

        # Invalid JSON
        with self.assertRaises(json.decoder.JSONDecodeError):
            SCRIPT_FUNCTIONS['jsonParse'](['asdf'], None)

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonParse']([None], None))


    def test_json_stringify(self):
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([{'b': 2, 'a': 1}], None), '{"a":1,"b":2}')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([{'b': 2, 'a': {'d': 4, 'c': 3}}], None), '{"a":{"c":3,"d":4},"b":2}')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([[{'b': 2, 'a': 1}]], None), '[{"a":1,"b":2}]')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([[3, 2, 1]], None), '[3,2,1]')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([123], None), '123')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify'](['abc'], None), '"abc"')
        self.assertEqual(SCRIPT_FUNCTIONS['jsonStringify']([None], None), 'null')

        # Non-zero indent
        self.assertEqual(
            SCRIPT_FUNCTIONS['jsonStringify']([{'a': 1, 'b': 2}, 4], None),
            '''\
{
    "a": 1,
    "b": 2
}'''
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['jsonStringify']([{'a': 1, 'b': 2}, 4.], None),
            '''\
{
    "a": 1,
    "b": 2
}'''
        )

        # Non-number indent
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([None, 'abc'], None))

        # Non-integer indent
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([None, 4.5], None))

        # Zero indent
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([{'a': 1, 'b': 2}, 0], None))

        # Negative indent
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([None, -4], None))


    #
    # Math functions
    #


    def test_math_abs(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAbs']([-3], None), 3)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAbs'](['abc'], None))


    def test_math_acos(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAcos']([1], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAcos'](['abc'], None))


    def test_math_asin(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAsin']([0], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAsin'](['abc'], None))


    def test_math_atan(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAtan']([0], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAtan'](['abc'], None))


    def test_math_atan2(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAtan2']([0, 1], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAtan2'](['abc', 1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathAtan2']([0, 'abc'], None))


    def test_math_ceil(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathCeil']([0.25], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathCeil'](['abc'], None))


    def test_math_cos(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathCos']([0], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathCos'](['abc'], None))


    def test_math_floor(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathFloor']([1.125], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathFloor'](['abc'], None))


    def test_math_ln(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathLn']([math.e], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLn'](['abc'], None))

        # Invalid value
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLn']([0], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLn']([-10], None))


    def test_math_log(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathLog']([10], None), 1)

        # Base
        self.assertEqual(SCRIPT_FUNCTIONS['mathLog']([8, 2], None), 3)
        self.assertEqual(SCRIPT_FUNCTIONS['mathLog']([8, 0.5], None), -3)

        # Non-number value
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog'](['abc'], None))

        # Non-number base
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([10, 'abc'], None))

        # Invalid value
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([0], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([-10], None))

        # Invalid base
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([10, 1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([10, 0], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathLog']([10, -10], None))


    def test_math_max(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathMax']([1, 2, 3], None), 3)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMax'](['abc', 2, 3], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMax']([1, 'abc', 3], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMax']([1, 2, 'abc'], None))


    def test_math_min(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathMin']([1, 2, 3], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMin'](['abc', 2, 3], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMin']([1, 'abc', 3], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['mathMin']([1, 2, 'abc'], None))


    def test_math_pi(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathPi']([], None), math.pi)


    def test_math_random(self):
        value = SCRIPT_FUNCTIONS['mathRandom']([], None)
        self.assertIsInstance(value, float)
        self.assertEqual(value >= 0, True)
        self.assertEqual(value <= 1, True)


    def test_math_round(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.125], None), 5)

        # Digits
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.25, 1], None), 5.3)
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.25, 1.], None), 5.3)
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.15, 1], None), 5.2)

        # Non-number value
        self.assertIsNone(SCRIPT_FUNCTIONS['mathRound'](['abc'], None))

        # Non-number base
        self.assertIsNone(SCRIPT_FUNCTIONS['mathRound']([5.125, 'abc'], None))

        # Non-integer base
        self.assertIsNone(SCRIPT_FUNCTIONS['mathRound']([5.125, 1.5], None))

        # Negative base
        self.assertIsNone(SCRIPT_FUNCTIONS['mathRound']([5.125, -1], None))


    def test_math_sign(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSign']([5.125], None), 1)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathSign'](['abc'], None))


    def test_math_sin(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSin']([0], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathSin'](['abc'], None))


    def test_math_sqrt(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSqrt']([4], None), 2)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathSqrt'](['abc'], None))

        # Negative value
        self.assertIsNone(SCRIPT_FUNCTIONS['mathSqrt']([-4], None))


    def test_math_tan(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathTan']([0], None), 0)

        # Non-number
        self.assertIsNone(SCRIPT_FUNCTIONS['mathTan'](['abc'], None))


    #
    # Number functions
    #


    def test_number_parse_float(self):
        self.assertEqual(SCRIPT_FUNCTIONS['numberParseFloat'](['123.45'], None), 123.45)

        # Parse failure
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseFloat'](['invalid'], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseFloat'](['1234.45asdf'], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseFloat'](['1234.45 asdf'], None))

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseFloat']([10], None))


    def test_number_parse_int(self):
        self.assertEqual(SCRIPT_FUNCTIONS['numberParseInt'](['123'], None), 123)

        # Radix
        self.assertEqual(SCRIPT_FUNCTIONS['numberParseInt'](['10', 2], None), 2)
        self.assertEqual(SCRIPT_FUNCTIONS['numberParseInt'](['10', 2.], None), 2)

        # Parse failure
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['1234.45'], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['asdf'], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['1234asdf'], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['1234.45 asdf'], None))

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt']([10], None))

        # Non-number radix
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['10', 'abc'], None))

        # Non-integer radix
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['10', 2.5], None))

        # Invalid radix
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['10', 1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseInt'](['10', 37], None))


    def test_number_to_fixed(self):
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1.125], None), '1.13')

        # Digits
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1.125, 0], None), '1')
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1.125, 0.], None), '1')
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1.125, 1], None), '1.1')
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1, 1], None), '1.0')

        # Trim
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1.125, 1, True], None), '1.1')
        self.assertEqual(SCRIPT_FUNCTIONS['numberToFixed']([1, 1, True], None), '1')

        # Non-number value
        self.assertIsNone(SCRIPT_FUNCTIONS['numberToFixed']([None, 1], None))

        # Non-number digits
        self.assertIsNone(SCRIPT_FUNCTIONS['numberToFixed']([1.125, None], None))

        # Non-integer digits
        self.assertIsNone(SCRIPT_FUNCTIONS['numberToFixed']([1.125, 1.5], None))

        # Negative digits
        self.assertIsNone(SCRIPT_FUNCTIONS['numberToFixed']([1.125, -1], None))


    #
    # Object functions
    #


    def test_object_assign(self):
        obj = {'a': 1, 'b': 2}
        obj2 = {'b': 3, 'c': 4}
        self.assertDictEqual(SCRIPT_FUNCTIONS['objectAssign']([obj, obj2], None), {'a': 1, 'b': 3, 'c': 4})
        self.assertDictEqual(obj, {'a': 1, 'b': 3, 'c': 4})

        # Null inputs
        obj = {'a': 1, 'b': 2}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([None, obj], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([obj, None], None))
        self.assertDictEqual(obj, {'a': 1, 'b': 2})

        # Number inputs
        obj = {'a': 1, 'b': 2}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([0, obj], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([obj, 0], None))
        self.assertDictEqual(obj, {'a': 1, 'b': 2})

        # Array inputs
        obj = {'a': 1, 'b': 2}
        array = ['c', 'd']
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([obj, array], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['objectAssign']([array, obj], None))
        self.assertDictEqual(obj, {'a': 1, 'b': 2})
        self.assertListEqual(array, ['c', 'd'])


    def test_object_copy(self):
        obj = {'a': 1, 'b': 2}
        obj_copy = SCRIPT_FUNCTIONS['objectCopy']([obj], None)
        self.assertDictEqual(obj_copy, obj)
        self.assertIsNot(obj_copy, obj)

        # Null input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectCopy']([None], None))

        # Number input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectCopy']([0], None))

        # Array input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectCopy']([['a', 'b']], None))


    def test_object_delete(self):
        obj = {'a': 1, 'b': 2}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([obj, 'a'], None))
        self.assertDictEqual(obj, {'b': 2})

        # Missing key
        obj = {'b': 2}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([obj, 'a'], None))
        self.assertDictEqual(obj, {'b': 2})

        # Null input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([None, 'a'], None))

        # Number input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([0, 'a'], None))

        # Array input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([['a', 'b'], 'a'], None))

        # Non-string key
        self.assertIsNone(SCRIPT_FUNCTIONS['objectDelete']([obj, None], None))


    def test_object_get(self):
        obj = {'a': 1, 'b': 2}
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([obj, 'a'], None), 1)

        # Missing key with/without default
        obj = {}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectGet']([obj, 'a'], None))
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([obj, 'a', 1], None), 1)

        # Null input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectGet']([None, 'a'], None))
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([None, 'a', 1], None), 1)

        # Number input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectGet']([0, 'a'], None))
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([0, 'a', 1], None), 1)

        # Array input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectGet']([['a', 'b'], 'a'], None))
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([['a', 'b'], 'a', 1], None), 1)

        # Non-string key
        obj = {'a': 1, 'b': 2}
        self.assertIsNone(SCRIPT_FUNCTIONS['objectGet']([obj, None], None))
        self.assertEqual(SCRIPT_FUNCTIONS['objectGet']([obj, None, 1], None), 1)


    def test_object_has(self):
        obj = {'a': 1, 'b': None}
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([obj, 'a'], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([obj, 'b'], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([obj, 'c'], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([obj, 'd'], None), False)

        # Null input
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([None, 'a'], None), False)

        # Number input
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([0, 'a'], None), False)

        # Array input
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([['a', 'b'], 'a'], None), False)

        # Non-string key
        self.assertEqual(SCRIPT_FUNCTIONS['objectHas']([obj, None], None), False)


    def test_object_keys(self):
        obj = {'a': 1, 'b': 2}
        self.assertListEqual(SCRIPT_FUNCTIONS['objectKeys']([obj], None), ['a', 'b'])

        # Null input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectKeys']([None], None))

        # Number input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectKeys']([0], None))

        # Array input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectKeys']([['a', 'b']], None))


    def test_object_new(self):
        self.assertDictEqual(SCRIPT_FUNCTIONS['objectNew']([], None), {})

        # Key/values
        self.assertDictEqual(SCRIPT_FUNCTIONS['objectNew'](['a', 1, 'b', 2], None), {'a': 1, 'b': 2})

        # Missing final value
        self.assertDictEqual(SCRIPT_FUNCTIONS['objectNew'](['a', 1, 'b'], None), {'a': 1, 'b': None})

        # Non-string key
        self.assertIsNone(SCRIPT_FUNCTIONS['objectNew']([0, 1, 'b'], None), None)


    def test_object_set(self):
        obj = {'a': 1, 'b': 2}
        self.assertEqual(SCRIPT_FUNCTIONS['objectSet']([obj, 'c', 3], None), 3)
        self.assertDictEqual(obj, {'a': 1, 'b': 2, 'c': 3})

        # Null input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectSet']([None, 'c', 3], None))

        # Number input
        self.assertIsNone(SCRIPT_FUNCTIONS['objectSet']([0, 'c', 3], None))

        # Array input
        array = ['a', 'b']
        self.assertIsNone(SCRIPT_FUNCTIONS['objectSet']([array, 'c', 3], None))
        self.assertListEqual(array, ['a', 'b'])

        # Non-string key
        obj = {'a': 1, 'b': 2}
        self.assertEqual(SCRIPT_FUNCTIONS['objectSet']([obj, None, 3], None), None)
        self.assertDictEqual(obj, {'a': 1, 'b': 2})


    #
    # Regex functions
    #


    def test_regex_escape(self):
        self.assertEqual(SCRIPT_FUNCTIONS['regexEscape'](['a*b'], None), 'a\\*b')

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['regexEscape']([None], None))


    def test_regex_match(self):
        self.assertDictEqual(
            SCRIPT_FUNCTIONS['regexMatch']([re.compile('foo'), 'foo bar'], None),
            {
                'index': 0,
                'input': 'foo bar',
                'groups': {'0': 'foo'},
            }
        )

        # Named groups
        self.assertDictEqual(
            SCRIPT_FUNCTIONS['regexMatch']([re.compile(r'(?P<first>\w+)(\s+)(?P<last>\w+)'), 'foo bar thud'], None),
            {
                'index': 0,
                'input': 'foo bar thud',
                'groups': {'0': 'foo bar', '1': 'foo', '2': ' ', '3': 'bar', 'first': 'foo', 'last': 'bar'}
            }
        )

        # No match
        self.assertIsNone(SCRIPT_FUNCTIONS['regexMatch']([re.compile('foo'), 'boo bar'], None))

        # Non-regex
        self.assertIsNone(SCRIPT_FUNCTIONS['regexMatch']([None, 'foo bar'], None))

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['regexMatch']([re.compile('foo'), None], None))


    def test_regex_match_all(self):
        self.assertListEqual(
            SCRIPT_FUNCTIONS['regexMatchAll']([re.compile('(?P<name>([fb])o+)'), 'foo boooo bar'], None),
            [
                {
                    'index': 0,
                    'input': 'foo boooo bar',
                    'groups': {'0': 'foo', '1': 'foo', '2': 'f', 'name': 'foo'}
                },
                {
                    'index': 4,
                    'input': 'foo boooo bar',
                    'groups': {'0': 'boooo', '1': 'boooo', '2': 'b', 'name': 'boooo'}
                }
            ]
        )

        # No matches
        self.assertListEqual(
            SCRIPT_FUNCTIONS['regexMatchAll']([re.compile('foo'), 'boo boo bar'], None),
            []
        )

        # Non-regex
        self.assertIsNone(SCRIPT_FUNCTIONS['regexMatchAll']([None, 'abc'], None))

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['regexMatchAll']([re.compile('foo'), None], None))


    def test_regex_new(self):
        regex = SCRIPT_FUNCTIONS['regexNew'](['a*b'], None)
        self.assertIsInstance(regex, REGEX_TYPE)
        self.assertEqual(regex.pattern, 'a*b')
        self.assertEqual(regex.flags, re.U)

        # Named groups
        regex = SCRIPT_FUNCTIONS['regexNew']([r'(?<first>\w+)(\s+)(?<last>\w+)'], None)
        self.assertIsInstance(regex, REGEX_TYPE)
        self.assertEqual(regex.pattern, r'(?P<first>\w+)(\s+)(?P<last>\w+)')
        self.assertEqual(regex.flags, re.U)

        # Flag - "i"
        regex = SCRIPT_FUNCTIONS['regexNew'](['a*b', 'i'], None)
        self.assertIsInstance(regex, REGEX_TYPE)
        self.assertEqual(regex.pattern, 'a*b')
        self.assertEqual(regex.flags, re.I | re.U)

        # Flag - "m"
        regex = SCRIPT_FUNCTIONS['regexNew'](['a*b', 'm'], None)
        self.assertIsInstance(regex, REGEX_TYPE)
        self.assertEqual(regex.pattern, 'a*b')
        self.assertEqual(regex.flags, re.M | re.U)

        # Flag - "s"
        regex = SCRIPT_FUNCTIONS['regexNew'](['a*b', 's'], None)
        self.assertIsInstance(regex, REGEX_TYPE)
        self.assertEqual(regex.pattern, 'a*b')
        self.assertEqual(regex.flags, re.S | re.U)

        # Flag - unknown
        self.assertIsNone(SCRIPT_FUNCTIONS['regexNew'](['a*b', 'iz'], None))

        # Non-regex
        self.assertIsNone(SCRIPT_FUNCTIONS['regexNew']([None], None))

        # Non-string pattern
        self.assertIsNone(SCRIPT_FUNCTIONS['regexNew']([None], None))

        # Non-string flags
        self.assertIsNone(SCRIPT_FUNCTIONS['regexNew'](['a*b', 5], None))


    def test_regex_replace(self):
        self.assertEqual(SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'^(\w)(\w)$'), 'ab', '$2$1'], None), 'ba')

        # Named groups
        self.assertEqual(
            SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'^(?P<first>\w+)\s+(?P<last>\w+)'), 'foo bar', '$2, $1'], None),
            'bar, foo'
        )

        # Multiple replacements
        self.assertEqual(
            SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'(fo+)'), 'foo bar fooooo', '$1d'], None),
            'food bar foooood'
        )

        # Global flag (shouldn't ever happen)
        self.assertEqual(
            SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'(fo+)'), 'foo bar fooooo', '$1d'], None),
            'food bar foooood'
        )

        # JavaScript escape
        self.assertEqual(SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'^(\w)(\w)$'), 'ab', '$2$$$1'], None), 'b$a')

        # Python escape
        self.assertEqual(SCRIPT_FUNCTIONS['regexReplace']([re.compile(r'^(\w)(\w)$'), 'ab', '$2\\$1'], None), 'b\\a')

        # Non-regex
        self.assertIsNone(SCRIPT_FUNCTIONS['regexReplace']([None, 'ab', '$2$1'], None))

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['regexReplace']([re.compile('(a*)(b)'), None, '$2$1'], None))

        # Non-string substr
        self.assertIsNone(SCRIPT_FUNCTIONS['regexReplace']([re.compile('(a*)(b)'), 'ab', None], None))


    def test_regex_split(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['regexSplit']([re.compile(r'\s*,\s*'), '1,2, 3 , 4'], None), ['1', '2', '3', '4'])

        # Non-regex
        self.assertIsNone(SCRIPT_FUNCTIONS['regexSplit']([None, '1,2'], None))

        # Non-string
        self.assertIsNone(SCRIPT_FUNCTIONS['regexSplit']([re.compile(r'\s*,\s*'), None], None))


    #
    # Schema functions
    #


    def test_schema_parse(self):
        types = SCRIPT_FUNCTIONS['schemaParse'](['typedef int MyType', 'typedef MyType MyType2'], None)
        self.assertDictEqual(types, {
            'MyType': {'typedef': {'name': 'MyType', 'type': {'builtin': 'int'}}},
            'MyType2': {'typedef': {'name': 'MyType2','type': {'user': 'MyType'}}}
        })

        # Syntax error
        with self.assertRaises(schema_markdown.SchemaMarkdownParserError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaParse'](['asdf'], None)
        self.assertEqual(str(cm_exc.exception), ':1: error: Syntax error')


    def test_schema_parse_ex(self):
        # List input
        types = SCRIPT_FUNCTIONS['schemaParseEx']([['typedef int MyType', 'typedef MyType MyType2']], None)
        self.assertDictEqual(types, {
            'MyType': {'typedef': {'name': 'MyType', 'type': {'builtin': 'int'}}},
            'MyType2': {'typedef': {'name': 'MyType2','type': {'user': 'MyType'}}}
        })

        # String input
        types = SCRIPT_FUNCTIONS['schemaParseEx'](['typedef int MyType'], None)
        self.assertDictEqual(types, {
            'MyType': {'typedef': {'name': 'MyType','type': {'builtin': 'int'}}}
        })

        # Types provided
        types = SCRIPT_FUNCTIONS['schemaParseEx'](['typedef int MyType'], None)
        types2 = SCRIPT_FUNCTIONS['schemaParseEx'](['typedef MyType MyType2', types], None)
        self.assertDictEqual(types, {
            'MyType': {'typedef': {'name': 'MyType','type': {'builtin': 'int'}}},
            'MyType2': {'typedef': {'name': 'MyType2','type': {'user': 'MyType'}}}
        })
        self.assertIs(types, types2)

        # Filename provided
        types = SCRIPT_FUNCTIONS['schemaParseEx'](['typedef int MyType', {}, 'test.smd'], None)
        self.assertDictEqual(types, {
            'MyType': {'typedef': {'name': 'MyType','type': {'builtin': 'int'}}}
        })

        # Syntax error
        with self.assertRaises(schema_markdown.SchemaMarkdownParserError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaParseEx'](['asdf'], None)
        self.assertEqual(str(cm_exc.exception), ':1: error: Syntax error')

        # Syntax error with filename
        with self.assertRaises(schema_markdown.SchemaMarkdownParserError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaParseEx'](['asdf', {}, 'test.smd'], None)
        self.assertEqual(str(cm_exc.exception), 'test.smd:1: error: Syntax error')

        # Non-list/string input
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaParseEx']([None], None))

        # Non-doct types
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaParseEx'](['', None], None))

        # Non-string filename
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaParseEx'](['', {}, None], None))


    def test_schema_type_model(self):
        type_model = SCRIPT_FUNCTIONS['schemaTypeModel']([], None)
        self.assertTrue('Types' in type_model)
        self.assertDictEqual(SCRIPT_FUNCTIONS['schemaValidateTypeModel']([type_model], None), type_model)


    def test_schema_validate(self):
        types = SCRIPT_FUNCTIONS['schemaParse'](['# My struct', 'struct MyStruct', '', '  # An integer\n  int a'], None)
        self.assertDictEqual(SCRIPT_FUNCTIONS['schemaValidate']([types, 'MyStruct', {'a': 5}], None), {'a': 5})

        # Invalid types
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaValidate']([{}, 'MyStruct', {}], None)
        self.assertEqual(str(cm_exc.exception), "Invalid value {} (type 'dict'), expected type 'Types' [len > 0]")

        # Invalid value
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaValidate']([types, 'MyStruct', {}], None)
        self.assertEqual(str(cm_exc.exception), "Required member 'a' missing")

        # Non-dict types
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaValidate']([None, 'MyStruct', None], None))

        # Non-string type
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaValidate']([{}, None, None], None))


    def test_schema_validate_type_model(self):
        types = {'MyType': {'typedef': {'name': 'MyType','type': {'builtin': 'int'}}}}
        self.assertDictEqual(SCRIPT_FUNCTIONS['schemaValidateTypeModel']([types], None), types)

        # Invalid types
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['schemaValidateTypeModel']([{}], None)
        self.assertEqual(str(cm_exc.exception), "Invalid value {} (type 'dict'), expected type 'Types' [len > 0]")

        # Non-dict types
        self.assertIsNone(SCRIPT_FUNCTIONS['schemaValidateTypeModel']([None], None))


    #
    # String functions
    #


    def test_string_char_code_at(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 0], None), 97)
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 0.], None), 97)
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 1], None), 98)
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 2], None), 99)

        # Invalid index
        self.assertIsNone(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', -1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 4], None))

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['stringCharCodeAt']([None, 0], None))

        # Non-number index
        self.assertIsNone(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', None], None))

        # Non-integer index
        self.assertIsNone(SCRIPT_FUNCTIONS['stringCharCodeAt'](['abc', 1.5], None))


    def test_string_ends_with(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringEndsWith'](['foo bar', 'bar'], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['stringEndsWith'](['foo bar', 'foo'], None), False)

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['stringEndsWith']([None, 'bar'], None))

        # Non-string search
        self.assertIsNone(SCRIPT_FUNCTIONS['stringEndsWith'](['foo bar', None], None))


    def test_string_from_char_code(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringFromCharCode']([97, 98, 99], None), 'abc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringFromCharCode']([97., 98., 99.], None), 'abc')

        # Non-number code
        self.assertIsNone(SCRIPT_FUNCTIONS['stringFromCharCode']([97, 'b', 99], None))

        # Non-integer code
        self.assertIsNone(SCRIPT_FUNCTIONS['stringFromCharCode']([97, 98.5, 99], None))

        # Negative code
        self.assertIsNone(SCRIPT_FUNCTIONS['stringFromCharCode']([97, -98, 99], None))


    def test_string_index_of(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar'], None), 4)

        # Index provided
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar bar', 'bar', 5], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar bar', 'bar', 5.], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar bar', 'bar', 4], None), 4)
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar bar', 'bar', 0], None), 4)

        # Not Found
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bonk'], None), -1)

        # Not Found with index
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar', 5], None), -1)

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf']([None, 'bar'], None), -1)

        # Non-string search
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', None], None), -1)

        # Non-number index
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar', None], None), -1)

        # Non-integer index
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar', 1.5], None), -1)

        # Out-of-range index
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar', -1], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar', 7], None), -1)


    def test_string_last_index_of(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar'], None), 8)

        # Index provided
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar', 10], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar', 10.], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar', 9], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar', 8], None), 8)
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar', 7], None), 4)

        # Not Found
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bonk'], None), -1)

        # Not Found with index
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bar', 3], None), -1)

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf']([None, 'bar'], None), -1)

        # Non-string search
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', None], None), -1)

        # Non-number index
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bar', 'abc'], None), -1)

        # Non-integer index
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bar', 5.5], None), -1)

        # Out-of-range index
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bar', -1], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar', 'bar', 7], None), -1)


    def test_string_length(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLength'](['foo'], None), 3)

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringLength']([None], None), 0)


    def test_string_lower(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLower'](['Foo'], None), 'foo')

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringLower']([None], None), None)


    def test_string_new(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([123], None), '123')

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([None], None), 'null')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([True], None), 'true')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([False], None), 'false')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([0], None), '0')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([0.], None), '0')
        dt = value_parse_datetime('2022-06-21T12:30:15.100+00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([dt], None), value_string(dt))
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([{'b': 2, 'a': 1}], None), '{"a":1,"b":2}')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([[1, 2, 3]], None), '[1,2,3]')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([SCRIPT_FUNCTIONS['stringNew']], None), '<function>')
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([re.compile('^test')], None), '<regex>')


    def test_string_repeat(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', 2], None), 'abcabc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', 2.], None), 'abcabc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', 1], None), 'abc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', 0], None), '')

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat']([None, 3], None), None)

        # Non-number count
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', None], None), None)

        # Non-integer count
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', 1.5], None), None)

        # Negative count
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['abc', -2], None), None)


    def test_string_replace(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar', 'bar', 'bonk'], None), 'foo bonk')
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar bar', 'bar', 'bonk'], None), 'foo bonk bonk')

        # Not found
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar', 'abc', 'bonk'], None), 'foo bar')

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace']([None, 'bar', 'bonk'], None), None)

        # Non-string search
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar', None, 'bonk'], None), None)

        # Non-string replacement
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar', 'bar', None], None), None)


    def test_string_slice(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 5], None), 'oo b')
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1., 5.], None), 'oo b')
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 0, 7], None), 'foo bar')
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 6], None), 'oo ba')

        # Empty slice
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 7], None), '')
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 1], None), '')

        # No end index
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1], None), 'oo bar')

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice']([None, 1, 5], None))

        # Non-number begin/end
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', None, 5], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 'abc'], None))

        # Non-integer begin/end
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1.5, 5], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 5.5], None))

        # Out-of-range begin/end
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', -1, 5], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 8], None))


    def test_string_split(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar', ', '], None), ['foo', 'bar'])
        self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar, bonk', ', '], None), ['foo', 'bar', 'bonk'])

        # Not found
        self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo', ', '], None), ['foo'])

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringSplit']([None, ', '], None), None)

        # Non-string separator
        self.assertEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar', None], None), None)


    def test_string_starts_with(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringStartsWith'](['foo bar', 'foo'], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['stringStartsWith'](['foo bar', 'bar'], None), False)

        # Non-string value
        self.assertIsNone(SCRIPT_FUNCTIONS['stringStartsWith']([None, 'foo'], None))

        # Non-string search
        self.assertIsNone(SCRIPT_FUNCTIONS['stringStartsWith'](['foo bar', None], None))


    def test_string_trim(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim']([' abc  '], None), 'abc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim'](['\tabc\n'], None), 'abc')
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim'](['abc'], None), 'abc')

        #  Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim']([None], None), None)


    def test_string_upper(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringUpper'](['Foo'], None), 'FOO')

        # Non-string value
        self.assertEqual(SCRIPT_FUNCTIONS['stringUpper']([None], None), None)


    #
    # System functions
    #


    def test_system_boolean(self):
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([[1, 2, 3]], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([[]], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([True], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([False], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([datetime.datetime.now()], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([SCRIPT_FUNCTIONS['systemBoolean']], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([None], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([0], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([1], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([0.], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([1.], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([{}], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([re.compile(r'^abc$')], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean'](['abc'], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([''], None), False)
        self.assertEqual(SCRIPT_FUNCTIONS['systemBoolean']([()], None), True)


    def test_system_compare(self):
        # null
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([None, None], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([None, 0], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([0, None], None), 1)

        # number
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5, 5], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5, 5.], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5., 5.], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5, 6], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5, 6.], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([5., 6], None), -1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([6, 5], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([6, 5.], None), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([6., 5], None), 1)

        # object
        o1 = {'a': 1}
        o2 = {'a': 1}
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([o1, o1], None), 0)
        self.assertEqual(SCRIPT_FUNCTIONS['systemCompare']([o1, o2], None), 0)


    def test_system_fetch(self):
        def fetch_fn(request):
            url = request['url']
            if url.startswith('fail'):
                return None
            if url.startswith('raise'):
                raise Exception(url) # pylint: disable=broad-exception-raised

            body = request.get('body')
            headers = request.get('headers')
            method = 'GET' if body is None else 'POST'
            body_msg = '' if body is None else f' - {body}'
            headers_msg = '' if headers is None else f' - {value_json(headers)}'
            return f'{method} {url}{body_msg}{headers_msg}'

        def log_fn(message):
            logs.append(message)

        def url_fn(url):
            return 'dir/' + url

        options = {'debug': True, 'fetchFn': fetch_fn, 'logFn': log_fn}

        # URL
        logs = []
        self.assertEqual(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], options), 'GET test.txt')
        self.assertListEqual(logs, [])

        # Request model
        logs = []
        self.assertEqual(SCRIPT_FUNCTIONS['systemFetch']([{'url': 'test.txt'}], options), 'GET test.txt')
        self.assertListEqual(logs, [])

        # Array
        logs = []
        self.assertListEqual(
            SCRIPT_FUNCTIONS['systemFetch']([['test.txt', {'url': 'test2.txt', 'body': 'abc'}]], options),
            ['GET test.txt', 'POST test2.txt - abc']
        )
        self.assertListEqual(logs, [])

        # Headers
        logs = []
        self.assertEqual(
            SCRIPT_FUNCTIONS['systemFetch']([{'url': 'test.txt', 'headers': {'HEADER': 'VALUE'}}], options),
            'GET test.txt - {"HEADER":"VALUE"}'
        )
        self.assertListEqual(logs, [])

        # Empty array
        logs = []
        self.assertListEqual(SCRIPT_FUNCTIONS['systemFetch']([[]], options), [])
        self.assertListEqual(logs, [])

        # URL function
        logs = []
        options_url_fn = {'debug': True, 'fetchFn': fetch_fn, 'logFn': log_fn, 'urlFn': url_fn}
        self.assertEqual(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], options_url_fn), 'GET dir/test.txt')
        self.assertListEqual(logs, [])

        # Failure
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['fail.txt'], options))
        self.assertListEqual(logs, ['BareScript: Function "systemFetch" failed for resource "fail.txt"'])

        # Exception failure
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['raise.txt'], options))
        self.assertListEqual(logs, ['BareScript: Function "systemFetch" failed for resource "raise.txt"'])

        # Null options failure
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], None))
        self.assertListEqual(logs, [])

        # Null fetch function failure
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], {'debug': True, 'logFn': log_fn}))
        self.assertListEqual(logs, ['BareScript: Function "systemFetch" failed for resource "test.txt"'])

        # Failure with null log function
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], {'debug': True}))
        self.assertListEqual(logs, [])

        # Failure with debug off
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch'](['test.txt'], {'logFn': log_fn}))
        self.assertListEqual(logs, [])

        # Invalid request model
        logs = []
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['systemFetch']([{}], options)
        self.assertEqual(str(cm_exc.exception), "Required member 'url' missing")
        self.assertListEqual(logs, [])

        # Invalid array of request models
        logs = []
        with self.assertRaises(schema_markdown.ValidationError) as cm_exc:
            SCRIPT_FUNCTIONS['systemFetch']([[{}]], options)
        self.assertEqual(str(cm_exc.exception), "Required member 'url' missing")
        self.assertListEqual(logs, [])

        # Unexpected input type
        logs = []
        self.assertIsNone(SCRIPT_FUNCTIONS['systemFetch']([None], {'logFn': log_fn}))
        self.assertListEqual(logs, [])


    def test_system_global_get(self):
        options = {'globals': {'a': 1}}
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalGet'](['a'], options), 1)

        # Unknown
        options = {'globals': {}}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemGlobalGet'](['a'], options))

        # Default value
        options = {'globals': {'a': 1}}
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalGet'](['a', 2], options), 1)
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalGet'](['b', 2], options), 2)

        # No globals
        options = {}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemGlobalGet'](['a'], options))
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalGet'](['a', 2], options), 2)

        # Null options
        self.assertIsNone(SCRIPT_FUNCTIONS['systemGlobalGet'](['a'], None))
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalGet'](['a', 2], None), 2)

        # Non-string name
        options = {'globals': {'a': 1}}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemGlobalGet']([None], options))


    def test_system_global_set(self):
        options = {'globals': {}}
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalSet'](['a', 1], options), 1)
        self.assertDictEqual(options['globals'], {'a': 1})
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalSet'](['a', 2], options), 2)
        self.assertDictEqual(options['globals'], {'a': 2})

        # No globals
        options = {}
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalSet'](['a', 1], options), 1)

        # Null options
        self.assertEqual(SCRIPT_FUNCTIONS['systemGlobalSet'](['a', 1], None), 1)

        # Non-string name
        options = {'globals': {}}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemGlobalSet']([None], options))


    def test_system_is(self):
        # null
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([None, None], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([None, 0], None), False)

        # number
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([5, 5], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([5, 5.], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([5, 6], None), False)

        # object
        o1 = {'a': 1}
        o2 = {'a': 1}
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([o1, o1], None), True)
        self.assertEqual(SCRIPT_FUNCTIONS['systemIs']([o1, o2], None), False)


    def test_system_log(self):
        logs = []
        def log_fn(string):
            logs.append(string)

        options = {'logFn': log_fn}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog'](['Hello'], options))
        self.assertListEqual(logs, ['Hello'])

        # Debug
        logs = []
        options = {'logFn': log_fn, 'debug': True}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog'](['Hello'], options))
        self.assertListEqual(logs, ['Hello'])

        # No-debug
        logs = []
        options = {'logFn': log_fn, 'debug': False}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog'](['Hello'], options))
        self.assertListEqual(logs, ['Hello'])

        # Null options
        logs = []
        options = None
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog'](['Hello'], options))
        self.assertListEqual(logs, [])

        # No log function
        logs = []
        options = {}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog'](['Hello'], options))
        self.assertListEqual(logs, [])

        # Non-string message
        logs = []
        options = {'logFn': log_fn}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLog']([None], options))
        self.assertListEqual(logs, ['null'])


    def test_system_log_debug(self):
        logs = []
        def log_fn(string):
            logs.append(string)

        options = {'logFn': log_fn}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug'](['Hello'], options))
        self.assertListEqual(logs, [])

        # Debug
        logs = []
        options = {'logFn': log_fn, 'debug': True}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug'](['Hello'], options))
        self.assertListEqual(logs, ['Hello'])

        # No-debug
        logs = []
        options = {'logFn': log_fn, 'debug': False}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug'](['Hello'], options))
        self.assertListEqual(logs, [])

        # Null options
        logs = []
        options = None
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug'](['Hello'], options))
        self.assertListEqual(logs, [])

        # No log function
        logs = []
        options = {'debug': True}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug'](['Hello'], options))
        self.assertListEqual(logs, [])

        # Non-string message
        logs = []
        options = {'logFn': log_fn, 'debug': True}
        self.assertIsNone(SCRIPT_FUNCTIONS['systemLogDebug']([None], options))
        self.assertListEqual(logs, ['null'])


    def test_system_partial(self):
        def test_fn(args, options):
            name, number = args
            self.assertEqual(name, 'test')
            self.assertEqual(number, 1)
            self.assertDictEqual(options, {'debug': False})
            return f'{name}-{number}'

        partial_fn = SCRIPT_FUNCTIONS['systemPartial']([test_fn, 'test'], None)
        self.assertEqual(partial_fn([1], {'debug': False}), 'test-1')

        # Non-function
        self.assertIsNone(SCRIPT_FUNCTIONS['systemPartial']([None, 'test'], None))

        # No args
        self.assertIsNone(SCRIPT_FUNCTIONS['systemPartial']([test_fn], None))


    def test_system_type(self):
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([[1, 2, 3]], None), 'array')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([True], None), 'boolean')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([False], None), 'boolean')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([datetime.datetime.now()], None), 'datetime')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([SCRIPT_FUNCTIONS['systemType']], None), 'function')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([None], None), 'null')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([0], None), 'number')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([0.], None), 'number')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([{}], None), 'object')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType']([re.compile(r'^abc$')], None), 'regex')
        self.assertEqual(SCRIPT_FUNCTIONS['systemType'](['abc'], None), 'string')
        self.assertIsNone(SCRIPT_FUNCTIONS['systemType']([()], None))


    #
    # URL functions
    #


    def test_url_encode(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncode'](["https://foo.com/this & 'that'"], None),
            "https://foo.com/this%20&%20'that'"
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncode'](['https://foo.com/this (& that)'], None),
            'https://foo.com/this%20(&%20that%29'
        )

        # No extra
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncode'](['https://foo.com/this & that', False], None),
            'https://foo.com/this%20&%20that'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncode'](['https://foo.com/this (& that)', False], None),
            'https://foo.com/this%20(&%20that)'
        )

        # Non-string URL
        self.assertIsNone(SCRIPT_FUNCTIONS['urlEncode']([None], None))


    def test_url_encode_component(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncodeComponent'](["https://foo.com/this & 'that'"], None),
            "https%3A%2F%2Ffoo.com%2Fthis%20%26%20'that'"
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncodeComponent'](['https://foo.com/this (& that)'], None),
            'https%3A%2F%2Ffoo.com%2Fthis%20(%26%20that%29'
        )

        # No extra
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncodeComponent'](['https://foo.com/this & that', False], None),
            'https%3A%2F%2Ffoo.com%2Fthis%20%26%20that'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncodeComponent'](['https://foo.com/this (& that)', False], None),
            'https%3A%2F%2Ffoo.com%2Fthis%20(%26%20that)'
        )

        # Non-string URL
        self.assertIsNone(SCRIPT_FUNCTIONS['urlEncodeComponent']([None], None))
