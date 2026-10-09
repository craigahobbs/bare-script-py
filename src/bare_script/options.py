# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript runtime option function implementations
"""

import os
from pathlib import Path
import re

import urllib3


# The fetch connection pool
FETCH_POOL_COUNT = int(os.getenv('BARESCRIPT_FETCH_POOL_COUNT', '10'))
FETCH_POOL_SIZE = int(os.getenv('BARESCRIPT_FETCH_POOL_SIZE', '10'))
FETCH_POOL_MANAGER = urllib3.PoolManager(num_pools=FETCH_POOL_COUNT, maxsize=FETCH_POOL_SIZE)


def fetch_http(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources using HTTP - the request's method, or
    GET (POST if there's a body) by default
    """

    # Not a URL (e.g. a relative path)? Don't let it be read as a host name.
    url = request['url']
    if not _R_URL.match(url):
        raise ValueError(f'Invalid URL "{url}"')
    body = request.get('body')
    headers = request.get('headers') or {}
    method = request.get('method')
    if method is None:
        method = 'GET' if body is None else 'POST'
    response = FETCH_POOL_MANAGER.request(method, url, body=body, headers=headers, retries=0)
    try:
        # Any 2xx status is success (e.g. "201 Created") - the same as the JavaScript fetch's "ok"
        if not 200 <= response.status <= 299:
            raise urllib3.exceptions.HTTPError(f'Fetch "{method}" "{url}" failed ({response.status})')
        response_data = response.data if request.get('binary', False) else response.data.decode('utf-8')
    finally:
        response.close()
    return response_data


def fetch_read_only(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources that uses HTTP for
    URLs (see :func:`fetch_http`), otherwise read-only file system access - a file read is a GET
    request
    """

    return _fetch_helper(request, False)


def fetch_read_write(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources that uses HTTP for
    URLs (see :func:`fetch_http`), otherwise read-write file system access - a file read is a GET
    request, a file write is a POST or PUT request with a body, and a file delete is a DELETE request
    """

    return _fetch_helper(request, True)


# Helper to fetch a URL or read/write/delete a file - file writes and deletes fail unless writable, and any other
# method fails
def _fetch_helper(request, writable):
    # HTTP?
    url = request['url']
    if _R_URL.match(url):
        return fetch_http(request)

    # File delete? A binary request's response is bytes
    method = request.get('method')
    body = request.get('body')
    if method == 'DELETE':
        if not writable or body is not None:
            return None
        os.remove(url)
        return b'{}' if request.get('binary', False) else '{}'

    # File write? A bytes body is written as-is, and a binary request's response is bytes
    if body is not None:
        if not writable or method not in (None, 'POST', 'PUT'):
            return None
        if isinstance(body, bytes):
            with open(url, 'wb') as fh:
                fh.write(body)
        else:
            with open(url, 'w', encoding='utf-8') as fh:
                fh.write(body)
        return b'{}' if request.get('binary', False) else '{}'

    # File read - a binary request's response is bytes
    if method not in (None, 'GET'):
        return None
    if request.get('binary', False):
        with open(url, 'rb') as fh:
            return fh.read()
    with open(url, 'r', encoding='utf-8') as fh:
        return fh.read()


def log_stdout(text):
    """
    A :func:`log function <log_fn>` implementation that outputs to stdout
    """

    print(text)


def url_file_relative(file_, url):
    """
    A :func:`URL function <url_fn>` implementation that fixes up file-relative paths

    :param file_: The URL or OS path to which relative URLs are relative
    :param url: The URL or POSIX path to resolve
    :return: The resolved URL
    """

    # URL?
    if re.match(_R_URL, url):
        return url

    # Absolute POSIX path? If so, convert to OS path
    if url.startswith('/'):
        return str(Path(url))

    # URL is relative POSIX path...

    # Is relative-file a URL?
    if re.match(_R_URL, file_):
        return f'{file_[:file_.rfind("/") + 1]}{url}'

    # The relative-file is an OS path...
    return os.path.normpath(os.path.join(os.path.dirname(file_), str(Path(url))))


_R_URL = re.compile(r'^[a-z]+:')
