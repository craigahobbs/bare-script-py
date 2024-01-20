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

    # Convert to OS path
    path = posixpath_to_os(url)

    # File write?
    body = request.get('body')
    if body is not None:
        return None

    # File read
    with open(path, 'r', encoding='utf-8') as fh:
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

    # Convert to OS path
    path = posixpath_to_os(url)

    # File write?
    body = request.get('body')
    if body is not None:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(body)
        return '{}'

    # File read
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def log_print(message):
    """
    A :func:`log function <log_fn>` implementation that uses print
    """

    print(message)


def ospath_to_posix(path):
    """
    Convert an OS path to a POSIX path

    :param path: The OS path
    :type path: str
    :return: The POSIX path
    :rtype: str
    """

    # Don't modify URLs
    if _R_URL.match(path):
        return path

    # Already POSIX?
    if os.sep == '/':
        return path

    prefix = '/' if os.path.isabs(path) and not path.startswith(os.sep) else ''
    return prefix + path.replace(os.sep, '/')


def posixpath_to_os(path):
    """
    Convert a POSIX path to an OS path

    :param path: The POSIX path
    :type path: str
    :return: The OS path
    :rtype: str
    """

    # Don't modify URLs
    if _R_URL.match(path):
        return path

    # OS is POSIX?
    if os.sep == '/':
        return path

    ospath = path.replace('/', os.sep)

    if path.startswith('/'):
        ospath_no_prefix = ospath[1:]
        if os.path.isabs(ospath_no_prefix):
            return ospath_no_prefix

    return ospath


def relpath_resolve(relpath, path):
    """
    Resolve a path to a relative-path

    :param relpath: The path to which relative paths are relative
    :type relpath: str
    :param path: The path to resolve
    :type path: str
    :return: The resolved path
    :rtype: str
    """

    # No relpath?
    if relpath is None:
        return path

    # URL path?
    if _R_URL.match(path):
        return path

    # Absolute path?
    if path.startswith('/'):
        return path

    return f'{relpath[:relpath.rfind("/") + 1]}{path}'


_R_URL = re.compile(r'^[a-z]+:')
