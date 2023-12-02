# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import math
import unittest

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

    def test_array_new(self):
        self.assertListEqual(SCRIPT_FUNCTIONS['arrayNew']([1, 2, 3], None), [1, 2, 3])

    #
    # Datetime functions
    #

    def test_datetime_day(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([datetime.datetime(2022, 5, 21)], None), 21)

    def test_datetime_day_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([datetime.datetime(2022, 5, 21, tzinfo=datetime.UTC), True], None), 21)

    def test_datetime_day_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeDay']([None], None), None)

    def test_datetime_hour(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([datetime.datetime(2022, 5, 21, 7)], None), 7)

    def test_datetime_hour_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([datetime.datetime(2022, 5, 21, 7, tzinfo=datetime.UTC), True], None), 7)

    def test_datetime_hour_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeHour']([None], None), None)

    def test_datetime_iso_format(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(2022, 8, 29, 15, 8, tzinfo=datetime.UTC)], None),
            '2022-08-29T15:08:00+00:00'
        )
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(2022, 8, 29, 15, 8), True], None), '2022-08-29')
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOFormat']([datetime.datetime(2022, 11, 9, 15, 8), True], None), '2022-11-09')

    def test_datetime_iso_parse(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeISOFormat']([SCRIPT_FUNCTIONS['datetimeISOParse'](['2022-08-29T15:08:00.000Z'], None)], None),
            '2022-08-29T15:08:00+00:00'
        )
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeISOParse'](['invalid'], None), None)

    def test_datetime_minute(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([datetime.datetime(2022, 5, 21, 7, 15)], None), 15)

    def test_datetime_minute_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([datetime.datetime(2022, 5, 21, 7, 15, tzinfo=datetime.UTC), True], None), 15)

    def test_datetime_minute_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMinute']([None], None), None)

    def test_datetime_month(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([datetime.datetime(2022, 6, 21)], None), 6)

    def test_datetime_month_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([datetime.datetime(2022, 6, 21, tzinfo=datetime.UTC), True], None), 6)

    def test_datetime_month_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeMonth']([None], None), None)

    def test_datetime_new(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21], None), datetime.datetime(2022, 6, 21))

    def test_datetime_new_complete(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNew']([2022, 6, 21, 12, 30, 15, 100], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000)
        )

    def test_datetime_new_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21], None), datetime.datetime(2022, 6, 21, tzinfo=datetime.UTC))

    def test_datetime_new_utc_complete(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeNewUTC']([2022, 6, 21, 12, 30, 15, 100], None),
            datetime.datetime(2022, 6, 21, 12, 30, 15, 100000, tzinfo=datetime.UTC)
        )

    def test_datetime_now(self):
        self.assertIsInstance(SCRIPT_FUNCTIONS['datetimeNow']([], None), datetime.datetime)

    def test_datetime_second(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([datetime.datetime(2022, 5, 21, 7, 15, 30)], None), 30)

    def test_datetime_second_utc(self):
        self.assertEqual(
            SCRIPT_FUNCTIONS['datetimeSecond']([datetime.datetime(2022, 5, 21, 7, 15, 30, tzinfo=datetime.UTC), True], None),
            30
        )

    def test_datetime_second_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeSecond']([None], None), None)

    def test_datetime_today(self):
        today = datetime.date.today()
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeToday']([], None), datetime.datetime(today.year, today.month, today.day))

    def test_datetime_year(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([datetime.datetime(2022, 5, 21)], None), 2022)

    def test_datetime_year_utc(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([datetime.datetime(2022, 5, 21, tzinfo=datetime.UTC), True], None), 2022)

    def test_datetime_year_non_datetime(self):
        self.assertEqual(SCRIPT_FUNCTIONS['datetimeYear']([None], None), None)

    #
    # Math functions
    #

    def test_math_abs(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAbs']([-3], None), 3)

    def test_math_acos(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAcos']([1], None), 0)

    def test_math_asin(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAsin']([0], None), 0)

    def test_math_atan(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAtan']([0], None), 0)

    def test_math_atan2(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathAtan2']([0, 1], None), 0)

    def test_math_ceil(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathCeil']([0.25], None), 1)

    def test_math_cos(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathCos']([0], None), 1)

    def test_math_floor(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathFloor']([1.125], None), 1)

    def test_math_ln(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathLn']([math.e], None), 1)

    def test_math_log(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathLog']([10], None), 1)

    def test_math_log_base(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathLog']([8, 2], None), 3)

    def test_math_max(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathMax']([1, 2, 3], None), 3)

    def test_math_min(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathMin']([1, 2, 3], None), 1)

    def test_math_pi(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathPi']([], None), math.pi)

    def test_math_random(self):
        self.assertIsInstance((SCRIPT_FUNCTIONS['mathRandom']([], None)), float)

    def test_math_round(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.125], None), 5)

    def test_math_round_digits(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.25, 1], None), 5.3)

    def test_math_round_digits_2(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathRound']([5.15, 1], None), 5.2)

    def test_math_sign(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSign']([5.125], None), 1)

    def test_math_sin(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSin']([0], None), 0)

    def test_math_sqrt(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathSqrt']([4], None), 2)

    def test_math_tan(self):
        self.assertEqual(SCRIPT_FUNCTIONS['mathTan']([0], None), 0)

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
