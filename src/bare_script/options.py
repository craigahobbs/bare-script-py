# Licensed under the MIT License
# https://github.com/craigahobbs/bare-script-py/blob/main/LICENSE

"""
BareScript runtime option function implementations
"""

import os
import re
import urllib


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
            fh.write(url)
        return '{}'

    # File read
    with open(url, 'r', encoding='utf-8') as fh:
        return fh.read()


def log_print(message):
    """
    A :func:`log function <log_fn>` implementation that uses print
    """

    print(message)


def url_file_relative(file_, url):
    """
    A :func:`URL function <url_fn>` implementation that fixes up file-relative paths
    """

    if re.match(_R_URL, url) or os.path.isabs(url):
        return url

    return os.path.join(os.path.dirname(file_), url)


_R_URL = re.compile(r'^[a-z]+:')
