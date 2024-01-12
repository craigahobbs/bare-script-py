# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest

import bare_script.__main__


class TestMain(unittest.TestCase):

    def test_main_submodule(self):
        self.assertTrue(bare_script.__main__)


    @unittest.skip
    def test_main(self):
        self.fail()
