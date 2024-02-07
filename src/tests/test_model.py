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
            self.assertEqual(str(cm_exc.exception), "Invalid value {} (type 'object'), expected type 'Expression'")


    def test_lint_script_empty_script(self):
        script = {
            'statements': []
        }
        self.assertListEqual(lint_script(validate_script(script)), [
            'Empty script'
        ])


# test('lintScript, function redefined', () => {
#     const script = {
#         'statements': [
#             {'function': {'name': 'testFn', 'statements': []}},
#             {'function': {'name': 'testFn', 'statements': []}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Redefinition of function "testFn" (index 1)'
#     ]);
# });


# test('lintScript, function duplicate argument', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'args': ['a', 'b', 'a'],
#                     'statements': [
#                         {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Duplicate argument "a" of function "testFn" (index 0)'
#     ]);
# });


# test('lintScript, function unused argument', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'args': ['a', 'b'],
#                     'statements': [
#                         {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'number': 1}}}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unused argument "b" of function "testFn" (index 0)'
#     ]);
# });


# test('lintScript, function argument function call ok', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'args': ['a'],
#                     'statements': [
#                         {'return': {'expr': {'function': {'name': 'a'}}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), []);
# });


# test('lintScript, function unused variable', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'expr': {'name': 'a', 'expr': {'number': 1}}},
#                         {'expr': {'name': 'b', 'expr': {'number': 2}}},
#                         {'expr': {'name': 'c', 'expr': {'variable': 'a'}}},
#                         {'expr': {'name': 'd', 'expr': {'number': 3}}},
#                         {'jump': {'label': 'testLabel', 'expr': {'variable': 'd'}}},
#                         {'label': 'testLabel'},
#                         {'expr': {'name': 'e', 'expr': {'unary': {
#                             'op': '-',
#                             'expr': {'group': {'binary': {'op': '+', 'left': {'variable': 'b'}, 'right': {'variable': 'c'}}}}
#                         }}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unused variable "e" defined in function "testFn" (index 6)'
#     ]);
# });


# test('lintScript, function arg used variable ok', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'expr': {'name': 'a', 'expr': {'number': 1}}},
#                         {'expr': {'expr': {'function': {'name': 'foo', 'args': [{'variable': 'a'}]}}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), []);
# });


# test('lintScript, global unused variable ok', () => {
#     const script = {
#         'statements': [
#             {'expr': {'name': 'a', 'expr': {'number': 1}}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), []);
# });


# test('lintScript, function variable used before assignment', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
#                         {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Variable "b" of function "testFn" used (index 0) before assignment (index 1)'
#     ]);
# });


# test('lintScript, function variable used before assignment arg ok', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'args': ['b'],
#                     'statements': [
#                         {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
#                         {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), []);
# });


# test('lintScript, global variable used before assignment', () => {
#     const script = {
#         'statements': [
#             {'expr': {'name': 'a', 'expr': {'variable': 'b'}}},
#             {'expr': {'name': 'b', 'expr': {'variable': 'a'}}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Global variable "b" used (index 0) before assignment (index 1)'
#     ]);
# });


# test('lintScript, function unused label', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'label': 'unusedLabel'}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unused label "unusedLabel" in function "testFn" (index 0)'
#     ]);
# });


# test('lintScript, global unused label', () => {
#     const script = {
#         'statements': [
#             {'label': 'unusedLabel'}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unused global label "unusedLabel" (index 0)'
#     ]);
# });


# test('lintScript, function unknown label', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'jump': {'label': 'unknownLabel'}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unknown label "unknownLabel" in function "testFn" (index 0)'
#     ]);
# });


# test('lintScript, global unknown label', () => {
#     const script = {
#         'statements': [
#             {'jump': {'label': 'unknownLabel'}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Unknown global label "unknownLabel" (index 0)'
#     ]);
# });


# test('lintScript, function label redefined', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'label': 'testLabel'},
#                         {'label': 'testLabel'},
#                         {'jump': {'label': 'testLabel'}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Redefinition of label "testLabel" in function "testFn" (index 1)'
#     ]);
# });


# test('lintScript, global label redefined', () => {
#     const script = {
#         'statements': [
#             {'label': 'testLabel'},
#             {'label': 'testLabel'},
#             {'jump': {'label': 'testLabel'}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Redefinition of global label "testLabel" (index 1)'
#     ]);
# });


# test('lintScript, function pointless statement', () => {
#     const script = {
#         'statements': [
#             {
#                 'function': {
#                     'name': 'testFn',
#                     'statements': [
#                         {'expr': {'expr': {'unary': {'op': '!', 'expr': {
#                             'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'function': {'name': 'foo'}}}}
#                         }}}}},
#                         {'expr': {'expr': {'unary': {'op': '!', 'expr': {
#                             'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'number': 1}}}
#                         }}}}}
#                     ]
#                 }
#             }
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Pointless statement in function "testFn" (index 1)'
#     ]);
# });


# test('lintScript, global pointless statement', () => {
#     const script = {
#         'statements': [
#             {'expr': {'expr': {'unary': {'op': '!', 'expr': {
#                 'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'function': {'name': 'foo'}}}}
#             }}}}},
#             {'expr': {'expr': {'unary': {'op': '!', 'expr': {
#                 'group': {'binary': {'op': '+', 'left': {'number': 0}, 'right': {'number': 1}}}
#             }}}}}
#         ]
#     };
#     assert.deepEqual(lintScript(validateScript(script)), [
#         'Pointless global statement (index 1)'
#     ]);
# });
