# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

from io import StringIO
import unittest
import unittest.mock

from bare_script.baredoc import main


class TestBaredoc(unittest.TestCase):

    def test_main_help(self):
        with unittest.mock.patch('sys.stdout', StringIO()) as stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as stderr:
            with self.assertRaises(SystemExit) as cm_exc:
                main(['-h'])

            self.assertNotEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)
            self.assertEqual(stdout.getvalue().splitlines()[0], 'usage: bare [-h] file [file ...]')
            self.assertEqual(stderr.getvalue(), '')
