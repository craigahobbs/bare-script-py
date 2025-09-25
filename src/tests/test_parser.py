# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from bare_script import BareScriptParserError, parse_expression, parse_script, validate_expression, validate_script


class TestParseScript(unittest.TestCase):

    def test_array_input(self):
        script = validate_script(parse_script([
            'a = arrayNew( \\',
            '    1,\\',
            '''\
    2 \\
)
'''
        ]))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}}
                    }
                }
            ]
        })


    def test_comments(self):
        script = validate_script(parse_script('''\
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

for num in arrayNew(1, 2, 3):  # Iterate numbers
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
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'include': {
                        'includes': [
                            {'url': 'args.bare', 'system': True},
                            {'url': 'util.bare'}
                        ]
                    }
                },
                {
                    'function': {
                        'name': 'main',
                        'statements': [
                            {'expr': {'expr': {'function': {'name': 'markdownPrint', 'args': [{'string': '# TODO'}]}}}},
                            {'return': {'expr': {'variable': 'true'}}}
                        ]
                    }
                },
                {'jump': {'label': 'label'}},
                {'label': 'label'},
                {
                    'jump': {
                        'label': '__bareScriptIf0',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'false'}}}
                    }
                },
                {'expr': {'name': 'ix', 'expr': {'number': 0.0}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf0'},
                {
                    'jump': {
                        'label': '__bareScriptIf1',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'false'}}}
                    }
                },
                {'expr': {'name': 'ix', 'expr': {'number': 1.0}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf1'},
                {'expr': {'name': 'ix', 'expr': {'number': 2.0}}},
                {'label': '__bareScriptDone0'},
                {
                    'expr': {
                        'name': '__bareScriptValues2',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1.0},{'number': 2.0},{'number': 3.0}]}}
                    }
                },
                {
                    'expr': {
                        'name': '__bareScriptLength2',
                        'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues2'}]}}
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptDone2',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength2'}}}
                    }
                },
                {'expr': {'name': '__bareScriptIndex2', 'expr': {'number': 0.0}}},
                {'label': '__bareScriptLoop2'},
                {
                    'expr': {
                        'name': 'num',
                        'expr': {
                            'function': {
                                'name': 'arrayGet',
                                'args': [{'variable': '__bareScriptValues2'}, {'variable': '__bareScriptIndex2'}]
                            }
                        }
                    }
                },
                {'expr': {'expr': {'function': {'name': 'systemLog', 'args': [{'variable': 'num'}]}}}},
                {
                    'expr': {
                        'name': '__bareScriptIndex2',
                        'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex2'},'right': {'number': 1.0}}}
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptLoop2',
                        'expr': {
                            'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex2'},'right': {'variable': '__bareScriptLength2'}}
                        }
                    }
                },
                {'label': '__bareScriptDone2'},
                {'expr': {'name': 'ix', 'expr': {'number': 0.0}}},
                {
                    'jump': {
                        'label': '__bareScriptDone3',
                        'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}}
                    }
                },
                {'label': '__bareScriptLoop3'},
                {
                    'jump': {
                        'label': '__bareScriptDone4',
                        'expr': {
                            'unary': {'op': '!', 'expr': {'binary': {'op': '==', 'left': {'variable': 'ix'},'right': {'number': 5.0}}}}
                        }
                    }
                },
                {'jump': {'label': '__bareScriptDone3'}},
                {'label': '__bareScriptDone4'},
                {
                    'expr': {
                        'name': 'ix',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'ix'},'right': {'number': 1.0}}}
                    }
                },
                {
                    'jump': {
                        'label': '__bareScriptDone5',
                        'expr': {
                            'unary': {'op': '!', 'expr': {'binary': {'op': '==', 'left': {'variable': 'ix'},'right': {'number': 3.0}}}}
                        }
                    }
                },
                {'jump': {'label': '__bareScriptLoop3'}},
                {'label': '__bareScriptDone5'},
                {'jump': {'label': '__bareScriptLoop3', 'expr': {'variable': 'true'}}},
                {'label': '__bareScriptDone3'},
                {'return': {}}
            ]
        })


    def test_line_continuation(self):
        script = validate_script(parse_script('''\
a = arrayNew( \\
    1, \\
    2 \\
 )
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}}
                    }
                }
            ]
        })


    def test_line_continuation_comments(self):
        script = validate_script(parse_script('''\
# Comments don't continue \\
a = arrayNew( \\
    # Comments are OK within a continuation...
    1, \\
    # ...with or without a continuation backslash \\
    2 \\
)
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'expr': {
                        'name': 'a',
                        'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}]}}
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
Syntax error, line number 1:
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
Syntax error, line number 1:
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
Syntax error, line number 1:
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
Syntax error, line number 1:
... alue39 + value40, value41 + value42 + value43 + value44 + value45, value46 + value47 + value48 + value49 + value50 @#$ )
                                                                                                                      ^
''')


    def test_jumpif_statement(self):
        script = validate_script(parse_script('''\
n = 10
i = 0
a = 0
b = 1

fib:
    jumpif (i >= [n]) fibend
    tmp = b
    b = a + b
    a = tmp
    i = i + 1
    jump fib
fibend:

return a
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'name': 'n', 'expr': {'number': 10}}},
                {'expr': {'name': 'i', 'expr': {'number': 0}}},
                {'expr': {'name': 'a', 'expr': {'number': 0}}},
                {'expr': {'name': 'b', 'expr': {'number': 1}}},
                {'label': 'fib'},
                {
                    'jump': {
                        'label': 'fibend',
                        'expr': {'binary': {'op': '>=', 'left': {'variable': 'i'}, 'right': {'variable': 'n'}}}
                    }
                },
                {'expr': {'name': 'tmp', 'expr': {'variable': 'b'}}},
                {
                    'expr': {
                        'name': 'b',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}
                    }
                },
                {'expr': {'name': 'a', 'expr': {'variable': 'tmp'}}},
                {
                    'expr': {
                        'name': 'i',
                        'expr': {'binary': {'op': '+', 'left': {'variable': 'i'}, 'right': {'number': 1}}}
                    }
                },
                {'jump': {'label': 'fib'}},
                {'label': 'fibend'},
                {'return': {'expr': {'variable': 'a'}}}
            ]
        })


    def test_function_statement(self):
        script = validate_script(parse_script('''\
function addNumbers(a, b):
    return a + b
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'name': 'addNumbers',
                        'args': ['a', 'b'],
                        'statements': [
                            {
                                'return': {
                                    'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}
                                }
                            }
                        ]
                    }
                }
            ]
        })


    def test_async_function_statement(self):
        script = validate_script(parse_script('''\
async function fetchURL(url):
    return systemFetch(url)
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'fetchURL',
                        'args': ['url'],
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'systemFetch', 'args': [{'variable': 'url'}]}}}}
                        ]
                    }
                }
            ]
        })


    def test_function_statement_empty_return(self):
        script = validate_script(parse_script('''\
function fetchURL(url):
    return
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'name': 'fetchURL',
                        'args': ['url'],
                        'statements': [
                            {'return': {}}
                        ]
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array(self):
        script = validate_script(parse_script('''\
function argsCount(args...):
    return arrayLength(args)
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'name': 'argsCount',
                        'args': ['args'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': 'args'}]}}}}
                        ]
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array_no_args(self):
        script = validate_script(parse_script('''\
function test(...):
    return 1
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'name': 'test',
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'number': 1}}}
                        ]
                    }
                }
            ]
        })


    def test_function_statement_last_arg_array_spaces(self):
        script = validate_script(parse_script('''\
function argsCount(args ... ):
    return arrayLength(args)
endfunction
'''))
        self.assertDictEqual(script, {
            'statements': [
                {
                    'function': {
                        'name': 'argsCount',
                        'args': ['args'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': 'args'}]}}}}
                        ]
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
Syntax error, line number 1:
function test()
        ^
''')


    def test_if_then_statement(self):
        script = validate_script(parse_script('''\
if i > 0:
    a = 1
elif i < 0:
    a = 2
else:
    a = 3
endif
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf0'},
                {'jump': {
                    'label': '__bareScriptIf1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '<', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}}
                 },
                {'expr': {'name': 'a', 'expr': {'number': 2}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf1'},
                {'expr': {'name': 'a', 'expr': {'number': 3}}},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_if_then_statement_only(self):
        script = validate_script(parse_script('''\
if i > 0:
    a = 1
endif
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}}},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_if_then_statement_if_else_if(self):
        script = validate_script(parse_script('''\
if i > 0:
    a = 1
elif i < 0:
    a = 2
endif
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf0'},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '<', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'expr': {'name': 'a', 'expr': {'number': 2}}},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_if_then_statement_if_else(self):
        script = validate_script(parse_script('''\
if i > 0:
    a = 1
else:
    a = 2
endif
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {
                    'label': '__bareScriptIf0',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'expr': {'name': 'a', 'expr': {'number': 1}}},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptIf0'},
                {'expr': {'name': 'a', 'expr': {'number': 2}}},
                {'label': '__bareScriptDone0'}
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
No matching if statement, line number 1:
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
No matching if statement, line number 2:
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
No matching if statement, line number 1:
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
No matching if statement, line number 2:
    else:
^
''')


    def test_if_then_statement_error_endif_outside_if_then(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endif
''')
        self.assertEqual(str(cm_exc.exception), '''\
No matching if statement, line number 1:
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
No matching if statement, line number 2:
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
Elif statement following else statement, line number 5:
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
Multiple else statements, line number 5:
else:
^
''')


    def test_if_then_statement_error_no_endif(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
if i > 0:
''')
        self.assertEqual(str(cm_exc.exception), '''\
Missing endif statement, line number 1:
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
Missing endif statement, line number 2:
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
No matching if statement, line number 3:
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
No matching if statement, line number 3:
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
No matching if statement, line number 3:
    else:
^
''')


    def test_while_do_statement(self):
        script = validate_script(parse_script('''\
i = 0
while i < arrayLength(values):
    i = i + 1
endwhile
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'name': 'i', 'expr': {'number': 0}}},
                {'jump': {
                    'label': '__bareScriptDone0',
                    'expr': {'unary': {
                        'op': '!',
                        'expr': {'binary': {
                            'op': '<',
                            'left': {'variable': 'i'},
                            'right': {'function': {'name': 'arrayLength', 'args': [{'variable': 'values'}]}}
                        }}
                    }}
                }},
                {'label': '__bareScriptLoop0'},
                {'expr': {'name': 'i', 'expr': {'binary': {'op': '+', 'left': {'variable': 'i'}, 'right': {'number': 1}}}}},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {'binary': {
                        'op': '<',
                        'left': {'variable': 'i'},
                        'right': {'function': {'name': 'arrayLength', 'args': [{'variable': 'values'}]}}
                    }}
                }},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_while_do_statement_break(self):
        script = validate_script(parse_script('''\
while true:
    break
endwhile
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}}}},
                {'label': '__bareScriptLoop0'},
                {'jump': {'label': '__bareScriptDone0'}},
                {'jump': {'label': '__bareScriptLoop0', 'expr': {'variable': 'true'}}},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_while_do_statement_continue(self):
        script = validate_script(parse_script('''\
while true:
    continue
endwhile
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': 'true'}}}}},
                {'label': '__bareScriptLoop0'},
                {'jump': {'label': '__bareScriptLoop0'}},
                {'jump': {'label': '__bareScriptLoop0', 'expr': {'variable': 'true'}}},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_while_do_statement_error_endwhile_outside_while_do(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endwhile
''')
        self.assertEqual(str(cm_exc.exception), '''\
No matching while statement, line number 1:
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
No matching while statement, line number 2:
endwhile
^
''')


    def test_while_do_statement_error_no_endwhile(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
while true:
''')
        self.assertEqual(str(cm_exc.exception), '''\
Missing endwhile statement, line number 1:
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
Missing endwhile statement, line number 2:
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
No matching while statement, line number 3:
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
Break statement outside of loop, line number 3:
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
Continue statement outside of loop, line number 3:
        continue
^
''')


    def test_foreach_statement(self):
        script = validate_script(parse_script('''\
values = arrayNew(1, 2, 3)
sum = 0
for value in values:
    sum = sum + value
endfor
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {
                    'name': 'values',
                    'expr': {'function': {'name': 'arrayNew', 'args': [{'number': 1}, {'number': 2}, {'number': 3}]}}
                }},
                {'expr': {'name': 'sum', 'expr': {'number': 0}}},
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}}
                }},
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}}}},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}}},
                {'label': '__bareScriptLoop0'},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }}
                }},
                {'expr': {
                    'name': 'sum',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'sum'}, 'right': {'variable': 'value'}}}
                }},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}}
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    }
                }},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_foreach_statement_with_index(self):
        script = validate_script(parse_script('''\
for value, ixValue in values:
endfor
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}}
                }},
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}}}},
                {'expr': {'name': 'ixValue', 'expr': {'number': 0}}},
                {'label': '__bareScriptLoop0'},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': 'ixValue'}]
                    }}
                }},
                {'expr': {
                    'name': 'ixValue',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'ixValue'}, 'right': {'number': 1}}}
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {'binary': {'op': '<', 'left': {'variable': 'ixValue'}, 'right': {'variable': '__bareScriptLength0'}}}
                }},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_foreach_statement_break(self):
        script = validate_script(parse_script('''\
for value in values:
    if i > 0:
        break
    endif
endfor
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}}
                }},
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}}}},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}}},
                {'label': '__bareScriptLoop0'},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }}
                }},
                {'jump': {
                    'label': '__bareScriptDone1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'jump': {'label': '__bareScriptDone0'}},
                {'label': '__bareScriptDone1'},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}}
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    }
                }},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_foreach_statement_continue(self):
        script = validate_script(parse_script('''\
for value in values:
    if i > 0:
        continue
    endif
endfor
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'name': '__bareScriptValues0', 'expr': {'variable': 'values'}}},
                {'expr': {
                    'name': '__bareScriptLength0',
                    'expr': {'function': {'name': 'arrayLength', 'args': [{'variable': '__bareScriptValues0'}]}}
                }},
                {'jump': {'label': '__bareScriptDone0', 'expr': {'unary': {'op': '!', 'expr': {'variable': '__bareScriptLength0'}}}}},
                {'expr': {'name': '__bareScriptIndex0', 'expr': {'number': 0}}},
                {'label': '__bareScriptLoop0'},
                {'expr': {
                    'name': 'value',
                    'expr': {'function': {
                        'name': 'arrayGet',
                        'args': [{'variable': '__bareScriptValues0'}, {'variable': '__bareScriptIndex0'}]
                    }}
                }},
                {'jump': {
                    'label': '__bareScriptDone1',
                    'expr': {'unary': {'op': '!', 'expr': {'binary': {'op': '>', 'left': {'variable': 'i'}, 'right': {'number': 0}}}}}
                }},
                {'jump': {'label': '__bareScriptContinue0'}},
                {'label': '__bareScriptDone1'},
                {'label': '__bareScriptContinue0'},
                {'expr': {
                    'name': '__bareScriptIndex0',
                    'expr': {'binary': {'op': '+', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'number': 1}}}
                }},
                {'jump': {
                    'label': '__bareScriptLoop0',
                    'expr': {
                        'binary': {'op': '<', 'left': {'variable': '__bareScriptIndex0'}, 'right': {'variable': '__bareScriptLength0'}}
                    }
                }},
                {'label': '__bareScriptDone0'}
            ]
        })


    def test_foreach_statement_error_foreach_outside_foreach(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
endfor
''')
        self.assertEqual(str(cm_exc.exception), '''\
No matching for statement, line number 1:
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
No matching for statement, line number 2:
endfor
^
''')


    def test_foreach_statement_error_no_endfor(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
for value in values:
''')
        self.assertEqual(str(cm_exc.exception), '''\
Missing endfor statement, line number 1:
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
Missing endfor statement, line number 2:
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
No matching for statement, line number 3:
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
Break statement outside of loop, line number 3:
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
Continue statement outside of loop, line number 3:
        continue
^
''')


    def test_break_statement_error_break_outside_loop(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
break
''')
        self.assertEqual(str(cm_exc.exception), '''\
Break statement outside of loop, line number 1:
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
Break statement outside of loop, line number 2:
    break
^
''')


    def test_continue_statement_error_continue_outside_loop(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
continue
''')
        self.assertEqual(str(cm_exc.exception), '''\
Continue statement outside of loop, line number 1:
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
Continue statement outside of loop, line number 2:
    continue
^
''')


    def test_include_statement(self):
        script = validate_script(parse_script('''\
include 'fi\\'le.bare'
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'include': {'includes': [{'url': "fi'le.bare"}]}}
            ]
        })


    def test_include_statement_system(self):
        script = validate_script(parse_script('''\
include <file.bare>
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'include': {'includes': [{'url': 'file.bare', 'system': True}]}}
            ]
        })


    def test_include_statement_double_quotes(self):
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_script('''\
include "file.bare"
''')
        self.assertEqual(str(cm_exc.exception), '''\
Syntax error, line number 1:
include "file.bare"
       ^
''')
        self.assertEqual(cm_exc.exception.column_number, 8)
        self.assertEqual(cm_exc.exception.line_number, 1)


    def test_include_statement_multiple(self):
        script = validate_script(parse_script('''\
include 'test.bare'
include <test2.bare>
include 'test3.bare'
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}, {'url': 'test2.bare', 'system': True}, {'url': 'test3.bare'}]}}
            ]
        })


    def test_expression_statement(self):
        script = validate_script(parse_script('''\
foo()
'''))
        self.assertDictEqual(script, {
            'statements': [
                {'expr': {'expr': {'function': {'name': 'foo', 'args': []}}}}
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
Syntax error, line number 3:
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
Syntax error, line number 2:
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
Syntax error, line number 1:
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
Syntax error, line number 1:
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
Nested function definition, line number 2:
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
No matching function definition, line number 2:
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
Syntax error:
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
Syntax error:
{expr_text}
   ^
''')
        self.assertEqual(cm_exc.exception.error, 'Syntax error')
        self.assertEqual(cm_exc.exception.line, expr_text)
        self.assertEqual(cm_exc.exception.column_number, 4
)
        self.assertIsNone(cm_exc.exception.line_number)


    def test_syntax_error_unmatched_parenthesis(self):
        expr_text = '10 * (1 + 2'
        with self.assertRaises(BareScriptParserError) as cm_exc:
            parse_expression(expr_text)
        self.assertEqual(str(cm_exc.exception), f'''\
Unmatched parenthesis:
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
Syntax error:
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


    def test_string_literal(self):
        expr = parse_expression("'abc'")
        self.assertDictEqual(validate_expression(expr), {'string': 'abc'})


    def test_string_literal_escapes(self):
        expr = parse_expression("'ab \\'c\\' d\\\\e \\f'")
        self.assertDictEqual(validate_expression(expr), {'string': "ab 'c' d\\e \\f"})


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
        expr = parse_expression('"ab \\"c\\" d\\\\e \\f"')
        self.assertDictEqual(validate_expression(expr), {'string': 'ab "c" d\\e \\f'})


    def test_string_literal_double_quote_backslash_end(self):
        expr = parse_expression('test("abc \\\\", "def")')
        self.assertDictEqual(validate_expression(expr), {
            'function': {
                'name': 'test',
                'args': [{'string': 'abc \\'}, {'string': 'def'}]
            }
        })
