# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import os
import unittest

from bare_script import BareScriptParserError, BareScriptRuntimeError, evaluate_expression, execute_script, \
    validate_expression, validate_script


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

        options = {'globals': {'errorFunction': error_function}, 'logFn': log_fn, 'debug': False}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, [])


    def test_jump(self):
        script = validate_script({
            'statements': [
                {'expr': {'name': 'a', 'expr': {'number': 5}}},
                {'jump': {'label': 'lab2'}},
                {'label': 'lab'},
                {'expr': {'name': 'a', 'expr': {'number': 6}}},
                {'jump': {'label': 'lab3'}},
                {'label': 'lab2'},
                {'expr': {'name': 'a', 'expr': {'number': 7}}},
                {'jump': {'label': 'lab'}},
                {'label': 'lab3'},
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
                {'label': 'fib'},
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
                {'label': 'fibend'},
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
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.mds', 'test2.mds'), True)
            return 'b = 2' if url == 'test2.mds' else '''\
include 'test2.mds'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_system(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds', 'system': True}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'system/test.mds')
            return 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn, 'systemPrefix': 'system/'}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)


    def test_include_system_no_prefix(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds', 'system': True}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.mds')
            return 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)


    def test_include_multiple(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds', 'system': True}, {'url': 'test2.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.mds', 'test2.mds'), True)
            return 'b = a + 1' if url.endswith('test2.mds') else 'a = 1'

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_subdir(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'lib/test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('lib/test.mds', os.path.join('lib', 'test2.mds')), True)
            return 'b = 2' if url.endswith('test2.mds') else '''\
include 'test2.mds'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_absolute(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url in ('test.mds', 'http://foo.local/test2.mds'), True)
            return 'b = 2' if url.endswith('test2.mds') else '''\
include 'http://foo.local/test2.mds'
a = 1
'''

        options = {'globals': {}, 'fetchFn': fetch_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertEqual(options['globals']['a'], 1)
        self.assertEqual(options['globals']['b'], 2)


    def test_include_no_fetch_fn(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        options = {}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            self.assertIsNone(execute_script(script, options))
            self.assertEqual(str(cm_exc.exception), 'Include of "test.mds" failed')


    def test_include_lint_ok(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.mds')
            return '''\
function test():
endfunction
'''

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'debug': True, 'globals': {}, 'fetchFn': fetch_fn, 'logFn': log_fn}
        self.assertIsNone(execute_script(script, options))
        self.assertListEqual(logs, [])
        self.assertEqual(callable(options['globals']['test']), True)


    def test_include_fetch_fn_error(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.mds')
            raise Exception('response error') # pylint: disable=broad-exception-raised

        options = {'fetchFn': fetch_fn}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            execute_script(script, options)
            self.assertEqual(str(cm_exc.exception), 'Include of "test.mds" failed')


    def test_include_parser_error(self):
        script = validate_script({
            'statements': [
                {'include': {'includes': [{'url': 'test.mds'}]}}
            ]
        })

        def fetch_fn(request):
            url = request['url']
            self.assertEqual(url, 'test.mds')
            return 'foo bar'

        options = {'fetchFn': fetch_fn}
        with self.assertRaises(BareScriptParserError) as cm_exc:
            execute_script(script, options)
            self.assertEqual(str(cm_exc.exception), '''\
Included from "test.mds"
Syntax error, line number 1:
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
                                'name': 'ceil',
                                'args': [
                                    {'variable': 'varName'}
                                ]
                            }
                        }
                    }
                }
            }
        })
        options = {'globals': {'varName': 4}}
        self.assertEqual(evaluate_expression(expr, options), 19)


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
                    {'function': {'name': 'testValue', 'args': [{'string': 'b'}]}}
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
                'testValue': test_value
            }
        }
        self.assertEqual(evaluate_expression(expr, options), 'a')
        self.assertListEqual(test_values, ['a'])
        options['globals']['test'] = False
        self.assertEqual(evaluate_expression(expr, options), 'b')
        self.assertListEqual(test_values, ['a', 'b'])


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
                    {'variable': 'true'}
                ]
            }
        })
        self.assertEqual(evaluate_expression(expr), None)


    def test_function_if_no_false_expression(self):
        expr = validate_expression({
            'function': {
                'name': 'if',
                'args': [
                    {'variable': 'false'},
                    {'number': 1}
                ]
            }
        })
        self.assertEqual(evaluate_expression(expr), None)


    def test_function_builtin(self):
        expr = validate_expression({
            'function': {
                'name': 'abs',
                'args': [
                    {'number': -1}
                ]
            }
        })
        self.assertEqual(evaluate_expression(expr), 1)


    def test_function_no_builtins(self):
        expr = validate_expression({
            'function': {
                'name': 'abs',
                'args': [
                    {'number': -1}
                ]
            }
        })
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, None, None, False)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "abs"')


    def test_function_global(self):
        expr = validate_expression({
            'function': {
                'name': 'fnName',
                'args': [
                    {'number': 3}
                ]
            }
        })

        def fn_name(args, unused_options):
            number, = args
            return 2 * number

        options = {'globals': {'fnName': fn_name}}
        self.assertEqual(evaluate_expression(expr, options), 6)


    def test_function_local(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal',
                'args': [
                    {'number': 3}
                ]
            }
        })

        def fn_local(args, unused_options):
            number, = args
            return 2 * number

        locals_ = {'fnLocal': fn_local}
        self.assertEqual(evaluate_expression(expr, None, locals_), 6)


    def test_function_local_null(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal'
            }
        })
        options = {'globals': {'fnLocal': 'abc'}}
        locals_ = {'fnLocal': None}
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr, options, locals_)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "fnLocal"')


    def test_function_non_function(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal'
            }
        })
        options = {'globals': {'fnLocal': 'abc'}}
        self.assertEqual(evaluate_expression(expr, options), None)


    def test_function_non_function_log_fn(self):
        expr = validate_expression({
            'function': {
                'name': 'fnLocal'
            }
        })

        logs = []
        def log_fn(message):
            logs.append(message)

        options = {'globals': {'fnLocal': 'abc'}, 'logFn': log_fn, 'debug': True}
        self.assertEqual(evaluate_expression(expr, options), None)
        self.assertListEqual(logs, ['BareScript: Function "fnLocal" failed with error: \'str\' object is not callable'])


    def test_function_unknown(self):
        expr = validate_expression({
            'function': {
                'name': 'fnUnknown'
            }
        })
        with self.assertRaises(BareScriptRuntimeError) as cm_exc:
            evaluate_expression(expr)
        self.assertEqual(str(cm_exc.exception), 'Undefined function "fnUnknown"')


    def test_function_runtime_error(self):
        expr = validate_expression({
            'function': {
                'name': 'test'
            }
        })

        def test(unused_args, unused_options):
            raise BareScriptRuntimeError('Test error')

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
                'right': {'function': {'name': 'testValue', 'args': [{'string': 'abc'}]}}
            }
        })

        test_values = []
        def test_value(args, unused_options):
            value, = args
            test_values.append(value)
            return value

        options = {
            'globals': {
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
                'right': {'function': {'name': 'testValue', 'args': [{'string': 'abc'}]}}
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
                'testValue': test_value
            }
        }
        self.assertEqual(evaluate_expression(expr, options), True)
        self.assertListEqual(test_values, [])
        options['globals']['leftValue'] = False
        self.assertEqual(evaluate_expression(expr, options), 'abc')
        self.assertListEqual(test_values, ['abc'])


    def test_binary_exponentiation(self):
        expr = validate_expression({'binary': {'op': '**', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 100)


    def test_binary_multiplication(self):
        expr = validate_expression({'binary': {'op': '*', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 20)


    def test_binary_division(self):
        expr = validate_expression({'binary': {'op': '/', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 5)


    def test_binary_modulus(self):
        expr = validate_expression({'binary': {'op': '%', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 0)


    def test_binary_addition(self):
        expr = validate_expression({'binary': {'op': '+', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 12)


    def test_binary_subtraction(self):
        expr = validate_expression({'binary': {'op': '-', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), 8)


    def test_binary_less_than_or_equal_to(self):
        expr = validate_expression({'binary': {'op': '<=', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), False)


    def test_binary_less_than(self):
        expr = validate_expression({'binary': {'op': '<', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), False)


    def test_binary_greater_than_or_equal_to(self):
        expr = validate_expression({'binary': {'op': '>=', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), True)


    def test_binary_greater_than(self):
        expr = validate_expression({'binary': {'op': '>', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), True)


    def test_binary_equality(self):
        expr = validate_expression({'binary': {'op': '==', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), False)


    def test_binary_inequality(self):
        expr = validate_expression({'binary': {'op': '!=', 'left': {'number': '10'}, 'right': {'number': 2}}})
        self.assertEqual(evaluate_expression(expr), True)


    def test_unary_not(self):
        expr = validate_expression({'unary': {'op': '!', 'expr': {'variable': 'False'}}})
        self.assertEqual(evaluate_expression(expr), True)


    def test_unary_negate(self):
        expr = validate_expression({'unary': {'op': '-', 'expr': {'number': 1}}})
        self.assertEqual(evaluate_expression(expr), -1)


    def test_group(self):
        expr = validate_expression({
            'group': {
                'binary': {
                    'op': '*',
                    'left': {'number': 2},
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
        self.assertEqual(evaluate_expression(expr), 16)
