# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from io import StringIO
import os
import unittest
import unittest.mock

from bare_script.__main__ import main as main_main
from bare_script.bare import main


class TestBare(unittest.TestCase):

    def test_main_submodule(self):
        self.assertIs(main_main, main)


    def test_main_help(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-h'])

            self.assertEqual(cm_exc.exception.code, 0)
            self.assertEqual(
                stdout.getvalue().splitlines()[0],
                'usage: bare [-h] [-c CODE] [-d] [-m] [-s] [-v VAR EXPR] [file ...]'
            )
            self.assertEqual(stderr.getvalue(), '')


    def test_main_help_no_scripts(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main([])

            self.assertEqual(cm_exc.exception.code, 0)
            self.assertEqual(
                stdout.getvalue().splitlines()[0],
                'usage: bare [-h] [-c CODE] [-d] [-m] [-s] [-v VAR EXPR] [file ...]'
            )
            self.assertEqual(stderr.getvalue(), '')


    def test_main_argument_error(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['--unknown'])

            self.assertEqual(cm_exc.exception.code, 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue().splitlines()[-1], 'bare: error: unrecognized arguments: --unknown')


    def test_main_inline(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("Hello")'])

            self.assertListEqual(mock_file.call_args_list, [])
            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_inline_fetch(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['Hello']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', "systemLog(systemFetch('test.txt'))"])

            self.assertListEqual(mock_file.call_args_list, [
                unittest.mock.call('test.txt', 'r', encoding='utf-8')
            ])
            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_system_include(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'include <markdownUp.bare>', '-c', "markdownPrint('Hello')"])

            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_markdown_up(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-m', '-c', "markdownPrint('Hello')"])

            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_file(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['systemLog("Hello")']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertListEqual(mock_file.call_args_list, [
                unittest.mock.call('test.bare', 'r', encoding='utf-8')
            ])
            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_file_fetch(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ["systemLog(systemFetch('test.txt'))", 'Hello']

            with self.assertRaises(SystemExit) as cm_exc:
                main([os.path.join('subdir', 'test.bare')])

            self.assertListEqual(mock_file.call_args_list, [
                unittest.mock.call(os.path.join('subdir', 'test.bare'), 'r', encoding='utf-8'),
                unittest.mock.call(os.path.join('subdir', 'test.txt'), 'r', encoding='utf-8')
            ])
            self.assertEqual(mock_stdout.getvalue(), 'Hello\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_mixed_begin(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000, 1000.1, 1000.2, 1000.3, 1000.4]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['systemLog("1")', 'systemLog("2")']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare', 'test2.bare', '-c', 'systemLog("3")', '-c', 'systemLog("4")'])

            self.assertEqual(mock_stdout.getvalue(), '''\
1
2
3
4
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_mixed_middle(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000, 1000.1, 1000.2, 1000.3, 1000.4]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['systemLog("2")', 'systemLog("3")']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("1")', 'test.bare', 'test2.bare', '-c', 'systemLog("4")'])

            self.assertEqual(mock_stdout.getvalue(), '''\
1
2
3
4
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_mixed_end(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000, 1000.1, 1000.2, 1000.3, 1000.4]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['systemLog("3")', 'systemLog("4")']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("1")', '-c', 'systemLog("2")', 'test.bare', 'test2.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
1
2
3
4
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_parse_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'asdf asdf'])

            self.assertEqual(mock_stdout.getvalue(), '''\
<string>:1: Syntax error
asdf asdf
    ^
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_script_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'unknown()'])

            self.assertEqual(mock_stdout.getvalue(), '''\
<string>:1: Undefined function "unknown"
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_fetch_error(self):
        with unittest.mock.patch('builtins.open', side_effect=FileNotFoundError), \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), 'Failed to load "test.bare"\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_status_return(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return 2'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 2)


    def test_main_status_return_zero(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return 0'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_status_return_max(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return 255'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 255)


    def test_main_status_return_beyond_max(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return 256'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_status_return_negative(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return -1'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_status_return_non_integer_true(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return "abc"'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_status_return_non_integer_false(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return ""'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_variables(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("Hi " + vName + "!")', '-v', 'vName', '"Bob"'])

            self.assertEqual(mock_stdout.getvalue(), 'Hi Bob!\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_variables_parse_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-v', 'A', 'asdf asdf', '-c', 'return A'])

            self.assertEqual(mock_stdout.getvalue(), '''\
Syntax error
asdf asdf
    ^
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_variables_evaluate_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-v', 'A', 'unknown()', '-c', 'return A'])

            self.assertEqual(mock_stdout.getvalue(), '''\
Undefined function "unknown"
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_debug(self):
        with unittest.mock.patch('time.time', side_effect=[1000, 1000.1, 1001, 1001.1]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-d', '-c', 'systemLog("Hello")', '-c', 'systemLogDebug("Goodbye")'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript static analysis "<string>" ... OK
Hello
BareScript executed in 100.0 milliseconds
BareScript static analysis "<string2>" ... OK
Goodbye
BareScript executed in 100.0 milliseconds
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_debug_static_analysis_warnings(self):
        with unittest.mock.patch('time.time', side_effect=[1000, 1000.1]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-d', '-c', '0'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript static analysis "<string>" ... 1 warning:
<string>:1: Pointless global statement
BareScript executed in 100.0 milliseconds
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_debug_static_analysis_warnings_multiple(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000, 1000.1]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['0\n1\n']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-d', 'test.bare'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript static analysis "test.bare" ... 2 warnings:
test.bare:1: Pointless global statement
test.bare:2: Pointless global statement
BareScript executed in 100.0 milliseconds
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_static_analysis(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-s', '-c', 'return 0', '-c', 'return 1'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript static analysis "<string>" ... OK
BareScript static analysis "<string2>" ... OK
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_static_analysis_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-s', '-c', '0', '-c', '1'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript static analysis "<string>" ... 1 warning:
<string>:1: Pointless global statement
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)
