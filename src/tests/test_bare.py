# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from bare_script.__main__ import main as main_main
from bare_script.bare import main


class TestBare(unittest.TestCase):

    def test_main_submodule(self):
        self.assertIs(main_main, main)


    def test_main(self):
        self.assertEqual(callable(main), True)
