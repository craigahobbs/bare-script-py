# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import unittest

from schema_markdown import ValidationError

from bare_script import add_calculated_field, aggregate_data, filter_data, join_data, sort_data, validate_data


class TestData(unittest.TestCase):

    def test_validate_data(self):
        data = [
            {'A': 1, 'B': '5', 'C': 10},
            {'A': 2, 'B': '6', 'C': None},
            {'A': 3, 'B': '7', 'C': None}
        ]
        self.assertDictEqual(validate_data(data), {
            'A': 'number',
            'B': 'string',
            'C': 'number'
        })
        self.assertListEqual(data, [
            {'A': 1, 'B': '5', 'C': 10},
            {'A': 2, 'B': '6', 'C': None},
            {'A': 3, 'B': '7', 'C': None}
        ])


    def test_validate_data_csv(self):
        data = [
            {'A': 1, 'B': '5', 'C': 10},
            {'A': 2, 'B': 6, 'C': None},
            {'A': 3, 'B': '7', 'C': 'null'}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'A': 'number',
            'B': 'number',
            'C': 'number'
        })
        self.assertListEqual(data, [
            {'A': 1, 'B': 5, 'C': 10},
            {'A': 2, 'B': 6, 'C': None},
            {'A': 3, 'B': 7, 'C': None}
        ])


    def test_validate_data_datetime(self):
        data = [
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': '2022-08-30'},
            {'date': '2022-08-30T11:04:00Z'},
            {'date': '2022-08-30T11:04:00-07:00'},
            {'date': None}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'date': 'datetime'
        })

        # Fixup the date-format above as its affected by the current time zone
        date = data[1].get('date')
        data[1]['date'] = datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.timezone.utc)

        self.assertListEqual(data, [
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, 11, 4, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, 18, 4, tzinfo=datetime.timezone.utc)},
            {'date': None}
        ])


    def test_validate_data_datetime_string(self):
        data = [
            {'date': '2022-08-30'},
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': '2022-08-30T11:04:00Z'},
            {'date': '2022-08-30T11:04:00-07:00'},
            {'date': None}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'date': 'datetime'
        })

        # Fixup the date-format above as its affected by the current time zone
        date = data[0].get('date')
        data[0]['date'] = datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.timezone.utc)

        self.assertListEqual(data, [
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, 11, 4, tzinfo=datetime.timezone.utc)},
            {'date': datetime.datetime(2022, 8, 30, 18, 4, tzinfo=datetime.timezone.utc)},
            {'date': None}
        ])


    def test_validate_data_bool(self):
        data = [
            {'A': 1, 'B': True},
            {'A': 2, 'B': False},
            {'A': 3, 'B': 'true'},
            {'A': 4, 'B': 'false'},
            {'A': 5, 'B': None}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'A': 'number',
            'B': 'boolean'
        })
        self.assertListEqual(data, [
            {'A': 1, 'B': True},
            {'A': 2, 'B': False},
            {'A': 3, 'B': True},
            {'A': 4, 'B': False},
            {'A': 5, 'B': None}
        ])


    def test_validate_data_bool_string(self):
        data = [
            {'A': 1, 'B': 'true'},
            {'A': 2, 'B': 'false'},
            {'A': 3, 'B': True},
            {'A': 4, 'B': False},
            {'A': 5, 'B': None}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'A': 'number',
            'B': 'boolean'
        })
        self.assertListEqual(data, [
            {'A': 1, 'B': True},
            {'A': 2, 'B': False},
            {'A': 3, 'B': True},
            {'A': 4, 'B': False},
            {'A': 5, 'B': None}
        ])


    def test_validate_data_unknown(self):
        data = [
            {'A': 1, 'B': set('1')},
            {'A': 2, 'B': set('2')}
        ]
        self.assertDictEqual(validate_data(data, True), {
            'A': 'number'
        })
        self.assertListEqual(data, [
            {'A': 1, 'B': set('1')},
            {'A': 2, 'B': set('2')}
        ])


    def test_validate_data_number_error(self):
        data = [
            {'A': 1},
            {'A': '2'}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value "2", expected type number')


    def test_validate_data_number_error_bool(self):
        data = [
            {'A': 1},
            {'A': True}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value true, expected type number')


    def test_validate_data_number_error_csv(self):
        data = [
            {'A': 1},
            {'A': 'abc'}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data, True)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value "abc", expected type number')


    def test_validate_data_datetime_error(self):
        data = [
            {'A': datetime.datetime(2022, 7, 30, tzinfo=datetime.timezone.utc)},
            {'A': 2}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value 2, expected type datetime')


    def test_validate_data_datetime_error_csv(self):
        data = [
            {'A': datetime.datetime(2022, 7, 30, tzinfo=datetime.timezone.utc)},
            {'A': 'abc'}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data, True)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value "abc", expected type datetime')


    def test_validate_data_boolean_error(self):
        data = [
            {'A': False},
            {'A': 2}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value 2, expected type boolean')


    def test_validate_data_boolean_error_csv(self):
        data = [
            {'A': True},
            {'A': 'abc'}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data, True)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value "abc", expected type boolean')


    def test_validate_data_string_error(self):
        data = [
            {'A': 'a1'},
            {'A': 2}
        ]
        with self.assertRaises(TypeError) as cm_exc:
            validate_data(data, True)
        self.assertEqual(str(cm_exc.exception), 'Invalid "A" field value 2, expected type string')


    def test_join_data(self):
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
        self.assertListEqual(join_data(left_data, right_data, 'a'), [
            {'a': 1, 'b': 5, 'a2': 1, 'c': 10},
            {'a': 1, 'b': 6, 'a2': 1, 'c': 10},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 11},
            {'a': 2, 'b': 7, 'a2': 2, 'c': 12},
            {'a': 3, 'b': 8}
        ])


    def test_join_data_left(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 2, 'b': 7}
        ]
        right_data = [
            {'a': 1, 'c': 10}
        ]
        self.assertListEqual(join_data(left_data, right_data, 'a'), [
            {'a': 1, 'b': 5, 'a2': 1, 'c': 10},
            {'a': 2, 'b': 7}
        ])
        self.assertListEqual(join_data(left_data, right_data, 'a', is_left_join=True), [
            {'a': 1, 'b': 5, 'a2': 1, 'c': 10}
        ])


    def test_join_data_variables(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 1, 'b': 6},
            {'a': 2, 'b': 7}
        ]
        right_data = [
            {'a': 2, 'c': 10},
            {'a': 4, 'c': 11},
            {'a': 4, 'c': 12}
        ]
        self.assertListEqual(
            join_data(left_data, right_data, 'a', 'a / denominator', variables={'denominator': 2}),
            [
                {'a': 1, 'b': 5, 'a2': 2, 'c': 10},
                {'a': 1, 'b': 6, 'a2': 2, 'c': 10},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 11},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 12}
            ]
        )


    def test_join_data_globals(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 1, 'b': 6},
            {'a': 2, 'b': 7}
        ]
        right_data = [
            {'a': 2, 'c': 10},
            {'a': 4, 'c': 11},
            {'a': 4, 'c': 12}
        ]
        self.assertListEqual(
            join_data(left_data, right_data, 'a', 'a / denominator', options = {'globals': {'denominator': 2}}),
            [
                {'a': 1, 'b': 5, 'a2': 2, 'c': 10},
                {'a': 1, 'b': 6, 'a2': 2, 'c': 10},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 11},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 12}
            ]
        )


    def test_join_data_globals_variables(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 1, 'b': 6},
            {'a': 2, 'b': 7}
        ]
        right_data = [
            {'a': 2, 'c': 10},
            {'a': 4, 'c': 11},
            {'a': 4, 'c': 12}
        ]
        self.assertListEqual(
            join_data(left_data, right_data, 'a', 'a / (d1 + d2)', False, {'d1': 1.5}, {'globals': {'d2': 0.5}}),
            [
                {'a': 1, 'b': 5, 'a2': 2, 'c': 10},
                {'a': 1, 'b': 6, 'a2': 2, 'c': 10},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 11},
                {'a': 2, 'b': 7, 'a2': 4, 'c': 12}
            ]
        )


    def test_join_data_unique(self):
        left_data = [
            {'a': 1, 'b': 5},
            {'a': 1, 'b': 6},
            {'a': 2, 'b': 7},
            {'a': 3, 'b': 8}
        ]
        right_data = [
            {'a': 1, 'a2': 0, 'c': 10},
            {'a': 2, 'a2': 0, 'c': 11},
            {'a': 2, 'a2': 0, 'c': 12}
        ]
        self.assertListEqual(join_data(left_data, right_data, 'a'), [
            {'a': 1, 'b': 5, 'a2': 0, 'a3': 1, 'c': 10},
            {'a': 1, 'b': 6, 'a2': 0, 'a3': 1, 'c': 10},
            {'a': 2, 'b': 7, 'a2': 0, 'a3': 2, 'c': 11},
            {'a': 2, 'b': 7, 'a2': 0, 'a3': 2, 'c': 12},
            {'a': 3, 'b': 8}
        ])


    def test_add_calculated_field(self):
        data = [
            {'A': 1, 'B': 5},
            {'A': 2, 'B': 6}
        ]
        self.assertListEqual(add_calculated_field(data, 'C', 'A * B'), [
            {'A': 1, 'B': 5, 'C': 5},
            {'A': 2, 'B': 6, 'C': 12}
        ])


    def test_add_calculated_field_variables(self):
        data = [
            {'A': 1},
            {'A': 2}
        ]
        self.assertListEqual(add_calculated_field(data, 'C', 'A * B', {'B': 5}), [
            {'A': 1, 'C': 5},
            {'A': 2, 'C': 10}
        ])


    def test_add_calculated_field_globals(self):
        data = [
            {'A': 1},
            {'A': 2}
        ]
        self.assertListEqual(add_calculated_field(data, 'C', 'A * B * X', {'B': 5}, {'globals': {'X': 2}}), [
            {'A': 1, 'C': 10},
            {'A': 2, 'C': 20}
        ])


    def test_filter_data(self):
        data = [
            {'A': 1, 'B': 5},
            {'A': 6, 'B': 2},
            {'A': 3, 'B': 7}
        ]
        self.assertListEqual(filter_data(data, 'A > B'), [
            {'A': 6, 'B': 2}
        ])


    def test_filter_data_variables(self):
        data = [
            {'A': 1, 'B': 5},
            {'A': 6, 'B': 2},
            {'A': 3, 'B': 7}
        ]
        self.assertListEqual(filter_data(data, 'A > test', {'test': 5}), [
            {'A': 6, 'B': 2}
        ])


    def test_filter_data_globals(self):
        data = [
            {'A': 1, 'B': 5},
            {'A': 6, 'B': 2},
            {'A': 3, 'B': 7}
        ]
        self.assertListEqual(filter_data(data, 'A > test * X', {'test': 2.5}, {'globals': {'X': 2}}), [
            {'A': 6, 'B': 2}
        ])


    def test_aggregate_data(self):
        data = [
            {'A': 1, 'B': 1, 'C': 4},
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1}
        ]
        aggregation = {
            'measures': [
                {'field': 'C', 'function': 'average'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'C': 4.5}
        ])


    def test_aggregate_data_categories(self):
        data = [
            {'A': 1, 'B': 1, 'C': 4},
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'average'},
                {'field': 'C', 'function': 'average', 'name': 'Average(C)'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 4.5, 'Average(C)': 4.5},
            {'A': 1, 'B': 2, 'C': 7.5, 'Average(C)': 7.5},
            {'A': 2, 'B': 1, 'C': 9.5, 'Average(C)': 9.5},
            {'A': 2, 'B': 2, 'C': None, 'Average(C)': None}
        ])


    def test_aggregate_data_count(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'count'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 2},
            {'A': 1, 'B': 2, 'C': 2},
            {'A': 2, 'B': 1, 'C': 2},
            {'A': 2, 'B': 2, 'C': None}
        ])


    def test_aggregate_data_max(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 1, 'C': 4},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'max'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2, 'C': None}
        ])


    def test_aggregate_data_min(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 1, 'C': 4},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'min'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 4},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 2, 'C': None}
        ])


    def test_aggregate_data_stddev(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 10},
            {'A': 2, 'B': 1, 'C': 5},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'stddev'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 0.5},
            {'A': 1, 'B': 2, 'C': 1.5},
            {'A': 2, 'B': 1, 'C': 2.5},
            {'A': 2, 'B': 2, 'C': None}
        ])


    def test_aggregate_data_sum(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 1},
            {'A': 1, 'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        aggregation = {
            'categories': ['A', 'B'],
            'measures': [
                {'field': 'C', 'function': 'sum'}
            ]
        }
        self.assertListEqual(aggregate_data(data, aggregation), [
            {'A': 1, 'B': 1, 'C': 11},
            {'A': 1, 'B': 2, 'C': 15},
            {'A': 2, 'B': 1, 'C': 19},
            {'A': 2, 'B': 2, 'C': None}
        ])


    def test_aggregate_data_invalid(self):
        with self.assertRaises(ValidationError) as cm_exc:
            aggregate_data([], {})
        self.assertEqual(str(cm_exc.exception), "Required member 'measures' missing")


    def test_sort_data(self):
        data = [
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1},
            {'B': 2, 'C': 7},
            {'A': 1, 'B': 2, 'C': 8},
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2}
        ]
        self.assertListEqual(sort_data(data, [['A', True], ['B']]), [
            {'A': 2, 'B': 1, 'C': 9},
            {'A': 2, 'B': 1, 'C': 10},
            {'A': 2, 'B': 2},
            {'A': 1},
            {'A': 1, 'B': 1, 'C': 5},
            {'A': 1, 'B': 1, 'C': 6},
            {'A': 1, 'B': 2, 'C': 8},
            {'B': 2, 'C': 7}
        ])
