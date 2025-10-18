# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import datetime
import os
import unittest

from bare_script import BareScriptParserError, BareScriptRuntimeError, evaluate_expression, execute_script, \
    validate_expression, validate_script
from bare_script.library import COVERAGE_GLOBAL_NAME
from bare_script.value import ValueArgsError


class TestExecuteScript(unittest.TestCase):

    def test_execute_script(self):
        script = validate_script({
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}}},
                {'expr': {'name': 'b', 'expr': {'number': 7}}},
                {'return': {
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}
                }}
            ]
        })
        self.assertEqual(execute_script(script), 12)


    def test_execute_script_global_override(self):
        script = validate_script({
            'statements': [
                {'return': {
                    'expr': {'function': {'name': 'systemFetch', 'args': [{'string': 'the-url'}]}}
                }}
            ]
        })
        options = {
            'globals': {
                'systemFetch': lambda args, unused_options: f'Hello, {args[0]}!'
            }
        }
        self.assertEqual(execute_script(script, options), 'Hello, the-url!')


    def test_execute_script_coverage(self):
        script = validate_script({
            'scriptName': 'test.bare',
            'scriptLines': [
                'function main():',
                '    jump label',
                '    label:',
                '',
                '    if false:',
                '        ix = 0',
                '    elif false:',
                '        ix = 1',
                '    else:',
                '        ix = 2',
                '    endif',
                '',
                '    for num in [1, 2, 3]:',
                '        systemLog(num)',
                '    endfor  # Numbers ',
                '',
                '    ix = 0',
                '    while true:',
                '        if ix == 5:',
                '            break',
                '        endif',
                '        ix = ix + 1',
                '        if ix == 3:',
                '            continue',
                '        endif',
                '    endwhile',
                '',
                '    return true',
                'endfunction',
                '',
                'return main()'
            ],
            'statements': [
                {'function': {
                    'name': 'main',
                    'lineNumber': 1,
                    'statements': [
                        {'jump': {'label': 'label', 'lineNumber': 2}},
                        {'label': {'lineNumber': 3, 'name': 'label'}},
                        {'jump': {
                            'expr': {'unary': {'expr': {'variable': 'false'}, 'op': '!'}},
                            'label': '__bareScriptIf0',
                            'lineNumber': 5
                        }},
                        {'expr': {'expr': {'number': 0.0}, 'lineNumber': 6, 'name': 'ix'}},
                        {'jump': {'label': '__bareScriptDone0', 'lineNumber': 7}},
                        {'label': {'lineNumber': 7, 'name': '__bareScriptIf0'}},
                        {'jump': {
                            'expr': {'unary': {'expr': {'variable': 'false'},'op': '!'}},
                            'label': '__bareScriptIf1',
                            'lineNumber': 7
                        }},
                        {'expr': {'expr': {'number': 1.0}, 'lineNumber': 8, 'name': 'ix'}},
                        {'jump': {'label': '__bareScriptDone0', 'lineNumber': 9}},
                        {'label': {'lineNumber': 9, 'name': '__bareScriptIf1'}},
                        {'expr': {'expr': {'number': 2.0}, 'lineNumber': 10, 'name': 'ix'}},
                        {'label': {'lineNumber': 11, 'name': '__bareScriptDone0'}},
                        {'expr': {
                            'expr': {'function': {'args': [{'number': 1.0}, {'number': 2.0}, {'number': 3.0}], 'name': 'arrayNew'}},
                            'lineNumber': 13,
                            'name': '__bareScriptValues2'
                        }},
                        {'expr': {
                            'expr': {'function': {'args': [{'variable': '__bareScriptValues2'}], 'name': 'arrayLength'}},
                            'lineNumber': 13,
                            'name': '__bareScriptLength2'
                        }},
                        {'jump': {
                            'expr': {'unary': {'expr': {'variable': '__bareScriptLength2'}, 'op': '!'}},
                            'label': '__bareScriptDone2',
                            'lineNumber': 13
                        }},
                        {'expr': {'expr': {'number': 0.0}, 'lineNumber': 13, 'name': '__bareScriptIndex2'}},
                        {'label': {'lineNumber': 13, 'name': '__bareScriptLoop2'}},
                        {'expr': {
                            'expr': {
                                'function': {
                                    'args': [{'variable': '__bareScriptValues2'}, {'variable': '__bareScriptIndex2'}],
                                    'name': 'arrayGet'
                                }
                            },
                            'lineNumber': 13,
                            'name': 'num'
                        }},
                        {'expr': {'expr': {'function': {'args': [{'variable': 'num'}], 'name': 'systemLog'}}, 'lineNumber': 14}},
                        {'expr': {
                            'expr': {'binary': {'left': {'variable': '__bareScriptIndex2'}, 'op': '+', 'right': {'number': 1.0}}},
                            'lineNumber': 15,
                            'name': '__bareScriptIndex2'
                        }},
                        {'jump': {
                            'expr': {
                                'binary': {
                                    'left': {'variable': '__bareScriptIndex2'},
                                    'op': '<',
                                    'right': {'variable': '__bareScriptLength2'}}
                            },
                            'label': '__bareScriptLoop2',
                            'lineNumber': 15
                        }},
                        {'label': {'lineNumber': 15, 'name': '__bareScriptDone2'}},
                        {'expr': {'expr': {'number': 0.0}, 'lineNumber': 17, 'name': 'ix'}},
                        {'jump': {
                            'expr': {'unary': {'expr': {'variable': 'true'}, 'op': '!'}},
                            'label': '__bareScriptDone3',
                            'lineNumber': 18
                        }},
                        {'label': {'lineNumber': 18, 'name': '__bareScriptLoop3'}},
                        {'jump': {
                            'expr': {
                                'unary': {
                                    'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '==', 'right': {'number': 5.0}}},
                                    'op': '!'
                                }},
                            'label': '__bareScriptDone4',
                            'lineNumber': 19
                        }},
                        {'jump': {'label': '__bareScriptDone3', 'lineNumber': 20}},
                        {'label': {'lineNumber': 21, 'name': '__bareScriptDone4'}},
                        {'expr': {
                            'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '+', 'right': {'number': 1.0}}},
                            'lineNumber': 22,
                            'name': 'ix'
                        }},
                        {'jump': {
                            'expr': {
                                'unary': {
                                    'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '==', 'right': {'number': 3.0}}},
                                    'op': '!'
                                }
                            },
                            'label': '__bareScriptDone5',
                            'lineNumber': 23
                        }},
                        {'jump': {'label': '__bareScriptLoop3', 'lineNumber': 24}},
                        {'label': {'lineNumber': 25, 'name': '__bareScriptDone5'}},
                        {'jump': {'expr': {'variable': 'true'}, 'label': '__bareScriptLoop3', 'lineNumber': 26}},
                        {'label': {'lineNumber': 26, 'name': '__bareScriptDone3'}},
                        {'return': {'expr': {'variable': 'true'}, 'lineNumber': 28}}
                    ]
                }},
                {'return': {'expr': {'function': {'args': [], 'name': 'main'}}, 'lineNumber': 31}}
            ]
        })
        options = {'globals': {COVERAGE_GLOBAL_NAME: {'enabled': True}}}
        self.assertEqual(execute_script(script, options), True)
        main_statement = script['statements'][0]
        self.assertDictEqual(options['globals'][COVERAGE_GLOBAL_NAME], {
            'enabled': True,
            'scripts': {
                'test.bare': {
                    'script': script,
                    'covered': {
                        '1': {'count': 1, 'statement': main_statement},
                        '2': {'count': 1, 'statement': {'jump': {'label': 'label', 'lineNumber': 2}}},
                        '3': {'count': 1, 'statement': {'label': {'lineNumber': 3, 'name': 'label'}}},
                        '5': {'count': 1, 'statement': {'jump': {
                            'expr': {'unary': {'expr': {'variable': 'false'}, 'op': '!'}},
                            'label': '__bareScriptIf0',
                            'lineNumber': 5
                        }}},
                        '7': {'count': 2, 'statement': {'label': {'lineNumber': 7, 'name': '__bareScriptIf0'}}},
                        '9': {'count': 1, 'statement': {'label': {'lineNumber': 9, 'name': '__bareScriptIf1'}}},
                        '10': {'count': 1, 'statement': {'expr': {'expr': {'number': 2.0}, 'lineNumber': 10, 'name': 'ix'}}},
                        '11': {'count': 1, 'statement': {'label': {'lineNumber': 11, 'name': '__bareScriptDone0'}}},
                        '13': {'count': 10, 'statement': {'expr': {
                            'expr': {'function': {'args': [{'number': 1.0}, {'number': 2.0}, {'number': 3.0}], 'name': 'arrayNew'}},
                            'lineNumber': 13,
                            'name': '__bareScriptValues2'
                        }}},
                        '14': {'count': 3, 'statement': {'expr': {
                            'expr': {'function': {'args': [{'variable': 'num'}], 'name': 'systemLog'}},
                            'lineNumber': 14
                        }}},
                        '15': {'count': 7, 'statement': {'expr': {
                            'expr': {'binary': {'left': {'variable': '__bareScriptIndex2'}, 'op': '+', 'right': {'number': 1.0}}},
                            'lineNumber': 15,
                            'name': '__bareScriptIndex2'
                        }}},
                        '17': {'count': 1, 'statement': {'expr': {'expr': {'number': 0.0}, 'lineNumber': 17, 'name': 'ix'}}},
                        '18': {'count': 7, 'statement': {'jump': {
                            'expr': {'unary': {'expr': {'variable': 'true'}, 'op': '!'}},
                            'label': '__bareScriptDone3',
                            'lineNumber': 18
                        }}},
                        '19': {'count': 6, 'statement': {'jump': {
                            'expr': {'unary': {
                                'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '==', 'right': {'number': 5.0}}},
                                'op': '!'
                            }},
                            'label': '__bareScriptDone4',
                            'lineNumber': 19
                        }}},
                        '20': {'count': 1, 'statement': {'jump': {'label': '__bareScriptDone3', 'lineNumber': 20}}},
                        '21': {'count': 5, 'statement': {'label': {'lineNumber': 21, 'name': '__bareScriptDone4'}}},
                        '22': {'count': 5, 'statement': {'expr': {
                            'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '+', 'right': {'number': 1.0}}},
                            'lineNumber': 22,
                            'name': 'ix'
                        }}},
                        '23': {'count': 5, 'statement': {'jump': {
                            'expr': {'unary': {
                                'expr': {'binary': {'left': {'variable': 'ix'}, 'op': '==', 'right': {'number': 3.0}}},
                                'op': '!'
                            }},
                            'label': '__bareScriptDone5',
                            'lineNumber': 23
                        }}},
                        '24': {'count': 1, 'statement': {'jump': {'label': '__bareScriptLoop3', 'lineNumber': 24}}},
                        '25': {'count': 4, 'statement': {'label': {'lineNumber': 25, 'name': '__bareScriptDone5'}}},
                        '26': {'count': 5, 'statement': {'jump': {
                            'expr': {'variable': 'true'},
                            'label': '__bareScriptLoop3',
                            'lineNumber': 26
                        }}},
                        '28': {'count': 1, 'statement': {'return': {'expr': {'variable': 'true'}, 'lineNumber': 28}}},
                        '31': {'count': 1, 'statement': {'return': {'expr': {'function': {'args': [], 'name': 'main'}}, 'lineNumber': 31}}}
                    }
                }
            }
        })


    def test_execute_script_coverage_include(self):
        def fetch_fn(request):
            url = request['url']
            if url == os.path.join('system', 'sysutil.bare'):
                return 'a = 1'
            self.assertEqual(url, 'util.bare')
            return 'b = 2'

        script = validate_script({
            'scriptName': 'test.bare',
            'scriptLines': [
                'include <sysutil.bare>',
                '',
                "include 'util.bare'"
            ],
            'statements': [
                {'include': {'includes': [{'url': 'sysutil.bare', 'system': True}], 'lineNumber': 1}},
                {'include': {'includes': [{'url': 'util.bare'}], 'lineNumber': 3}}
            ]
        })
        options = {
            'globals': {COVERAGE_GLOBAL_NAME: {'enabled': True}},
            'fetchFn': fetch_fn,
            'systemPrefix': 'system' + os.sep
        }
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)
        self.assertDictEqual(options['globals'][COVERAGE_GLOBAL_NAME], {
            'enabled': True,
            'scripts': {
                'test.bare': {
                    'script': script,
                    'covered': {
                        '1': {
                            'statement': {'include': {'lineNumber': 1, 'includes': [ {'url': 'sysutil.bare', 'system': True}]}},
                            'count': 1
                        },
                        '3': {
                            'statement': {'include': {'lineNumber': 3, 'includes': [ {'url': 'util.bare'}]}},
                            'count': 1
                        }
                    }
                },
                'util.bare': {
                    'script': {
                        'statements': [
                            {'expr': {'name': 'b', 'expr': {'number': 2.0}, 'lineNumber': 1}}
                        ],
                        'scriptLines': [
                            'b = 2'
                        ],
                        'scriptName': 'util.bare'
                    },
                    'covered': {
                        '1': {
                            'statement': {'expr': {'name': 'b', 'expr': {'number': 2.0}, 'lineNumber': 1}},
                            'count': 1
                        }
                    }
                }
            }
        })


    def test_execute_script_coverage_disabled(self):
        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, os.path.join('system', 'sysutil.bare'))
            return 'b = 7'

        script = validate_script({
            'scriptName': 'test.bare',
            'scriptLines': [
                'include <sysutil.bare>',
                'a = 5',
                'return a + b'
            ],
            'statements': [
                {'include': {'includes': [{'url': 'sysutil.bare', 'system': True}], 'lineNumber': 1}},
                {'expr': {'name': 'a', 'expr': {'number': 5}, 'lineNumber': 2}},
                {'expr': {'name': 'b', 'expr': {'number': 7}, 'lineNumber': 3}},
                {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}, 'lineNumber': 4}}
            ]
        })
        options = {
            'globals': {COVERAGE_GLOBAL_NAME: {'enabled': False}},
            'fetchFn': fetch_fn,
            'systemPrefix': 'system' + os.sep
        }
        self.assertEqual(execute_script(script, options), 12)
        self.assertDictEqual(options['globals'][COVERAGE_GLOBAL_NAME], {'enabled': False})


    def test_execute_script_coverage_non_object(self):
        script = validate_script({
            'scriptName': 'test.bare',
            'scriptLines': [
                'a = 5',
                'b = 7',
                'return a + b'
            ],
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}, 'lineNumber': 1}},
                {'expr': {'name': 'b', 'expr': {'number': 7}, 'lineNumber': 2}},
                {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}, 'lineNumber': 3}}
            ]
        })
        options = {'globals': {COVERAGE_GLOBAL_NAME: 42}}
        self.assertEqual(execute_script(script, options), 12)
        self.assertEqual(options['globals'][COVERAGE_GLOBAL_NAME], 42)


    def test_execute_script_coverage_no_name(self):
        script = validate_script({
            'scriptLines': [
                'a = 5',
                'b = 7',
                'return a + b'
            ],
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}, 'lineNumber': 1}},
                {'expr': {'name': 'b', 'expr': {'number': 7}, 'lineNumber': 2}},
                {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}, 'lineNumber': 3}}
            ]
        })
        options = {'globals': {COVERAGE_GLOBAL_NAME: {'enabled': True}}}
        self.assertEqual(execute_script(script, options), 12)
        self.assertDictEqual(options['globals'][COVERAGE_GLOBAL_NAME], {'enabled': True})


    def test_execute_script_coverage_no_linenos(self):
        script = validate_script({
            'scriptName': 'test.bare',
            'scriptLines': [
                'a = 5',
                'b = 7',
                'return a + b'
            ],
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}}},
                {'expr': {'name': 'b', 'expr': {'number': 7}}},
                {'return': {'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}}}
            ]
        })
        options = {'globals': {COVERAGE_GLOBAL_NAME: {'enabled': True}}}
        self.assertEqual(execute_script(script, options), 12)
        self.assertDictEqual(options['globals'][COVERAGE_GLOBAL_NAME], {'enabled': True})


    def test_function(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'multiplyNumbers',
                        'args': ['a', 'b'],
                        'statements': [
                            {'expr': {'name': 'c', 'expr': {'variable': 'b'}}},
                            {'return': {
                                'expr': {'binary': {'op': '*', 'left': {'variable': 'a'}, 'right': {'variable': 'c'}}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'multiplyNumbers', 'args': [{'number': 5}, {'number': 7}]}}
                }}
            ]
        })
        self.assertEqual(execute_script(script), 35)


    def test_function_missing_arg(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'createPair',
                        'args': ['a', 'b'],
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'createPair', 'args': [{'number': 5}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [5, None])


    def test_function_last_arg_array(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'test',
                        'args': ['a', 'b'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'test', 'args': [{'number': 1}, {'number': 2}, {'number': 3}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [1, [2, 3]])


    def test_function_last_arg_array_missing(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'test',
                        'args': ['a', 'b'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'test', 'args': [{'number': 1}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [1, []])


    def test_function_async(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'multiplyNumbers',
                        'args': ['a', 'b'],
                        'statements': [
                            {'expr': {'name': 'c', 'expr': {'variable': 'b'}}},
                            {'return': {
                                'expr': {'binary': {'op': '*', 'left': {'variable': 'a'}, 'right': {'variable': 'c'}}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'multiplyNumbers', 'args': [{'number': 5}, {'number': 7}]}}
                }}
            ]
        })
        self.assertEqual(execute_script(script), 35)


    def test_function_async_missing_arg(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'createPair',
                        'args': ['a', 'b'],
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'createPair', 'args': [{'number': 5}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [5, None])


    def test_function_async_last_arg_array(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'test',
                        'args': ['a', 'b'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'test', 'args': [{'number': 1}, {'number': 2}, {'number': 3}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [1, [2, 3]])


    def test_function_async_last_arg_array_missing(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'async': True,
                        'name': 'test',
                        'args': ['a', 'b'],
                        'lastArgArray': True,
                        'statements': [
                            {'return': {
                                'expr': {'function': {'name': 'arrayNew', 'args': [{'variable': 'a'}, {'variable': 'b'}]}}
                            }}
                        ]
                    }
                },
                {'return': {
                    'expr': {'function': {'name': 'test', 'args': [{'number': 1}]}}
                }}
            ]
        })
        self.assertListEqual(execute_script(script), [1, []])


    def test_function_error(self):
        script = validate_script({
            'statements': [
                {'return': {
                    'expr': {'function': {'name': 'errorFunction'}}
                }}
            ]
        })

        def error_function(unused_args, unused_options):
            raise ValueError('unexpected error')

        options = {'globals': {'errorFunction': error_function}}
        self.assertIsNone(execute_script(script, options))


    def test_function_argument_error(self):
        script = validate_script({
            'statements': [
                {'return': {
                    'expr': {'function': {'name': 'errorFunction'}}
                }}
            ]
        })

        def error_function(unused_args, unused_options):
            raise ValueArgsError('myArg', None, -1)

        options = {'globals': {'errorFunction': error_function}}
        self.assertEqual(execute_script(script, options), -1)


    def test_function_error_log(self):
        script = validate_script({
            'statements': [
                {'return': {
                    'expr': {'function': {'name': 'errorFunction'}}
                }}
            ]
        })

        def error_function(unused_args, unused_options):
            raise ValueError('unexpected error')

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'globals': {'errorFunction': error_function}, 'logFn': log_fn, 'debug': True}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, ['BareScript: Function "errorFunction" failed with error: unexpected error'])


    def test_function_error_log_no_debug(self):
        script = validate_script({
            'statements': [
                {'return': {
                    'expr': {'function': {'name': 'errorFunction'}}
                }}
            ]
        })

        def error_function(unused_args, unused_options):
            raise ValueError('unexpected error')

        logs = []
        def log_fn(message):
            logs.append(message)
        log_fn('empty')

        options = {'globals': {'errorFunction': error_function}, 'logFn': log_fn, 'debug': False}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, ['empty'])


    def test_function_native_call(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'multiplyNumbers',
                        'args': ['a', 'b'],
                        'statements': [
                            {'expr': {'name': 'c', 'expr': {'variable': 'b'}}},
                            {'return': {
                                'expr': {'binary': {'op': '*', 'left': {'variable': 'a'}, 'right': {'variable': 'c'}}}
                            }}
                        ]
                    }
                }
            ]
        })
        globals_ = {}
        execute_script(script, {'globals': globals_})
        options = {'globals': globals_}
        self.assertEqual(globals_['multiplyNumbers']([2, 3], options), 6)
        self.assertEqual(options['statementCount'], 2)


    def test_jump(self):
        script = validate_script({
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}}},
                {'jump': {'label': 'lab2'}},
                {'label': {'name': 'lab'}},
                {'expr': {'name': 'a', 'expr': {'number': 6}}},
                {'jump': {'label': 'lab3'}},
                {'label': {'name': 'lab2'}},
                {'expr': {'name': 'a', 'expr': {'number': 7}}},
                {'jump': {'label': 'lab'}},
                {'label': {'name': 'lab3'}},
                {'return': {'expr': {'variable': 'a'}}}
            ]
        })
        self.assertEqual(execute_script(script), 6)


    def test_jumpif(self):
        script = validate_script({
            'statements': [
                {'expr': {'name': 'n', 'expr': {'number': 10}}},
                {'expr': {'name': 'i', 'expr': {'number': 0}}},
                {'expr': {'name': 'a', 'expr': {'number': 0}}},
                {'expr': {'name': 'b', 'expr': {'number': 1}}},
                {'label': {'name': 'fib'}},
                {'jump': {
                    'label': 'fibend',
                    'expr': {'binary': {'op': '>=', 'left': {'variable': 'i'}, 'right': {'variable': 'n'}}}
                }},
                {'expr': {'name': 'tmp', 'expr': {'variable': 'b'}}},
                {'expr': {
                    'name': 'b',
                    'expr': {'binary': {'op': '+', 'left': {'variable': 'a'}, 'right': {'variable': 'b'}}}
                }},
                {'expr': {'name': 'a', 'expr': {'variable': 'tmp'}}},
                {'expr': {'name': 'i', 'expr': {'binary': {'op': '+', 'left': {'variable': 'i'}, 'right': {'number': 1}}}}},
                {'jump': {'label': 'fib'}},
                {'label': {'name': 'fibend'}},
                {'return': {'expr': {'variable': 'a'}}}
            ]
        })
        self.assertEqual(execute_script(script), 55)


    def test_jump_error_unknown_label(self):
        script = validate_script({
            'statements': [
                {'jump': {'label': 'unknownLabel'}}
            ]
        })
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            execute_script(script)
        self.assertEqual(str(cm_exc.exception), 'Unknown jump label "unknownLabel"')


    def test_jump_error_unknown_label_script_name(self):
        script = validate_script({
            'scriptName': 'test.bare',
            'statements': [
                {'jump': {'label': 'unknownLabel', 'lineNumber': 1}}
            ]
        })
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            execute_script(script)
        self.assertEqual(str(cm_exc.exception), 'test.bare:1: Unknown jump label "unknownLabel"')


    def test_return(self):
        script = validate_script({
            'statements': [
                {'return': {'expr': {'number': 5}}}
            ]
        })
        self.assertEqual(execute_script(script), 5)


    def test_return_blank(self):
        script = validate_script({
            'statements': [
                {'return': {}}
            ]
        })
        self.assertIsNone(execute_script(script))


    def test_include(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.bare', 'test2.bare'), True)
            return 'b = 2' if url == 'test2.bare' else '''\
include 'test2.bare'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_no_fetch_fn(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        options = {}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            self.assertIsNone(execute_script(script, options))
        self.assertEqual(str(cm_exc.exception), 'Include of "test.bare" failed')


    def test_include_system(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare', 'system': True}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, os.path.join('system', 'test.bare'))
            return 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn, 'systemPrefix': 'system' + os.sep}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)


    def test_include_system_no_prefix(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare', 'system': True}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            return 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)


    def test_include_multiple(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare', 'system': True}, {'url': 'test2.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.bare', 'test2.bare'), True)
            return 'b = a + 1' if url.endswith('test2.bare') else 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_subdir(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'lib/test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('lib/test.bare', os.path.join('lib', 'test2.bare')), True)
            return 'b = 2' if url.endswith('test2.bare') else '''\
include 'test2.bare'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_absolute(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.bare', 'http://foo.local/test2.bare'), True)
            return 'b = 2' if url.endswith('test2.bare') else '''\
include 'http://foo.local/test2.bare'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_lint(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            return '''\
function test(a):
endfunction
'''

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'debug': True, 'globals': {}, 'fetchFn': fetch_fn, 'logFn': log_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, [
            'BareScript: Include "test.bare" static analysis... 1 warning:',
            'BareScript:     Unused argument "a" of function "test" (index 0)'
        ])


    def test_include_lint_multiple(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            return '''\
function test(a, b):
endfunction
'''

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'debug': True, 'globals': {}, 'fetchFn': fetch_fn, 'logFn': log_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, [
            'BareScript: Include "test.bare" static analysis... 2 warnings:',
            'BareScript:     Unused argument "a" of function "test" (index 0)',
            'BareScript:     Unused argument "b" of function "test" (index 0)'
        ])


    def test_include_lint_ok(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            return '''\
function test():
endfunction
'''

        logs = []
        def log_fn(message):
            logs.append(message)
        log_fn('empty')

        options = {'debug': True, 'globals': {}, 'fetchFn': fetch_fn, 'logFn': log_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, ['empty'])


    def test_include_fetch_fn_error(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            raise Exception('response error')

        options = {'fetchFn': fetch_fn}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            execute_script(script, options)
        self.assertEqual(str(cm_exc.exception), 'Include of "test.bare" failed')


    def test_include_parser_error(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.bare'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.bare')
            return 'foo bar'

        options = {'fetchFn': fetch_fn}
        with self.assertRaises(BareScriptParserError) as cm_exc:
            execute_script(script, options)
        self.assertEqual(str(cm_exc.exception), '''\
test.bare:1: Syntax error
foo bar
   ^
''')


    def test_error_max_statements(self):
        script = validate_script({
            'statements': [
                {
                    'function': {
                        'name': 'fn',
                        'statements': [
                            {'expr': {'expr': {'variable': 'a'}}},
                            {'expr': {'expr': {'variable': 'b'}}}
                        ]
                    }
                },
                {'expr': {'expr': {'function': {'name': 'fn'}}}}
            ]
        })
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            execute_script(script, {'maxStatements': 3})
        self.assertEqual(str(cm_exc.exception), 'Exceeded maximum script statements (3)')
        self.assertIsNone(execute_script(script, {'maxStatements': 4}))
        self.assertIsNone(execute_script(script, {'maxStatements': 0}))


class TestEvaluateExpression(unittest.TestCase):

    def test_evaluate_expression(self):
        expr = validate_expression({
            'binary': {
                'op': '+',
                'left': {'number': 7},
                'right': {
                    'binary': {
                        'op': '*',
                        'left': {'number': 3},
                        'right': {
                            'function': {
                                'name': 'testNumber'
                            }
                        }
                    }
                }
            }
        })
        options = {'globals': {'testNumber': _test_number}}
        self.assertEqual(evaluate_expression(expr, options), 13)


    def test_no_globals(self):
        expr = validate_expression({'string': 'abc'})
        options = {}
        self.assertEqual(evaluate_expression(expr, options), 'abc')


    def test_string(self):
        expr = validate_expression({'string': 'abc'})
        self.assertEqual(evaluate_expression(expr), 'abc')


    def test_variable(self):
        expr = validate_expression({'variable': 'varName'})
        options = {'globals': {'varName': 4}}
        self.assertEqual(evaluate_expression(expr, options), 4)


    def test_variable_local(self):
        expr = validate_expression({'variable': 'varName'})
        locals_ = {'varName': 4}
        self.assertEqual(evaluate_expression(expr, None, locals_), 4)
        self.assertDictEqual(locals_, {'varName': 4})


    def test_variable_null_local_non_null_global(self):
        expr = validate_expression({'variable': 'varName'})
        options = {'globals': {'varName': 4}}
        locals_ = {'varName': None}
        self.assertEqual(evaluate_expression(expr, options, locals_), None)


    def test_variable_unknown(self):
        expr = validate_expression({'variable': 'varName'})
        self.assertEqual(evaluate_expression(expr), None)


    def test_variable_literal_null(self):
        expr = validate_expression({'variable': 'null'})
        self.assertEqual(evaluate_expression(expr), None)


    def test_variable_literal_true(self):
        expr = validate_expression({'variable': 'true'})
        self.assertEqual(evaluate_expression(expr), True)


    def test_variable_literal_false(self):
        expr = validate_expression({'variable': 'false'})
        self.assertEqual(evaluate_expression(expr), False)


    def test_function(self):
        expr = validate_expression({
            'function': {
                'name': 'myFunc',
                'args': [{'number': 1}, {'number': 2}]
            }
        })
        options = {
            'globals': {
                'myFunc': lambda args, unusedOptions: args[0] + args[1]
            }
        }
        self.assertEqual(evaluate_expression(expr, options), 3)


    def test_function_no_return(self):
        expr = validate_expression({
            'function': {
                'name': 'myFunc'
            }
        })

        def my_func(unused_args, unused_options):
            pass

        options = {
            'globals': {
                'myFunc': my_func
            }
        }
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_function_if(self):
        expr = validate_expression({
            'function': {
                'name': 'if',
                'args': [
                    {'variable': 'test'},
                    {'function': {'name': 'testValue', 'args': [{'string': 'a'}]}},
                    {'function': {'name': 'testValue', 'args': [{'function': {'name': 'testString'}}]}}
                ]
            }
        })

        test_values = []
        def test_value(args, unused_options):
            value, = args
            test_values.append(value)
            return value

        options = {
            'globals': {
                'test': True,
                'testString': _test_string,
                'testValue': test_value
            }
        }
        self.assertEqual(evaluate_expression(expr, options), 'a')
        self.assertListEqual(test_values, ['a'])
        options['globals']['test'] = False
        self.assertEqual(evaluate_expression(expr, options), 'abc')
        self.assertListEqual(test_values, ['a', 'abc'])


    def test_function_if_no_value_expression(self):
        expr = validate_expression({
            'function': {
                'name': 'if'
            }
        })
        self.assertEqual(evaluate_expression(expr), None)


    def test_function_if_no_true_expression(self):
        expr = validate_expression({
            'function': {
                'name': 'if',
                'args': [
                    {'function': {'name': 'testNumber'}}
                ]
            }
        })
        options = {'globals': {'testNumber': _test_number}}
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_function_if_no_false_expression(self):
        expr = validate_expression({
            'function': {
                'name': 'if',
                'args': [
                    {'function': {'name': 'testFalse'}},
                    {'number': 1}
                ]
            }
        })
        options = {'globals': {'testFalse': _test_false}}
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_function_builtin(self):
        expr = validate_expression({
            'function': {
                'name': 'abs',
                'args': [
                    {'function': {'name': 'testNumber'}}
                ]
            }
        })
        options = {'globals': {'testNumber': _test_number}}
        self.assertEqual(evaluate_expression(expr, options), 2)


    def test_function_no_builtins(self):
        expr = validate_expression({
            'function': {
                'name': 'abs',
                'args': [
                    {'function': {'name': 'testNumber'}}
                ]
            }
        })
        options = {'globals': {'testNumber': _test_number}}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, options, None, False)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "abs"')


    def test_function_global(self):
        expr = validate_expression({
            'function': {
                'name': 'fnName',
                'args': [
                    {'function': {'name': 'testNumber'}}
                ]
            }
        })

        def fn_name(args, unused_options):
            number, = args
            return 2 * number

        options = {'globals': {'testNumber': _test_number, 'fnName': fn_name}}
        self.assertEqual(evaluate_expression(expr, options), 4)


    def test_function_local(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal',
                'args': [
                    {'function': {'name': 'testNumber'}}
                ]
            }
        })

        def fn_local(args, unused_options):
            number, = args
            return 2 * number

        options = {'globals': {'testNumber': _test_number}}
        locals_ = {'fnLocal': fn_local}
        self.assertEqual(evaluate_expression(expr, options, locals_), 4)


    def test_function_local_null(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal',
                'args': [
                    {'function': {'name': 'testString'}}
                ]
            }
        })
        options = {'globals': {'testString': _test_string, 'fnLocal': 'abc'}}
        locals_ = {'fnLocal': None}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, options, locals_)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "fnLocal"')


    def test_function_non_function(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal',
                'args': [
                    {'function': {'name': 'testString'}}
                ]
            }
        })
        options = {'globals': {'testString': _test_string, 'fnLocal': 'abc'}}
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_function_non_function_log_fn(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal',
                'args': [
                    {'function': {'name': 'testString'}}
                ]
            }
        })

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'globals': {'testString': _test_string, 'fnLocal': 'abc'}, 'logFn': log_fn, 'debug': True}
        self.assertEqual(evaluate_expression(expr, options), None)
        self.assertListEqual(logs, ['BareScript: Function "fnLocal" failed with error: \'str\' object is not callable'])


    def test_function_unknown(self):
        expr = validate_expression({
            'function': {
                'name': 'fnUnknown',
                'args': [
                    {'function': {'name': 'testString'}}
                ]
            }
        })
        options = {'globals': {}}
        locals_ = {'testString': _test_string}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, options, locals_)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "fnUnknown"')


    def test_function_unknown_no_globals(self):
        expr = validate_expression({
            'function': {
                'name': 'fnUnknown',
                'args': [
                    {'function': {'name': 'testString'}}
                ]
            }
        })
        locals_ = {'testString': _test_string}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, None, locals_)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "fnUnknown"')


    def test_function_runtime_error(self):
        expr = validate_expression({
            'function': {
                'name': 'test'
            }
        })

        def test(unused_args, unused_options):
            raise BareScriptRuntimeError(None, None, 'Test error')

        options = {
            'globals': {
                'test': test
            }
        }
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, options)
        self.assertEqual(str(cm_exc.exception), 'Test error')


    def test_binary_logical_and(self):
        expr = validate_expression({
            'binary': {
                'op': '&&',
                'left': {'variable': 'leftValue'},
                'right': {'function': {'name': 'testValue', 'args': [{'function': {'name': 'testString'}}]}}
            }
        })

        test_values = []
        def test_value(args, unused_options):
            value, = args
            test_values.append(value)
            return value

        options = {
            'globals': {
                'testString': _test_string,
                'testValue': test_value
            }
        }
        self.assertEqual(evaluate_expression(expr, options), None)
        self.assertListEqual(test_values, [])
        options['globals']['leftValue'] = True
        self.assertEqual(evaluate_expression(expr, options), 'abc')
        self.assertListEqual(test_values, ['abc'])


    def test_binary_logical_or(self):
        expr = validate_expression({
            'binary': {
                'op': '||',
                'left': {'variable': 'leftValue'},
                'right': {'function': {'name': 'testValue', 'args': [{'function': {'name': 'testString'}}]}}
            }
        })

        test_values = []
        def test_value(args, unused_options):
            value, = args
            test_values.append(value)
            return value

        options = {
            'globals': {
                'leftValue': True,
                'testString': _test_string,
                'testValue': test_value
            }
        }
        self.assertEqual(evaluate_expression(expr, options), True)
        self.assertListEqual(test_values, [])
        options['globals']['leftValue'] = False
        self.assertEqual(evaluate_expression(expr, options), 'abc')
        self.assertListEqual(test_values, ['abc'])


    def test_binary_addition(self):
        options = {
            'globals': {
                'dt3': datetime.date(2024, 1, 6),
                'testDate': _test_date,
                'testNumber': _test_number,
                'testString': _test_string
            }
        }

        # number + number
        expr = validate_expression({'binary': {'op': '+', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 12)

        # string + string
        expr = validate_expression({'binary': {'op': '+', 'left': {'string': 'foo'}, 'right': {'function': {'name': 'testString'}}}})
        self.assertEqual(evaluate_expression(expr, options), 'fooabc')

        # string + <non-string>
        expr = validate_expression({'binary': {'op': '+', 'left': {'string': 'foo'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 'foo2')

        # <non-string> + string
        expr = validate_expression({'binary': {'op': '+', 'left': {'function': {'name': 'testNumber'}}, 'right': {'string': 'foo'}}})
        self.assertEqual(evaluate_expression(expr, options), '2foo')

        # datetime + number
        expr = validate_expression({'binary': {'op': '+', 'left': {'function': {'name': 'testDate'}}, 'right': {'number': 86400000}}})
        self.assertEqual(evaluate_expression(expr, options), datetime.datetime(2024, 1, 7))

        # datetime (date) + number
        expr = validate_expression({'binary': {'op': '+', 'left': {'variable': 'dt3'}, 'right': {'number': 86400000}}})
        self.assertEqual(evaluate_expression(expr, options), datetime.datetime(2024, 1, 7))

        # number + datetime
        expr = validate_expression({'binary': {'op': '+', 'left': {'number': -86400000}, 'right': {'function': {'name': 'testDate'}}}})
        self.assertEqual(evaluate_expression(expr, options), datetime.datetime(2024, 1, 5))

        # number + datetime (date)
        expr = validate_expression({'binary': {'op': '+', 'left': {'number': -86400000}, 'right': {'variable': 'dt3'}}})
        self.assertEqual(evaluate_expression(expr, options), datetime.datetime(2024, 1, 5))

        # Invalid - bool + number
        expr = validate_expression({'binary': {'op': '+', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - number + bool
        expr = validate_expression({'binary': {'op': '+', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - datetime + bool
        expr = validate_expression({'binary': {'op': '+', 'left': {'function': {'name': 'testDate'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - bool + datetime
        expr = validate_expression({'binary': {'op': '+', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testDate'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '+', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_subtraction(self):
        options = {
            'globals': {
                'dt2': datetime.datetime(2024, 1, 7),
                'dt3': datetime.date(2024, 1, 6),
                'testDate': _test_date,
                'testNumber': _test_number
            }
        }

        # number - number
        expr = validate_expression({'binary': {'op': '-', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 8)

        # datetime - datetime
        expr = validate_expression({'binary': {'op': '-', 'left': {'variable': 'dt2'}, 'right': {'function': {'name': 'testDate'}}}})
        self.assertEqual(evaluate_expression(expr, options), 86400000)

        # datetime (date) - datetime
        expr = validate_expression({'binary': {'op': '-', 'left': {'variable': 'dt2'}, 'right': {'variable': 'dt3'}}})
        self.assertEqual(evaluate_expression(expr, options), 86400000)

        # datetime - datetime (date)
        expr = validate_expression({'binary': {'op': '-', 'left': {'variable': 'dt3'}, 'right': {'variable': 'dt2'}}})
        self.assertEqual(evaluate_expression(expr, options), -86400000)

        # Invalid - bool - number
        expr = validate_expression({'binary': {'op': '-', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - number - bool
        expr = validate_expression({'binary': {'op': '-', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '-', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_multiplication(self):
        options = {'globals': {'testNumber': _test_number}}

        # number * number
        expr = validate_expression({'binary': {'op': '*', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 20)

        # Invalid - bool * number
        expr = validate_expression({'binary': {'op': '*', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - number * bool
        expr = validate_expression({'binary': {'op': '*', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '*', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_division(self):
        options = {'globals': {'testNumber': _test_number}}

        # number / number
        expr = validate_expression({'binary': {'op': '/', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 5)

        # Invalid - bool / number
        expr = validate_expression({'binary': {'op': '/', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - number / bool
        expr = validate_expression({'binary': {'op': '/', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '/', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_equality(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '==', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), False)


    def test_binary_inequality(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '!=', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), True)


    def test_binary_less_than_or_equal_to(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '<=', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), False)


    def test_binary_less_than(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '<', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), False)


    def test_binary_greater_than_or_equal_to(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '>=', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), True)


    def test_binary_greater_than(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'binary': {'op': '>', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), True)


    def test_binary_modulus(self):
        options = {'globals': {'testNumber': _test_number}}

        # number % number
        expr = validate_expression({'binary': {'op': '%', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 0)

        # Invalid - bool % number
        expr = validate_expression({'binary': {'op': '%', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - number % bool
        expr = validate_expression({'binary': {'op': '%', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '%', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_exponentiation(self):
        options = {'globals': {'testNumber': _test_number}}

        # number ** number
        expr = validate_expression({'binary': {'op': '**', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 100)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '**', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '**', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '**', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_bitwise_and(self):
        options = {'globals': {'testNumber': _test_number}}

        # number & number
        expr = validate_expression({'binary': {'op': '&', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 2)

        # Left float
        expr = validate_expression({'binary': {'op': '&', 'left': {'number': 10.}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 2)

        # Right float
        expr = validate_expression({'binary': {'op': '&', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 6.}}})
        self.assertEqual(evaluate_expression(expr, options), 2)

        # Invalid - left non-integer
        expr = validate_expression({'binary': {'op': '&', 'left': {'number': 10.5}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right non-integer
        expr = validate_expression({'binary': {'op': '&', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '&', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '&', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '&', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_bitwise_or(self):
        options = {'globals': {'testNumber': _test_number}}

        # number | number
        expr = validate_expression({'binary': {'op': '|', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 10)

        # Left float
        expr = validate_expression({'binary': {'op': '|', 'left': {'number': 10.}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 10)

        # Right float
        expr = validate_expression({'binary': {'op': '|', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 6.}}})
        self.assertEqual(evaluate_expression(expr, options), 6)

        # Invalid - left non-integer
        expr = validate_expression({'binary': {'op': '|', 'left': {'number': 10.5}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right non-integer
        expr = validate_expression({'binary': {'op': '|', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '|', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '|', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '|', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_bitwise_xor(self):
        options = {'globals': {'testNumber': _test_number}}

        # number ^ number
        expr = validate_expression({'binary': {'op': '^', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 8)

        # Left float
        expr = validate_expression({'binary': {'op': '^', 'left': {'number': 10.}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 8)

        # Right float
        expr = validate_expression({'binary': {'op': '^', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 6.}}})
        self.assertEqual(evaluate_expression(expr, options), 4)

        # Invalid - left non-integer
        expr = validate_expression({'binary': {'op': '^', 'left': {'number': 10.5}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right non-integer
        expr = validate_expression({'binary': {'op': '^', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '^', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '^', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '^', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_left_shift(self):
        options = {'globals': {'testNumber': _test_number}}

        # number << number
        expr = validate_expression({'binary': {'op': '<<', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 40)

        # Left float
        expr = validate_expression({'binary': {'op': '<<', 'left': {'number': 10.}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 40)

        # Right float
        expr = validate_expression({'binary': {'op': '<<', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.}}})
        self.assertEqual(evaluate_expression(expr, options), 8)

        # Invalid - left non-integer
        expr = validate_expression({'binary': {'op': '<<', 'left': {'number': 10.5}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right non-integer
        expr = validate_expression({'binary': {'op': '<<', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '<<', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '<<', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '<<', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_binary_right_shift(self):
        options = {'globals': {'testNumber': _test_number}}

        # number >> number
        expr = validate_expression({'binary': {'op': '>>', 'left': {'number': 10}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 2)

        # Left float
        expr = validate_expression({'binary': {'op': '>>', 'left': {'number': 10.}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), 2)

        # Right float
        expr = validate_expression({'binary': {'op': '>>', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 1.}}})
        self.assertEqual(evaluate_expression(expr, options), 1)

        # Invalid - left non-integer
        expr = validate_expression({'binary': {'op': '>>', 'left': {'number': 10.5}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right non-integer
        expr = validate_expression({'binary': {'op': '>>', 'left': {'function': {'name': 'testNumber'}}, 'right': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - left bool
        expr = validate_expression({'binary': {'op': '>>', 'left': {'variable': 'true'}, 'right': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - right bool
        expr = validate_expression({'binary': {'op': '>>', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'binary': {'op': '>>', 'left': {'function': {'name': 'testNumber'}}, 'right': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_unary_not(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({'unary': {'op': '!', 'expr': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), False)


    def test_unary_negate(self):
        options = {'globals': {'testNumber': _test_number, 'testString': _test_string}}

        # - number
        expr = validate_expression({'unary': {'op': '-', 'expr': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), -2)

        # Invalid
        expr = validate_expression({'unary': {'op': '-', 'expr': {'function': {'name': 'testString'}}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_unary_bitwise_not(self):
        options = {'globals': {'testNumber': _test_number, 'testString': _test_string}}

        # ~ number
        expr = validate_expression({'unary': {'op': '~', 'expr': {'function': {'name': 'testNumber'}}}})
        self.assertEqual(evaluate_expression(expr, options), -3)

        # Float
        expr = validate_expression({'unary': {'op': '~', 'expr': {'number': 2.}}})
        self.assertEqual(evaluate_expression(expr, options), -3)

        # Invalid - non-integer
        expr = validate_expression({'unary': {'op': '~', 'expr': {'number': 2.5}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid - bool
        expr = validate_expression({'unary': {'op': '~', 'expr': {'variable': 'true'}}})
        self.assertEqual(evaluate_expression(expr, options), None)

        # Invalid
        expr = validate_expression({'unary': {'op': '~', 'expr': {'variable': 'null'}}})
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_group(self):
        options = {'globals': {'testNumber': _test_number}}
        expr = validate_expression({
            'group': {
                'binary': {
                    'op': '*',
                    'left': {'function': {'name': 'testNumber'}},
                    'right': {
                        'group': {
                            'binary': {
                                'op': '+',
                                'left': {'number': 3},
                                'right': {'number': 5}
                            }
                        }
                    }
                }
            }
        })
        self.assertEqual(evaluate_expression(expr, options), 16)


# Helper functions to get test values of specific types
def _test_date(unused_args, unused_options):
    return datetime.datetime(2024, 1, 6)


def _test_false(unused_args, unused_options):
    return False


def _test_number(unused_args, unused_options):
    return 2


def _test_string(unused_args, unused_options):
    return 'abc'
