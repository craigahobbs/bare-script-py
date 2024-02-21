# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

# pylint: disable=missing-class-docstring, missing-function-docstring, missing-module-docstring

import os
import unittest
import unittest.mock
import urllib.request

from bare_script import fetch_http, fetch_read_only, fetch_read_write, log_stdout, url_file_relative


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


    def test_fetch_read_only(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_only({'url': 'http://example.com'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {})


    def test_fetch_read_only_post(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_only({'url': 'http://example.com', 'body': 'Post me!'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertEqual(request.data, b'Post me!')
            self.assertDictEqual(request.headers, {})


    def test_fetch_read_only_headers(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_only({'url': 'http://example.com', 'headers': {
                'Accept': 'application/json, application/xml'
            }})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {'Accept': 'application/json, application/xml'})


    def test_fetch_read_only_relative(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open(read_data='Hello!')) as mock_file:
            result = fetch_read_only({'url': 'test.txt'})
            self.assertEqual(result, 'Hello!')
            mock_file.assert_called_with('test.txt', 'r', encoding='utf-8')


    def test_fetch_read_only_relative_post(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file:
            result = fetch_read_only({'url': 'test.txt', 'body': 'Hello!'})
            self.assertIsNone(result)
            mock_file().write.assert_not_called()


    def test_fetch_read_write(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_write({'url': 'http://example.com'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {})


    def test_fetch_read_write_post(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_write({'url': 'http://example.com', 'body': 'Post me!'})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertEqual(request.data, b'Post me!')
            self.assertDictEqual(request.headers, {})


    def test_fetch_read_write_headers(self):
        with unittest.mock.patch('urllib.request.urlopen', return_value=MockResponse(b'Hello!')) as mock_urlopen:
            result = fetch_read_write({'url': 'http://example.com', 'headers': {
                'Accept': 'application/json, application/xml'
            }})
            self.assertEqual(result, 'Hello!')
            request = mock_urlopen.call_args[0][0]
            self.assertIsInstance(request, urllib.request.Request)
            self.assertEqual(request.full_url, 'http://example.com')
            self.assertIsNone(request.data)
            self.assertDictEqual(request.headers, {'Accept': 'application/json, application/xml'})


    def test_fetch_read_write_relative(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open(read_data='Hello!')) as mock_file:
            result = fetch_read_write({'url': 'test.txt'})
            self.assertEqual(result, 'Hello!')
            mock_file.assert_called_with('test.txt', 'r', encoding='utf-8')


    def test_fetch_read_write_relative_post(self):
        with unittest.mock.patch('builtins.open', unittest.mock.mock_open()) as mock_file:
            result = fetch_read_write({'url': 'test.txt', 'body': 'Hello!'})
            self.assertEqual(result, '{}')
            mock_file().write.assert_called_with('Hello!')


    def test_log_stdout(self):
        with unittest.mock.patch('builtins.print') as mock_print:
            log_stdout('Hello!')
            mock_print.assert_called_once_with("Hello!")


    def test_url_file_relative(self):
        # URL
        self.assertEqual(
            url_file_relative('http://craigahobbs.github.io/file.txt', 'http://craigahobbs.github.io/'),
            'http://craigahobbs.github.io/'
        )
        self.assertEqual(
            url_file_relative(os.sep + os.path.join('subdir', 'file.txt'), 'http://craigahobbs.github.io/'),
            'http://craigahobbs.github.io/'
        )
        self.assertEqual(
            url_file_relative(os.sep, 'http://craigahobbs.github.io/'),
            'http://craigahobbs.github.io/'
        )
        self.assertEqual(
            url_file_relative(os.path.join('subdir', 'file.txt'), 'http://craigahobbs.github.io/'),
            'http://craigahobbs.github.io/'
        )
        self.assertEqual(
            url_file_relative('file.txt', 'http://craigahobbs.github.io/'),
            'http://craigahobbs.github.io/'
        )

        # Absolute path
        self.assertEqual(
            url_file_relative('http://craigahobbs.github.io/file.txt', '/file2.txt'),
            os.sep + 'file2.txt'
        )
        self.assertEqual(
            url_file_relative(os.sep + os.path.join('subdir', 'file.txt'), '/file2.txt'),
            os.sep + 'file2.txt'
        )
        self.assertEqual(
            url_file_relative(os.sep, '/file2.txt'),
            os.sep + 'file2.txt'
        )
        self.assertEqual(
            url_file_relative(os.path.join('subdir', 'file.txt'), '/file2.txt'),
            os.sep + 'file2.txt'
        )
        self.assertEqual(
            url_file_relative('file.txt', '/file2.txt'),
            os.sep + 'file2.txt'
        )

        # Relative path
        self.assertEqual(
            url_file_relative('http://craigahobbs.github.io/file.txt', 'file2.txt'),
            'http://craigahobbs.github.io/file2.txt'
        )
        self.assertEqual(
            url_file_relative(os.sep + os.path.join('subdir', 'file.txt'), 'file2.txt'),
            os.sep + os.path.join('subdir', 'file2.txt')
        )
        self.assertEqual(
            url_file_relative(os.sep, 'file2.txt'),
            os.sep + 'file2.txt'
        )
        self.assertEqual(
            url_file_relative(os.path.join('subdir', 'file.txt'), 'file2.txt'),
            os.path.join('subdir', 'file2.txt')
        )
        self.assertEqual(
            url_file_relative('file.txt', 'file2.txt'),
            'file2.txt'
        )
