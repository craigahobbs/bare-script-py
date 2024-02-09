# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from io import StringIO
import json
import unittest
import unittest.mock

from bare_script.baredoc import main


class TestBaredoc(unittest.TestCase):

    def test_main_help(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-h'])

            self.assertEqual(stdout.getvalue().splitlines()[0], 'usage: bare [-h] [-o file] file [file ...]')
            self.assertEqual(stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main(self):
        mock_open_obj = unittest.mock.mock_open()
        with unittest.mock.patch('builtins.open', mock_open_obj) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function.
# $doc:
# $doc: More on the function.
# $arg arg1: The first argument
# $arg arg2: The second argument.
# $arg arg2:
# $arg arg2: More on the second argument.
# $return: The message
function myFunction(arg1, arg2)
    message = 'Hello'
    systemLog(message)
    return message
endfunction
''']

            main(['test.bare', '-o', 'test.json'])
            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')

            self.assertListEqual(mock_open_ctx.call_args_list, [
                unittest.mock.call('test.bare', 'r', encoding='utf-8'),
                unittest.mock.call('test.json', 'w', encoding='utf-8')
            ])

            mock_file_handle = mock_open_obj()
            mock_file_handle.read.assert_called_once()
            mock_file_handle.write.assert_called_once_with(json.dumps({
                'functions': [
                    {
                        'args':[
                            {'name':'arg1', 'doc':['The first argument']},
                            {'name':'arg2', 'doc':['The second argument.','','More on the second argument.']}
                        ],
                        'doc': ['This is my function.','','More on the function.'],
                        'group': 'My Group',
                        'name': 'myFunction',
                        'return':['The message']
                    }
                ]
            }, separators=(',', ':'), sort_keys=True))


    def test_main_stdout(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function
function myFunction()
    systemLog('Hello')
endfunction
''']

            main(['test.bare'])
            self.assertEqual(mock_stdout.getvalue(), json.dumps({
                'functions': [
                    {
                        'doc': ['This is my function'],
                        'group': 'My Group',
                        'name': 'myFunction'
                    }
                ]
            }, separators=(',', ':'), sort_keys=True) + '\n')
            self.assertEqual(mock_stderr.getvalue(), '')


    def test_main_function_doc_leading_trim(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc:
# $doc: This is my function
# $doc:
function myFunction()
    systemLog('Hello')
endfunction
''']

            main(['test.bare'])
            self.assertEqual(mock_stdout.getvalue(), json.dumps({
                'functions': [
                    {
                        'doc': ['This is my function', ''],
                        'group': 'My Group',
                        'name': 'myFunction'
                    }
                ]
            }, separators=(',', ':'), sort_keys=True) + '\n')
            self.assertEqual(mock_stderr.getvalue(), '')


    def test_main_arg_doc_leading_trim(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function
# $arg arg:
# $arg arg: The first argument
# $arg arg:
function myFunction()
    systemLog('Hello')
endfunction
''']

            main(['test.bare'])
            self.assertEqual(mock_stdout.getvalue(), json.dumps({
                'functions': [
                    {
                        'args':[{'doc':['The first argument',''], 'name':'arg'}],
                        'doc': ['This is my function'],
                        'group': 'My Group',
                        'name': 'myFunction'
                    }
                ]
            }, separators=(',', ':'), sort_keys=True) + '\n')
            self.assertEqual(mock_stderr.getvalue(), '')


    def test_main_error_no_files(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
error: No library functions
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_missing_function_members(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
error: Function "myFunction" missing group
error: Function "myFunction" missing documentation
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_keyword_outside_function(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $group: My Group
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:1: group keyword outside function
error: No library functions
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_empty_group(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group:
# $doc: This is my function
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:2: Invalid function group name ""
error: Function "myFunction" missing group
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_group_redefinition(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $group: My Other Group
# $doc: This is my function
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:3: Function "myFunction" group redefinition
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_empty_function(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function:
# $group: My Group
# $doc: This is my function
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:1: Invalid function name ""
test.bare:2: group keyword outside function
test.bare:3: doc keyword outside function
error: No library functions
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_function_redefinition(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function
function myFunction()
    systemLog('Hello')
endfunction

# $function: myFunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:8: Function "myFunction" redefinition
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_arg_outside_function(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $arg arg: My arg
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:1: Function argument "arg" outside function
error: No library functions
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_error_invalid_keyword(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_open_ctx, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_open_ctx.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function
# $returns: Bad return keyword
function myFunction()
    systemLog('Hello')
endfunction
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
test.bare:4: Invalid documentation comment "('returns',)"
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)
