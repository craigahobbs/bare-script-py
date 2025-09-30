# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from schema_markdown import ValidationError
from bare_script import lint_script, validate_expression, validate_script


class TestModel(unittest.TestCase):

    def test_validate_script(self):
        script = {'statements': []}
        self.assertDictEqual(validate_script(script), script)


    def test_validate_script_error(self):
        script = {}
        with self.assertRaises(ValidationError) as cm_exc:
            validate_script(script)
        self.assertEqual(str(cm_exc.exception), "Required member 'statements' missing")


    def test_validate_expression(self):
        expr = {'number': 1}
        self.assertDictEqual(validate_expression(expr), expr)


    def test_validate_expression_error(self):
        expr = {}
        with self.assertRaises(ValidationError) as cm_exc:
            validate_expression(expr)
        self.assertEqual(str(cm_exc.exception), "Invalid value {} (type 'dict'), expected type 'Expression'")


    def test_lint_script_empty_script(self):
        script = {
            'statements': []
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Empty script'
        ])


    def test_lint_script_function_redefined(self):
        script = {
            'statements': [
                {'function': {'name': 'testFn', 'statements': []}},
                {'function': {'name': 'testFn', 'statements': []}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Redefinition of function "testFn" (index 1)'
        ])


    def test_lint_script_function_duplicate_argument(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['a', 'b', 'a'],
                        'statements': [
                            {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Duplicate argument "a" of function "testFn" (index 0)'
        ])


    def test_lint_script_function_unused_argument(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['a', 'b'],
                        'statements': [
                            {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'number': 1}}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unused argument "b" of function "testFn" (index 0)'
        ])


    def test_lint_script_function_argument_function_call_ok(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['a'],
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'a'}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])


    def test_lint_script_function_unused_variable(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'number': 1}}},
                            {'expr': {'name': 'b', 'expr': {'number': 2}}},
                            {'expr': {'name': 'c', 'expr': {'variable': 'a'}}},
                            {'expr': {'name': 'd', 'expr': {'number': 3}}},
                            {'jump': {'label': 'testLabel', 'expr': {'variable': 'd'}}},
                            {'label': {'name': 'testLabel'}},
                            {'expr': {'name': 'e', 'expr': {'unary': {
                                'op': '-',
                                'expr': {'group': {'binary': {'op': '+', 'left': {'variable': 'b'}, 'right': {'variable': 'c'}}}}
                            }}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unused variable "e" defined in function "testFn" (index 6)'
        ])


    def test_lint_script_function_arg_used_variable_ok(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'number': 1}}},
                            {'expr': {'expr': {'function': {'name': 'foo', 'args': [{'variable': 'a'}]}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])


    def test_lint_script_global_unused_variable_ok(self):
        script = {
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 1}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])


    def test_lint_script_function_variable_used_before_assignment(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
                            {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Variable "b" of function "testFn" used (index 0) before assignment (index 1)'
        ])


    def test_lint_script_function_variable_used_before_assignment_arg_ok(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['b'],
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
                            {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])


    def test_lint_script_function_variable_used_before_assignment_reassign_ok(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'number': 1}}},
                            {'expr': {'expr': {'function': {'name': 'mathSqrt', 'args': [{'variable': 'a'}]}}}},
                            {'expr': {'name': 'a', 'expr': {'number': 2}}},
                            {'expr': {'expr': {'function': {'name': 'mathSqrt', 'args': [{'variable': 'a'}]}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])


    def test_lint_script_global_variable_used_before_assignment(self):
        script = {
            'statements': [
                {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
                {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Global variable "b" used (index 0) before assignment (index 1)'
        ])


    def test_lint_script_function_unused_label(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'label': {'name': 'usedLabel'}},
                            {'label': {'name': 'unusedLabel'}},
                            {'jump': {'label': 'usedLabel'}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unused label "unusedLabel" in function "testFn" (index 1)'
        ])


    def test_lint_script_global_unused_label(self):
        script = {
            'statements': [
                {'label': {'name': 'usedLabel'}},
                {'label': {'name': 'unusedLabel'}},
                {'jump': {'label': 'usedLabel'}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unused global label "unusedLabel" (index 1)'
        ])


    def test_lint_script_function_unknown_label(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'jump': {'label': 'unknownLabel'}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unknown label "unknownLabel" in function "testFn" (index 0)'
        ])


    def test_lint_script_global_unknown_label(self):
        script = {
            'statements': [
                {'jump': {'label': 'unknownLabel'}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Unknown global label "unknownLabel" (index 0)'
        ])


    def test_lint_script_function_label_redefined(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'label': {'name': 'testLabel'}},
                            {'label': {'name': 'testLabel'}},
                            {'jump': {'label': 'testLabel'}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Redefinition of label "testLabel" in function "testFn" (index 1)'
        ])


    def test_lint_script_global_label_redefined(self):
        script = {
            'statements': [
                {'label': {'name': 'testLabel'}},
                {'label': {'name': 'testLabel'}},
                {'jump': {'label': 'testLabel'}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Redefinition of global label "testLabel" (index 1)'
        ])


    def test_lint_script_function_pointless_statement(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'expr': {'unary': {'op': '!', 'expr': {
                                'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'function': {'name': 'foo'}}}}
                            }}}}},
                            {'expr': {'expr': {'unary': {'op': '!', 'expr': {
                                'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'number': 1}}}
                            }}}}}
                        ]
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Pointless statement in function "testFn" (index 1)'
        ])


    def test_lint_script_global_pointless_statement(self):
        script = {
            'statements': [
                {'expr': {'expr': {'unary': {'op': '!', 'expr': {
                    'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'function': {'name': 'foo'}}}}
                }}}}},
                {'expr': {'expr': {'unary': {'op': '!', 'expr': {
                    'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'number': 1}}}
                }}}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Pointless global statement (index 1)'
        ])


    def test_lint_script_inert(self):
        script = {
            'statements': [
                {'return': {'expr': {'number': 0}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])
