# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from io import StringIO
import sys
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
            if sys.version_info < (3, 9): # pragma: no cover
                self.assertEqual(stdout.getvalue().splitlines()[0], 'usage: bare [-h] [-c CODE] [-d] [-s] [-v VAR EXPR] [file [file ...]]')
            else:
                self.assertEqual(stdout.getvalue().splitlines()[0], 'usage: bare [-h] [-c CODE] [-d] [-s] [-v VAR EXPR] [file ...]')
            self.assertEqual(stderr.getvalue(), '')


    def test_main_inline(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("Hello!")'])

            self.assertEqual(mock_stdout.getvalue(), 'Hello!\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_file(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['systemLog("Hello!")']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), 'Hello!\n')
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


    def test_main_status_returned(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'return 2'])

            self.assertEqual(mock_stdout.getvalue(), '')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 2)


    def test_main_variables(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'systemLog("Hi " + vName + "!")', '-v', 'vName', '"Bob"'])

            self.assertEqual(mock_stdout.getvalue(), 'Hi Bob!\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_debug(self):
        with unittest.mock.patch('time.time', side_effect=[1000, 1000.1]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-d', '-c', 'systemLog("Hello!")'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript: Static analysis "-c 1" ... OK
Hello!
BareScript: Script executed in 100.0 milliseconds
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_debug_lint_warnings(self):
        with unittest.mock.patch('time.time', side_effect=[1000, 1000.1]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-d', '-c', '0'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript: Static analysis "-c 1" ... 1 warning:
BareScript:     Pointless global statement (index 0)
BareScript: Script executed in 100.0 milliseconds
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_static_ok(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-s', '-c', 'systemLog("Hello!")'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript: Static analysis "-c 1" ... OK
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)


    def test_main_static_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-s', '-c', '0'])

            self.assertEqual(mock_stdout.getvalue(), '''\
BareScript: Static analysis "-c 1" ... 1 warning:
BareScript:     Pointless global statement (index 0)
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_status_parse_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-c', 'asdf asdf'])

            self.assertEqual(mock_stdout.getvalue(), '''\
-c 1:
Syntax error, line number 1:
asdf asdf
    ^
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)


    def test_main_variables_parse_error(self):
        with unittest.mock.patch('time.time', side_effect=[1000]), \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            with self.assertRaises(SystemExit) as cm_exc:
                main(['-v', 'A', 'asdf asdf', '-c', '0'])

            self.assertEqual(mock_stdout.getvalue(), '''\
Syntax error:
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
                main(['-v', 'A', 'unknown()', '-c', '0'])

            self.assertEqual(mock_stdout.getvalue(), '''\
Undefined function "unknown"
''')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 1)
