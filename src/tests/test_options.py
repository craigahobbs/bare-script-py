# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import unittest
import unittest.mock
import urllib.request

from bare_script import fetch_http


class MockResponse:
    def __init__(self, read_data):
        self.read_data = read_data

    def read(self):
        return self.read_data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestOptions(unittest.TestCase):

    def test_fetch_http(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_http({'url': 'http://example.com'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {})


    def test_fetch_http_post(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_http({'url': 'http://example.com', 'body': 'Post me!'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertEqual(request.data, b'Post me!')
            self.assertDictEqual(request.headers, {})


    def test_fetch_http_headers(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_http({'url': 'http://example.com', 'headers': {
                'Accept': 'application/json, application/xml'
            }})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {'Accept': 'application/json, application/xml'})
