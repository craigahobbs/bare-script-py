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
