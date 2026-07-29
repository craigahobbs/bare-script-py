# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from bare_script import validate_expression, validate_script
from bare_script.include import SchemaValidationError


class TestModel(unittest.TestCase):

    def test_validate_script(self):
        script = {'statements': []}
        self.assertDictEqual(validate_script(script), script)


    def test_validate_script_error(self):
        script = {}
        with self.assertRaises(SchemaValidationError) as cm_exc:
            validate_script(script)
        self.assertEqual(str(cm_exc.exception), 'Required member "statements" missing')


    def test_validate_expression(self):
        expr = {'number': 1}
        self.assertDictEqual(validate_expression(expr), expr)


    def test_validate_expression_error(self):
        expr = {}
        with self.assertRaises(SchemaValidationError) as cm_exc:
            validate_expression(expr)
        self.assertEqual(str(cm_exc.exception), 'Invalid value {} (type "object"), expected type "Expression"')
