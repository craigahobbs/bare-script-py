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

            self.assertNotEqual(stdout.getvalue(), '')
            self.assertEqual(stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)
            self.assertEqual(stdout.getvalue().splitlines()[0], 'usage: bare [-h] file [file ...]')
            self.assertEqual(stderr.getvalue(), '')


    def test_main(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file, \
             unittest.mock.patch('sys.stdout', StringIO()) as mock_stdout, \
             unittest.mock.patch('sys.stderr', StringIO()) as mock_stderr:

            mock_file.return_value.read.side_effect = ['''\
# $function: myFunction
# $group: My Group
# $doc: This is my function
# $arg arg1: The first argument
# $arg arg2: The second argument.
# $arg arg2: More on the second argument.
# $return: Something
''']

            with self.assertRaises(SystemExit) as cm_exc:
                main(['test.bare'])

            self.assertEqual(mock_stdout.getvalue(), json.dumps({
                "functions": [
                    {
                        "args": [
                            {"name": "arg1", "doc": ["The first argument"]},
                            {"name": "arg2", "doc": ["The second argument.", "More on the second argument."]}
                        ],
                        "doc": ["This is my function"],
                        "group": "My Group",
                        "name": "myFunction",
                        "return": ["Something"]
                    }
                ]
            }, separators=(',', ':'), sort_keys=True) + '\n')
            self.assertEqual(mock_stderr.getvalue(), '')
            self.assertEqual(cm_exc.exception.code, 0)
