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
    A :func:`fetch function <fetch_fn>` implementation that fetches resources using HTTP GET and POST
    """

    url = request['url']
    body = request.get('body')
    headers = request.get('headers') or {}
    method = 'GET' if body is None else 'POST'
    try:
        response = FETCH_POOL_MANAGER.request(method, url, body=body, headers=headers, retries=0)
        if response.status != 200:
            raise urllib3.exceptions.HTTPError(f'Fetch "{method}" "{url}" failed ({response.status})')
        response_text = response.data.decode('utf-8')
    finally:
        response.close()
    return response_text


def fetch_read_only(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources that uses HTTP GET
    and POST for URLs, otherwise read-only file system access
    """

    # HTTP GET/POST?
    url = request['url']
    if _R_URL.match(url):
        return fetch_http(request)

    # File write?
    body = request.get('body')
    if body is not None:
        return None

    # File read
    with open(url, 'r', encoding='utf-8') as fh:
        return fh.read()


def fetch_read_write(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources that uses HTTP GET
    and POST for URLs, otherwise read-write file system access
    """

    # HTTP GET/POST?
    url = request['url']
    if _R_URL.match(url):
        return fetch_http(request)

    # File write?
    body = request.get('body')
    if body is not None:
        with open(url, 'w', encoding='utf-8') as fh:
            fh.write(body)
        return '{}'

    # File read
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
