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
            'statements': [],
            'scriptName': 'test.bare',
            'scriptLines': []
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:1: Empty script'
        ])


    def test_lint_script_function_redefined(self):
        script = {
            'statements': [
                {'function': {'name': 'testFn', 'statements': [], 'lineNumber': 1}},
                {'function': {'name': 'testFn', 'statements': [], 'lineNumber': 4}}
            ],
            'scriptName': 'test.bare',
            'scriptLines': [
                'function testFn():',
                'endfunction',
                '',
                'function testFn():',
                'endfunction'
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:4: Redefinition of function "testFn"'
        ])


    def test_lint_script_function_duplicate_argument(self):
        script = {
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['a', 'b', 'a'],
                        'statements': [
                            {'return': {
                                'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}},
                                'lineNumber': 2
                            }}
                        ],
                        'lineNumber': 1
                    }
                }
            ],
            'scriptName': 'test.bare',
            'scriptLines': [
                'function testFn(a, b, a):',
                '    return a + b',
                'endfunction'
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:1: Duplicate argument "a" of function "testFn"'
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
            ':1: Unused argument "b" of function "testFn"'
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
            'scriptName': 'test.bare',
            'scriptLines': [
                'function testFn():',
                '    a = 1',
                '    b = 2',
                '    c = a',
                '    d = 3',
                '    jump testLabel',
                '    testLabel:',
                '    e = -(b + c)',
                'endfunction'
            ],
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                            {'expr': {'name': 'b', 'expr': {'number': 2}, 'lineNumber': 3}},
                            {'expr': {'name': 'c', 'expr': {'variable': 'a'}, 'lineNumber': 4}},
                            {'expr': {'name': 'd', 'expr': {'number': 3}, 'lineNumber': 5}},
                            {'jump': {'label': 'testLabel', 'expr': {'variable': 'd'}, 'lineNumber': 6}},
                            {'label': {'name': 'testLabel', 'lineNumber': 7}},
                            {'expr': {'name': 'e', 'expr': {'unary': {
                                'op': '-',
                                'expr': {'group': {'binary': {'op': '+', 'left': {'variable': 'b'}, 'right': {'variable': 'c'}}}}
                            }}, 'lineNumber': 8}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:8: Unused variable "e" defined in function "testFn"'
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
            'scriptName': 'test.bare',
            'scriptLines': [
                'function testFn():',
                '    a = b',
                '    b = a',
                'endfunction'
            ],
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'variable': 'b'}, 'lineNumber': 2}},
                            {'expr': {'name': 'b', 'expr': {'variable': 'a'}, 'lineNumber': 3}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:2: Variable "b" of function "testFn" used before assignment'
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


    def test_lint_script_function_unknown_global(self):
        script = {
            'scriptName': 'test.bare',
            'scriptLines': [
                'function testFn(b):',
                '    a = 1',
                '    a = a',
                '    a = b',
                '    a = UNKNOWN',
                'endfunction'
            ],
            'statements': [
                {
                    'function': {
                        'name': 'testFn',
                        'args': ['b'],
                        'statements': [
                            {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                            {'expr': {'name': 'a', 'expr': {'variable': 'a'}, 'lineNumber': 3}},
                            {'expr': {'name': 'a', 'expr': {'variable': 'b'}, 'lineNumber': 4}},
                            {'expr': {'name': 'a', 'expr': {'variable': 'UNKNOWN'}, 'lineNumber': 5}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        }
        self.assertListEqual(lint_script(validate_script(script), {}), [
            'test.bare:5: Unknown global variable "UNKNOWN"'
        ])


    def test_lint_script_global_unknown_global(self):
        script = {
            'scriptName': 'test.bare',
            'scriptLines': [
                'a = 1',
                'a = a',
                'a = UNKNOWN'
            ],
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 1}},
                {'expr': {'name': 'a', 'expr': {'variable': 'a'}, 'lineNumber': 2}},
                {'expr': {'name': 'a', 'expr': {'variable': 'UNKNOWN'}, 'lineNumber': 3}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script), {}), [
            'test.bare:3: Unknown global variable "UNKNOWN"'
        ])


    def test_lint_script_global_variable_used_before_assignment(self):
        script = {
            'statements': [
                {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
                {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            ':1: Global variable "b" used before assignment'
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
            ':1: Unused label "unusedLabel" in function "testFn"'
        ])


    def test_lint_script_global_unused_label(self):
        script = {
            'statements': [
                {'label': {'name': 'usedLabel', 'lineNumber': 1}},
                {'label': {'name': 'unusedLabel', 'lineNumber': 2}},
                {'jump': {'label': 'usedLabel', 'lineNumber': 3}}
            ],
            'scriptName': 'test.bare',
            'scriptLines': [
                'usedlabel:',
                'unusedLabel:',
                'jump usedLabel'
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'test.bare:2: Unused global label "unusedLabel"'
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
            ':1: Unknown label "unknownLabel" in function "testFn"'
        ])


    def test_lint_script_global_unknown_label(self):
        script = {
            'statements': [
                {'jump': {'label': 'unknownLabel'}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            ':1: Unknown global label "unknownLabel"'
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
            ':1: Redefinition of label "testLabel" in function "testFn"'
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
            ':1: Redefinition of global label "testLabel"'
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
            ':1: Pointless statement in function "testFn"'
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
            ':1: Pointless global statement'
        ])


    def test_lint_script_inert(self):
        script = {
            'statements': [
                {'return': {'expr': {'number': 0}}}
            ]
        }
        self.assertListEqual(lint_script(validate_script(script)), [])
