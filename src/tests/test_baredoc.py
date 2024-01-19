# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

from bare_script.baredoc import main


class TestBaredoc(unittest.TestCase):

    def test_main(self):
        self.assertEqual(callable(main), True)
