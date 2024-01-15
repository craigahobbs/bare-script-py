# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import json
import math
import unittest

import schema_markdown

from bare_script import EXPRESSION_FUNCTIONS, SCRIPT_FUNCTIONS


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
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 1, 1], None), [])

        # End index less than start index
        self.assertListEqual(SCRIPT_FUNCTIONS['arraySlice']([array, 2, 1], None), [])

        # Non-array
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 1, 3], None))

        # Start index outside valid range
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, -1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 4], None))

        # Non-number start index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 'abc'], None))

        # Non-integer start index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 1.5], None))

        # End index outside valid range
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 0, -1], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 0, 5], None))

        # Non-number end index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 0, 'abc'], None))

        # Non-integer end index
        self.assertIsNone(SCRIPT_FUNCTIONS['arraySlice']([None, 0, 1.5], None))


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
    # Datetime functions
    #


    def test_datetime_day(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([local_dt], None), 21)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([utc_dt], None), 21)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([None], None), None)


    def test_datetime_hour(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([local_dt], None), 7)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([utc_dt], None), 7)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([None], None), None)


    def test_datetime_iso_format(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([local_dt], None), '2022-06-21T15:15:30+00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([utc_dt], None), '2022-06-21T07:15:30+00:00')

        # is_date
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([local_dt, True], None), '2022-06-21')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([utc_dt, True], None), '2022-06-21')

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([None], None), None)


    def test_datetime_iso_parse(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00+00:00'], None)], None),
            '2022-08-29T15:08:00+00:00'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00Z'], None)], None),
            '2022-08-29T15:08:00+00:00'
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00-08:00'], None)], None),
            '2022-08-29T23:08:00+00:00'
        )

        # Invalid datetime string
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOParse'](['invalid'], None), None)

        # Non-string datetime string
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOParse']([None], None), None)


    def test_datetime_millisecond(self):
        local_dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 100500).astimezone()
        utc_dt = datetime.datetime(2022, 6, 21, 7, 15, 30, 101500, tzinfo=datetime.timezone.utc)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMillisecond']([local_dt], None), 101)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMillisecond']([utc_dt], None), 102)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMillisecond']([None], None), None)


    def test_datetime_minute(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([local_dt], None), 15)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([utc_dt], None), 15)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([None], None), None)


    def test_datetime_month(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([local_dt], None), 6)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([utc_dt], None), 6)

        # Non-datetime
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([None], None), None)


    def test_datetime_new(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 100], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000).astimezone()
        )

        # Float arguments
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000).astimezone()
        )

        # Required arguments only
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21], None), datetime.datetime(2022, 6, 21).astimezone())

        # Extra months
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 26, 21, 12, 30, 15, 100], None),
            datetime.datetime(2024, 2, 21, 12, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, -14, 21, 12, 30, 15, 100], None),
            datetime.datetime(2020, 10, 21, 12, 30, 15, 100000).astimezone()
        )

        # Extra days
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 7, 20, 12, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 250, 12, 30, 15, 100], None),
            datetime.datetime(2023, 2, 5, 12, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, -50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 4, 11, 12, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, -250, 12, 30, 15, 100], None),
            datetime.datetime(2021, 9, 23, 12, 30, 15, 100000).astimezone()
        )

        # Extra hours
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 23, 2, 30, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, -50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 18, 22, 30, 15, 100000).astimezone()
        )

        # Extra minutes
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 15, 20, 15, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, -200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 8, 40, 15, 100000).astimezone()
        )

        # Extra seconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 33, 20, 100000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, -200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 26, 40, 100000).astimezone()
        )

        # Extra milliseconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 17, 200000).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, -2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 12, 800000).astimezone()
        )

        # Extra everything
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 12, 31, 23, 59, 59, 1000], None),
            datetime.datetime(2023, 1, 1, 0, 0, 0, 0).astimezone()
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2023, 1, 1, 0, 0, 0, -1000], None),
            datetime.datetime(2022, 12, 31, 23, 59, 59, 0).astimezone()
        )

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


    def test_datetime_new_utc(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, 100], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Float arguments
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022., 6., 21., 12., 30., 15., 100.], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Required arguments only
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21], None),
            datetime.datetime(2022, 6, 21, tzinfo=datetime.timezone.utc)
        )

        # Extra months
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 26, 21, 12, 30, 15, 100], None),
            datetime.datetime(2024, 2, 21, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, -14, 21, 12, 30, 15, 100], None),
            datetime.datetime(2020, 10, 21, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Extra days
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 7, 20, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 250, 12, 30, 15, 100], None),
            datetime.datetime(2023, 2, 5, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, -50, 12, 30, 15, 100], None),
            datetime.datetime(2022, 4, 11, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, -250, 12, 30, 15, 100], None),
            datetime.datetime(2021, 9, 23, 12, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Extra hours
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 23, 2, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, -50, 30, 15, 100], None),
            datetime.datetime(2022, 6, 18, 22, 30, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Extra minutes
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 15, 20, 15, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, -200, 15, 100], None),
            datetime.datetime(2022, 6, 21, 8, 40, 15, 100000, tzinfo=datetime.timezone.utc)
        )

        # Extra seconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 33, 20, 100000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, -200, 100], None),
            datetime.datetime(2022, 6, 21, 12, 26, 40, 100000, tzinfo=datetime.timezone.utc)
        )

        # Extra milliseconds
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, 2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 17, 200000, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, -2200], None),
            datetime.datetime(2022, 6, 21, 12, 30, 12, 800000, tzinfo=datetime.timezone.utc)
        )

        # Extra everything
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 12, 31, 23, 59, 59, 1000], None),
            datetime.datetime(2023, 1, 1, 0, 0, 0, 0, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2023, 1, 1, 0, 0, 0, -1000], None),
            datetime.datetime(2022, 12, 31, 23, 59, 59, 0, tzinfo=datetime.timezone.utc)
        )

        # Non-number arguments
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC'](['2022', 6, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, '6', 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, '21', 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, '12', 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, '30', 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, '15', 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, '100'], None))

        # Non-integer arguments
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022.5, 6, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6.5, 21, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21.5, 12, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12.5, 30, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30.5, 15, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15.5, 100], None))
        self.assertIsNone(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, 100.5], None))


    def test_datetime_now(self):
        self.assertIsInstance(SCRIPT_FUNCTIONS['datetimeNow']([], None), datetime.datetime)


    def test_datetime_second(self):
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([local_dt], None), 30)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([utc_dt], None), 30)

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
        local_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-08:00')
        utc_dt = datetime.datetime.fromisoformat('2022-06-21T07:15:30-00:00')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([local_dt], None), 2022)
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([utc_dt], None), 2022)

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

        # Zero indent
        self.assertEqual(
            SCRIPT_FUNCTIONS['jsonStringify']([{'a': 1, 'b': 2}, 0], None),
            '''\
{
"a": 1,
"b": 2
}'''
        )

        # Non-number space
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([None, 'abc'], None))

        # Non-integer space
        self.assertIsNone(SCRIPT_FUNCTIONS['jsonStringify']([None, 4.5], None))

        # Negative space
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
        self.assertIsInstance((SCRIPT_FUNCTIONS['mathRandom']([], None)), float)


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
        self.assertIsNone(SCRIPT_FUNCTIONS['numberParseFloat'](['asdf'], None))
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
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt'](['A', 0], None), 65)


    def test_string_char_code_at_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringCharCodeAt']([None, 0], None), None)


    def test_string_ends_with(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringEndsWith'](['foo bar', 'bar'], None), True)


    def test_string_ends_with_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringEndsWith']([None, 'bar'], None), None)


    def test_string_index_of(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar', 'bar'], None), 4)


    def test_string_index_of_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf']([None, 'bar'], None), -1)


    def test_string_index_of_position(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringIndexOf'](['foo bar bar', 'bar', 5], None), 8)


    def test_string_from_char_code(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringFromCharCode']([65, 66, 67], None), 'ABC')


    def test_string_last_index_of(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf'](['foo bar bar', 'bar'], None), 8)


    def test_string_last_index_of_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLastIndexOf']([None, 'bar'], None), -1)


    def test_string_length(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLength'](['foo'], None), 3)


    def test_string_length_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLength']([None], None), None)


    def test_string_lower(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLower'](['Foo'], None), 'foo')


    def test_string_lower_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringLower']([None], None), None)


    def test_string_new(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringNew']([123], None), '123')


    def test_string_repeat(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat'](['*', 3], None), '***')


    def test_string_repeat_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringRepeat']([None, 3], None), None)


    def test_string_replace(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace'](['foo bar', 'bar', 'bonk'], None), 'foo bonk')


    def test_string_replace_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringReplace']([None, 'bar', 'bonk'], None), None)


    @unittest.skip
    def test_string_replace_regex(self):
        # self.assertEqual(SCRIPT_FUNCTIONS.stringReplace(['foo bar', /\s+bar/g, ' bonk'], None), 'foo bonk')
        self.fail()


    @unittest.skip
    def test_string_replace_regex_replacer_function(self):
        # const replacerFunction = (args, options) => {
        #    assert.deepEqual(args, [' bar', 3, 'foo bar']);
        #    assert.deepEqual(options, {});
        #    return ' bonk';
        #assert.equal(SCRIPT_FUNCTIONS.stringReplace(['foo bar', /\s+bar/g, replacerFunction], {}), 'foo bonk');
        self.fail()


    @unittest.skip
    def test_string_replace_replacer_function(self):
        # const replacerFunction = (args, options) => {
        #    assert.deepEqual(args, ['bar', 4, 'foo bar']);
        #    assert.deepEqual(options, {});
        #    return 'bonk';
        #assert.equal(SCRIPT_FUNCTIONS.stringReplace(['foo bar', 'bar', replacerFunction], {}), 'foo bonk');
        self.fail()


    def test_string_slice(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice'](['foo bar', 1, 5], None), 'oo b')


    def test_string_slice_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringSlice']([None, 1, 5], None), None)


    def test_string_split(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar', ', '], None), ['foo', 'bar'])


    def test_string_split_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringSplit']([None, ', '], None), None)


    @unittest.skip
    def test_string_split_regex(self):
        # self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar', /,\s*/], None), ['foo', 'bar'])
        self.fail()


    @unittest.skip
    def test_string_split_limit(self):
        # self.assertListEqual(SCRIPT_FUNCTIONS['stringSplit'](['foo, bar, bonk', /,\s*/, 2], None), ['foo', 'bar'])
        self.fail()


    def test_string_starts_with(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringStartsWith'](['foo bar', 'foo'], None), True)


    def test_string_starts_with_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringStartsWith']([None, 'foo'], None), None)


    def test_string_trim(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim']([' abc '], None), 'abc')


    def test_string_trim_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringTrim']([None], None), None)


    def test_string_upper(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringUpper'](['Foo'], None), 'FOO')


    def test_string_upper_non_string(self):
        self.assertEqual(SCRIPT_FUNCTIONS['stringUpper']([None], None), None)


    #
    # URL functions
    #


    def test_url_encode(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['urlEncode'](['https://foo.com/this & that'], None),
            'https://foo.com/this%20&%20that'
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
            SCRIPT_FUNCTIONS['urlEncodeComponent'](['https://foo.com/this & that'], None),
            'https%3A%2F%2Ffoo.com%2Fthis%20%26%20that'
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
