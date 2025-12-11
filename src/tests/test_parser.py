# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from bare_script import BareScriptParserError, parse_expression, parse_script, validate_expression, validate_script


class TestParseScript(unittest.TestCase):

    def test_array_input(self):
        script = validate_script(parse_script([
            'a = [ \\',
            '    1,\\',
            '''\
    2 \\
]
'''
        ]))
        self.assertDictEqual(script, {
            'scriptLines': [
                'a = [ \\',
                '    1,\\',
                '    2 \\',
                ']',
                ''
            ],
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}},
                        'lineNumber': 1,
                        'lineCount': 4
                    }
                }
            ]
        })


    def test_script_name(self):
        script_str = 'return 1 + 2'
        script = validate_script(parse_script(script_str, 1, 'test.bare'))
        self.assertDictEqual(script, {
            'scriptName': 'test.bare',
            'scriptLines': script_str.splitlines(),
            'statements': [
                {
                    'return': {
                        'expr': {'binary': {'op': '+', 'left': {'number': 1.0}, 'right': {'number': 2.0}}},
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_script_name_error(self):
        script_str = '''\
a = 1
return a + 1 asdf
'''
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script(script_str, 1, 'test.bare'))
        self.assertEqual(str(cm_exc.exception), '''\
test.bare:2: Syntax error
return a + 1 asdf
            ^
''')


    def test_array_literals(self):
        script_lines = [
            'a = [1, "2", [3, null]]'
        ]
        script = validate_script(parse_script(script_lines, 1, 'test.bare'))
        self.assertDictEqual(script, {
            'scriptName': 'test.bare',
            'scriptLines': script_lines,
            'statements': [
                {'expr': {
                    'name': 'a',
                    'expr': {'function': {
                        'name': 'arrayNew',
                        'args': [
                            {'number': 1.0},
                            {'string': '2'},
                            {'function': {
                                'name': 'arrayNew',
                                'args': [
                                    {'number': 3.0},
                                    {'variable': 'null'}
                                ]
                            }}
                        ],
                    }},
                    'lineNumber': 1
                }}
            ]
        })

        # Missing value
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = [, 2]'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = [, 2]
     ^
''')

        # Missing separator
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = [1 2]'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = [1 2]
      ^
''')


    def test_object_literals(self):
        script_lines = [
            'a = {"a": 1, "b": "2", "c": {"d": 3, "e": null}}',
            'b = {}'
        ]
        script = validate_script(parse_script(script_lines, 1, 'test.bare'))
        self.assertDictEqual(script, {
            'scriptName': 'test.bare',
            'scriptLines': script_lines,
            'statements': [
                {'expr': {
                    'name': 'a',
                    'expr': {'function': {
                        'name': 'objectNew',
                        'args': [
                            {'string': 'a'},
                            {'number': 1.0},
                            {'string': 'b'},
                            {'string': '2'},
                            {'string': 'c'},
                            {'function': {
                                'name': 'objectNew',
                                'args': [
                                    {'string': 'd'},
                                    {'number': 3.0},
                                    {'string': 'e'},
                                    {'variable': 'null'}
                                ]
                            }}
                        ]
                    }},
                    'lineNumber': 1
                }},
                {'expr': {
                    'name': 'b',
                    'expr': {'function': {'name': 'objectNew', 'args': []}},
                    'lineNumber': 2
                }}
            ]
        })

        # Key only
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = {"b"}'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = {"b"}
        ^
''')

        # No keys
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = {1, 2}'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = {1, 2}
      ^
''')

        # Key, no value
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = {"b":}'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = {"b":}
         ^
''')

        # Missing value
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = {, "b": 2}'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = {, "b": 2}
     ^
''')

        # Missing separator
        with self.assertRaises(BareScriptParserError) as cm_exc:
            validate_script(parse_script('a = {"a": 1 "b": 2}'))
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
a = {"a": 1 "b": 2}
           ^
''')


    def test_comments(self):
        script_str = '''\
include <args.bare>  # Application arguments

include 'util.bare'  # Utilities

# Main entry point
function main():             # Start running
    markdownPrint('# TODO')  # TODO
    return true              # Success!
endfunction                  # End running

jump label  # Jump to next
label:      # Where to jump

if false:    # Never happen
    ix = 0
elif false:  # Never happen
    ix = 1
else:        # Always happened
    ix = 2
endif        # It happens

for num in [1, 2, 3]:  # Iterate numbers
    systemLog(num)
endfor  # Numbers done

ix = 0
while true:  # Forever?
    if ix == 5:
        break  # All done
    endif
    ix = ix + 1
    if ix == 3:
        continue  # Silly
    endif
endwhile  # Keep doing it

return  # Bye!
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'include': {
                        'includes': [
                            {'url': 'args.bare', 'system': True},
                            {'url': 'util.bare'}
                        ],
                        'lineNumber': 1,
                        'lineCount': 3
                    }
                },
                {
                    'function': {
                        'name': 'main',
                        'statements': [
                            {'expr': {'expr': {'function': {'name': 'markdownPrint', 'args': [{'string': '# TODO'}]}}, 'lineNumber': 7}},
                            {'return': {'expr': {'variable': 'true'}, 'lineNumber': 8}}
                        ],
                        'lineNumber': 6
                    }
                },
                {'jump': {'label': 'label', 'lineNumber': 11}},
                {'label': {'name': 'label', 'lineNumber': 12}},
                {
                    'jump': {
                        'label': '__bareScriptIf0',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'false'}}},
                        'lineNumber': 14
                    }
                },
                {'expr': {'name': 'ix', 'expr': {'number': 0.0}, 'lineNumber': 15}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 16}},
                {'label': {'name': '__bareScriptIf0', 'lineNumber': 16}},
                {
                    'jump': {
                        'label': '__bareScriptIf1',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'false'}}},
                        'lineNumber': 16
                    }
                },
                {'expr': {'name': 'ix', 'expr': {'number': 1.0}, 'lineNumber': 17}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 18}},
                {'label': {'name': '__bareScriptIf1', 'lineNumber': 18}},
                {'expr': {'name': 'ix', 'expr': {'number': 2.0}, 'lineNumber': 19}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 20}},
                {
                    'expr': {
                        'name': '__bareScriptValues2',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1.0},{'number': 2.0},{'number': 3.0}]}},
                        'lineNumber': 22
                    }
                },
                {
                    'expr': {
                        'name': '__bareScriptLength2',
                        'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues2'}]}},
                        'lineNumber': 22
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptDone2',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength2'}}},
                        'lineNumber': 22
                    }
                },
                {'expr': {'name': '__bareScriptIndex2', 'expr': {'number': 0.0}, 'lineNumber': 22}},
                {'label': {'name': '__bareScriptLoop2', 'lineNumber': 22}},
                {
                    'expr': {
                        'name': 'num',
                        'expr': {
                            'function': {
                                'name': 'arrayGet',
                                'args': [{'variable': '__bareScriptValues2'}, {'variable': '__bareScriptIndex2'}]
                            }
                        },
                        'lineNumber': 22
                    }
                },
                {'expr': {'expr': {'function': {'name': 'systemLog', 'args': [{'variable': 'num'}]}}, 'lineNumber': 23}},
                {
                    'expr': {
                        'name': '__bareScriptIndex2',
                        'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex2'},'right': {'number': 1.0}}},
                        'lineNumber': 24
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptLoop2',
                        'expr': {
                            'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex2'},'right': {'variable': '__bareScriptLength2'}}
                        },
                        'lineNumber': 24
                    }
                },
                {'label': {'name': '__bareScriptDone2', 'lineNumber': 24}},
                {'expr': {'name': 'ix', 'expr': {'number': 0.0}, 'lineNumber': 26}},
                {
                    'jump': {
                        'label': '__bareScriptDone3',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}},
                        'lineNumber': 27
                    }
                },
                {'label': {'name': '__bareScriptLoop3', 'lineNumber': 27}},
                {
                    'jump': {
                        'label': '__bareScriptDone4',
                        'expr': {
                            'unary': {'op': '!', 'expr': {'binary': {'op': '==', 'left': {'variable': 'ix'},'right': {'number': 5.0}}}}
                        },
                        'lineNumber': 28
                    }
                },
                {'jump': {'label': '__bareScriptDone3', 'lineNumber': 29}},
                {'label': {'name': '__bareScriptDone4', 'lineNumber': 30}},
                {
                    'expr': {
                        'name': 'ix',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'ix'},'right': {'number': 1.0}}},
                        'lineNumber': 31
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptDone5',
                        'expr': {
                            'unary': {'op': '!', 'expr': {'binary': {'op': '==', 'left': {'variable': 'ix'},'right': {'number': 3.0}}}}
                        },
                        'lineNumber': 32
                    }
                },
                {'jump': {'label': '__bareScriptLoop3', 'lineNumber': 33}},
                {'label': {'name': '__bareScriptDone5', 'lineNumber': 34}},
                {'jump': {'label': '__bareScriptLoop3', 'expr': {'variable': 'true'}, 'lineNumber': 35}},
                {'label': {'name': '__bareScriptDone3', 'lineNumber': 35}},
                {'return': {'lineNumber': 37}}
            ]
        })


    def test_line_continuation(self):
        script_str = '''\
a = [ \\
    1, \\
    2 \\
 ]
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}},
                        'lineNumber': 1,
                        'lineCount': 4
                    }
                }
            ]
        })


    def test_line_continuation_comments(self):
        script_str = '''\
# Comments don't continue \\
a = [ \\
    # Comments are OK within a continuation...
    1, \\
    # ...with or without a continuation backslash \\
    2 \\
]
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}},
                        'lineNumber': 2,
                        'lineCount': 6
                    }
                }
            ]
        })


    def test_line_continuation_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
    fn1(arg1, \\
    fn2(),
    null))
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
    fn1(arg1, fn2(),
                    ^
''')


    def test_long_line_error_middle(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
    reallyLongFunctionName( \\
        value1 + value2 + value3 + value4 + value5, \\
        value6 + value7 + value8 + value9 + value10, \\
        value11 + value12 + value13 + value14 + value15, \\
        value16 + value17 + value18 + value19 + value20, \\
        value21 + value22 + value23 + value24 + value25, \\
        @#$, \\
        value26 + value27 + value28 + value29 + value30, \\
        value31 + value32 + value33 + value34 + value35, \\
        value36 + value37 + value38 + value39 + value40, \\
        value41 + value42 + value43 + value44 + value45, \\
        value46 + value47 + value48 + value49 + value50 \\
   )
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
...  + value20, value21 + value22 + value23 + value24 + value25, @#$, value26 + value27 + value28 + value29 + value30, value ...
                                                                ^
''')


    def test_long_line_error_left(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
    reallyLongFunctionName( \\
        @#$, \\
        value1 + value2 + value3 + value4 + value5, \\
        value6 + value7 + value8 + value9 + value10, \\
        value11 + value12 + value13 + value14 + value15, \\
        value16 + value17 + value18 + value19 + value20, \\
        value21 + value22 + value23 + value24 + value25, \\
        value26 + value27 + value28 + value29 + value30, \\
        value31 + value32 + value33 + value34 + value35, \\
        value36 + value37 + value38 + value39 + value40, \\
        value41 + value42 + value43 + value44 + value45, \\
        value46 + value47 + value48 + value49 + value50 \\
   )
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
    reallyLongFunctionName( @#$, value1 + value2 + value3 + value4 + value5, value6 + value7 + value8 + value9 + value10 ...
                           ^
''')


    def test_long_line_error_right(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
    reallyLongFunctionName( \\
        value1 + value2 + value3 + value4 + value5, \\
        value6 + value7 + value8 + value9 + value10, \\
        value11 + value12 + value13 + value14 + value15, \\
        value16 + value17 + value18 + value19 + value20, \\
        value21 + value22 + value23 + value24 + value25, \\
        value26 + value27 + value28 + value29 + value30, \\
        value31 + value32 + value33 + value34 + value35, \\
        value36 + value37 + value38 + value39 + value40, \\
        value41 + value42 + value43 + value44 + value45, \\
        value46 + value47 + value48 + value49 + value50 \\
        @#$ \\
   )
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
... alue39 + value40, value41 + value42 + value43 + value44 + value45, value46 + value47 + value48 + value49 + value50 @#$ )
                                                                                                                      ^
''')


    def test_jumpif_statement(self):
        script_str = '''\
n = 10
i = 0
a = 0
b = 1

fib:
    jumpif (i >= n) fibend
    tmp = b
    b = a + b
    a = tmp
    i = i + 1
    jump fib
fibend:

return a
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'name': 'n', 'expr': {'number': 10}, 'lineNumber': 1}},
                {'expr': {'name': 'i', 'expr': {'number': 0}, 'lineNumber': 2}},
                {'expr': {'name': 'a', 'expr': {'number': 0}, 'lineNumber': 3}},
                {'expr': {'name': 'b', 'expr': {'number': 1}, 'lineNumber': 4}},
                {'label': {'name': 'fib', 'lineNumber': 6}},
                {
                    'jump': {
                        'label': 'fibend',
                        'expr': {'binary': {'op': '>=', 'left': {'variable': 'i'}, 'right': {'variable': 'n'}}},
                        'lineNumber': 7
                    }
                },
                {'expr': {'name': 'tmp', 'expr': {'variable': 'b'}, 'lineNumber': 8}},
                {
                    'expr': {
                        'name': 'b',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}},
                        'lineNumber': 9
                    }
                },
                {'expr': {'name': 'a', 'expr': {'variable': 'tmp'}, 'lineNumber': 10}},
                {
                    'expr': {
                        'name': 'i',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'i'}, 'right': {'number': 1}}},
                        'lineNumber': 11
                    }
                },
                {'jump': {'label': 'fib', 'lineNumber': 12}},
                {'label': {'name': 'fibend', 'lineNumber': 13}},
                {'return': {'expr': {'variable': 'a'}, 'lineNumber': 15}}
            ]
        })


    def test_function_statement(self):
        script_str = '''\
function addNumbers(a, b):
    return a + b
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'name': 'addNumbers',
                        'args': ['a', 'b'],
                        'statements': [
                            {
                                'return': {
                                    'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}},
                                    'lineNumber': 2
                                }
                            }
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_async_function_statement(self):
        script_str = '''\
async function fetchURL(url):
    return systemFetch(url)
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'fetchURL',
                        'args': ['url'],
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'systemFetch', 'args': [{'variable': 'url'}]}}, 'lineNumber': 2}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_function_statement_empty_return(self):
        script_str = '''\
function fetchURL(url):
    return
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'name': 'fetchURL',
                        'args': ['url'],
                        'statements': [
                            {'return': {'lineNumber': 2}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array(self):
        script_str = '''\
function argsCount(args...):
    return arrayLength(args)
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'name': 'argsCount',
                        'args': ['args'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': 'args'}]}}, 'lineNumber': 2}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array_no_args(self):
        script_str = '''\
function test(...):
    return 1
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'name': 'test',
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'number': 1}, 'lineNumber': 2}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array_spaces(self):
        script_str = '''\
function argsCount(args ... ):
    return arrayLength(args)
endfunction
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {
                    'function': {
                        'name': 'argsCount',
                        'args': ['args'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': 'args'}]}}, 'lineNumber': 2}}
                        ],
                        'lineNumber': 1
                    }
                }
            ]
        })


    def test_function_statement_missing_colon(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
function test()
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
function test()
        ^
''')


    def test_if_then_statement(self):
        script_str = '''\
if i > 0:
    a = 1
elif i < 0:
    a = 2
else:
    a = 3
endif
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 3}},
                {'label': {'name': '__bareScriptIf0', 'lineNumber': 3}},
                {'jump': {
                    'label': '__bareScriptIf1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '<', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 3
                }},
                {'expr': {'name': 'a', 'expr': {'number': 2}, 'lineNumber': 4}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 5}},
                {'label': {'name': '__bareScriptIf1', 'lineNumber': 5}},
                {'expr': {'name': 'a', 'expr': {'number': 3}, 'lineNumber': 6}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 7}}
            ]
        })


    def test_if_then_statement_only(self):
        script_str = '''\
if i > 0:
    a = 1
endif
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 3}}
            ]
        })


    def test_if_then_statement_if_else_if(self):
        script_str = '''\
if i > 0:
    a = 1
elif i < 0:
    a = 2
endif
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 3}},
                {'label': {'name': '__bareScriptIf0', 'lineNumber': 3}},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '<', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 3
                }},
                {'expr': {'name': 'a', 'expr': {'number': 2}, 'lineNumber': 4}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 5}}
            ]
        })


    def test_if_then_statement_if_else(self):
        script_str = '''\
if i > 0:
    a = 1
else:
    a = 2
endif
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}, 'lineNumber': 2}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 3}},
                {'label': {'name': '__bareScriptIf0', 'lineNumber': 3}},
                {'expr': {'name': 'a', 'expr': {'number': 2}, 'lineNumber': 4}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 5}}
            ]
        })


    def test_if_then_statement_error_else_if_outside_if_then(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
elif i < 0:
    a = 3
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: No matching if statement
elif i < 0:
^
''')


    def test_if_then_statement_error_else_if_outside_if_then_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
    elif i < 0:
        a = 3
    endif
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching if statement
    elif i < 0:
^
''')


    def test_if_then_statement_error_else_then_outside_if_then(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
else:
    a = 3
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: No matching if statement
else:
^
''')


    def test_if_then_statement_error_else_then_outside_if_then_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
    else:
        a = 3
    endif
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching if statement
    else:
^
''')


    def test_if_then_statement_error_endif_outside_if_then(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: No matching if statement
endif
^
''')


    def test_if_then_statement_error_endif_outside_if_then_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
    endif
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching if statement
    endif
^
''')


    def test_if_then_statement_error_else_if_after_else(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
    a = 1
else:
    a = 2
elif i < 0:
    a = 3
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:5: Elif statement following else statement
elif i < 0:
^
''')


    def test_if_then_statement_error_multiple_else(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
    a = 1
else:
    a = 2
else:
    a = 3
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:5: Multiple else statements
else:
^
''')


    def test_if_then_statement_error_no_endif(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Missing endif statement
if i > 0:
^
''')


    def test_if_then_statement_error_endif_outside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
function test():
    if i > 0:
endfunction
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Missing endif statement
    if i > 0:
^
''')


    def test_if_then_statement_error_endif_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
function test():
    endif
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: No matching if statement
    endif
^
''')


    def test_if_then_statement_error_elif_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
function test():
    elif i == 1:
    endif
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: No matching if statement
    elif i == 1:
^
''')


    def test_if_then_statement_error_else_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
function test():
    else:
    endif
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: No matching if statement
    else:
^
''')


    def test_if_then_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if @#$:
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
if @#$:
   ^
''')


    def test_if_then_statement_elif_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if true:
elif @#$:
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Syntax error
elif @#$:
     ^
''')


    def test_while_do_statement(self):
        script_str = '''\
i = 0
while i < arrayLength(values):
    i = i + 1
endwhile
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'name': 'i', 'expr': {'number': 0}, 'lineNumber': 1}},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {
                        'op': '!',
                        'expr': {'binary': {
                            'op': '<',
                            'left': {'variable': 'i'},
                            'right': {'function': {'name': 'arrayLength', 'args': [{'variable': 'values'}]}}
                        }}
                    }},
                    'lineNumber': 2
                }},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 2}},
                {'expr': {
                    'name': 'i',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'i'}, 'right': {'number': 1}}},
                    'lineNumber': 3
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {'binary': {
                        'op': '<',
                        'left': {'variable': 'i'},
                        'right': {'function': {'name': 'arrayLength', 'args': [{'variable': 'values'}]}}
                    }},
                    'lineNumber': 4
                }},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 4}}
            ]
        })


    def test_while_do_statement_break(self):
        script_str = '''\
while true:
    break
endwhile
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}}, 'lineNumber': 1}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 1}},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 2}},
                {'jump': {'label': '__bareScriptLoop0', 'expr': {'variable': 'true'}, 'lineNumber': 3}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 3}}
            ]
        })


    def test_while_do_statement_continue(self):
        script_str = '''\
while true:
    continue
endwhile
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}}, 'lineNumber': 1}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 1}},
                {'jump': {'label': '__bareScriptLoop0', 'lineNumber': 2}},
                {'jump': {'label': '__bareScriptLoop0', 'expr': {'variable': 'true'}, 'lineNumber': 3}},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 3}}
            ]
        })


    def test_while_do_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while @#$:
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
while @#$:
      ^
''')


    def test_while_do_statement_error_endwhile_outside_while_do(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: No matching while statement
endwhile
^
''')


    def test_while_do_statement_error_endwhile_outside_while_do_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching while statement
endwhile
^
''')


    def test_while_do_statement_error_no_endwhile(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Missing endwhile statement
while true:
^
''')


    def test_while_do_statement_error_endwhile_outside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
function test():
    while i > 0:
endfunction
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Missing endwhile statement
    while i > 0:
^
''')


    def test_while_do_statement_error_endwhile_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while i > 0:
function test():
    endwhile
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: No matching while statement
    endwhile
^
''')


    def test_while_do_statement_error_break_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while i > 0:
function test():
        break
    endwhile
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: Break statement outside of loop
        break
^
''')


    def test_while_do_statement_error_continue_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while i > 0:
function test():
        continue
    endwhile
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: Continue statement outside of loop
        continue
^
''')


    def test_foreach_statement(self):
        script_str = '''\
values = [1, 2, 3]
sum = 0
for value in values:
    sum = sum + value
endfor
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {
                    'name': 'values',
                    'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}, {'number': 3}]}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'sum', 'expr': {'number': 0}, 'lineNumber': 2}},
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}, 'lineNumber': 3}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}},
                    'lineNumber': 3
                }},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}},
                    'lineNumber': 3
                }},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}, 'lineNumber': 3}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 3}},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }},
                    'lineNumber': 3
                }},
                {'expr': {
                    'name': 'sum',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'sum'}, 'right': {'variable': 'value'}}},
                    'lineNumber': 4
                }},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}},
                    'lineNumber': 5
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    },
                    'lineNumber': 5
                }},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 5}}
            ]
        })


    def test_foreach_statement_with_index(self):
        script_str = '''\
for value, ixValue in values:
endfor
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}, 'lineNumber': 1}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}},
                    'lineNumber': 1
                }},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': 'ixValue', 'expr': {'number': 0}, 'lineNumber': 1}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 1}},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': 'ixValue'}]
                    }},
                    'lineNumber': 1
                }},
                {'expr': {
                    'name': 'ixValue',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'ixValue'}, 'right': {'number': 1}}},
                    'lineNumber': 2
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {'binary': {'op': '<', 'left': {'variable': 'ixValue'}, 'right': {'variable': '__bareScriptLength0'}}},
                    'lineNumber': 2
                }},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 2}}
            ]
        })


    def test_foreach_statement_break(self):
        script_str = '''\
for value in values:
    if i > 0:
        break
    endif
endfor
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}, 'lineNumber': 1}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}},
                    'lineNumber': 1
                }},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}, 'lineNumber': 1}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 1}},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }},
                    'lineNumber': 1
                }},
                {'jump': {
                    'label': '__bareScriptDone1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 2
                }},
                {'jump': {'label': '__bareScriptDone0', 'lineNumber': 3}},
                {'label': {'name': '__bareScriptDone1', 'lineNumber': 4}},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}},
                    'lineNumber': 5
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    },
                    'lineNumber': 5
                }},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 5}}
            ]
        })


    def test_foreach_statement_continue(self):
        script_str = '''\
for value in values:
    if i > 0:
        continue
    endif
endfor
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}, 'lineNumber': 1}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}},
                    'lineNumber': 1
                }},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}},
                    'lineNumber': 1
                }},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}, 'lineNumber': 1}},
                {'label': {'name': '__bareScriptLoop0', 'lineNumber': 1}},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }},
                    'lineNumber': 1
                }},
                {'jump': {
                    'label': '__bareScriptDone1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}},
                    'lineNumber': 2
                }},
                {'jump': {'label': '__bareScriptContinue0', 'lineNumber': 3}},
                {'label': {'name': '__bareScriptDone1', 'lineNumber': 4}},
                {'label': {'name': '__bareScriptContinue0', 'lineNumber': 5}},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}},
                    'lineNumber': 5
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    },
                    'lineNumber': 5
                }},
                {'label': {'name': '__bareScriptDone0', 'lineNumber': 5}}
            ]
        })


    def test_foreach_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in @#$:
endfor
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
for value in @#$:
             ^
''')


    def test_foreach_statement_error_foreach_outside_foreach(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endfor
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: No matching for statement
endfor
^
''')


    def test_foreach_statement_error_endfor_outside_foreach_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
endfor
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching for statement
endfor
^
''')


    def test_foreach_statement_error_no_endfor(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Missing endfor statement
for value in values:
^
''')


    def test_foreach_statement_error_endfor_outside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
function test():
    for value in values:
endfunction
endfor
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Missing endfor statement
    for value in values:
^
''')


    def test_foreach_statement_error_endfor_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
function test():
    endfor
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: No matching for statement
    endfor
^
''')


    def test_foreach_statement_error_break_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
function test():
        break
    endfor
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: Break statement outside of loop
        break
^
''')


    def test_foreach_statement_error_continue_inside_function(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
function test():
        continue
    endfor
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: Continue statement outside of loop
        continue
^
''')


    def test_break_statement_error_break_outside_loop(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
break
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Break statement outside of loop
break
^
''')


    def test_break_statement_error_break_outside_loop_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
    break
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Break statement outside of loop
    break
^
''')


    def test_continue_statement_error_continue_outside_loop(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
continue
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Continue statement outside of loop
continue
^
''')


    def test_continue_statement_error_continue_outside_loop_2(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
    continue
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Continue statement outside of loop
    continue
^
''')


    def test_include_statement(self):
        script_str = '''\
include 'fi\\'le.bare'
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'include': {'includes': [{'url': "fi'le.bare"}], 'lineNumber': 1}}
            ]
        })


    def test_include_statement_system(self):
        script_str = '''\
include <file.bare>
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'include': {'includes': [{'url': 'file.bare', 'system': True}], 'lineNumber': 1}}
            ]
        })


    def test_include_statement_double_quotes(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
include "file.bare"
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
include "file.bare"
       ^
''')
        self.assertEqual(cm_exc.exception.column_number, 8)
        self.assertEqual(cm_exc.exception.line_number, 1)


    def test_include_statement_multiple(self):
        script_str = '''\
include 'test.bare'
include <test2.bare>
include 'test3.bare'
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'include': {
                    'includes': [{'url': 'test.bare'}, {'url': 'test2.bare', 'system': True}, {'url': 'test3.bare'}],
                    'lineNumber': 1,
                    'lineCount': 3
                }}
            ]
        })


    def test_expression_statement(self):
        script_str = '''\
foo()
'''
        script = validate_script(parse_script(script_str))
        self.assertDictEqual(script, {
            'scriptLines': [*script_str.splitlines(), ''],
            'statements': [
                {'expr': {'expr': {'function': {'name': 'foo', 'args': []}}, 'lineNumber': 1}}
            ]
        })


    def test_expression_statement_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
a = 0
b = 1
foo \\
bar
c = 2
''')
        self.assertEqual(str(cm_exc.exception), '''\
:3: Syntax error
foo bar
   ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, 'foo bar')
        self.assertEqual(cm_exc.exception.column_number, 4)
        self.assertEqual(cm_exc.exception.line_number, 3)


    def test_assignment_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
a = 0
b = 1 + foo bar
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Syntax error
b = 1 + foo bar
           ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, 'b = 1 + foo bar')
        self.assertEqual(cm_exc.exception.column_number, 12)
        self.assertEqual(cm_exc.exception.line_number, 2)


    def test_jump_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
jumpif (@#$) label
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
jumpif (@#$) label
        ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, 'jumpif (@#$) label')
        self.assertEqual(cm_exc.exception.column_number, 9)
        self.assertEqual(cm_exc.exception.line_number, 1)


    def test_return_statement_expression_syntax_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
return @#$
''')
        self.assertEqual(str(cm_exc.exception), '''\
:1: Syntax error
return @#$
       ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, 'return @#$')
        self.assertEqual(cm_exc.exception.column_number, 8)
        self.assertEqual(cm_exc.exception.line_number, 1)


    def test_nested_function_statement_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
function foo():
    function bar():
    endfunction
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: Nested function definition
    function bar():
^
''')
        self.assertEqual(cm_exc.exception.error, 'Nested function definition')
        self.assertEqual(cm_exc.exception.line, '    function bar():')
        self.assertEqual(cm_exc.exception.column_number, 1)
        self.assertEqual(cm_exc.exception.line_number, 2)


    def test_endfunction_statement_error(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
a = 1
endfunction
''')
        self.assertEqual(str(cm_exc.exception), '''\
:2: No matching function definition
endfunction
^
''')
        self.assertEqual(cm_exc.exception.error, 'No matching function definition')
        self.assertEqual(cm_exc.exception.line, 'endfunction')
        self.assertEqual(cm_exc.exception.column_number, 1)
        self.assertEqual(cm_exc.exception.line_number, 2)


class TestParseExpression(unittest.TestCase):

    def test(self):
        expr = parse_expression('7 + 3 * 5')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {'number': 7},
                'right': {
                    'binary': {
                        'op': '*',
                        'left': {'number': 3},
                        'right': {'number': 5}
                    }
                }
            }
        })


    def test_array_literals(self):
        expr = parse_expression('[1, 2]')
        self.assertDictEqual(validate_expression(expr), {'variable': '1, 2'})

        expr = parse_expression('[1, 2]', array_literals=True)
        self.assertDictEqual(validate_expression(expr), {'function': {'args': [{'number': 1.0}, {'number': 2.0}], 'name': 'arrayNew'}})


    def test_unary(self):
        expr = parse_expression('!a')
        self.assertDictEqual(validate_expression(expr), {
            'unary': {
                'op': '!',
                'expr': {'variable': 'a'}
            }
        })

        # Bitwise NOT
        expr = parse_expression('~a')
        self.assertDictEqual(validate_expression(expr), {
            'unary': {
                'op': '~',
                'expr': {'variable': 'a'}
            }
        })


    def test_syntax_error(self):
        expr_text = ' @#$'
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_expression(expr_text)
        self.assertEqual(str(cm_exc.exception), f'''\
Syntax error
{expr_text}
^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, expr_text)
        self.assertEqual(cm_exc.exception.column_number, 1)
        self.assertIsNone(cm_exc.exception.line_number)


    def test_next_text_syntax_error(self):
        expr_text = 'foo bar'
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_expression(expr_text)
        self.assertEqual(str(cm_exc.exception), f'''\
Syntax error
{expr_text}
   ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, expr_text)
        self.assertEqual(cm_exc.exception.column_number, 4)
        self.assertIsNone(cm_exc.exception.line_number)


    def test_syntax_error_unmatched_parenthesis(self):
        expr_text = '10 * (1 + 2'
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_expression(expr_text)
        self.assertEqual(str(cm_exc.exception), f'''\
Unmatched parenthesis
{expr_text}
    ^
''')
        self.assertEqual(cm_exc.exception.error, 'Unmatched parenthesis')
        self.assertEqual(cm_exc.exception.line, expr_text)
        self.assertEqual(cm_exc.exception.column_number, 5)
        self.assertIsNone(cm_exc.exception.line_number)


    def test_function_argument_syntax_error(self):
        expr_text = 'foo(1, 2 3)'
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_expression(expr_text)
        self.assertEqual(str(cm_exc.exception), f'''\
Syntax error
{expr_text}
        ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, expr_text)
        self.assertEqual(cm_exc.exception.column_number, 9)
        self.assertIsNone(cm_exc.exception.line_number)


    def test_operator_precedence(self):
        expr = parse_expression('7 * 3 + 5')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {
                    'binary': {
                        'op': '*',
                        'left': {'number': 7},
                        'right': {'number': 3}
                    }
                },
                'right': {'number': 5}
            }
        })


    def test_operator_precedence_2(self):
        expr = parse_expression('2 * 3 + 4 - 1')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '-',
                'left': {
                    'binary': {
                        'op': '+',
                        'left': {
                            'binary': {
                                'op': '*',
                                'left': {'number': 2},
                                'right': {'number': 3}
                            }
                        },
                        'right': {'number': 4}
                    }
                },
                'right': {'number': 1}
            }
        })


    def test_operator_precedence_3(self):
        expr = parse_expression('2 + 3 + 4 - 1')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '-',
                'left': {
                    'binary': {
                        'op': '+',
                        'left': {
                            'binary': {
                                'op': '+',
                                'left': {'number': 2},
                                'right': {'number': 3}
                            }
                        },
                        'right': {'number': 4}
                    }
                },
                'right': {'number': 1}
            }
        })


    def test_operator_precedence_4(self):
        expr = parse_expression('1 - 2 + 3 + 4 + 5 * 6')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {
                    'binary': {
                        'op': '+',
                        'left': {
                            'binary': {
                                'op': '+',
                                'left': {
                                    'binary': {
                                        'op': '-',
                                        'left': {'number': 1},
                                        'right': {'number': 2}
                                    }
                                },
                                'right': {'number': 3}
                            }
                        },
                        'right': {'number': 4}
                    }
                },
                'right': {
                    'binary': {
                        'op': '*',
                        'left': {'number': 5},
                        'right': {'number': 6}
                    }
                }
            }
        })


    def test_operator_precedence_5(self):
        expr = parse_expression('1 + 2 * 5 / 2')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {'number': 1},
                'right': {
                    'binary': {
                        'op': '/',
                        'left': {
                            'binary': {
                                'op': '*',
                                'left': {'number': 2},
                                'right': {'number': 5}
                            }
                        },
                        'right': {'number': 2}
                    }
                }
            }
        })


    def test_operator_precedence_6(self):
        expr = parse_expression('1 + 2 / 5 * 2')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {'number': 1},
                'right': {
                    'binary': {
                        'op': '*',
                        'left': {
                            'binary': {
                                'op': '/',
                                'left': {'number': 2},
                                'right': {'number': 5}
                            }
                        },
                        'right': {'number': 2}
                    }
                }
            }
        })


    def test_operator_precedence_7(self):
        expr = parse_expression('1 + 2 / 3 / 4 * 5')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '+',
                'left': {'number': 1},
                'right': {
                    'binary': {
                        'op': '*',
                        'left': {
                            'binary': {
                                'op': '/',
                                'left': {
                                    'binary': {
                                        'op': '/',
                                        'left': {'number': 2},
                                        'right': {'number': 3}
                                    }
                                },
                                'right': {'number': 4}
                            }
                        },
                        'right': {'number': 5}
                    }
                }
            }
        })


    def test_operator_precedence_8(self):
        expr = parse_expression('1 >= 2 && 3 < 4 - 5')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '&&',
                'left': {
                    'binary': {
                        'op': '>=',
                        'left': {'number': 1},
                        'right': {'number': 2}
                    }
                },
                'right': {
                    'binary': {
                        'op': '<',
                        'left': {'number': 3},
                        'right': {
                            'binary': {
                                'op': '-',
                                'left': {'number': 4},
                                'right': {'number': 5}
                            }
                        }
                    }
                }
            }
        })


    def test_bitwise_operators(self):
        expr = parse_expression('1 & 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '&',
                'left': {'number': 1},
                'right': {'number': 3}
            }
        })

        expr = parse_expression('1 | 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '|',
                'left': {'number': 1},
                'right': {'number': 3}
            }
        })

        expr = parse_expression('1 ^ 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '^',
                'left': {'number': 1},
                'right': {'number': 3}
            }
        })

        expr = parse_expression('1 << 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '<<',
                'left': {'number': 1},
                'right': {'number': 3}
            }
        })

        expr = parse_expression('1 >> 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '>>',
                'left': {'number': 1},
                'right': {'number': 3}
            }
        })


    def test_bitwise_precedence(self):
        # Shift operators after additive, before relational
        expr = parse_expression('1 + 2 << 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '<<',
                'left': {
                    'binary': {
                        'op': '+',
                        'left': {'number': 1.0},
                        'right': {'number': 2.0}
                    }
                },
                'right': {'number': 3.0}
            }
        })

        # Bitwise after equality
        expr = parse_expression('1 == 2 & 3')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '&',
                'left': {
                    'binary': {
                        'op': '==',
                        'left': {'number': 1},
                        'right': {'number': 2}
                    }
                },
                'right': {'number': 3}
            }
        })

        # Bitwise AND before XOR and OR
        expr = parse_expression('1 & 2 ^ 3 | 4')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '|',
                'left': {
                    'binary': {
                        'op': '^',
                        'left': {
                            'binary': {
                                'op': '&',
                                'left': {'number': 1},
                                'right': {'number': 2}
                            }
                        },
                        'right': {'number': 3}
                    }
                },
                'right': {'number': 4}
            }
        })


    def test_group(self):
        expr = parse_expression('(7 + 3) * 5')
        self.assertDictEqual(validate_expression(expr), {
            'binary': {
                'op': '*',
                'left': {
                    'group': {
                        'binary': {
                            'op': '+',
                            'left': {'number': 7},
                            'right': {'number': 3}
                        }
                    }
                },
                'right': {'number': 5}
            }
        })


    def test_group_nested(self):
        expr = parse_expression('(1 + (2))')
        self.assertDictEqual(validate_expression(expr), {
            'group': {
                'binary': {
                    'op': '+',
                    'left': {'number': 1},
                    'right': {'group': {'number': 2}}
                }
            }
        })


    def test_number_literal(self):
        expr = parse_expression('1')
        self.assertDictEqual(validate_expression(expr), {'number': 1.0})
        expr = parse_expression('-1')
        self.assertDictEqual(validate_expression(expr), {'number': -1.0})

        expr = parse_expression('1.1')
        self.assertDictEqual(validate_expression(expr), {'number': 1.1})

        expr = parse_expression('-1.1')
        self.assertDictEqual(validate_expression(expr), {'number': -1.1})

        expr = parse_expression('1e3')
        self.assertDictEqual(validate_expression(expr), {'number': 1000})

        expr = parse_expression('1e+3')
        self.assertDictEqual(validate_expression(expr), {'number': 1000})

        expr = parse_expression('1e-3')
        self.assertDictEqual(validate_expression(expr), {'number': .001})

        expr = parse_expression('0x1fF')
        self.assertDictEqual(validate_expression(expr), {'number': 511})

        expr = parse_expression('0x20 + 0x01')
        self.assertDictEqual(validate_expression(expr), {'binary': {'op': '+', 'left': {'number': 32}, 'right': {'number': 1}}})


    def test_string_literal(self):
        expr = parse_expression("'abc'")
        self.assertDictEqual(validate_expression(expr), {'string': 'abc'})


    def test_string_literal_escapes(self):
        expr = parse_expression("'ab \\'c\\' d\\\\e \\\\f'")
        self.assertDictEqual(validate_expression(expr), {'string': "ab 'c' d\\e \\f"})

        # More
        expr = parse_expression('"\\n\\r\\t\\b\\f\\\\\'\\"\\\\"')
        self.assertDictEqual(validate_expression(expr), {'string': '\n\r\t\b\f\\\'"\\'})

        # Hex
        expr = parse_expression('"\\uD83D\\uDE00"')
        self.assertDictEqual(validate_expression(expr), {'string': '\ud83d\ude00'})

        # Escaped
        expr = parse_expression(
            '"Escape me: \\\\ \\[ \\] \\( \\) \\< \\> \\\\\\" \\\\\' \\* \\_ \\~ \\` \\# \\| \\-"'
        )
        self.assertDictEqual(
            validate_expression(expr),
            {'string': "Escape me: \\ \\[ \\] \\( \\) \\< \\> \\\" \\' \\* \\_ \\~ \\` \\# \\| \\-"}
        )


    def test_string_literal_backslash_end(self):
        expr = parse_expression("test('abc \\\\', 'def')")
        self.assertDictEqual(validate_expression(expr), {
            'function': {
                'name': 'test',
                'args': [{'string': 'abc \\'}, {'string': 'def'}]
            }
        })


    def test_string_literal_double_quote(self):
        expr = parse_expression('"abc"')
        self.assertDictEqual(validate_expression(expr), {'string': 'abc'})


    def test_string_literal_double_quote_escapes(self):
        expr = parse_expression('"ab \\"c\\" d\\\\e \\\\f"')
        self.assertDictEqual(validate_expression(expr), {'string': 'ab "c" d\\e \\f'})

        # More
        expr = parse_expression('"\\n\\r\\t\\b\\f\\\\\'\\"\\\\"')
        self.assertDictEqual(validate_expression(expr), {'string': '\n\r\t\b\f\\\'"\\'})

        # Hex
        expr = parse_expression('"\\uD83D\\uDE00"')
        self.assertDictEqual(validate_expression(expr), {'string': '\ud83d\ude00'})

        # Escaped
        expr = parse_expression(
            '"Escape me: \\\\ \\[ \\] \\( \\) \\< \\> \\\\\\" \\\\\' \\* \\_ \\~ \\` \\# \\| \\-"'
        )
        self.assertDictEqual(
            validate_expression(expr),
            {'string': "Escape me: \\ \\[ \\] \\( \\) \\< \\> \\\" \\' \\* \\_ \\~ \\` \\# \\| \\-"}
        )


    def test_string_literal_double_quote_backslash_end(self):
        expr = parse_expression('test("abc \\\\", "def")')
        self.assertDictEqual(validate_expression(expr), {
            'function': {
                'name': 'test',
                'args': [{'string': 'abc \\'}, {'string': 'def'}]
            }
        })
