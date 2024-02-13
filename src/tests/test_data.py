# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import unittest

from bare_script import validate_data


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