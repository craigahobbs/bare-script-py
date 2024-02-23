# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript runtime option function implementations
"""

import os
from pathlib import Path
import re
import urllib.request


def fetch_http(request):
    """
    A :func:`fetch function <fetch_fn>` implementation that fetches resources using HTTP GET and POST
    """

    body = request.get('body')
    req = urllib.request.Request(
        request['url'],
        data=body.encode('utf-8') if body is not None else None,
        headers=request.get('headers', {})
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode('utf-8')


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
    return os.path.join(os.path.dirname(file_), str(Path(url)))


_R_URL = re.compile(r'^[a-z]+:')
